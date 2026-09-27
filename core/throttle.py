"""Per-visitor limits on the endpoints that cost money.

The model allowance is 8,000 tokens a minute for the whole deployment, shared by
everyone. Without a limit here, one person refreshing a package build starves
the entire batch, and the site looks broken to everybody else rather than slow
to the person causing it.

Limits are deliberately generous for reading and tight for generating. In-memory
rather than Redis: a single instance is what this will run on, and an in-memory
counter that works today beats a dependency that is not deployed yet.
"""
import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits = defaultdict(lambda: defaultdict(deque))

# bucket -> (requests, seconds)
LIMITS = {
    "generate": (6, 3600),     # building packages is the expensive one
    "chat": (30, 3600),
    "resume": (20, 3600),
    "submit": (10, 3600),
    "read": (300, 3600),
}


def check(bucket, who):
    """(allowed, retry_after_seconds)."""
    limit, window = LIMITS.get(bucket, LIMITS["read"])
    now = time.time()
    with _lock:
        q = _hits[bucket][who]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False, int(window - (now - q[0])) + 1
        q.append(now)
        return True, 0


def client(request):
    """The caller's address, honouring the proxy header hosts actually set."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return getattr(getattr(request, "client", None), "host", "unknown")

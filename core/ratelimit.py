"""One token budget, shared by everything that calls the model.

The free tier allows 8,000 tokens a minute for the whole key, but the package
builder and the chat each tracked their own budget, so they spent each other's
allowance and the chat came back with a bare "429: Too Many Requests" while a
package was being built. A student sees that as the site being broken.

So the budget lives here, every caller goes through `call`, and a 429 waits for
the window to refill and retries rather than surfacing. The only thing the
caller ever sees is a slower answer.
"""
import json
import re
import ssl
import threading
import time
import urllib.error
import urllib.request

import certifi

SSL_CTX = ssl.create_default_context(cafile=certifi.where())
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_lock = threading.Lock()
_budget = {"remaining": None, "reset_at": 0.0}


def _secs(v):
    """Groq states resets as '5m45.6s' or '32.197s'."""
    if not v:
        return 0.0
    m = re.match(r"(?:(\d+(?:\.\d+)?)m)?(\d+(?:\.\d+)?)s", str(v).strip())
    return float(m.group(1) or 0) * 60 + float(m.group(2)) if m else 0.0


def note(headers):
    h = {k.lower(): v for k, v in dict(headers).items()}
    with _lock:
        if "x-ratelimit-remaining-tokens" in h:
            _budget["remaining"] = int(float(h["x-ratelimit-remaining-tokens"]))
        if h.get("x-ratelimit-reset-tokens"):
            _budget["reset_at"] = time.time() + _secs(h["x-ratelimit-reset-tokens"])


class Busy(Exception):
    """Rate limited for longer than this caller is willing to wait."""

    def __init__(self, seconds):
        self.seconds = max(1, int(seconds))
        super().__init__(f"rate limited for about {self.seconds}s")


def wait_for(need, log=None, cap=75):
    """Returns the seconds still needed if the wait exceeds cap, else waits."""
    with _lock:
        rem, reset = _budget["remaining"], _budget["reset_at"]
    if rem is None or rem >= need:
        return 0.0
    delay = max(0.0, reset - time.time()) + 1.0
    if delay > cap:
        return delay
    if delay > 0:
        if log:
            log(f"waiting {delay:.0f}s for the token window")
        time.sleep(delay)
        with _lock:
            _budget["remaining"] = None
    return 0.0


def call(payload, api_key, timeout=90, log=None, tries=4, ua="recce/1.0",
         max_wait=75):
    """POST to the model, waiting out rate limits instead of failing on them.

    max_wait is how long this caller can afford to sit there. A package build
    can wait a minute because nobody is watching a spinner; a chat turn cannot,
    because the browser gives up first and the person is left with nothing. When
    the wait would exceed it, Busy is raised carrying the real number of seconds
    so the interface can say how long rather than showing a bare 429.
    """
    need = int(payload.get("max_tokens", 1200)) + 600
    over = wait_for(need, log, cap=max_wait)
    if over:
        raise Busy(over)

    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": ua, "Authorization": f"Bearer {api_key}"}

    last = None
    for attempt in range(tries):
        req = urllib.request.Request(GROQ_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                note(r.headers)
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 and attempt < tries - 1:
                note(e.headers)
                h = {k.lower(): v for k, v in dict(e.headers).items()}
                delay = _secs(h.get("retry-after")) or float(h.get("retry-after") or 0) \
                    or max(1.0, _budget["reset_at"] - time.time())
                delay = min(max(delay, 2.0), 70.0)
                if delay > max_wait:
                    raise Busy(delay)
                if log:
                    log(f"rate limited, retrying in {delay:.0f}s")
                time.sleep(delay)
                with _lock:
                    _budget["remaining"] = None
                continue
            if e.code == 400 and attempt < tries - 1:
                detail = e.read().decode()[:220]
                if "json_validate_failed" in detail:
                    payload["max_tokens"] = min(int(payload.get("max_tokens", 3000) * 1.6), 5200)
                    body = json.dumps(payload).encode()
                    if log:
                        log(f"reply truncated, retrying with {payload['max_tokens']} tokens")
                    wait_for(payload["max_tokens"] + 800, log)
                    continue
            raise
    raise last or RuntimeError("rate limited")

"""Collapsing the same interview question written a dozen different ways.

This is the load-bearing computation. "Asked by 12 students" is only a trust
signal if those twelve reports really were the same question, so both kinds of
error cost something real: merge too eagerly and the count is inflated, merge
too timidly and one question fragments into five with a count of 2 each and the
signal disappears into noise.

Three stages, cheapest first:

  normalise  strips the stylistic variation students introduce, and expands the
             shorthand they actually type (ll, dp, bst) into words the embedding
             model has seen in training
  block      only compares questions that share a rare token, because comparing
             every pair is quadratic and the overwhelming majority of pairs are
             obviously unrelated
  embed      scores the surviving pairs with MiniLM, then merges by connected
             components above a threshold

The threshold is not guessed. tune() sweeps it against hand-laballed pairs and
reports precision and recall at each value, so the number shipped is chosen
with the cost of each error visible.
"""
import re
import sqlite3
from collections import defaultdict

# Students type shorthand. The embedding model was not trained on placement
# slang, so "reverse a LL" and "reverse a linked list" land further apart than
# they should unless the shorthand is expanded first.
SHORTHAND = {
    "ll": "linked list", "dll": "doubly linked list", "bst": "binary search tree",
    "dp": "dynamic programming", "bfs": "breadth first search",
    "dfs": "depth first search", "oops": "object oriented programming",
    "oop": "object oriented programming", "os": "operating system",
    "dbms": "database management system", "sql": "sql",
    "ds": "data structures", "algo": "algorithm", "algos": "algorithms",
    "tc": "time complexity", "sc": "space complexity",
    "ml": "machine learning", "dl": "deep learning", "oo": "object oriented",
    "lru": "least recently used", "api": "api", "db": "database",
    "num": "number", "arr": "array", "str": "string", "prob": "problem",
}

# phrasing that carries no information about which question was asked
FILLER = re.compile(
    r"\b(he|she|they|interviewer|sir|maam|ma'?am|then|also|asked me to|asked|"
    r"was asked|they asked|me|about|some|basic|simple|one|question|questions|"
    r"on|regarding|related to|write a|write|code|coded|program|to|the|a|an|"
    r"explain|tell|describe|what is|what are|how to|how do you|why|please)\b",
    re.I)

WORD = re.compile(r"[a-z0-9+#]+")


def normalise(text):
    """Light cleanup for the embedding stage.

    Deliberately keeps the filler words. MiniLM was trained on ordinary
    sentences, so it reads "explain deadlock in operating system" more reliably
    than the keyword soup that aggressive stripping produces. Stripping helped
    blocking and quietly cost recall, which is the opposite of what was wanted.
    """
    s = (text or "").lower()
    s = re.sub(r"[^a-z0-9+#\s]", " ", s)
    toks = [SHORTHAND.get(t, t) for t in WORD.findall(s)]
    return re.sub(r"\s+", " ", " ".join(toks)).strip()


def key_tokens(text):
    """The content words a question is blocked on, filler removed.

    Blocking wants the opposite of what the embedder wants: only the rare,
    identifying words, because a block keyed on "what" would hold everything.
    """
    stripped = FILLER.sub(" ", normalise(text))
    return {t for t in stripped.split() if len(t) > 2}


def signature(norm):
    return {t for t in FILLER.sub(" ", norm).split() if len(t) > 2}


def blocks(rows, max_df=0.30):
    """Group candidates so only plausible pairs get compared.

    A token that appears in more than max_df of all questions is too common to
    discriminate ("array" in a DSA round tells you nothing), so it is not used
    as a blocking key.
    """
    n = len(rows)
    df = defaultdict(int)
    sigs = {}
    for qid, norm in rows:
        sig = signature(norm)
        sigs[qid] = sig
        for t in sig:
            df[t] += 1

    cutoff = max(2, int(n * max_df))
    buckets = defaultdict(set)
    for qid, sig in sigs.items():
        keys = [t for t in sig if df[t] <= cutoff]
        # a question made entirely of common words still needs somewhere to go
        for t in (keys or sorted(sig)[:2]):
            buckets[t].add(qid)

    pairs = set()
    for members in buckets.values():
        if len(members) < 2 or len(members) > 400:
            continue
        m = sorted(members)
        for i in range(len(m)):
            for j in range(i + 1, len(m)):
                pairs.add((m[i], m[j]))
    return pairs


_MODEL = None
HAVE_MODEL = None


def model():
    """MiniLM, or None where it is not installed.

    sentence-transformers pulls in torch, which is about 600 MB and does not
    fit the free host this deploys to. Rather than make the whole site
    undeployable for one stage of one feature, the embedding step is optional
    and the deduplicator falls back to token overlap. That is measurably worse
    and the caller is told so, which is better than the site not starting.
    """
    global _MODEL, HAVE_MODEL
    if _MODEL is None and HAVE_MODEL is not False:
        try:
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            HAVE_MODEL = True
        except Exception:
            HAVE_MODEL = False
    return _MODEL


def _jaccard(a, b):
    """Token overlap. Blunt, but it still merges the phrasings that differ by a
    filler word, which is most of them."""
    A, B = set(a.split()), set(b.split())
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def _vectors(texts_in_order):
    """Embeddings from whichever backend is present.

    ONNX first: it is the same MiniLM at 106 MB of runtime and weights instead
    of 590 MB, so it is the one that actually fits the host. torch is kept as a
    fallback for a machine that already has it.
    """
    try:
        import embed_onnx
        if embed_onnx.available():
            return embed_onnx.encode(texts_in_order), "onnx"
    except Exception:
        pass
    m = model()
    if m is not None:
        return m.encode(texts_in_order, normalize_embeddings=True,
                        show_progress_bar=False, batch_size=64), "torch"
    return None, "overlap"


def score_pairs(rows, pairs):
    """Cosine similarity for the candidate pairs, or overlap with no model."""
    texts = {qid: norm for qid, norm in rows}
    ids = sorted(texts)
    vecs, backend = _vectors([texts[i] for i in ids])
    if vecs is None:
        return {(a, b): _jaccard(texts[a], texts[b]) for a, b in pairs}

    import numpy as np
    idx = {qid: k for k, qid in enumerate(ids)}
    return {(a, b): float(np.dot(vecs[idx[a]], vecs[idx[b]])) for a, b in pairs}


def backend():
    """Which embedding path is live, for the caller that wants to say so."""
    try:
        import embed_onnx
        if embed_onnx.available():
            return "onnx"
    except Exception:
        pass
    return "torch" if model() is not None else "overlap"


def cluster(rows, scored, threshold):
    """Connected components above the threshold.

    Union-find rather than a fixed number of clusters, because how many
    distinct questions exist is exactly what is being discovered.
    """
    parent = {qid: qid for qid, _ in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for (a, b), s in scored.items():
        if s >= threshold:
            union(a, b)

    groups = defaultdict(list)
    for qid, _ in rows:
        groups[find(qid)].append(qid)
    return list(groups.values())


def cluster_avg(rows, scored, threshold):
    """Agglomerative merging with average linkage.

    cluster() above is single linkage: one stray high-scoring pair is enough to
    fuse two unrelated clusters, and because merges are transitive the damage
    spreads. "difference between array and linked list" links to the array
    questions and to the linked list questions, and single linkage happily
    merges all three groups into one.

    Average linkage asks whether the two clusters are similar *on the whole*
    before merging, so a single misleading pair cannot drag a group across.
    """
    sim = {}
    for (a, b), s in scored.items():
        sim[(a, b)] = s
        sim[(b, a)] = s

    clusters = {qid: [qid] for qid, _ in rows}

    def between(ca, cb):
        """Mean similarity across every pair spanning the two clusters.

        Pairs that blocking never scored count as zero rather than being
        skipped: they were judged too dissimilar to be worth comparing, and
        treating them as missing would quietly reward sparse evidence."""
        total = 0.0
        for x in ca:
            for y in cb:
                total += sim.get((x, y), 0.0)
        return total / (len(ca) * len(cb))

    while True:
        best, pair = threshold, None
        keys = list(clusters)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                # only consider clusters that blocking linked at all
                if not any((x, y) in sim for x in clusters[a] for y in clusters[b]):
                    continue
                s = between(clusters[a], clusters[b])
                if s >= best:
                    best, pair = s, (a, b)
        if not pair:
            break
        a, b = pair
        clusters[a] += clusters.pop(b)

    return list(clusters.values())

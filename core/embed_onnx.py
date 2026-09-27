"""MiniLM without torch.

The deduplicator is the load-bearing feature and it needs real embeddings:
token overlap measured F1 0.431 against MiniLM's 0.804, which makes the report
counts untrustworthy. But sentence-transformers drags in torch at 590 MB, which
does not fit a 512 MB host, so the choice appeared to be a paid tier or a broken
trust signal.

It is the same model either way. Running the quantised ONNX export through
onnxruntime costs 83 MB of runtime and 23 MB of weights instead of 590 MB, and
produces the same vectors. Mean pooling over the attention mask then L2
normalisation, which is exactly what sentence-transformers does for this model.
"""
import os

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.environ.get("RECCE_MODEL_DIR", os.path.join(HERE, "models"))

_session = None
_tokenizer = None


def available():
    return (os.path.exists(os.path.join(MODEL_DIR, "model.onnx"))
            and os.path.exists(os.path.join(MODEL_DIR, "tokenizer.json")))


def _load():
    global _session, _tokenizer
    if _session is None:
        import onnxruntime
        from tokenizers import Tokenizer
        opts = onnxruntime.SessionOptions()
        opts.intra_op_num_threads = 1        # a web dyno has one core to spare
        _session = onnxruntime.InferenceSession(
            os.path.join(MODEL_DIR, "model.onnx"), opts,
            providers=["CPUExecutionProvider"])
        _tokenizer = Tokenizer.from_file(os.path.join(MODEL_DIR, "tokenizer.json"))
        _tokenizer.enable_truncation(max_length=256)
        _tokenizer.enable_padding()
    return _session, _tokenizer


def encode(texts, batch_size=32):
    """Normalised sentence embeddings, same shape as sentence-transformers."""
    session, tok = _load()
    names = {i.name for i in session.get_inputs()}
    out = []

    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i + batch_size]
        enc = tok.encode_batch(chunk)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)

        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        feed = {k: v for k, v in feed.items() if k in names}

        hidden = session.run(None, feed)[0]                 # (b, seq, dim)

        # mean pool over real tokens only, then L2 normalise
        m = mask[..., None].astype(np.float32)
        summed = (hidden * m).sum(axis=1)
        counts = np.clip(m.sum(axis=1), 1e-9, None)
        vecs = summed / counts
        norms = np.clip(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-12, None)
        out.append(vecs / norms)

    return np.vstack(out) if out else np.zeros((0, 384), dtype=np.float32)

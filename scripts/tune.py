"""Choosing the merge threshold by measuring it, not by eyeballing clusters.

Reported as pairwise precision and recall over every pair of phrasings:

  precision  of the pairs we merged, how many really were the same question
             (low precision = inflated counts, the trust signal lies)
  recall     of the pairs that really were the same, how many we merged
             (low recall = one question splits into fragments and vanishes)

Both matter and they trade off, which is the entire reason this sweeps a range
instead of shipping one number.
"""
import json, os, sys, sqlite3
from itertools import combinations

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "core"))
import dedup


def load():
    db = sqlite3.connect(os.path.join(HERE, "recce.db"))
    rows = [(qid, dedup.normalise(t)) for qid, t in db.execute(
        "select id, raw_text from reported_question where submission_id = -1")]
    truth = {int(k): v for k, v in json.load(
        open(os.path.join(HERE, "dev_truth.json"))).items()}
    return rows, truth


def evaluate(rows, truth, scored, threshold, how="single"):
    groups = (dedup.cluster_avg if how == "average" else dedup.cluster)(
        rows, scored, threshold)
    assigned = {}
    for ci, members in enumerate(groups):
        for qid in members:
            assigned[qid] = ci

    tp = fp = fn = 0
    for a, b in combinations(sorted(truth), 2):
        same_truth = truth[a] == truth[b]
        same_pred = assigned[a] == assigned[b]
        if same_pred and same_truth:
            tp += 1
        elif same_pred and not same_truth:
            fp += 1
        elif not same_pred and same_truth:
            fn += 1
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f, len(groups)


if __name__ == "__main__":
    rows, truth = load()
    pairs = dedup.blocks(rows)
    total = len(rows) * (len(rows) - 1) // 2
    print(f"{len(rows)} phrasings, {len(truth)} labelled")
    print(f"blocking compares {len(pairs)} of {total} pairs "
          f"({100*len(pairs)/total:.1f}%)\n")

    scored = dedup.score_pairs(rows, pairs)
    for how in ("single", "average"):
        print(f"--- {how} linkage ---")
        print(f"{'thresh':>7}{'prec':>8}{'recall':>8}{'F1':>7}{'clusters':>10}   (true: 45)")
        best = None
        for t in [x / 100 for x in range(50, 96, 5)]:
            p, r, f, n = evaluate(rows, truth, scored, t, how)
            if best is None or f > best[1]:
                best = (t, f, p, r, n)
            print(f"{t:>7.2f}{p:>8.3f}{r:>8.3f}{f:>7.3f}{n:>10}")
        print(f"best F1 {best[1]:.3f} at {best[0]:.2f} "
              f"(P {best[2]:.3f}  R {best[3]:.3f}  {best[4]} clusters)\n")

"""Predicting what a drive will ask, then letting reality mark the answer.

Made before the drive, scored after it. Ground truth arrives on its own, for
free, every time students report back, so this is one of the few things here
that cannot be quietly tuned until it looks good: the prediction is written
down first.

Scored as hit rate, the share of questions actually asked whose topic was in
the predicted list. Strictly out of sample: a prediction for a drive is built
only from drives held strictly before it.
"""
import json, os, sqlite3, sys
from collections import defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as _db
from topics import topics_of

HALF_LIFE_DAYS = 240.0


def _asked(db, drive_id):
    """Topics actually asked at a drive, with how many distinct students said so."""
    rows = db.execute(
        """select c.text, count(distinct s.student_id)
             from canonical_question c
             join question_link l     on l.canonical_id = c.id
             join reported_question r on r.id = l.reported_id
             join submission s        on s.id = r.submission_id
            where s.drive_id = ? and s.flagged = 0
            group by c.id""", (drive_id,)).fetchall()
    out = defaultdict(float)
    for text, n in rows:
        for t in topics_of(text):
            out[t] += n
    return out


def predict(db, drive_id, k=10):
    """Rank topics for one drive using only what was known beforehand.

    Weights this company's own history above the wider campus, because what a
    company asks is more like its own past than like everyone else's, but does
    not ignore the rest: a company's first visit has no history of its own.
    """
    row = db.execute(
        "select d.company_id, d.held_on from drive d where d.id = ?", (drive_id,)).fetchone()
    if not row:
        return []
    company_id, held_on = row

    prior = db.execute(
        "select id, company_id, held_on from drive where held_on < ?", (held_on,)).fetchall()
    if not prior:
        return []

    hy, hm, hd = (int(x) for x in held_on.split("-"))
    h_ord = date(hy, hm, hd).toordinal()

    score = defaultdict(float)
    for did, cid, held in prior:
        try:
            y, m, d_ = (int(x) for x in held.split("-"))
            age = max(0, h_ord - date(y, m, d_).toordinal())
        except Exception:
            age = 0
        recency = 0.5 ** (age / HALF_LIFE_DAYS)
        weight = (3.0 if cid == company_id else 1.0) * recency
        for topic, n in _asked(db, did).items():
            score[topic] += n * weight

    return [t for t, _ in sorted(score.items(), key=lambda kv: -kv[1])[:k]]


def backtest(db, k=10):
    """Score every drive that had at least one drive before it."""
    drives = db.execute(
        """select d.id, co.name, d.held_on from drive d
             join company co on co.id = d.company_id
            order by d.held_on""").fetchall()
    results = []
    for did, name, held in drives:
        pred = predict(db, did, k)
        if not pred:
            continue
        actual = _asked(db, did)
        if not actual:
            continue
        total = sum(actual.values())
        hit = sum(v for t, v in actual.items() if t in pred)
        results.append({"drive": did, "company": name, "held_on": held,
                        "predicted": pred, "hit_rate": hit / total if total else 0.0})
    return results


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = _db.connect(os.path.join(here, "recce.db"))
    for k in (5, 10):
        res = backtest(db, k)
        if not res:
            print("not enough history")
            break
        print(f"--- top-{k} topic prediction, {len(res)} drives scored ---")
        for r in res:
            print(f"  {r['held_on']}  {r['company']:<11} hit rate {r['hit_rate']:>6.1%}")
        avg = sum(r["hit_rate"] for r in res) / len(res)
        print(f"  {'':<25}mean {avg:>11.1%}\n")

"""Running the deduplicator over live submissions to build canonical questions.

Idempotent: rebuilds the clusters from scratch each time rather than trying to
merge incrementally. Incremental clustering drifts, because a merge decision
made when there were forty reports may be wrong at four hundred, and the whole
value of the count depends on the clusters being right.
"""
import os, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as _db
import dedup
from topics import topic_of

THRESHOLD = 0.60          # chosen by scripts/tune.py, average linkage
LINKAGE = "average"


def rebuild(db, threshold=THRESHOLD, log=print):
    rows = [(qid, dedup.normalise(t)) for qid, t in db.execute(
        "select id, raw_text from reported_question where submission_id != -1")]
    if not rows:
        log("no submissions yet")
        return 0

    pairs = dedup.blocks(rows)
    scored = dedup.score_pairs(rows, pairs)
    groups = dedup.cluster_avg(rows, scored, threshold)

    raw = dict(db.execute(
        "select id, raw_text from reported_question where submission_id != -1"))
    db.execute("delete from question_link")
    db.execute("delete from canonical_question")

    for members in groups:
        # the clearest phrasing is the longest one: students who write more
        # have usually recalled the question rather than gestured at it
        best = max(members, key=lambda q: len(raw[q]))
        text = raw[best]
        cur = db.execute(
            "insert into canonical_question (text, topic) values (?,?)",
            (text, topic_of(text)))
        canon = cur.lastrowid
        for qid in members:
            sim = 1.0 if qid == best else max(
                (scored.get((min(qid, o), max(qid, o)), 0.0)
                 for o in members if o != qid), default=0.0)
            db.execute(
                "insert into question_link (reported_id, canonical_id, similarity, method)"
                " values (?,?,?,?)",
                (qid, canon, sim, "exact" if sim >= 0.999 else "embedding"))
    db.commit()
    log(f"{len(rows)} reports -> {len(groups)} canonical questions")
    return len(groups)


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = _db.connect(os.path.join(here, "recce.db"))
    rebuild(db)
    print("\ntop reported questions:")
    for text, topic, n in db.execute(
        """select c.text, c.topic, count(distinct s.student_id) n
             from canonical_question c
             join question_link l on l.canonical_id = c.id
             join reported_question r on r.id = l.reported_id
             join submission s on s.id = r.submission_id
            group by c.id order by n desc limit 8"""):
        print(f"  {n:>3} students  [{topic}]  {text[:58]}")

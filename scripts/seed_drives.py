"""A synthetic campus season, so every downstream feature can be demonstrated.

INVENTED DATA. Companies, drives, students and who reported what are all made
up. It exists to exercise the prep-set, funnel and prediction code end to end
before the first real submission arrives. Nothing computed from it is a real
finding, and the loader marks every student it creates as synthetic so real
data can never be silently mixed in with it.
"""
import hashlib, os, random, sqlite3, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "core"))
from seedlib import GROUPS_BY_TOPIC  # noqa

random.seed(7)

CAMPUS = "DSATM Bengaluru"

# company -> (how many sat, round structure, what they lean on)
COMPANIES = {
    "Infosys":    (140, ["aptitude", "coding", "tech", "hr"],
                   ["dbms", "oops", "operating sys", "hr", "arrays"]),
    "TCS":        (160, ["aptitude", "coding", "tech", "hr"],
                   ["arrays", "dbms", "oops", "hr", "strings"]),
    "Accenture":  (120, ["aptitude", "coding", "tech", "hr"],
                   ["dbms", "networking", "oops", "hr", "arrays"]),
    "Wipro":      (110, ["aptitude", "tech", "hr"],
                   ["oops", "dbms", "operating sys", "hr"]),
    "Cognizant":  (95,  ["aptitude", "coding", "tech", "hr"],
                   ["arrays", "strings", "dbms", "hr", "trees"]),
    "Zoho":       (60,  ["coding", "coding", "tech", "hr"],
                   ["arrays", "strings", "linked list", "dynamic prog", "trees"]),
}

DRIVES = [  # (company, date, role, ctc)
    ("Infosys",   "2026-08-12", "Systems Engineer", 3.6),
    ("TCS",       "2026-08-19", "Assistant System Engineer", 3.4),
    ("Accenture", "2026-09-02", "Associate Software Engineer", 4.5),
    ("Wipro",     "2026-09-09", "Project Engineer", 3.5),
    ("Cognizant", "2026-09-16", "Programmer Analyst", 4.0),
    ("Zoho",      "2026-09-23", "Member Technical Staff", 6.5),
    ("Infosys",   "2026-02-10", "Systems Engineer", 3.6),   # a prior season
    ("TCS",       "2026-02-17", "Assistant System Engineer", 3.4),
]


def main():
    db = sqlite3.connect(os.path.join(HERE, "recce.db"))
    db.executescript(open(os.path.join(HERE, "core", "schema.sql")).read())

    # wipe any previous synthetic season, leaving the dev dedup rows alone
    db.execute("delete from question_link")
    db.execute("delete from reported_question where submission_id != -1")
    db.execute("delete from submission")
    db.execute("delete from round")
    db.execute("delete from drive")
    db.execute("delete from company")
    db.execute("delete from student where email_hash like 'synthetic:%'")

    for name in COMPANIES:
        db.execute("insert into company (name, slug) values (?,?)",
                   (name, name.lower()))
    cid = {n: i for n, i in db.execute("select name, id from company")}

    students = []
    for k in range(200):
        h = "synthetic:" + hashlib.sha256(f"stu{k}".encode()).hexdigest()[:24]
        cur = db.execute(
            "insert into student (email_hash, batch, branch, verified_at)"
            " values (?,?,?,datetime('now'))", (h, 2027, "CSE"))
        students.append(cur.lastrowid)

    nq = 0
    for company, held, role, ctc in DRIVES:
        sat, rounds, leans = COMPANIES[company]
        cur = db.execute(
            "insert into drive (company_id, campus, held_on, role, ctc_lpa)"
            " values (?,?,?,?,?)", (cid[company], CAMPUS, held, role, ctc))
        did = cur.lastrowid
        for seq, kind in enumerate(rounds, 1):
            db.execute("insert into round (drive_id, seq, kind) values (?,?,?)",
                       (did, seq, kind))

        # a realistic funnel: most of the loss is early
        survivors = random.sample(students, min(sat, len(students)))
        for seq in range(1, len(rounds) + 1):
            keep = 0.42 if seq == 1 else (0.55 if seq == 2 else 0.75)
            survivors = survivors[:max(1, int(len(survivors) * keep))]
            for sid in survivors:
                db.execute(
                    """insert into submission (student_id, drive_id, reached_seq, selected)
                       values (?,?,?,0)
                       on conflict(student_id, drive_id)
                       do update set reached_seq = excluded.reached_seq""",
                    (sid, did, seq))
        for sid in survivors:
            db.execute("update submission set selected = 1"
                       " where student_id = ? and drive_id = ?", (sid, did))

        # only a fraction of people bother to write up what they were asked
        subs = [(r[0], r[1]) for r in db.execute(
            "select id, reached_seq from submission where drive_id = ?", (did,))]
        for sub_id, reached in random.sample(subs, max(4, int(len(subs) * 0.45))):
            for seq in range(1, reached + 1):
                kind = rounds[seq - 1]
                pool = ["hr"] if kind == "hr" else leans
                for _ in range(random.randint(1, 3)):
                    topic = random.choice(pool)
                    variants = GROUPS_BY_TOPIC.get(topic)
                    if not variants:
                        continue
                    group = random.choice(variants)
                    db.execute("insert into reported_question"
                               " (submission_id, round_seq, raw_text) values (?,?,?)",
                               (sub_id, seq, random.choice(group)))
                    nq += 1

    db.commit()
    print(f"{len(DRIVES)} drives, {len(students)} students, "
          f"{db.execute('select count(*) from submission').fetchone()[0]} submissions, "
          f"{nq} reported questions   (synthetic)")


if __name__ == "__main__":
    main()

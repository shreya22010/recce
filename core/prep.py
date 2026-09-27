"""Everything you need before a drive, for one company.

Organised the way the day actually runs — round by round, in the order you
will sit them — rather than by topic, because at 11pm the night before nobody
wants a coverage table. They want to know what the aptitude section looks like,
what gets asked in tech, and what HR will open with.

Where a company has no reported history the honest answer is to say so rather
than to quietly show a generic list dressed up as company-specific. That
generic list is still worth having, so it is given, clearly labelled as the
common pattern rather than as anything to do with this company.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources
from topics import topics_of

ROUND_ORDER = ["aptitude", "english", "coding", "tech", "managerial", "hr"]

ROUND_BLURB = {
    "aptitude": "Timed quantitative and logical reasoning. Speed matters more than depth.",
    "english": "Verbal ability: comprehension, grammar, sometimes a written essay.",
    "coding": "Write working code. Usually one or two problems against a timer.",
    "tech": "Spoken technical interview on your projects, DBMS, OOPs, OS and networks.",
    "managerial": "Scenario and judgement questions, often mixed with technical follow-ups.",
    "hr": "Fit, motivation and logistics. Rehearse these; they are the easiest marks to drop.",
}

# What most campus drives run when nothing is known about a specific company.
# Deliberately conservative: the four rounds nearly every mass recruiter uses.
COMMON_PATTERN = ["aptitude", "coding", "tech", "hr"]


def find_company(db, name):
    """Match a typed name against known companies, tolerantly."""
    n = (name or "").strip().lower()
    if not n:
        return None
    row = db.execute("select id, name from company where lower(name) = ?", (n,)).fetchone()
    if row:
        return row
    row = db.execute("select id, name from company where lower(name) like ?",
                     (f"%{n}%",)).fetchone()
    return row


def _questions(db, company_id=None):
    q = """select c.text, c.topic, count(distinct s.student_id) n,
                  group_concat(distinct ro.kind), group_concat(distinct co.name)
             from canonical_question c
             join question_link l     on l.canonical_id = c.id
             join reported_question r on r.id = l.reported_id
             join submission s        on s.id = r.submission_id
             join drive d             on d.id = s.drive_id
             join company co          on co.id = d.company_id
             left join round ro       on ro.drive_id = d.id and ro.seq = r.round_seq
            where s.flagged = 0"""
    args = []
    if company_id:
        q += " and d.company_id = ?"
        args.append(company_id)
    q += " group by c.id order by n desc"
    out = []
    for text, topic, n, kinds, comps in db.execute(q, args):
        kinds = [k for k in (kinds or "").split(",") if k]
        out.append({"text": text, "topic": topic, "students": n,
                    "rounds": kinds,
                    "companies": sorted({c for c in (comps or "").split(",") if c}),
                    "practice": sources.practice_for_topic(topic)})
    return out


def _pattern(db, company_id):
    """The rounds this company has actually run, in order, with how often."""
    rows = db.execute(
        """select ro.kind, count(distinct d.id)
             from round ro join drive d on d.id = ro.drive_id
            where d.company_id = ?
            group by ro.kind""", (company_id,)).fetchall()
    if not rows:
        return []
    seen = {k: n for k, n in rows}
    return [k for k in ROUND_ORDER if k in seen]


def build(db, name):
    """The whole sheet for one company, or the honest absence of one."""
    hit = find_company(db, name)
    checks = sources.cross_check(hit[1] if hit else name)

    if not hit:
        generic = _questions(db)[:30]
        return {
            "company": name.strip(),
            "known": False,
            "why": "No one has reported a drive for this company yet, so nothing below is "
                   "specific to them. This is the pattern most campus drives follow and the "
                   "questions asked most often across every company on record.",
            "pattern": COMMON_PATTERN,
            "rounds": _rounds_payload(COMMON_PATTERN, generic, company_specific=False),
            "cross_check": checks,
            "reports": 0, "students": 0,
        }

    cid, cname = hit
    pattern = _pattern(db, cid) or COMMON_PATTERN
    qs = _questions(db, cid)
    n_students = db.execute(
        "select count(distinct student_id) from submission s"
        " join drive d on d.id = s.drive_id where d.company_id = ?", (cid,)).fetchone()[0]

    # a company with one or two reports is not yet evidence of a pattern
    thin = len(qs) < 5
    return {
        "company": cname,
        "known": True,
        "thin": thin,
        "why": ("Only a handful of students have reported this drive so far, so treat the "
                "pattern below as provisional." if thin else None),
        "pattern": pattern,
        "rounds": _rounds_payload(pattern, qs, company_specific=True),
        "cross_check": checks,
        "reports": sum(q["students"] for q in qs),
        "students": n_students,
    }


def _rounds_payload(pattern, questions, company_specific):
    out = []
    for kind in pattern:
        if company_specific:
            mine = [q for q in questions if kind in q["rounds"]]
        else:
            # without a company, place questions by the round their topic suits
            mine = [q for q in questions
                    if (kind == "hr" and q["topic"] == "hr")
                    or (kind == "coding" and q["topic"] in
                        {"arrays", "strings", "linked list", "trees", "dynamic prog",
                         "stacks queues", "sorting", "searching", "hashing"})
                    or (kind == "tech" and q["topic"] in
                        {"dbms", "oops", "operating sys", "networking", "system design"})]
        out.append({
            "kind": kind,
            "blurb": ROUND_BLURB.get(kind, ""),
            "questions": mine[:25],
            "practice": sources.practice_for(kind),
        })
    return out

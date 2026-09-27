"""Where every claim on the page came from.

Two kinds of item, and they must never look alike:

  reported   a named drive on a date, said by students who sat it. The evidence
             is the submission, so it carries the college, the date and how many
             independent people said it.
  generated  standard material for this kind of drive. Not evidence of anything
             about this company, so it carries a search link instead: the user
             can go and check whether anyone else says the same.

The search link matters more than it looks. The whole complaint about existing
question banks is that you cannot tell where anything came from, and a claim you
cannot chase is worth very little the night before a drive.
"""
import os
import sqlite3
import sys
from urllib.parse import quote_plus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def verify_links(question, company):
    """Somewhere to go and check one specific question against other accounts."""
    q = quote_plus(f"{company} {question}"[:120])
    bare = quote_plus(question[:110])
    return [
        {"site": "GeeksforGeeks", "url": f"https://www.geeksforgeeks.org/?s={bare}"},
        {"site": "LeetCode Discuss", "url": f"https://leetcode.com/discuss/search?query={q}"},
        {"site": "Google", "url": f"https://www.google.com/search?q={q}"},
    ]


def practice_link(topic, question=""):
    import sources
    direct = sources.practice_for_topic(topic)
    if direct:
        return direct
    return f"https://www.geeksforgeeks.org/?s={quote_plus(question[:80])}" if question else None


def drive_evidence(db, company):
    """Every reported question with the drive it came from.

    Keyed on the normalised question so a generated item can be matched against
    it and upgraded, carrying the dates with it.
    """
    import dedup
    rows = db.execute(
        """select c.text, c.topic, d.held_on, d.campus, d.role,
                  count(distinct s.student_id) n
             from canonical_question c
             join question_link l     on l.canonical_id = c.id
             join reported_question r on r.id = l.reported_id
             join submission s        on s.id = r.submission_id
             join drive d             on d.id = s.drive_id
             join company co          on co.id = d.company_id
            where s.flagged = 0 and lower(co.name) = lower(?)
            group by c.id, d.id
            order by d.held_on desc""", (company,)).fetchall()

    by_q = {}
    for text, topic, held, campus, role, n in rows:
        key = dedup.normalise(text)
        entry = by_q.setdefault(key, {"text": text, "topic": topic,
                                      "students": 0, "drives": []})
        entry["students"] += n
        entry["drives"].append({"date": held, "year": (held or "")[:4],
                                "campus": campus, "role": role, "students": n})
    return by_q


def drives_of(db, company):
    """The drives themselves, which is what a candidate wants first."""
    return [
        {"date": held, "year": (held or "")[:4], "campus": campus, "role": role,
         "rounds": [r for r in (rounds or "").split(",") if r],
         "students": n, "offers": offers}
        for held, campus, role, rounds, n, offers in db.execute(
            """select d.held_on, d.campus, d.role,
                      (select group_concat(kind) from (
                          select kind from round where drive_id = d.id order by seq)),
                      count(distinct s.student_id),
                      sum(s.selected)
                 from drive d
                 join company co   on co.id = d.company_id
                 left join submission s on s.drive_id = d.id
                where lower(co.name) = lower(?)
                group by d.id order by d.held_on desc""", (company,))]

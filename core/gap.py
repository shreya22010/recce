"""What the job posting says they want, against what they actually ask.

This is the one thing here that no existing site can produce, and the reason is
mundane: it needs live job descriptions and verified interview reports in the
same place, and nobody holds both. Job boards have no idea what gets asked in
the room. Prep sites have no idea who is hiring.

The output is a divergence, not a score. A posting that talks about cloud and
microservices while every reported round is DSA and SQL is telling you exactly
how to spend the week before the drive.

Honest limit: this only works for companies present in both datasets. Most
large Indian service firms hire through in-house portals with no public API, so
their postings are not in the index and nothing can be said about them.
"""
import os, sqlite3, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Everything the app needs lives with the app: the crawled index, the taxonomy
# and the matcher. Nothing points at a sibling directory that only exists on
# one laptop.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DB = os.environ.get("JOBS_DB", os.path.join(ROOT, "jobs.db"))
TAXONOMY = os.path.join(ROOT, "taxonomy.json")
sys.path.insert(0, os.path.join(HERE, "core"))
import db as _db
sys.path.insert(0, os.path.join(ROOT, "vendor"))
from topics import topics_of

# jobscout's taxonomy is about technologies; a drive is about subjects. This is
# the join between the two vocabularies, and it is deliberately partial: a
# posting asking for Kubernetes maps to nothing a campus round tests, and
# pretending otherwise would invent a divergence that is not there.
SKILL_TO_TOPIC = {
    "sql": "dbms", "mysql": "dbms", "postgresql": "dbms", "database": "dbms",
    "dbms": "dbms", "nosql": "dbms", "mongodb": "dbms", "oracle": "dbms",
    "java": "oops", "c++": "oops", "oop": "oops", "object oriented": "oops",
    "python": "arrays", "data structures": "arrays", "algorithms": "arrays",
    "linux": "operating sys", "unix": "operating sys", "operating system": "operating sys",
    "networking": "networking", "tcp": "networking", "http": "networking",
    "rest": "networking", "api": "networking",
    "system design": "system design", "microservices": "system design",
    "scalability": "system design", "distributed": "system design",
    "aws": "cloud", "azure": "cloud", "gcp": "cloud", "cloud": "cloud",
    "docker": "cloud", "kubernetes": "cloud", "ci/cd": "cloud", "devops": "cloud",
}


def jd_profile(company, limit=400):
    """Topic shares implied by what this company's live postings ask for."""
    import structured
    tax, pats = structured.load_taxonomy(TAXONOMY)
    db = sqlite3.connect(JOBS_DB)
    rows = db.execute(
        """select title, description from jobs
            where lower(company) = ? and in_india = 1 and description != ''
            limit ?""", (company.lower(), limit)).fetchall()
    if not rows:
        return None, 0

    counts = defaultdict(float)
    for title, desc in rows:
        found = structured.extract((title or "") + " " + (desc or ""), tax, pats,
                                   (company,))
        seen = {SKILL_TO_TOPIC[s] for s in found if s in SKILL_TO_TOPIC}
        for t in seen:
            counts[t] += 1
    total = sum(counts.values()) or 1
    return {t: c / total for t, c in counts.items()}, len(rows)


def asked_profile(db, company):
    """Topic shares of what students actually reported being asked."""
    rows = db.execute(
        """select c.text, count(distinct s.student_id)
             from canonical_question c
             join question_link l     on l.canonical_id = c.id
             join reported_question r on r.id = l.reported_id
             join submission s        on s.id = r.submission_id
             join drive d             on d.id = s.drive_id
             join company co          on co.id = d.company_id
            where co.name = ? and s.flagged = 0
            group by c.id""", (company,)).fetchall()
    if not rows:
        return None, 0
    counts = defaultdict(float)
    for text, n in rows:
        for t in topics_of(text):
            counts[t] += n
    total = sum(counts.values()) or 1
    return {t: c / total for t, c in counts.items()}, len(rows)


def divergence(db, company):
    jd, n_jobs = jd_profile(company)
    asked, n_q = asked_profile(db, company)
    if not jd or not asked:
        return None
    topics = sorted(set(jd) | set(asked))
    rows = [{"topic": t, "posting": jd.get(t, 0.0), "asked": asked.get(t, 0.0),
             "delta": asked.get(t, 0.0) - jd.get(t, 0.0)} for t in topics]
    rows.sort(key=lambda r: -abs(r["delta"]))
    return {"company": company, "postings": n_jobs, "questions": n_q, "rows": rows}


if __name__ == "__main__":
    db = _db.connect(os.path.join(HERE, "recce.db"))
    for co, in db.execute("select name from company order by name"):
        d = divergence(db, co)
        if not d:
            print(f"{co:<11} no overlap (not in the job index)")
            continue
        print(f"\n{d['company']}  ({d['postings']} live postings, {d['questions']} questions)")
        print(f"  {'topic':<15}{'in postings':>13}{'actually asked':>16}")
        for r in d["rows"][:8]:
            print(f"  {r['topic']:<15}{r['posting']:>12.0%}{r['asked']:>15.0%}"
                  f"   {'+' if r['delta']>0 else ''}{r['delta']*100:>5.0f} pts")

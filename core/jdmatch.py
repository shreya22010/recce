"""Matching a resume against one job description.

Reuses the skill extraction and scoring that jobscout already evaluated against
alternatives on labelled data, rather than inventing a second scorer that has
never been measured. The percentage shown is coverage: of the skills this
posting asks for, the share the resume can evidence.

Deliberately not a model call. A number produced by a language model would vary
between runs on identical input, and a match score that moves when nothing
changed is worse than no score.
"""
import os
import sys

# Everything the app needs lives with the app: the crawled index, the taxonomy
# and the matcher. Nothing points at a sibling directory that only exists on
# one laptop.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DB = os.environ.get("JOBS_DB", os.path.join(ROOT, "jobs.db"))
TAXONOMY = os.path.join(ROOT, "taxonomy.json")
sys.path.insert(0, os.path.join(ROOT, "vendor"))
import structured

TAX, PATS = structured.load_taxonomy(TAXONOMY)


def match(resume_text, jd_text, company=None, resume_skills=None):
    drop = (company,) if company else ()
    jd_skills = structured.extract(jd_text or "", TAX, PATS, drop)
    mine = set(resume_skills or []) or structured.extract(resume_text or "", TAX, PATS)
    mine = {s for s in mine if s in TAX}

    if not jd_skills:
        return {"percent": None, "have": [], "missing": [], "extra": sorted(mine),
                "note": "No recognisable skills in that job description, so there is "
                        "nothing concrete to match against. Paste the requirements "
                        "section rather than the company blurb."}

    have = sorted(jd_skills & mine)
    missing = sorted(jd_skills - mine)

    # weight by how rare a skill is, so matching "python" counts for less than
    # matching something the market rarely asks for
    earned = sum(TAX.get(s, 1.0) for s in have)
    total = sum(TAX.get(s, 1.0) for s in jd_skills) or 1.0
    pct = round(100 * earned / total)

    return {"percent": pct,
            "have": [{"skill": s, "weight": round(TAX.get(s, 1.0), 2)} for s in have],
            "missing": [{"skill": s, "weight": round(TAX.get(s, 1.0), 2)}
                        for s in sorted(missing, key=lambda x: -TAX.get(x, 1.0))],
            "extra": sorted(mine - jd_skills)[:20],
            "asked": len(jd_skills),
            "note": None}


def advice(res):
    """What to change, ordered by what it would buy."""
    if res.get("percent") is None:
        return []
    out = []
    for m in res["missing"][:6]:
        out.append({"skill": m["skill"],
                    "gain": round(100 * m["weight"] / max(1e-9, sum(
                        x["weight"] for x in res["missing"] + res["have"]))),
                    "why": f"This posting asks for {m['skill']} and your resume does not "
                           f"evidence it."})
    return out

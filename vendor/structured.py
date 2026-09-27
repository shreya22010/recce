"""
Match on what a job asks for, not on how its description reads.

Neither earlier ranker answered the question a person actually has. Keyword
matching counted words she happened to share with the posting. Embeddings
compared the overall shape of two documents. Both produce a number; neither can
say what the job needs that she does not have.

This extracts the skills each side names, using one shared vocabulary, and
compares the sets. That makes the score explainable by construction — the same
comparison that ranks a job also produces "you have 6 of 8, missing Docker".

Two things are weighted deliberately:

  rarity   a job naming xgboost tells you far more about it than one naming
           python, so each skill is weighted by inverse document frequency.

  coverage a job wanting five things she has all of is a better fit than one
           wanting twenty she has six of, even though six beats five.
"""
import json, re, sqlite3

def load_taxonomy(path="taxonomy.json"):
    tax = json.load(open(path))
    pats = {t: re.compile(r"(?<![A-Za-z0-9+#.])" + re.escape(t) + r"(?![A-Za-z0-9+#])", re.I)
            for t in tax}
    return tax, pats

def extract(text, tax, pats, drop=()):
    """
    Every skill from the vocabulary that this text names.

    `drop` exists because a company's own name is frequently also a technology.
    Stripe's intern posting listed "stripe" as a required skill, so the one job
    in the index worth applying to reported a miss against the company hiring
    for it. Twilio, Databricks, Elastic, Supabase, Snowflake and Redis all have
    the same problem.
    """
    low = (text or "").lower()
    skip = {d.lower() for d in drop}
    return {t for t in tax if t not in skip and t in low and pats[t].search(text)}

def score(job_skills, my_skills, tax, title_skills=frozenset()):
    """
    Returns the score and the evidence behind it, together. Nothing here can
    rank a job without also being able to explain the ranking.
    """
    if not job_skills:
        return 0.0, {"have": [], "missing": [], "coverage": 0.0}

    have = job_skills & my_skills
    missing = job_skills - my_skills

    # a skill named in the title is what the job is, not one line in a list
    weight = lambda s: tax[s] * (2.0 if s in title_skills else 1.0)

    earned = sum(weight(s) for s in have)
    asked = sum(weight(s) for s in job_skills)
    coverage = earned / asked

    # absolute overlap and proportional fit disagree often enough to matter, so
    # keep both: the first favours substantial roles, the second favours ones
    # she can actually do all of
    return round(earned * (0.35 + 0.65 * coverage), 2), {
        "have": sorted(have, key=lambda s: -tax[s]),
        "missing": sorted(missing, key=lambda s: -tax[s]),
        "coverage": round(coverage, 2),
    }

def rank(resume_text, db_path="jobs.db", india_only=True, limit=40):
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from match import eligible, load

    tax, pats = load_taxonomy()
    mine = extract(resume_text, tax, pats)

    db = sqlite3.connect(db_path)
    out = []
    for j in load(db, india_only):
        t = eligible(j)
        if not t:
            continue
        title_sk = extract(j["title"], tax, pats)
        job_sk = title_sk | extract(j["description"] or "", tax, pats)
        s, why = score(job_sk, mine, tax, title_sk)
        if s <= 0:
            continue
        j.update(tier=t, score=s, matched=why["have"][:6], gap=why)
        out.append(j)

    for j in out:
        if j["tier"] == "early":
            j["score"] = round(j["score"] + 6, 2)

    out.sort(key=lambda j: -j["score"])
    return mine, out[:limit]

if __name__ == "__main__":
    resume = open("resume.txt").read()
    mine, top = rank(resume)
    print(f"\n  your skills, from the shared vocabulary ({len(mine)}):")
    print(f"    {', '.join(sorted(mine))}\n")
    print(f"  ── structured ── top 15\n")
    for j in top[:15]:
        mark = "★" if j["tier"] == "early" else " "
        g = j["gap"]
        print(f"  {mark} {j['score']:>6}  {j['company'][:13]:<14} {j['title'][:44]:<45} {j['location'][:16]}")
        print(f"            have {len(g['have'])}/{len(g['have'])+len(g['missing'])}"
              f"  ·  missing: {', '.join(g['missing'][:4]) or 'nothing'}")
    json.dump(top, open("ranked_structured.json", "w"), indent=1)

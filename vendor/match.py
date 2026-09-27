"""
Two rankers over the same candidate set, so the difference can be measured.

The gate is shared and comes first. Seniority is not a scoring signal, it is a
filter: a 2027 graduate cannot apply to a role demanding five years, however
well the words line up. Ranking those highly would be precise and useless.

What differs is how the survivors are ordered.

  keyword  — the original. Counts hand-weighted skills from a dictionary. It
             cannot see that "built REST APIs with FastAPI" and "backend
             services in Python" are the same claim, because they share no words.

  semantic — cosine similarity between the resume and the job in embedding
             space, where that pair lands close together.

Keeping both is the point. Without the weaker one there is no baseline, and a
score with nothing to compare it against says nothing at all.
"""
import re, sqlite3
import numpy as np

# ── the gate ───────────────────────────────────────────────────────────────
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|head\s+of|director|manager|"
                    r"architect|vp|vice\s+president|chief|distinguished|fellow|"
                    r"iii|iv|7\+|8\+|10\+)\b", re.I)
YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?year[s]?(?:\s+of)?\s+(?:of\s+)?(?:relevant\s+)?experience", re.I)
EARLY = re.compile(r"\b(intern|internship|trainee|apprentice|graduate|new\s?grad|campus|"
                   r"fresher|entry[\s-]?level|early\s+career|junior|jr\.?|university|student)\b", re.I)
OFF_TRACK = re.compile(r"\b(sales|account\s+executive|recruit|talent|hr\b|people\s+ops|legal|"
                       r"counsel|finance|accounting|payroll|marketing|brand|copywriter|"
                       r"customer\s+success|technical\s+writer|designer|ux|product\s+manager|"
                       r"program\s+manager|scrum|operations\s+associate|risk\s+analyst|quote|"
                       r"fraud|sanctions|compliance|underwrit|collections|billing|procurement|"
                       r"logistics|supply\s+chain|solutions\s+engineer|sales\s+engineer|"
                       r"business\s+analyst|executive)\b", re.I)
ENGINEERING = re.compile(r"\b(engineer|engineering|developer|programmer|sde|swe|software|"
                         r"data\s+scien|machine\s+learning|ml\b|ai\b|research|backend|frontend|"
                         r"full[\s-]?stack|platform|infrastructure|devops|scientist)\b", re.I)

def tier(title, desc):
    if SENIOR.search(title): return None
    m = YEARS.search(desc or "")
    if m and int(m.group(1)) >= 3: return None
    if EARLY.search(title): return "early"
    if m and int(m.group(1)) <= 2: return "early"
    return "mid"

def eligible(job):
    """Everything a fresh graduate could plausibly apply to."""
    if OFF_TRACK.search(job["title"]): return None
    if not ENGINEERING.search(job["title"]): return None
    return tier(job["title"], job["description"] or "")

# ── ranker one: the hand-written dictionary ────────────────────────────────
SKILLS = {
    "llm":3.0,"large language model":3.0,"generative ai":3.0,"rag":3.0,
    "retrieval augmented":3.0,"embedding":2.5,"vector database":2.5,"pgvector":3.0,
    "prompt engineering":2.5,"machine learning":2.5,"scikit-learn":2.5,"nlp":2.0,
    "random forest":2.0,"data pipeline":2.0,"feature engineering":2.0,"pca":1.5,
    "python":2.5,"fastapi":2.5,"flask":2.0,"rest api":1.5,"react":2.0,"next.js":2.5,
    "typescript":2.0,"javascript":1.5,"postgres":2.0,"postgresql":2.0,"sql":1.5,
    "supabase":2.5,"mysql":1.5,"backend":1.5,"full stack":1.5,"java":1.5,
    "security":1.5,"cybersecurity":2.0,"cryptography":1.5,"authentication":1.2,
    "data structures":1.0,"algorithms":1.0,"docker":1.0,"aws":1.0,"git":0.5,
}
WORD = {s: re.compile(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", re.I) for s in SKILLS}

def resume_skills(text):
    return {s: w for s, w in SKILLS.items() if WORD[s].search(text)}

def keyword_score(job, mine):
    hay = f"{job['title']} {job['description'] or ''}"
    hit = [(s, w) for s, w in mine.items() if WORD[s].search(hay)]
    # a skill in the title is what the role is; the same word in a description
    # may be one line in a list of nice-to-haves
    return sum(w * (2 if WORD[s].search(job["title"]) else 1) for s, w in hit), [s for s, _ in hit]

# ── ranker two: similarity in embedding space ──────────────────────────────
def semantic_scores(resume_text, urls, db, model):
    vec = model.encode([resume_text], normalize_embeddings=True)[0].astype(np.float32)
    rows = db.execute(f"select url, vec from embeddings where url in "
                      f"({','.join('?' * len(urls))})", urls).fetchall()
    out = {}
    for url, blob in rows:
        # both sides are unit vectors, so the dot product is the cosine
        out[url] = float(np.frombuffer(blob, dtype=np.float32) @ vec)
    return out

def centered_scores(resume_text, urls, db, model):
    """
    Strip out what every job has in common before comparing.

    Raw cosine put a night-shift support role first and buried the one internship
    in the index, because every vector here points mostly in the same direction:
    these are all tech job descriptions, so they are all similar to a tech
    resume. That shared component swamps the differences that actually matter.

    Subtracting the mean job vector removes it. What is left is what makes each
    job distinctive, which is the only part worth ranking on.
    """
    rows = db.execute(f"select url, vec from embeddings where url in "
                      f"({','.join('?' * len(urls))})", urls).fetchall()
    mat = np.stack([np.frombuffer(b, dtype=np.float32) for _, b in rows])
    centre = mat.mean(axis=0)

    jobs = mat - centre
    jobs /= (np.linalg.norm(jobs, axis=1, keepdims=True) + 1e-9)

    r = model.encode([resume_text], normalize_embeddings=True)[0].astype(np.float32) - centre
    r /= (np.linalg.norm(r) + 1e-9)

    return {url: float(v @ r) for (url, _), v in zip(rows, jobs)}

def capability_text(resume_text):
    """
    Embed what she can do, not the whole document.

    A resume is mostly things that say nothing about fit: a phone number, a
    college name, board percentages, conference attendance. Averaged into a
    single vector they pull it toward "generic student" and away from "builds
    backends and ML pipelines".
    """
    keep, on = [], False
    for line in resume_text.splitlines():
        u = line.strip().upper()
        if u in ("SKILLS", "EXPERIENCE", "PROJECTS"): on = True; continue
        if u in ("EDUCATION", "CERTIFICATIONS & ACTIVITIES"): on = False; continue
        if on and line.strip(): keep.append(line.strip())
    return " ".join(keep) or resume_text

def blend(a, b, w=0.5):
    """Min-max each signal onto 0..1 first. Raw keyword points and cosine
    similarity are not on the same scale, so summing them directly would let
    whichever has the wider range decide the ranking on its own."""
    def norm(d):
        v = list(d.values())
        lo, hi = min(v), max(v)
        rng = (hi - lo) or 1.0
        return {k: (x - lo) / rng for k, x in d.items()}
    A, B = norm(a), norm(b)
    return {k: w * A[k] + (1 - w) * B.get(k, 0) for k in A}

def load(db, india_only=True):
    db.row_factory = sqlite3.Row
    q = "select * from jobs" + (" where in_india = 1" if india_only else "")
    return [dict(r) for r in db.execute(q)]

def rank(resume_text, how="semantic", db_path="jobs.db", india_only=True, limit=40):
    db = sqlite3.connect(db_path)
    jobs = []
    for j in load(db, india_only):
        t = eligible(j)
        if t:
            j["tier"] = t
            jobs.append(j)

    mine = resume_skills(resume_text)

    if how == "keyword":
        for j in jobs:
            j["score"], j["matched"] = keyword_score(j, mine)

    elif how in ("centered", "capability", "hybrid"):
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        urls = [j["url"] for j in jobs]
        text = capability_text(resume_text) if how in ("capability", "hybrid") else resume_text
        sem = centered_scores(text, urls, db, model)

        if how == "hybrid":
            kw = {j["url"]: keyword_score(j, mine)[0] for j in jobs}
            sem = blend(sem, kw, w=0.5)

        for j in jobs:
            j["score"] = round(sem.get(j["url"], 0.0) * 100, 1)
            j["matched"] = keyword_score(j, mine)[1]

    else:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        sims = semantic_scores(resume_text, [j["url"] for j in jobs], db, model)
        mine = resume_skills(resume_text)
        for j in jobs:
            # similarity carries the ranking; the skills come along only so the
            # result can say why it matched
            j["score"] = round(sims.get(j["url"], 0.0) * 100, 1)
            j["matched"] = keyword_score(j, mine)[1]

    # early-career roles get lifted after scoring, never before: the bonus
    # reorders good matches, it does not rescue bad ones
    for j in jobs:
        if j["tier"] == "early":
            j["score"] += 8 if how == "semantic" else 14

    jobs.sort(key=lambda j: -j["score"])
    return jobs[:limit]

if __name__ == "__main__":
    import sys, json
    resume = open("resume.txt").read()
    how = sys.argv[1] if len(sys.argv) > 1 else "semantic"
    top = rank(resume, how)
    print(f"\n  ── {how} ── top 15 of {len(top)}\n")
    for j in top[:15]:
        mark = "★" if j["tier"] == "early" else " "
        print(f"  {mark} {j['score']:>6}  {j['company'][:14]:<15} {j['title'][:50]:<51} {j['location'][:18]}")
    json.dump(top, open(f"ranked_{how}.json", "w"), indent=1)

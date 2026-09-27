"""Resume parsing and job matching, vendored from the jobscout crawler.

Copied rather than imported across directories. The previous version loaded
jobscout's api.py by absolute path, which meant the app only ran on the one
laptop where that folder exists, and every resume upload would have failed on a
deployed host with a FileNotFoundError.

This is the matcher that was evaluated against keyword, semantic, centered,
capability and hybrid rankers on a hand-labelled set and won, so it is copied
verbatim rather than rewritten.
"""
import io
import os
import sys

from fastapi import HTTPException

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import structured
from match import eligible, load

# daily keeps the applied/hidden sets; jd pulls the readable part out of a
# posting. Both live in core.
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
import daily
import jd

ROOT = os.path.dirname(HERE)
TAX, PATS = structured.load_taxonomy(os.path.join(ROOT, "taxonomy.json"))
MAX_PDF = 5 * 1024 * 1024


def read_pdf(data: bytes) -> str:
    import pypdf
    try:
        pages = pypdf.PdfReader(io.BytesIO(data)).pages
    except Exception:
        raise HTTPException(400, "That file could not be opened as a PDF.")
    text = "\n".join(p.extract_text() or "" for p in pages)
    if len(text.strip()) < 100:
        # Almost always a scanned or image-only resume. Saying so is more useful
        # than returning zero skills and letting them think the app is broken.
        raise HTTPException(422, "No text found — this looks like a scanned PDF. "
                                 "Export it from Word or Docs instead of scanning it.")
    return text

def profile(text: str) -> dict:
    """What can be read off a resume, so the interface never asks for it."""
    import re
    years = [int(y) for y in re.findall(r"\b(20[2-3]\d)\b", text)]
    CITIES = ["Bengaluru", "Bangalore", "Mumbai", "Pune", "Delhi", "Hyderabad",
              "Chennai", "Gurgaon", "Noida", "Kolkata", "Ahmedabad", "Jaipur"]
    city = next((c for c in CITIES if c.lower() in text.lower()), None)

    degree = None
    m = re.search(r"\b(B\.?E\.?|B\.?Tech|M\.?Tech|B\.?Sc|M\.?Sc|MCA|BCA)\b[^\n]{0,60}", text, re.I)
    if m:
        # resumes put the grade on the same line as the degree, so cut at
        # whatever marks the start of it rather than taking a fixed width
        d = re.split(r"\s*(?:CGPA|GPA|Percentage|\|)\b", m.group(0), flags=re.I)[0]
        degree = " ".join(d.split()).rstrip(" ,-·")[:60]

    interns = len(re.findall(r"\bintern(ship)?\b", text, re.I))

    return {
        "graduating": max(years) if years else None,
        "degree": degree,
        "city": city,
        "internships": min(interns, 5),
        "skills": sorted(structured.extract(text, TAX, PATS)),
    }

def find_matches(req, conn_factory):
    """Two databases, deliberately.

    The postings live in the bundled read-only SQLite index and the user's own
    state lives in the application database, which is Postgres on a deployment.
    Reading both from one connection asked Postgres for a jobs table that is not
    and never will be there.
    """
    import sqlite3
    mine = {s for s in req.skills if s in TAX}
    app_db = conn_factory()                       # applied / hidden / last run
    jobs_db = sqlite3.connect(os.environ.get(
        "JOBS_DB", os.path.join(ROOT, "jobs.db")))
    jobs_db.row_factory = sqlite3.Row
    done = daily.done_urls(app_db)
    since = daily.last_run(app_db)
    out = []
    gate = 0                                    # survived the seniority gate

    for j in load(jobs_db, india_only=True):
        # anything already applied to or dismissed never comes back. A daily
        # tool that keeps resurfacing yesterday's list stops being opened.
        if j["url"] in done:
            continue
        tier = eligible(j)
        if not tier:
            continue
        gate += 1
        if req.want == "internship" and tier != "early":
            continue
        loc = (j["location"] or "").lower()
        if req.where == "home" and req.city and req.city.lower() not in loc:
            continue
        if req.where == "custom" and req.custom_city and req.custom_city.lower() not in loc:
            continue

        own = (j["company"],)                       # never require a company's own name
        title_sk = structured.extract(j["title"], TAX, PATS, own)
        job_sk = title_sk | structured.extract(j["description"] or "", TAX, PATS, own)
        s, why = structured.score(job_sk, mine, TAX, title_sk)
        if s <= 0:
            continue
        if tier == "early":
            s = round(s + 6, 2)

        out.append({"title": j["title"], "company": j["company"], "location": j["location"],
                    "url": j["url"], "score": s, "tier": tier,
                    "have": why["have"], "missing": why["missing"][:6],
                    "summary": jd.summary(j["description"]),
                    "bullets": jd.bullets(j["description"]),
                    "posted": j["posted"] or "",
                    "coverage": why["coverage"],
                    "fit": ("strong" if why["coverage"] >= 0.5 else
                            "good" if why["coverage"] >= 0.25 or tier == "early" else
                            "stretch"),
                    "is_new": bool(since and (j.get("first_seen") or "") > since)})

    out.sort(key=lambda j: -j["score"])
    pool = jobs_db.execute("select count(*) from jobs where in_india = 1").fetchone()[0]
    return {"total_indexed": pool, "gate": gate, "eligible": len(out),
            "jobs": out[:req.limit]}

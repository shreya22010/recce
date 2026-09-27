"""The API behind Recce.

Two halves that need each other. The job half answers "who should I apply to"
and works from the first minute with nobody signed up, which is what gets
students through the door. The interview half answers "what will they ask" and
only becomes good once those students report back, which is why it is bolted to
the half that draws them in rather than shipped alone.

Everything expensive is offline: crawling, embedding, clustering. What happens
per request is set arithmetic.
"""
import hashlib, json, os, sqlite3, sys, tempfile
from datetime import date

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
# Everything the app needs lives with the app: the crawled index, the taxonomy
# and the matcher. Nothing points at a sibling directory that only exists on
# one laptop.
ROOT = HERE
JOBS_DB = os.environ.get("JOBS_DB", os.path.join(ROOT, "jobs.db"))
TAXONOMY = os.path.join(ROOT, "taxonomy.json")
sys.path.insert(0, os.path.join(HERE, "core"))
import env
env.load()                     # before anything reads DATABASE_URL or the key
import db as _db
sys.path.insert(0, os.path.join(ROOT, "vendor"))


from topics import topics_of

DB = os.path.join(HERE, "recce.db")
# Campus drives are not one college's problem, and plenty of students are told
# to give a personal address because their college mail is unreliable or expires
# after graduation. So any address is accepted; what changes is the label. A
# college domain is marked verified, a personal one is marked unverified, and
# the difference is shown next to the count rather than used to block anyone.
PERSONAL = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "yahoo.in",
            "icloud.com", "proton.me", "protonmail.com", "live.com", "rediffmail.com"}


def email_kind(email):
    domain = (email or "").strip().lower().rsplit("@", 1)[-1]
    if "@" not in (email or "") or "." not in domain:
        return None
    return "personal" if domain in PERSONAL else "college"

# Apply the schema on every start. Every statement is CREATE IF NOT EXISTS, so
# this is idempotent, and it means a fresh Postgres on a first deploy comes up
# with its tables instead of 500ing on the first request.
_db.init(DB, open(os.path.join(HERE, "core", "schema.sql")).read())

app = FastAPI(title="recce")
# A wildcard origin means any website can call this API and spend the model
# allowance it pays for. Set ALLOWED_ORIGINS to the deployed URL.
ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8010,http://127.0.0.1:8010").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


def guard(request: Request, bucket: str):
    """Refuse politely rather than letting one visitor drain the allowance."""
    import throttle
    ok, wait = throttle.check(bucket, throttle.client(request))
    if not ok:
        raise HTTPException(429, f"Too many requests. Try again in about "
                                 f"{wait // 60 + 1} minute(s).")


def conn():
    return _db.connect(DB)


def hash_email(email):
    """Stored as a hash so a submission can be tied to one person without the
    database ever holding who that person is."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------- reading ---

@app.get("/api/stats")
def stats():
    db = conn()
    q = lambda s: db.execute(s).fetchone()[0]
    jobs = sqlite3.connect(JOBS_DB)
    return {
        "companies": q("select count(*) from company"),
        "drives": q("select count(*) from drive"),
        "submissions": q("select count(*) from submission"),
        "reports": q("select count(*) from reported_question where submission_id != -1"),
        "questions": q("select count(*) from canonical_question"),
        "students": q("select count(distinct student_id) from submission"),
        "openings": jobs.execute(
            "select count(*) from jobs where in_india = 1").fetchone()[0],
        # a site that shows invented numbers without saying so is worse than an
        # empty one, so the interface is told outright
        "demo_rows": q("select count(*) from student where email_hash like 'synthetic:%'"),
        "real_rows": q("select count(*) from student where email_hash not like 'synthetic:%'"),
    }


@app.post("/api/clear_demo")
def clear_demo(request: Request):
    """Local only. Wiping rows is not something a visitor should be able to do."""
    if os.environ.get("DATABASE_URL") or os.environ.get("RECCE_ENV") == "production":
        raise HTTPException(403, "Not available on a deployment.")
    """Remove every seeded row, leaving anything real untouched.

    Order matters: question_link points at reported_question, which points at
    submission. Deleting a parent first trips the foreign keys, which is what
    they are there for."""
    db = conn()
    db.execute("""delete from question_link where reported_id in (
                    select r.id from reported_question r
                      join submission s on s.id = r.submission_id
                      join student st on st.id = s.student_id
                     where st.email_hash like 'synthetic:%')""")
    db.execute("""delete from reported_question where submission_id in (
                    select s.id from submission s join student st on st.id = s.student_id
                     where st.email_hash like 'synthetic:%')""")
    db.execute("""delete from submission where student_id in
                    (select id from student where email_hash like 'synthetic:%')""")
    db.execute("delete from student where email_hash like 'synthetic:%'")
    db.execute("delete from round where drive_id not in (select drive_id from submission)")
    db.execute("delete from drive where id not in (select drive_id from submission)")
    db.execute("delete from company where id not in (select company_id from drive)")
    db.commit()
    import build
    build.rebuild(db, log=lambda *a: None)
    return {"ok": True}


class Submission(BaseModel):
    email: str
    batch: int
    branch: str | None = None
    company: str
    campus: str
    held_on: str
    role: str | None = None
    reached_seq: int
    selected: bool = False
    rounds: list[str] = []          # round kinds, in the order they happened
    questions: list[dict] = []      # [{round_seq, text}]


@app.post("/api/submit")
def submit(s: Submission, request: Request):
    guard(request, "submit")
    """One student's account of one drive.

    The unique constraint on (student, drive) is the whole anti-gaming measure,
    and it lives in the schema. A second submission updates the first rather
    than adding to the count, so no amount of resubmitting manufactures
    agreement.
    """
    kind = email_kind(s.email)
    if not kind:
        raise HTTPException(400, "That does not look like an email address.")
    if not s.questions:
        raise HTTPException(400, "Add at least one question you were asked.")

    db = conn()
    h = hash_email(s.email)
    db.execute("insert or ignore into student (email_hash, batch, branch, verified_at)"
               " values (?,?,?,?)",
               (h, s.batch, s.branch,
                None if kind == "personal" else "domain:" + str(date.today())))
    sid = db.execute("select id from student where email_hash = ?", (h,)).fetchone()[0]

    db.execute("insert or ignore into company (name, slug) values (?,?)",
               (s.company, s.company.lower().replace(" ", "-")))
    cid = db.execute("select id from company where name = ?", (s.company,)).fetchone()[0]

    db.execute("""insert or ignore into drive (company_id, campus, held_on, role)
                  values (?,?,?,?)""", (cid, s.campus, s.held_on, s.role))
    did = db.execute("""select id from drive where company_id = ? and campus = ?
                          and held_on = ? and ifnull(role,'') = ifnull(?,'')""",
                     (cid, s.campus, s.held_on, s.role)).fetchone()[0]

    for seq, kind in enumerate(s.rounds, 1):
        db.execute("insert or ignore into round (drive_id, seq, kind) values (?,?,?)",
                   (did, seq, kind))

    db.execute("""insert into submission (student_id, drive_id, reached_seq, selected)
                  values (?,?,?,?)
                  on conflict(student_id, drive_id) do update set
                    reached_seq = excluded.reached_seq,
                    selected    = excluded.selected,
                    submitted_at = datetime('now')""",
               (sid, did, s.reached_seq, 1 if s.selected else 0))
    sub_id = db.execute("select id from submission where student_id = ? and drive_id = ?",
                        (sid, did)).fetchone()[0]

    db.execute("delete from reported_question where submission_id = ?", (sub_id,))
    for q in s.questions:
        text = (q.get("text") or "").strip()
        if len(text) < 8:
            continue
        db.execute("insert into reported_question (submission_id, round_seq, raw_text)"
                   " values (?,?,?)", (sub_id, int(q.get("round_seq") or 1), text))
    db.commit()

    return {"ok": True, "drive_id": did, "submission_id": sub_id,
            "note": "Clusters rebuild on the next pass, so your questions "
                    "join the counts shortly."}


class Ask(BaseModel):
    question: str
    language: str = "Python"


class Gen(BaseModel):
    company: str
    sections: list[str] = []
    language: str = "Python"
    force: bool = False


@app.get("/api/verify")
def verify_company(company: str):
    """Does this company exist, according to the open web."""
    import company as co
    found, info, suggestions = co.verify(company)
    return {"typed": company, "found": found, "info": info, "suggestions": suggestions}


class JD(BaseModel):
    company: str | None = None
    jd: str
    resume_text: str | None = None
    skills: list[str] = []


@app.post("/api/jd")
def jd_match(body: JD):
    import jdmatch
    res = jdmatch.match(body.resume_text, body.jd, body.company, body.skills)
    res["advice"] = jdmatch.advice(res)
    return res


class Chat(BaseModel):
    messages: list[dict]
    language: str = "Python"


@app.post("/api/chat")
def chat(body: Chat, request: Request):
    guard(request, "chat")
    import answers
    return answers.chat(body.messages, body.language)


class ResumeQ(BaseModel):
    company: str
    resume_text: str
    skills: list[str] = []


@app.post("/api/resume_questions")
def resume_questions(body: ResumeQ, request: Request):
    guard(request, "generate")
    """Questions about this candidate's actual resume, cached per company+resume."""
    import answers, hashlib as hl
    db = conn()
    key = "resumeq:" + hl.sha256(
        (body.company + body.resume_text[:4000]).encode()).hexdigest()[:24]
    row = db.execute("select content from package where company = ? and section = ?",
                     (body.company, key)).fetchone()
    if row:
        return json.loads(row[0])
    out = answers.resume_questions(body.resume_text, body.company, body.skills)
    if "error" not in out:
        db.execute("insert or replace into package (company, section, content, model)"
                   " values (?,?,?,?)", (body.company, key, json.dumps(out), "groq"))
        db.commit()
    return out


def _package(company, language="Python"):
    """The package with provenance attached to every single item.

    Two things had to change here. An item now carries where it came from, and
    the drive overview is built from candidate reports rather than generated,
    because "what the drive is like" is a claim about reality and should not be
    invented. Generated material stays, but as clearly-labelled preparation
    rather than as evidence about this company.
    """
    import package, dedup, sources, provenance
    db = conn()
    stored = {r[0]: json.loads(r[1]) for r in db.execute(
        "select section, content from package where company = ?", (company,))}
    evidence = provenance.drive_evidence(db, company)
    drives = provenance.drives_of(db, company)

    def attach(item, topic=None):
        q = item.get("q") or item.get("text") or ""
        hit = evidence.get(dedup.normalise(q))
        if hit:
            item["tag"] = "reported"
            item["students"] = hit["students"]
            item["drives"] = hit["drives"]
            item["years"] = sorted({d["year"] for d in hit["drives"]}, reverse=True)
        else:
            item.setdefault("tag", "predicted")
            item["verify"] = provenance.verify_links(q, company)
        if not item.get("practice_url"):
            link = provenance.practice_link(topic or item.get("topic"), q)
            if link:
                item["practice_url"] = link
        return item

    for name, sec in stored.items():
        for topic in (sec.get("topics") or []):
            topic["questions"] = [attach(q, topic.get("name"))
                                  for q in (topic.get("questions") or [])]
        for key in ("questions", "problems"):
            if isinstance(sec.get(key), list):
                sec[key] = [attach(q) for q in sec[key] if isinstance(q, dict)]

    import videos
    keep = package.relevant(stored.get("overview"))
    reported = package.reported_questions(db, company)
    return {"company": company,
            "drives": drives,
            "sections": [{**st, "content": stored.get(st["section"]),
                          "applies": (keep is None or st["section"] in keep),
                          "videos": videos.for_section(st["section"], company)}
                         for st in package.status(db, company)],
            "reported": reported,
            "cross_check": sources.cross_check(company),
            "review_links": sources.reviews_for(company),
            "has_key": bool(os.environ.get("GROQ_API_KEY"))}


@app.get("/api/package")
def get_package(company: str, language: str = "Python"):
    return _package(company, language)


@app.post("/api/package/merge")
def merge_duplicates():
    """Collapse companies that differ only in spelling."""
    db = conn()
    rows = [r[0] for r in db.execute("select distinct company from package")]
    seen, merged = {}, []
    for name in rows:
        key = name.lower().replace(" ", "")
        if key in seen:
            keep = seen[key]
            for sec, content in db.execute(
                    "select section, content from package where company = ?", (name,)):
                db.execute("insert or ignore into package (company, section, content)"
                           " values (?,?,?)", (keep, sec, content))
            db.execute("delete from package where company = ?", (name,))
            merged.append(f"{name} -> {keep}")
        else:
            seen[key] = name
    db.commit()
    return {"merged": merged}


@app.get("/api/package/pdf")
def package_pdf(company: str, sections: str = ""):
    """One section or the whole package, printed."""
    import pdf as pdfmod
    from fastapi.responses import FileResponse as FR
    pkg = _package(company)
    want = [x for x in sections.split(",") if x] or None
    if not any(s.get("content") for s in pkg["sections"]):
        raise HTTPException(400, "Nothing has been built for this company yet.")
    out = os.path.join(tempfile.gettempdir(),
                       f"{company.lower().replace(' ', '-')}"
                       f"{'-' + want[0] if want and len(want) == 1 else ''}-prep.pdf")
    try:
        pdfmod.to_pdf(pdfmod.build_html(pkg, want), out)
    except Exception as e:
        raise HTTPException(500, f"Could not print the PDF: {e}")
    return FR(out, media_type="application/pdf", filename=os.path.basename(out))


ESSENTIALS = ["overview", "reviews"]


@app.post("/api/package/essentials")
def essentials(g: Gen, request: Request):
    guard(request, "generate")
    """The three things wanted on opening a company: what they do, what they
    pay and what employees say, and what the test actually looks like.

    Separated from the rest because a student who opens a company page wants
    those immediately, and making them wait through twelve sections of question
    banks for the answer to "how many rounds is it" is the wrong order."""
    import package
    db = conn()
    done, failed = [], []
    # An overview built while the search endpoint was throttled has no sources
    # and says "unknown". Rebuilding it on the next open lets it heal itself
    # instead of being stuck with an honest but useless blank for ever.
    row = db.execute("select content from package where company = ? and section = 'overview'",
                     (g.company,)).fetchone()
    stale = False
    if row:
        try:
            ov = json.loads(row[0])
            stale = not (ov.get("sources") or ov.get("formats"))
        except Exception:
            stale = True

    for sec in ESSENTIALS:
        try:
            package.generate(db, g.company, sec, g.language,
                             g.force or (stale and sec == "overview"),
                             log=lambda m: print(f"  [{sec}] {m}", flush=True))
            done.append(sec)
        except Exception as e:
            failed.append({"section": sec, "error": str(e)[:160]})
    return {"generated": done, "failed": failed}


@app.post("/api/package/generate")
def gen_package(g: Gen, request: Request):
    guard(request, "generate")
    """Build the requested sections. One section per call keeps each one deep."""
    import package
    db = conn()
    want = g.sections or list(package.SECTIONS)
    if not g.sections:
        row = db.execute("select content from package where company = ? and section = 'overview'",
                         (g.company,)).fetchone()
        keep = package.relevant(json.loads(row[0])) if row else None
        if keep:
            want = [w for w in want if w in keep]
    done, failed = [], []
    for sec in want:
        if sec not in package.SECTIONS:
            continue
        try:
            package.generate(db, g.company, sec, g.language,
                             g.force or (stale and sec == "overview"),
                             log=lambda m: print(f"  [{sec}] {m}", flush=True))
            done.append(sec)
        except Exception as e:
            failed.append({"section": sec, "error": str(e)[:160]})
    return {"generated": done, "failed": failed}


@app.get("/api/prep")
def prep_for(company: str):
    """Everything for one drive, round by round, or an honest blank."""
    import prep
    return prep.build(conn(), company)


@app.get("/api/built")
def built():
    """Packages already generated, so the landing page is not an empty box."""
    db = conn()
    rows = db.execute(
        "select company, count(*) from package group by company order by company").fetchall()
    out = []
    for company, n in rows:
        total = 0
        for (blob,) in db.execute("select content from package where company = ?", (company,)):
            c = json.loads(blob)
            total += len(c.get("problems") or []) + len(c.get("questions") or [])
            total += sum(len(t.get("questions") or []) for t in (c.get("topics") or []))
        rep = db.execute(
            """select count(distinct c.id) from canonical_question c
                 join question_link l     on l.canonical_id = c.id
                 join reported_question r on r.id = l.reported_id
                 join submission s        on s.id = r.submission_id
                 join drive d             on d.id = s.drive_id
                 join company co          on co.id = d.company_id
                where lower(co.name) = lower(?)""", (company,)).fetchone()[0]
        out.append({"company": company, "sections": n, "questions": total, "reported": rep})
    return {"companies": out}


@app.get("/api/known_companies")
def known_companies():
    """Names that have reports behind them, for the search box to suggest."""
    db = conn()
    return {"companies": [
        {"name": n, "students": c} for n, c in db.execute(
            """select co.name, count(distinct s.student_id)
                 from company co
                 join drive d      on d.company_id = co.id
                 join submission s on s.drive_id = d.id
                group by co.id order by 2 desc""")]}


@app.post("/api/ask")
def ask_q(a: Ask):
    import answers
    out = answers.ask(conn(), a.question, a.language)
    # only coding answers vary by language; saying so stops the dropdown looking
    # broken when it is simply not applicable
    out["language"] = a.language if out.get("kind") == "coding" else None
    return out


class Flag(BaseModel):
    url: str | None = None
    submission_id: int | None = None
    reason: str | None = None


@app.post("/api/flag")
def flag(f: Flag, request: Request):
    """Hide a submission from every count.

    The column existed and nothing ever set it, which meant the moderation
    story was theoretical. One junk submission skews a question's report count,
    and the count is the whole trust signal.
    """
    guard(request, "submit")
    db = conn()
    if f.submission_id:
        db.execute("update submission set flagged = 1 where id = ?", (f.submission_id,))
    elif f.url:
        db.execute("""update submission set flagged = 1 where id in (
                        select r.submission_id from reported_question r
                         where r.raw_text = ?)""", (f.url,))
    else:
        raise HTTPException(400, "Give a submission_id or the question text.")
    db.commit()
    return {"ok": True}


@app.post("/api/rebuild")
def rebuild():
    """Re-cluster every report. Cheap at campus scale, run after a drive."""
    import build
    db = conn()
    n = build.rebuild(db, log=lambda *a: None)
    return {"canonical_questions": n}


# ------------------------------------------------------------- jobs half ----

class MatchRequest(BaseModel):
    skills: list[str]
    graduating: int | None = None
    city: str | None = None
    want: str = "either"
    where: str = "anywhere"
    custom_city: str | None = None
    limit: int = 60


# The matcher is vendored under vendor/ rather than loaded from a sibling repo
# by absolute path. It was evaluated against five alternatives on labelled data
# and won, so it is copied verbatim instead of rewritten.
import matching


@app.post("/api/resume")
async def resume(request: Request, file: UploadFile = File(...)):
    guard(request, "resume")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "That file is over 5 MB.")
    text = matching.read_pdf(data)

    # Refusing the wrong document matters more than being permissive: a prep
    # sheet parsed as a resume produced a graduating year scraped from a random
    # date and skills lifted from its question bank, and every number after that
    # was wrong while looking entirely normal.
    import isresume
    ok, reason, detail = isresume.looks_like_resume(text)
    if not ok:
        raise HTTPException(422, detail or "That does not look like a resume.")

    out = matching.profile(text)
    # the raw text goes back to the browser and is never stored, so the
    # resume-question and JD features can use it without the server keeping it
    out["text"] = text[:12000]
    return out


@app.post("/api/match")
def match(req: MatchRequest):
    return matching.find_matches(req, conn)


@app.get("/")
def home():
    return FileResponse(os.path.join(HERE, "web", "index.html"))

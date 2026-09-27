# Recce

Scout the drive before you sit it.

Campus placement preparation built on evidence rather than guesswork: what a
company actually asks, sourced and dated, next to the openings you actually
match.

---

## What it does

**Resume → openings.** Upload a resume, get the live postings you match from an
index of 4,251 Indian openings, the percentage of each posting's requirements
you can evidence, and the skills to add that would unlock the most near-misses.

**Job description → gap.** Paste a JD, get the share you cover weighted by how
rare each skill is, what is missing, and what to change.

**Company → prep package.** Type a company. It is verified against Wikipedia and
DuckDuckGo first, so a name that is not a company is refused rather than
answered. Then: their actual round structure written from live search results,
reported CTC and employee sentiment, aptitude with worked solutions, reasoning,
CS fundamentals, output prediction, SQL, coding problems with runnable code,
technical and HR answers, a plan, and a PDF of all of it.

**Ask anything** — a placement-only assistant. Coding in any language, aptitude,
HR answers. It declines everything else.

---

## The idea that holds it together

Every claim is marked **reported** or **predicted**.

Reported means a student who sat that drive said so, and it carries the date and
the college. Predicted means it is standard material for that kind of drive, not
confirmed for this company, and it carries links to check it.

Student submissions do not fill an empty page. They promote items from predicted
to reported, which means the page is worth opening before anyone has submitted
anything.

---

## The hard part: deduplication

"Asked by 12 students" is only a trust signal if those twelve reports really
were the same question. Merge too eagerly and the count inflates; merge too
timidly and one question fragments into five and disappears.

Three stages, cheapest first: normalise student shorthand (`ll`, `dp`, `bst`),
block on rare tokens so only **7.6%** of pairs are ever compared, then embed and
cluster by average linkage.

**Shipping at precision 0.927, recall 0.710, F1 0.804**, with the threshold
chosen by sweeping it against hand-labelled pairs rather than by inspecting
clusters until they looked right.

### Three results worth reporting

**Single linkage chained.** Connected components let one stray pair fuse
unrelated questions. Average linkage moved precision at the same threshold from
**0.411 to 0.927**.

**Over-normalising cost recall.** Stripping filler helped blocking and hurt the
embedding, because MiniLM was trained on sentences rather than keyword soup.
Splitting the two recovered it.

**ONNX matched torch exactly.** The embeddings run through onnxruntime with a
quantised MiniLM: 106 MB instead of 590 MB, and measured identical — F1 0.804 at
the same threshold. That is the difference between needing a paid host and
fitting a free one.

---

## Grounding, and what happens without it

An early version generated Mercor's process as quant, logical reasoning and
verbal — the standard Indian campus pattern. Mercor runs a single autonomous AI
video interview. The model had filled in a plausible default with the same
confidence as everything else, which is the worst failure this can have.

Round structures are now written from live search results about that specific
company and carry their sources. Mercor came back as *recruiter call → AI-led
interview → coding test → live technical → founder conversation*, and the
aptitude, reasoning and verbal sections are omitted because nothing in their
process calls for them. Where no source describes a process, it says so instead
of guessing.

---

## Where the jobs come from

Six ATS platforms' own public JSON APIs — Greenhouse, Lever, Ashby,
SmartRecruiters, Workable and Workday. No HTML scraping, no keys, no login, no
LinkedIn or Naukri: those prohibit automated collection and put listings behind
anti-bot measures, and defeating that is the line. The crawler identifies itself
with a contact address.

---

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env          # add a Groq key from console.groq.com/keys
./start.sh                    # http://localhost:8010
```

SQLite locally, Postgres in production via `DATABASE_URL`. See `DEPLOY.md`.

## Layout

```
api.py              FastAPI; per-IP limits, CORS, prompt-leak refusal
core/db.py          one interface, SQLite locally and Postgres deployed
core/dedup.py       normalise → block → embed → cluster
core/embed_onnx.py  MiniLM without torch
core/package.py     the 12 prep sections, generated once per company
core/websearch.py   grounds the round structure in real sources
core/company.py     verifies a company exists before generating anything
core/isresume.py    refuses a PDF that is not a resume
core/provenance.py  reported vs predicted, with dates and links
core/pdf.py         Chromium, or WeasyPrint where it is not installed
vendor/             the evaluated matcher, copied from the crawler
```

## Honest limits

- Email is domain-checked, not verified, so "one submission per student" is
  weaker than it sounds.
- Moderation is manual: `POST /api/flag` hides a submission, nothing calls it
  automatically.
- One model allowance is shared by all visitors: 8,000 tokens a minute.
  Requests queue behind it rather than failing.

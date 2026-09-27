# Deploying Recce

## Before anything

Rotate the Groq key if it has ever appeared in a screenshot or a chat:
<https://console.groq.com/keys>

## The two constraints that decide your host

**The deduplicator needs real embeddings.** Merging "reverse a LL" and "reverse
a singly linked list" into one question with a count of 12 is the whole trust
signal. With MiniLM that runs at **F1 0.804** (precision 0.927). Token overlap
alone manages **F1 0.431** (precision 0.454) — half the merges wrong, so the
counts lie.

It runs through **ONNX rather than torch**: the same model, 83 MB of runtime
plus 23 MB of quantised weights instead of 590 MB, and measurably identical
(F1 0.804 at the same threshold). Full quality therefore fits a free tier, and
torch is not installed.

**The PDF needs Chromium**, or WeasyPrint plus its system libraries. Neither is
present on a plain Python host, so the feature silently vanishes there.

Both are why this deploys as a **Docker image**, not a Python service.

## Your options, honestly

Any host that can run a Docker image with ~512 MB works. The image carries
Chromium, the ONNX runtime and the quantised model.

## 1. A database that survives a restart

Free hosts give you an ephemeral disk, so SQLite loses every submission and
generated package on restart. Create Postgres (Supabase free tier is fine) and
set `DATABASE_URL`.

No code changes: `core/db.py` uses Postgres when `DATABASE_URL` is set and the
local SQLite file otherwise.

## 2. Environment

| Variable | Why |
|---|---|
| `GROQ_API_KEY` | generation and chat |
| `DATABASE_URL` | `postgresql://…` — without it, data does not survive |
| `ALLOWED_ORIGINS` | your deployed URL; a wildcard lets any site spend your quota |
| `RECCE_CONTACT` | the address in the crawler's User-Agent |
| `RECCE_ENV` | `production` — disables the local-only demo-clear endpoint |

## 3. The job index

`jobs.db` ships with the app: 4,251 India postings, 25 MB, read-only. It is the
full 158 MB crawl trimmed to the rows the app actually queries. Refresh it by
running the crawler locally and redeploying.

## 4. What is protected

- Per-IP limits: 6 package builds an hour, 30 chat messages, 20 resumes
- CORS restricted to `ALLOWED_ORIGINS`
- Prompt-extraction refused before the model is called
- Uploads rejected unless they read as a resume
- One submission per student per drive, enforced by a unique constraint
- `clear_demo` disabled in production

## 5. Still open

- **Email is not verified**, only the domain is checked, so "one per student"
  is weaker than it sounds. Real verification needs a mail provider.
- **Moderation is manual.** `POST /api/flag` hides a submission; nothing calls
  it automatically.
- The Postgres path is exercised against a real PostgreSQL 16 from an empty
  database: schema creation, every endpoint, and a submission round trip.
- **One model allowance** is shared by every visitor: 8,000 tokens a minute.

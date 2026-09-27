"""The whole preparation package for one company, generated section by section.

The earlier design waited for students to report questions and showed an empty
page until they did, which made it useless on the day it was most needed. That
was backwards. The material for a campus aptitude round is not secret and does
not vary by student; what varies is which of it a particular company actually
uses. So everything is generated up front and each item is tagged by how much
is known about it:

  reported   a student who sat this company's drive said they were asked it
  predicted  not confirmed for this company, but standard for drives like it

A student report does not add a question to an empty page any more. It promotes
one from predicted to reported, which is a far more useful thing for it to do
and means the page is worth opening before anyone has submitted anything.

One call per section rather than one for everything: a single request for
twelve sections produces twelve shallow ones, and the whole point is depth.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import ssl
import urllib.request

import certifi

# macOS ships a Python that does not read the system keychain, so every HTTPS
# call fails with CERTIFICATE_VERIFY_FAILED. Point at certifi's bundle rather
# than disabling verification, which would accept any certificate at all.
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

COMMON = (
    "You are compiling a campus placement preparation package for final-year "
    "engineering students in India, for the company {company}. Be concrete and "
    "correct. Every numeric answer must be arithmetically right; work it out "
    "step by step before stating it. Never invent a specific fact about this "
    "company's process that you are not confident about: where you are "
    "generalising from how similar companies hire, that is expected and should "
    "be tagged predicted. Reply with JSON only, no prose around it."
)

SECTIONS = {
 "overview": dict(
   title="The drive at a glance",
   prompt="""Give what a candidate needs to know before the {company} campus drive.
JSON: {{"role":"typical role title","process":["stage 1","stage 2",...],
"eligibility":["criterion",...],"keep_ready":["document",...],
"formats":[{{"name":"Format A - MCQ heavy","sections":["Quant 12Q/15min",...],
"seen_in":"which drives/years this format was seen in, or 'commonly reported'"}}],
"what_decides":["the thing that actually filters candidates, one per line",...],
"sources":["the URL each claim about the process came from",...],
"confidence":"reported" or "predicted"}}

Write the process from the SOURCES supplied below, not from what a campus drive
usually looks like. Companies differ enormously: some run a single AI video
interview, some a take-home, some no aptitude test at all. Assuming the standard
quant/logical/verbal pattern for a company that does not use it is the worst
failure this can have, because it reads exactly like a correct answer.

If the sources do not describe the process, say so: return formats as an empty
list, put "Not publicly documented" in what_decides, and set confidence to
"unknown". An admitted gap is more useful than an invented round."""),

 "aptitude": dict(
   title="Quantitative aptitude",
   prompt="""Quant preparation for {company}'s aptitude round.
JSON: {{"topics":[{{"name":"Percentages","formulas":["x% of y = (x/100)*y",...],
"questions":[{{"q":"question text with numbers","steps":["step","step"],
"answer":"final answer","tag":"predicted"}}]}}]}}
Cover: percentages, profit and loss, averages, ratio, time and work, time speed
distance, simple and compound interest, permutations and combinations,
probability, numbers and ages. 8 topics, 3 questions each, every answer verified
by working it through. Include the shortcut students use under time pressure."""),

 "reasoning": dict(
   title="Logical reasoning",
   prompt="""Logical reasoning for {company}.
JSON: {{"topics":[{{"name":"Coding-Decoding","formulas":["approach tips"],
"questions":[{{"q":"...","steps":["..."],"answer":"...","tag":"predicted"}}]}}]}}
Cover coding-decoding, blood relations, direction sense, number and letter
series, syllogisms, seating arrangement, ranking, calendars, odd one out, data
sufficiency. 3 questions each."""),

 "verbal": dict(
   title="Verbal ability and the English round",
   prompt="""English preparation for {company}, including any spoken or written round.
JSON: {{"advice":["how the spoken/voice round is scored and how to pass it",...],
"topics":[{{"name":"Error spotting","questions":[{{"q":"...","steps":["..."],
"answer":"...","tag":"predicted"}}]}}]}}
Cover error spotting, sentence correction, reading comprehension approach,
synonyms and antonyms, para jumbles, and essay or email writing if used."""),

 "cs_mcq": dict(
   title="CS fundamentals",
   prompt="""CS fundamentals MCQs for {company}'s online test.
JSON: {{"topics":[{{"name":"Operating Systems","questions":[{{"q":"question",
"options":["A ...","B ...","C ...","D ..."],"answer":"B ...",
"why":"one line on why","tag":"predicted"}}]}}]}}
Cover OS, DBMS, computer networks, OOP, data structures. 5 questions per topic.
These are usually the main shortlisting filter, so favour breadth of definitions
over depth."""),

 "output": dict(
   title="Output prediction and debugging",
   prompt="""Guess-the-output and debugging questions for {company}.
JSON: {{"topics":[{{"name":"C output","questions":[{{"q":"code snippet as plain text",
"steps":["what the code actually does"],"answer":"the printed output",
"tag":"predicted"}}]}}]}}
Cover C, Java and Python output prediction, plus a debugging group where the
question is to find the bug. 3 per group. Keep snippets under 12 lines
and make sure the stated output is exactly what the code produces.""",
   max_tokens=5000),

 "sql": dict(
   title="SQL",
   prompt="""SQL questions for {company}.
JSON: {{"topics":[{{"name":"Joins and aggregation","questions":[{{"q":"task, with
the table shape stated","steps":["approach"],"answer":"the SQL query",
"tag":"predicted"}}]}}]}}
Cover joins, group by and having, subqueries, second highest salary, duplicates,
and the DELETE vs TRUNCATE style theory questions. 3 per group."""),

 "coding": dict(
   title="Coding problems",
   prompt="""Coding problems for {company}'s coding round, in {language}.
JSON: {{"problems":[{{"q":"problem statement","approach":"one line",
"code":"complete working {language} code","complexity":"O(..) time, O(..) space",
"edge":"an edge case the interviewer probes","tag":"predicted",
"practice_url":"a leetcode.com or geeksforgeeks.org URL for this problem"}}]}}
10 problems at the difficulty this company actually sets, ordered easiest first.
The code must run correctly as written.""",
   max_tokens=5000),

 "technical": dict(
   title="Technical interview",
   prompt="""Technical interview answers for {company}.
JSON: {{"topics":[{{"name":"OOP","questions":[{{"q":"question",
"answer":"the crisp spoken answer an interviewer wants, 3-5 sentences",
"tag":"predicted"}}]}}]}}
Cover OOP, DBMS, OS, networks, and the language basics they ask about. 5 per
topic. Write answers the way a candidate should say them out loud."""),

 "hr": dict(
   title="HR and project round",
   prompt="""HR round preparation for {company}.
JSON: {{"questions":[{{"q":"the HR question","answer":"a model answer a student
could actually say, under 110 words, first person, with [square brackets] where
they must insert their own detail","why":"what the interviewer is really checking",
"tag":"predicted"}}],
"project_questions":["questions they ask about any project on a resume",...],
"about_company":["what to know about {company} before the interview",...]}}
12 HR questions including the awkward ones: relocation, bond, why this company,
salary expectation, weakness, failure."""),

 "reviews": dict(
   title="Pay, culture and what employees say",
   prompt="""What candidates and employees report about working at {company}.
JSON: {{"ctc":[{{"role":"role title","fresher_ctc":"typical fresher package in LPA",
"bond":"bond or service agreement if any, else 'none reported'","note":"anything about
the breakup, base vs variable"}}],
"reviews":[{{"topic":"Work-life balance","says":"what employees commonly report",
"sentiment":"positive" or "mixed" or "negative"}}],
"watch_out":["something candidates say they wish they had known",...]}}
Cover work-life balance, pay and appraisals, the training period, project allocation and
bench time, management, and location or relocation. 6 review topics.
IMPORTANT: this is aggregated employee sentiment, not fact. Write each entry as what
employees report, never as a statement about the company. Do not invent exact salary
figures you are unsure of; give the commonly-cited range and say it is reported.""",
   max_tokens=2600),

 "plan": dict(
   title="Plan and checklist",
   prompt="""A preparation plan for the {company} drive.
JSON: {{"days":[{{"day":"Day 1","focus":"what to do that day","hours":"3-4 h"}}],
"checklist":["what to carry or do on test day",...],
"mistakes":["the mistake candidates actually make in this drive",...]}}
7 days, working backwards from the drive."""),
}


# The free tier allows 8,000 tokens per minute, which is about two of these
# calls. Firing eleven sections back to back therefore fails from the third one
# onward, which is the worst possible behaviour: half a package and an error
# that reads like the site is broken. So the remaining budget is read from the
# response headers and the next call waits for the window to refill instead.
MAX_TOKENS = 3000
_budget = {"remaining": None, "reset_at": 0.0}


def _secs(v):
    """Groq states resets as '5m45.6s' or '32.197s'."""
    if not v:
        return 0.0
    m = re.match(r"(?:(\d+(?:\.\d+)?)m)?(\d+(?:\.\d+)?)s", str(v).strip())
    return float(m.group(1) or 0) * 60 + float(m.group(2)) if m else 0.0


def _note_limits(headers):
    h = {k.lower(): v for k, v in dict(headers).items()}
    if "x-ratelimit-remaining-tokens" in h:
        _budget["remaining"] = int(float(h["x-ratelimit-remaining-tokens"]))
    if h.get("x-ratelimit-reset-tokens"):
        _budget["reset_at"] = time.time() + _secs(h["x-ratelimit-reset-tokens"])


def _wait_for_budget(need, log=None):
    rem = _budget["remaining"]
    if rem is None or rem >= need:
        return
    delay = max(0.0, _budget["reset_at"] - time.time()) + 1.0
    if delay > 0:
        if log:
            log(f"waiting {delay:.0f}s for the token window to refill")
        time.sleep(min(delay, 75))
        _budget["remaining"] = None


def _call(prompt, system, timeout=120, log=None, max_tokens=None):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")

    import ratelimit
    payload = {"model": MODEL, "temperature": 0.25,
               "max_tokens": max_tokens or MAX_TOKENS,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": prompt}]}
    data = ratelimit.call(payload, key, timeout=timeout, log=log)
    return json.loads(data["choices"][0]["message"]["content"])


def generate(db, company, section, language="Python", force=False, log=None):
    """Build one section, or return the stored one.

    The overview is grounded in live search results about how this company
    actually hires. Everything else is standard preparation material that does
    not vary by employer, so it does not need grounding."""
    if not force:
        row = db.execute("select content from package where company = ? and section = ?",
                         (company, section)).fetchone()
        if row:
            return json.loads(row[0])

    spec = SECTIONS[section]
    system = COMMON.format(company=company)
    prompt = spec["prompt"].format(company=company, language=language)

    if section == "overview":
        try:
            import websearch
            rows = websearch.hiring_context(company, db=db)
            ctx = websearch.as_prompt_context(rows)
            if ctx:
                prompt += ("\n\nSOURCES describing this company's hiring process:\n"
                           + ctx)
                if log:
                    log(f"grounded in {len(rows)} sources")
            else:
                prompt += ("\n\nNo sources were found describing this company's hiring "
                           "process. Return an empty formats list and confidence "
                           "\"unknown\" rather than assuming a typical campus pattern.")
        except Exception:
            pass
    content = _call(prompt, system, log=log,
                    max_tokens=spec.get("max_tokens"))

    db.execute("""insert into package (company, section, content, model)
                  values (?,?,?,?)
                  on conflict(company, section) do update set
                    content = excluded.content, model = excluded.model,
                    created_at = datetime('now')""",
               (company, section, json.dumps(content), MODEL))
    db.commit()
    return content


def reported_questions(db, company):
    """What students who actually sat this company's drive said they were asked."""
    rows = db.execute(
        """select c.text, c.topic, count(distinct s.student_id) n,
                  group_concat(distinct d.held_on)
             from canonical_question c
             join question_link l     on l.canonical_id = c.id
             join reported_question r on r.id = l.reported_id
             join submission s        on s.id = r.submission_id
             join drive d             on d.id = s.drive_id
             join company co          on co.id = d.company_id
            where s.flagged = 0 and lower(co.name) = lower(?)
            group by c.id order by n desc""", (company,)).fetchall()
    out = []
    for text, topic, n, dates in rows:
        years = sorted({d[:4] for d in (dates or "").split(",") if d})
        out.append({"text": text, "topic": topic, "students": n, "years": years})
    return out


def status(db, company):
    have = {r[0] for r in db.execute(
        "select section from package where company = ?", (company,))}
    return [{"section": k, "title": v["title"], "ready": k in have}
            for k, v in SECTIONS.items()]


# Which sections a company's process actually calls for. Showing every company
# a verbal-ability section because the template has one is how the page ends up
# describing a drive that does not exist: Infosys does not run an English round,
# so an English section under their name is simply wrong.
ALWAYS = {"overview", "reviews", "plan", "coding", "technical", "hr"}
EVIDENCE = {
    "aptitude": r"aptitude|quant|numerical|mathemat",
    "reasoning": r"reasoning|logical|analytical|puzzle",
    # "communication" on its own is not a verbal round. Every technical
    # interview mentions communication, and matching it added an English
    # section to a company whose process is a coding call.
    "verbal": (r"verbal\s+abilit|english\s+(test|round|section|assessment)|"
               r"comprehension|para\s*jumble|essay\s+writ|written\s+(test|english)|"
               r"voice\s+(test|round|assessment)|spoken\s+english|"
               r"communication\s+(test|round|assessment|section)|grammar"),
    "cs_mcq": r"mcq|multiple choice|fundamental|technical (test|assessment|mcq)|objective",
    "output": r"pseudocode|pseudo code|output|guess|debug|snippet",
    "sql": r"sql|database|dbms|query|rdbms",
}


def relevant(overview):
    """Sections supported by what the overview says about their process."""
    if not overview:
        return None
    blob = " ".join([
        " ".join(overview.get("process") or []),
        " ".join(str(x) for x in (overview.get("what_decides") or [])),
        " ".join(" ".join(f.get("sections") or []) + " " + str(f.get("name") or "")
                 for f in (overview.get("formats") or [])),
    ]).lower()
    keep = set(ALWAYS)
    for sec, pat in EVIDENCE.items():
        if re.search(pat, blob):
            keep.add(sec)
    return keep

"""Deciding whether an uploaded PDF is actually a resume.

Any PDF used to be accepted, so a prep sheet uploaded by mistake came back with
skills pulled out of its question bank and a graduating year scraped from a
random date. Every number downstream was then wrong while looking perfectly
normal, which is the worst way for this to fail.

Scored on the things a resume has and a document about a company does not: its
own contact details, section headings written in the first person's structure,
and dates in the shape of a degree. Plus a check for the giveaways of the
documents people actually upload by accident here, which are prep sheets and
job descriptions.
"""
import re

SECTIONS = [
    r"\beducation\b", r"\bexperience\b", r"\bwork experience\b", r"\bprojects?\b",
    r"\bskills?\b", r"\bcertification", r"\bachievements?\b", r"\binternships?\b",
    r"\bobjective\b", r"\bsummary\b", r"\bpublications?\b", r"\bactivities\b",
    r"\bcoursework\b", r"\breferences\b", r"\bawards?\b", r"\bextra.?curricular\b",
]
CONTACT = [
    r"[\w.+-]+@[\w-]+\.[\w.]+",                      # email
    r"(?:\+?91[\s-]?)?[6-9]\d{9}\b",                 # indian mobile
    r"linkedin\.com/in/", r"github\.com/",
]
DEGREE = r"\b(b\.?tech|b\.?e\b|m\.?tech|b\.?sc|m\.?sc|mca|bca|bachelor|master|diploma)\b"

# what people actually upload here by mistake
PREP_DOC = [
    r"\bprep(aration)?\s+(package|material|sheet|guide|plan)\b",
    r"\bmock test\b", r"\bpractice questions?\b", r"\bsyllabus\b",
    r"\banswer key\b", r"\bsolutions?\b.{0,20}\bexplanation\b",
    r"\bround\s*\d\b.{0,40}\bround\s*\d\b",
]
JD_DOC = [
    r"\b(we are looking for|the ideal candidate|roles? and responsibilit)",
    r"\b(job description|job title|about the role|what you'?ll do)\b",
    r"\b(equal opportunity employer|apply now)\b",
]


# A resume is one to three pages. The documents people upload here by mistake —
# prep packages, question banks, offer letters — are far longer, and length
# turned out to discriminate better than any keyword: a prep sheet contains an
# email address and the words projects, certification and internships too, so
# keyword scoring alone accepted an 82,000-character question bank as a resume.
MAX_CHARS = 20000
TYPICAL_MAX = 9000


def looks_like_resume(text):
    """(ok, reason, detail). ok=False means do not treat this as a resume."""
    raw = text or ""
    t = raw.lower()
    n = len(t.strip())
    if n < 200:
        return False, "too short", "There is almost no text in that PDF."
    if n > MAX_CHARS:
        return False, "too long", (f"That document is about {n // 1000}k characters, which is "
                                   "far longer than a resume. It looks like a prep package, a "
                                   "report or a book rather than a CV.")

    head = t[:max(900, int(n * 0.15))]          # a resume puts contact at the top
    sections = sum(1 for p in SECTIONS if re.search(p, t))
    contact_head = sum(1 for p in CONTACT if re.search(p, head))
    contact_any = sum(1 for p in CONTACT if re.search(p, t))
    degree = 1 if re.search(DEGREE, t) else 0
    prep = sum(1 for p in PREP_DOC if re.search(p, t))
    jd = sum(1 for p in JD_DOC if re.search(p, t))

    if prep >= 1 and contact_head == 0:
        return False, "prep material", ("This looks like preparation material or a question "
                                        "bank, not a resume.")
    if jd >= 2 and contact_head == 0:
        return False, "job description", ("This looks like a job description. Use Match a JD "
                                          "for that instead.")
    if contact_any == 0 and sections < 3:
        return False, "no resume structure", ("No contact details and no resume sections "
                                              "(education, experience, projects, skills) "
                                              "were found.")

    score = sections + contact_head * 3 + contact_any + degree
    if n > TYPICAL_MAX:
        score -= 2          # long and only vaguely resume-shaped is a bad sign
    if score < 5:
        return False, "not enough signal", ("This does not read like a resume. Expected "
                                            "contact details near the top and sections such "
                                            "as education, experience or projects.")
    return True, "ok", None

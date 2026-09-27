"""Turning a job description into the two or three lines a person actually
reads before deciding whether to click.

Most of a posting is boilerplate: mission, benefits, the equal-opportunity
statement. What decides whether you apply is the requirements list, and in
almost every posting that list is literally marked up as one, so the HTML is
the signal rather than the noise: take the <li> items and you have the
requirements without guessing at sentence boundaries.
"""
import html as _html
import re

# tags that end a line of meaning, so they become newlines rather than spaces
BREAK = re.compile(r"</(?:li|p|div|h[1-6]|tr)\s*>|<br\s*/?>", re.I)
LI = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")

REQ_HEAD = re.compile(
    r"(what (?:we'?re|you'?ll) (?:be )?(?:looking for|need|bring|do|doing)|"
    r"requirements?|qualifications?|who you are|responsibilities|"
    r"you (?:should |will )?have|minimum qualifications|basic qualifications|"
    r"skills|experience|we'?re looking for|about you|your profile)\b", re.I)

# sentences that sell, apologise, or comply, rather than inform
FLUFF = re.compile(
    r"\b(equal opportunit|without regard to|our mission|we believe|diversity|"
    r"diverse perspectives|committed to|accommodation|background check|"
    r"benefits|perks|compensation|salary|true self|underrepresented|"
    r"we look forward|what'?s next|encourages? you to|apply (?:now|today)|"
    r"this is a (?:full|part)-time|join us|reconsider and apply|"
    r"who we are|about (?:us|the team|adyen)|studies show)\b", re.I)


def _text(raw):
    """Markup to plain text, keeping line structure."""
    if not raw:
        return ""
    s = BREAK.sub("\n", raw)
    s = TAG.sub(" ", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _clean(s):
    s = re.sub(r"\s+", " ", _html.unescape(TAG.sub(" ", s))).strip(" -•·*\t")
    # style attributes sometimes survive as orphan fragments like '400;"'
    return re.sub(r"^\d+;\"?\s*", "", s)


def bullets(raw, limit=4):
    """The requirement lines, preferring the ones the posting marked up."""
    if not raw:
        return []
    items = [_clean(m) for m in LI.findall(raw)]
    if len(items) < 3:                       # a posting written as paragraphs
        items = [_clean(l) for l in _text(raw).split("\n")]

    out, seen = [], set()
    for s in items:
        if not (30 <= len(s) <= 165) or FLUFF.search(s):
            continue
        if REQ_HEAD.fullmatch(s.rstrip(":")):
            continue
        key = s.lower()[:45]
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


# postings that bother with a heading say where the role itself starts
ROLE_HEAD = re.compile(
    r"^\s*(about (?:the |this )?(?:role|job|position|opportunity)|the role|"
    r"your role|the opportunity|what you'?ll (?:do|be doing)|role overview|"
    r"job description|position summary)\s*:?\s*$", re.I)


def summary(raw, chars=215):
    """The first sentences that say something about the role itself.

    A posting almost always opens with the company pitch, so this skips ahead
    to the role heading when there is one. Without that, the first line of a
    Greenhouse posting is a sentence about how the company is the platform of
    choice for Meta and Uber, which tells you nothing about the job."""
    plain = _text(raw)
    if not plain:
        return ""
    lines = plain.split("\n")
    for i, line in enumerate(lines):
        if ROLE_HEAD.match(_clean(line)):
            plain = "\n".join(lines[i + 1:])
            break
    keep = []
    for line in plain.split("\n"):
        s = _clean(line)
        if len(s) < 40 or FLUFF.search(s):
            continue
        keep.append(s)
        if sum(len(k) for k in keep) > chars:
            break
    s = " ".join(keep)
    if not s:
        return ""
    if len(s) <= chars:
        return s
    cut = s[:chars]
    return cut[:cut.rfind(" ")] + "…"

"""Grounding the test pattern in what the web actually says.

Without this the model fills in whatever it considers a normal campus drive,
which for an Indian placement tool means quant, logical reasoning and verbal.
For Mercor that is completely wrong — their process is a single twenty-minute
autonomous AI video interview — and the page said it with the same confidence
as everything else. A plausible wrong answer is worse than an admitted gap.

So the round structure is written from search snippets about that company's
actual process, and the prompt is told to say the process is unknown rather
than assume the usual one. Snippets and links only: nothing is republished.
"""
import html
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

import certifi

SSL_CTX = ssl.create_default_context(cafile=certifi.where())
UA = {"User-Agent": "Mozilla/5.0 (compatible; recce/1.0)"}

LINK = re.compile(r"class=['\"]result-link['\"][^>]*>(.*?)</a>", re.S)
SNIP = re.compile(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", re.S)
HREF = re.compile(r"href=\"//duckduckgo\.com/l/\?uddg=([^&\"]+)")


def _clean(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


def _fetch(query, timeout):
    """Try the endpoints in turn. A 202 with no results is the throttle, not an
    error, so it has to be detected by looking for results rather than by
    status code."""
    q = urllib.parse.quote(query)
    attempts = [
        ("GET", f"https://lite.duckduckgo.com/lite/?q={q}", None),
        ("POST", "https://lite.duckduckgo.com/lite/",
         urllib.parse.urlencode({"q": query}).encode()),
        ("GET", f"https://html.duckduckgo.com/html/?q={q}", None),
    ]
    for method, url, body in attempts:
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                page = r.read().decode("utf8", "ignore")
            if "result-link" in page or "result__a" in page:
                return page
        except Exception:
            continue
        time.sleep(1.5)
    return ""


def search(query, limit=6, timeout=20, db=None):
    """Titles, snippets and URLs, cached permanently once found."""
    if db is not None:
        row = db.execute("select results from search_cache where query = ?",
                         (query,)).fetchone()
        if row:
            return json.loads(row[0])[:limit]

    page = _fetch(query, timeout)
    if not page:
        return []

    titles = [_clean(t) for t in LINK.findall(page)]
    snips = [_clean(s) for s in SNIP.findall(page)]
    hrefs = [urllib.parse.unquote(h) for h in HREF.findall(page)]

    out = []
    for i, title in enumerate(titles[:limit]):
        out.append({"title": title,
                    "snippet": snips[i] if i < len(snips) else "",
                    "url": hrefs[i] if i < len(hrefs) else ""})
    if out and db is not None:
        db.execute("insert or replace into search_cache (query, results) values (?,?)",
                   (query, json.dumps(out)))
        db.commit()
    return out


def hiring_context(company, limit=6, db=None):
    """What the web says about how this company actually hires."""
    seen, rows = set(), []
    for q in (f"{company} interview process rounds",
              f"{company} hiring process assessment test pattern"):
        for r in search(q, limit=limit, db=db):
            key = r["url"] or r["title"]
            if key in seen or not r["snippet"]:
                continue
            seen.add(key)
            rows.append(r)
        if len(rows) >= limit:
            break
    return rows[:limit]


def as_prompt_context(rows, cap=2600):
    if not rows:
        return ""
    parts = []
    for r in rows:
        parts.append(f"- {r['title']}\n  {r['snippet']}\n  ({r['url']})")
    return "\n".join(parts)[:cap]

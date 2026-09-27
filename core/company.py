"""Checking a company is real, and finding out what people say about it.

A typed name used to be matched against a hardcoded list, which meant the site
confidently built a package for anything that happened to look close enough and
refused real employers it had never heard of. Both failures are bad, and the
second is worse for a student whose campus is visited by a firm nobody has
written about.

So existence is checked against the open web: Wikipedia first, because a
company with an article has an unambiguous identity and a description worth
showing, then DuckDuckGo. Nothing is scraped; both expose an API for exactly
this, and the URL is kept so the claim can be followed.
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

import certifi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SSL_CTX = ssl.create_default_context(cafile=certifi.where())
UA = {"User-Agent": "recce/1.0 (campus placement prep; educational)"}

CORPORATE = ("compan", "corporation", "technology", "software", "services",
             "consult", "bank", "conglomerate", "manufactur", "firm", "group",
             "enterprise", "multinational", "startup", "business", "it service",
             "outsourc", "retail", "telecom", "pharmac", "automotive", "insur")


def _get(url, timeout=18):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return json.loads(r.read())


def _wikipedia(name):
    slug = urllib.parse.quote(name.strip().replace(" ", "_"))
    try:
        d = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
    except Exception:
        return None
    if d.get("type") == "disambiguation" or not d.get("extract"):
        return None
    return {"name": d.get("title"), "description": d.get("description") or "",
            "summary": d.get("extract"),
            "url": (d.get("content_urls") or {}).get("desktop", {}).get("page"),
            "source": "Wikipedia"}


def _wiki_search(name):
    """Fuzzy lookup, for a typo or an informal name."""
    q = urllib.parse.quote(f"{name} company")
    try:
        d = _get("https://en.wikipedia.org/w/api.php?action=query&list=search"
                 f"&srsearch={q}&format=json&srlimit=4")
    except Exception:
        return []
    return [r["title"] for r in (d.get("query") or {}).get("search", [])]


def _duckduckgo(name):
    q = urllib.parse.quote(name)
    try:
        d = _get(f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1")
    except Exception:
        return None
    if not d.get("AbstractText"):
        return None
    return {"name": d.get("Heading") or name, "description": "",
            "summary": d.get("AbstractText"), "url": d.get("AbstractURL"),
            "source": "DuckDuckGo"}


def _looks_corporate(hit):
    blob = f"{hit.get('description','')} {hit.get('summary','')}".lower()
    return any(w in blob for w in CORPORATE)


def canonical(name):
    """One spelling per company, so "infosys" and "Infosys" do not build twice.

    Everything downstream keys on the company string: the package cache, the
    reported questions, the search cache. Two spellings meant two packages, two
    sets of search results and a tile list that showed the same employer twice.
    """
    found, info, _ = verify(name)
    if found and info and info.get("name"):
        return info["name"].strip()
    return " ".join(w.capitalize() if w.islower() else w
                    for w in (name or "").strip().split())


def verify(name):
    """(found, info, suggestions).

    found is False only when nothing on the open web describes this as a
    company, which is the honest condition for refusing to generate: not "it is
    missing from my list", but "no public source says this exists".
    """
    name = (name or "").strip()
    if len(name) < 2:
        return False, None, []

    for probe in (_wikipedia, _duckduckgo):
        hit = probe(name)
        if hit and _looks_corporate(hit):
            return True, hit, []

    # known to us from a student's report, even if the web is silent
    try:
        import known
        canonical, _ = known.recognise(name)
        if canonical:
            return True, {"name": canonical, "description": "",
                          "summary": "No public article found, but this employer has been "
                                     "reported by students or appears in the live job index.",
                          "url": None, "source": "student reports"}, []
    except Exception:
        pass

    return False, None, _wiki_search(name)[:4]

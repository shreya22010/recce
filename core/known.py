"""Deciding whether a typed name is actually a company.

Typing nonsense produced a confident page of generated material for a company
that does not exist, which is worse than an error: it looks like every other
answer on the site and there is nothing to tell you it is fiction.

Three sources, cheapest first: companies students have reported, the live job
index jobscout already maintains, and a list of the recruiters that visit
Indian campuses but hire through portals with no public feed, so they never
appear in either.
"""
import os
import re
import sqlite3
import db as _db

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DB = os.environ.get("JOBS_DB", os.path.join(HERE, "..", "jobs.db"))

# Campus recruiters that hire through in-house portals, so no public API lists
# them. Without this, the biggest employers of Indian graduates read as unknown.
CAMPUS = """
infosys tcs wipro cognizant accenture capgemini hcltech hcl techmahindra
ltimindtree ltim mindtree mphasis persistent zensar birlasoft coforge
hexaware cybage kpit sonata virtusa ust happiest minds
ibm oracle sap dell cisco intel amd nvidia qualcomm texas instruments
microsoft google amazon adobe salesforce vmware paypal visa mastercard
deloitte pwc kpmg ey grant thornton genpact wns concentrix
jpmorgan goldman sachs morgan stanley wells fargo barclays hsbc citi
standard chartered deutsche bank nomura ubs bny mellon state street
zoho freshworks razorpay zerodha cred phonepe paytm flipkart swiggy zomato
myntra meesho nykaa lenskart unacademy byjus physicswallah groww upstox
tiger analytics fractal mu sigma quantiphi latentview axtria
bosch siemens honeywell abb schneider ge caterpillar cummins
l&t larsen toubro tata elxsi tata technologies jsw reliance adani
juspay sprinklr chargebee postman browserstack hasura zeta
societe generale optum unitedhealth epam thoughtworks publicis sapient
nagarro globallogic altimetrik incedo tredence
""".split()

_CACHE = {"names": None}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def all_names():
    if _CACHE["names"] is not None:
        return _CACHE["names"]
    names = {}
    for n in CAMPUS:
        names.setdefault(_norm(n), n)
    try:
        db = sqlite3.connect(JOBS_DB)
        for (c,) in db.execute("select distinct company from jobs"):
            if c:
                names.setdefault(_norm(c), c)
    except Exception:
        pass
    try:
        db = _db.connect(os.path.join(HERE, "recce.db"))
        for (c,) in db.execute("select name from company"):
            if c:
                names[_norm(c)] = c
    except Exception:
        pass
    _CACHE["names"] = names
    return names


def recognise(typed):
    """(canonical_name, suggestions). canonical is None when it is not a company.

    A short unknown string is far more likely to be a typo than an obscure
    employer, so the bar is higher for those: three characters of gibberish
    should not quietly match a real company by substring.
    """
    key = _norm(typed)
    if len(key) < 2:
        return None, []
    names = all_names()

    if key in names:
        return names[key], []

    # contained either way: "ltim" finds ltimindtree, "tcs india" finds tcs
    contains = [v for k, v in names.items()
                if (key in k and len(key) >= 4) or (len(k) >= 4 and k in key)]
    if contains:
        contains.sort(key=len)
        return contains[0], []

    # near misses, for a suggestion rather than a silent match
    import difflib
    close = difflib.get_close_matches(key, list(names), n=4, cutoff=0.75)
    return None, [names[c] for c in close]

"""The smallest set of topics that covers the most of what will be asked.

Every prep site hands you the same ranked list of everything. The useful
question is the opposite one: given eleven days and six companies visiting
*this* campus, what is the least I can study and still be ready for most of it.

A question counts as covered only when every topic it draws on is in the study
set, which is what stops this from collapsing into "sort topics by frequency".
Under that rule a topic can be worth nothing by itself and a great deal once
its partner is present, so the value of a set is not the sum of its parts and
the greedy step has to be evaluated against what is already chosen.

This is maximum coverage, which is NP-hard, so the greedy choice is an
approximation. For this shape of problem it is within a constant factor of
optimal, and the coverage curve it produces is the thing a student actually
needs: how much each extra topic buys, and where it stops being worth it.
"""
import math
import os
import sqlite3

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as _db
from topics import topics_of

HALF_LIFE_DAYS = 240.0     # a question asked two years ago counts for less


def demand(db, companies=None, campus=None, today=None):
    """What each canonical question is worth, weighted by reports and recency.

    Weighting by distinct students rather than raw reports, because one person
    filing the same question twice must not look like corroboration.
    """
    q = """select c.id, c.text, co.name, d.held_on,
                  count(distinct s.student_id) n
             from canonical_question c
             join question_link l      on l.canonical_id = c.id
             join reported_question r  on r.id = l.reported_id
             join submission s         on s.id = r.submission_id
             join drive d              on d.id = s.drive_id
             join company co           on co.id = d.company_id
            where s.flagged = 0"""
    args = []
    if companies:
        q += " and co.name in (%s)" % ",".join("?" * len(companies))
        args += list(companies)
    if campus:
        q += " and d.campus = ?"
        args.append(campus)
    q += " group by c.id, co.name, d.held_on"

    from datetime import date
    today = today or date.today().isoformat()
    ty, tm, td = (int(x) for x in today.split("-"))
    t_ord = date(ty, tm, td).toordinal()

    items = {}
    for cid, text, comp, held, n in db.execute(q, args):
        try:
            hy, hm, hd = (int(x) for x in held.split("-"))
            age = max(0, t_ord - date(hy, hm, hd).toordinal())
        except Exception:
            age = 0
        recency = 0.5 ** (age / HALF_LIFE_DAYS)
        w = n * recency
        if cid not in items:
            items[cid] = {"id": cid, "text": text, "topics": topics_of(text),
                          "weight": 0.0, "companies": set()}
        items[cid]["weight"] += w
        items[cid]["companies"].add(comp)
    return list(items.values())


def greedy(items, k=None):
    """Pick topics one at a time, each time the one that unlocks the most.

    Returns the running coverage after each pick, which is the output that
    matters: it shows where the curve flattens and studying more stops paying.
    """
    total = sum(i["weight"] for i in items) or 1.0
    universe = sorted({t for i in items for t in i["topics"]})
    k = k or len(universe)

    chosen, curve, covered_ids = [], [], set()
    for _ in range(min(k, len(universe))):
        best, best_gain, best_new = None, 0.0, None
        for t in universe:
            if t in chosen:
                continue
            trial = set(chosen) | {t}
            new = {i["id"] for i in items
                   if i["id"] not in covered_ids and i["topics"] <= trial}
            gain = sum(i["weight"] for i in items if i["id"] in new)
            if gain > best_gain:
                best, best_gain, best_new = t, gain, new
        if not best:
            break
        chosen.append(best)
        covered_ids |= best_new
        curve.append({"topic": best, "gain": best_gain / total,
                      "coverage": sum(i["weight"] for i in items
                                      if i["id"] in covered_ids) / total,
                      "unlocked": len(best_new)})
    return chosen, curve


def optimise(items, k, rounds=60):
    """Greedy, then swap topics in and out while it keeps helping.

    Greedy alone measured barely better than ranking topics by popularity, and
    at six topics it was worse. The reason is that it cannot revise: it takes
    the biggest immediate gain, which early on is a broad topic that unlocks
    many easy questions, and then cannot give it back when a cheaper pair would
    have covered more between them.

    Hill climbing fixes exactly that. It tries replacing each chosen topic with
    each unchosen one and keeps any swap that raises coverage, so an early
    commitment is no longer permanent. It is still not guaranteed optimal, but
    it recovers most of what myopia costs.
    """
    universe = sorted({t for i in items for t in i["topics"]})
    k = min(k, len(universe))
    chosen, _ = greedy(items, k)
    chosen = list(chosen[:k])
    # greedy can stop early when nothing adds coverage; fill the rest
    for t in universe:
        if len(chosen) >= k:
            break
        if t not in chosen:
            chosen.append(t)

    best = coverage_of(items, chosen)
    for _ in range(rounds):
        improved = False
        for out in list(chosen):
            for cand in universe:
                if cand in chosen:
                    continue
                trial = [c for c in chosen if c != out] + [cand]
                cov = coverage_of(items, trial)
                if cov > best + 1e-12:
                    chosen, best, improved = trial, cov, True
        if not improved:
            break
    return chosen, best


def by_frequency(items, k):
    """The baseline every prep site already gives you: the k topics that appear
    in the most questions, chosen without regard to whether they combine into
    anything answerable."""
    total = sum(i["weight"] for i in items) or 1.0
    score = {}
    for i in items:
        for t in i["topics"]:
            score[t] = score.get(t, 0.0) + i["weight"]
    top = [t for t, _ in sorted(score.items(), key=lambda kv: -kv[1])[:k]]
    cov = sum(i["weight"] for i in items if i["topics"] <= set(top)) / total
    return top, cov


def coverage_of(items, topics):
    total = sum(i["weight"] for i in items) or 1.0
    s = set(topics)
    return sum(i["weight"] for i in items if i["topics"] <= s) / total


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = _db.connect(os.path.join(here, "recce.db"))
    upcoming = ["Infosys", "TCS", "Accenture", "Wipro", "Cognizant", "Zoho"]
    items = demand(db, companies=upcoming, today="2026-09-27")
    print(f"{len(items)} distinct questions across {len(upcoming)} companies\n")

    chosen, curve = greedy(items)
    print(f"{'#':>3}  {'topic':<16}{'unlocks':>9}{'coverage':>10}")
    for n, row in enumerate(curve, 1):
        print(f"{n:>3}  {row['topic']:<16}{row['unlocked']:>9}{row['coverage']:>9.1%}")

    print(f"\n{'k':>3}{'frequency':>12}{'greedy':>10}{'+ local':>10}{'gain':>8}")
    for k in (3, 4, 5, 6, 8, 10):
        _, b = by_frequency(items, k)
        g = coverage_of(items, chosen[:k])
        o, cov = optimise(items, k)
        print(f"{k:>3}{b:>11.1%}{g:>10.1%}{cov:>10.1%}{(cov-b)*100:>+7.1f}")
    print()
    for k in (5, 8):
        o, cov = optimise(items, k)
        print(f"  {k} topics -> {cov:.1%}: {', '.join(sorted(o))}")

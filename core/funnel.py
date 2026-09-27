"""Where people actually get eliminated.

Every prep site lists questions. None of them tell you which round does the
killing, which is the thing that should decide how you spend your week: if the
wall is aptitude, no amount of DSA saves you.

Falls out of per-student-per-drive submissions for free, because each one
records the furthest round that student reached.
"""
import os, sqlite3, sys


def funnel(db, company, campus=None):
    q = """select d.id, d.held_on, d.role
             from drive d join company co on co.id = d.company_id
            where co.name = ?"""
    args = [company]
    if campus:
        q += " and d.campus = ?"
        args.append(campus)
    drives = db.execute(q + " order by d.held_on desc", args).fetchall()
    if not drives:
        return None

    ids = [d[0] for d in drives]
    marks = ",".join("?" * len(ids))
    rounds = db.execute(
        f"select seq, kind from round where drive_id in ({marks})"
        " group by seq, kind order by seq", ids).fetchall()

    total = db.execute(
        f"select count(*) from submission where drive_id in ({marks})", ids).fetchone()[0]

    steps, prev = [], None
    for seq, kind in rounds:
        reached = db.execute(
            f"select count(*) from submission"
            f" where drive_id in ({marks}) and reached_seq >= ?", ids + [seq]).fetchone()[0]
        drop = None if prev is None else (prev - reached) / prev if prev else 0
        steps.append({"seq": seq, "kind": kind, "reached": reached,
                      "drop_from_prev": drop})
        prev = reached

    offers = db.execute(
        f"select count(*) from submission where drive_id in ({marks}) and selected = 1",
        ids).fetchone()[0]

    # the round that eliminates the largest share of whoever entered it
    killer = max((s for s in steps if s["drop_from_prev"] is not None),
                 key=lambda s: s["drop_from_prev"], default=None)
    return {"company": company, "drives": len(drives), "sat": total,
            "steps": steps, "offers": offers,
            "offer_rate": offers / total if total else 0,
            "killer_round": killer}


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = _db.connect(os.path.join(here, "recce.db"))
    for co, in db.execute("select name from company order by name"):
        f = funnel(db, co)
        if not f:
            continue
        chain = " -> ".join(f"{s['kind']} {s['reached']}" for s in f["steps"])
        print(f"{co:<11} {f['sat']:>4} sat | {chain} | {f['offers']} offers "
              f"({f['offer_rate']:.0%})")
        k = f["killer_round"]
        if k:
            print(f"{'':<11} killer round: {k['kind']} (round {k['seq']}), "
                  f"{k['drop_from_prev']:.0%} eliminated there")

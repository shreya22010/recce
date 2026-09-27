"""
The daily run.

A one-off search tool and something you open every morning are different
products. The difference is not the ranker, it is memory: the index has to know
what it saw yesterday so it can say what is new, and it has to know what you
already did so it never shows you the same job twice.

Everything here exists to answer two questions a search cannot:
    what appeared since I last looked?
    what have I already applied to?
"""
import json, os, sqlite3, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DB = os.path.join(HERE, "..", "jobs.db")


def migrate(db):
    """
    first_seen is the column that makes daily use work.

    seen_at already existed but it is overwritten on every crawl, so it records
    the last time a job was confirmed alive, not when it appeared. Freshness
    needs the opposite: the first time we ever saw it, written once and never
    touched again.
    """
    # The jobs index is always SQLite and always shipped with first_seen
    # present; on Postgres there is no jobs table here at all. Either way the
    # pragma is meaningless, so it is guarded rather than assumed.
    try:
        cols = {r[1] for r in db.execute("pragma table_info(jobs)")}
    except Exception:
        cols = {"first_seen"}
    if "first_seen" not in cols:
        db.execute("alter table jobs add column first_seen text")
        # everything already indexed predates tracking, so backfill it to its
        # last-seen date rather than pretending it all appeared today
        db.execute("update jobs set first_seen = seen_at where first_seen is null")

    db.executescript("""
      create table if not exists applied (
        url        text primary key,
        applied_at text not null,
        note       text
      );
      create table if not exists hidden (
        url        text primary key,
        hidden_at  text not null,
        reason     text
      );
      create table if not exists runs (
        id      integer primary key autoincrement,
        ran_at  text not null,
        found   int  not null default 0,
        added   int  not null default 0
      );
      create index if not exists jobs_fresh on jobs (first_seen desc);
    """)
    db.commit()


def last_run(db):
    r = db.execute("select ran_at from runs order by id desc limit 1").fetchone()
    return r[0] if r else None


def record_run(db, found, added):
    db.execute("insert into runs (ran_at, found, added) values (?,?,?)",
               (time.strftime("%Y-%m-%d %H:%M"), found, added))
    db.commit()


def whats_new(db, since=None):
    """Jobs first seen after the given moment. Defaults to the previous run."""
    since = since or last_run(db)
    if not since:
        return []
    db.row_factory = sqlite3.Row
    return [dict(r) for r in db.execute(
        "select * from jobs where in_india = 1 and first_seen > ? order by first_seen desc",
        (since,))]


def mark_applied(db, url, note=None):
    db.execute("insert or replace into applied (url, applied_at, note) values (?,?,?)",
               (url, time.strftime("%Y-%m-%d %H:%M"), note))
    db.commit()


def hide(db, url, reason=None):
    db.execute("insert or replace into hidden (url, hidden_at, reason) values (?,?,?)",
               (url, time.strftime("%Y-%m-%d %H:%M"), reason))
    db.commit()


def done_urls(db):
    """Anything already acted on. Showing these again is the fastest way to make
    a daily tool feel broken."""
    return {r[0] for r in db.execute("select url from applied")} | \
           {r[0] for r in db.execute("select url from hidden")}


def summary(db):
    q = lambda s: db.execute(s).fetchone()[0]
    prev = last_run(db)
    new = len(whats_new(db)) if prev else 0
    return {
        "indexed": q("select count(*) from jobs"),
        "india": q("select count(*) from jobs where in_india = 1"),
        "companies": q("select count(distinct company) from jobs"),
        "applied": q("select count(*) from applied"),
        "hidden": q("select count(*) from hidden"),
        "last_run": prev,
        "new_since": new,
    }


if __name__ == "__main__":
    db = sqlite3.connect(DB)
    migrate(db)
    s = summary(db)
    print(f"\n  indexed   {s['indexed']:>6}   ({s['india']} in India, {s['companies']} companies)")
    print(f"  applied   {s['applied']:>6}")
    print(f"  hidden    {s['hidden']:>6}")
    print(f"  last run  {s['last_run'] or 'never'}")
    if s["last_run"]:
        print(f"  new since {s['new_since']:>6}")

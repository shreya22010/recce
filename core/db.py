"""One database interface, SQLite on a laptop and Postgres on a host.

SQLite is the right choice while building: no server, the file is the database,
and it is trivially inspectable. It is the wrong choice deployed, because the
free hosts hand you an ephemeral disk and every student submission and generated
package disappears on the next restart.

Rather than rewrite seventy-odd queries, this translates the handful of places
the two dialects differ. The application code keeps writing SQLite-flavoured SQL
with ? placeholders and keeps calling .lastrowid, and this makes both work.

Set DATABASE_URL to a postgres:// or postgresql:// URL to switch. Without it,
nothing changes and the local file is used exactly as before.
"""
import os
import re
import sqlite3

def _url():
    """Read the environment when asked, not when imported.

    Read at import time this silently chose SQLite whenever the module happened
    to be imported before the .env file was loaded — which is exactly what
    happened, so a run that looked like it was exercising Postgres was writing
    to the local file and reporting success.
    """
    return os.environ.get("DATABASE_URL", "").strip()


def is_pg():
    return _url().startswith(("postgres://", "postgresql://"))


class _Lazy:
    """So `db.DATABASE_URL` and `db.IS_PG` keep working as attributes."""

    def __getattr__(self, name):
        if name == "DATABASE_URL":
            return _url()
        if name == "IS_PG":
            return is_pg()
        raise AttributeError(name)


def __getattr__(name):
    if name == "DATABASE_URL":
        return _url()
    if name == "IS_PG":
        return is_pg()
    raise AttributeError(name)

# ---------------------------------------------------------------- SQL ----

# Differences that actually appear in this codebase. Deliberately a short,
# readable list rather than a general translator: a partial general translator
# is far more dangerous than an explicit one, because it fails silently on the
# case nobody thought about.
_SUBS = [
    (re.compile(r"\binsert or ignore\b", re.I), "insert"),
    (re.compile(r"\binsert or replace\b", re.I), "insert"),
    (re.compile(r"datetime\('now'\)", re.I), "now()"),
    (re.compile(r"\bgroup_concat\(distinct ([^)]+)\)", re.I),
     r"string_agg(distinct \1, ',')"),
    (re.compile(r"\bgroup_concat\(([^)]+)\)", re.I), r"string_agg(\1, ',')"),
    (re.compile(r"\bifnull\(", re.I), "coalesce("),
    (re.compile(r"\bpragma [^;]+;?", re.I), ""),
]

_IGNORE_TAIL = re.compile(
    r"^\s*insert\s+into\s+([a-z_]+)\s*\(([^)]*)\)", re.I)


def translate(sql, ignore_conflicts=False):
    """SQLite-flavoured SQL to Postgres.

    The % escaping is not cosmetic. psycopg reads % as the start of a
    placeholder, so a LIKE pattern such as 'synthetic:%' makes it reject the
    whole statement. Literal percent signs have to be doubled, and that has to
    happen before ? becomes %s or the new placeholders get doubled too.
    """
    out = sql
    for pat, rep in _SUBS:
        out = pat.sub(rep, out)
    if "?" in out:
        out = out.replace("%", "%%").replace("?", "%s")
    if ignore_conflicts and "on conflict" not in out.lower():
        out = out.rstrip().rstrip(";") + " on conflict do nothing"
    return out


class _Cursor:
    """Wraps a Postgres cursor so it behaves like sqlite3's.

    sqlite3 lets you iterate the object returned by execute() and read
    .lastrowid off it; psycopg does neither, so both are provided here instead
    of changing every call site.
    """

    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall())


class PgConnection:
    def __init__(self, url):
        import psycopg
        self._conn = psycopg.connect(url, autocommit=False)

    def execute(self, sql, params=()):
        replace = bool(re.match(r"\s*insert or replace", sql, re.I))
        ignore = bool(re.match(r"\s*insert or ignore", sql, re.I))
        q = translate(sql, ignore_conflicts=ignore)

        if replace and "on conflict" not in q.lower():
            m = _IGNORE_TAIL.match(q)
            if m:
                cols = [c.strip() for c in m.group(2).split(",")]
                sets = ", ".join(f"{c} = excluded.{c}" for c in cols[1:])
                q = q.rstrip().rstrip(";") + (
                    f" on conflict ({cols[0]}) do update set {sets}" if sets
                    else " on conflict do nothing")

        cur = self._conn.cursor()
        # With no parameters, psycopg still scans for placeholders and rejects a
        # literal % in a LIKE pattern. Passing no argument at all skips that.
        if params:
            cur.execute(q, params)
        else:
            cur.execute(q)
        last = None
        if re.match(r"\s*insert", q, re.I):
            try:
                cur.execute("select lastval()")
                last = cur.fetchone()[0]
            except Exception:
                last = None
        return _Cursor(cur, last)

    def executescript(self, sql):
        """Apply the schema one statement at a time.

        Postgres aborts the whole transaction on the first error, so a single
        failing statement silently took every later CREATE with it — the schema
        looked applied and three tables were missing. Committing per statement
        means one failure costs one table, and it is reported rather than
        swallowed.
        """
        failures = []
        for stmt in _split(sql):
            ddl = pg_ddl(stmt)
            try:
                cur = self._conn.cursor()
                cur.execute(ddl)
                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                failures.append((" ".join(ddl.split())[:70], str(e)[:120]))
        if failures:
            import sys
            for head, err in failures:
                print(f"schema: {head} -> {err}", file=sys.stderr)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def _split(script):
    return [s.strip() for s in script.split(";") if s.strip()]


def pg_ddl(stmt):
    """Schema DDL for Postgres: autoincrement keys and timestamp defaults."""
    s = re.sub(r"\binteger primary key\b", "serial primary key", stmt, flags=re.I)
    s = re.sub(r"datetime\('now'\)", "now()", s, flags=re.I)
    # a column that references another table's serial must stay an integer
    s = re.sub(r"serial primary key references", "integer primary key references", s,
               flags=re.I)
    return s


def connect(sqlite_path):
    """A connection to whichever database is configured."""
    if is_pg():
        return PgConnection(_url())
    db = sqlite3.connect(sqlite_path)
    db.execute("pragma foreign_keys = on")
    return db


def init(sqlite_path, schema_sql):
    db = connect(sqlite_path)
    if is_pg():
        db.executescript(schema_sql)
    else:
        db.executescript(schema_sql)
        db.commit()
    return db

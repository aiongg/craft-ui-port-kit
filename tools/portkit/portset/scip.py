"""Read access to the SCIP sqlite indexes (`<work.scip>/fw.sqlite`, `app.sqlite`, built by tools/scip/scipdb.py).

Table `occ`: one row per occurrence with `name`, `qual` (the enclosing type or module), `path`, `line` (1-based),
`crate` and `def` (1 for a definition). Without an index the lookups return nothing and the callers go on.
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache

from .context import ctx


@lru_cache(maxsize=None)
def con(repo: str) -> sqlite3.Connection | None:
    db = ctx.scip_dir / f"{repo}.sqlite"
    if not db.exists():
        return None
    c = sqlite3.connect(db)
    c.execute("update occ set path=replace(path, char(92), '/') where path like '%' || char(92) || '%'")   # a database built on Windows
    c.execute("create index if not exists occ_qual on occ(qual)")   # framework definitions look methods up by type
    return c


@lru_cache(maxsize=None)
def defs(name: str, qual: str | None = None) -> list[tuple[str, int]]:
    """Framework library definitions of `name` (of `qual::name` when qual is given): (path, 1-based line)."""
    c = con("fw")
    if c is None:
        return []
    q = ("select path, line from occ where name=? and def=1 and path not like '%/tests/%' "
         "and path not like '%/examples/%' and path like 'crates/%'")
    args = [name]
    if qual is not None:
        q += " and qual=?"
        args.append(qual)
    return c.execute(q, args).fetchall()


@lru_cache(maxsize=None)
def member_defs(qual: str) -> list[tuple[str, int]]:
    """Framework library definitions whose qualifier is `qual` (a type's methods and fields)."""
    c = con("fw")
    if c is None:
        return []
    return c.execute("select path, line from occ where qual=? and def=1 and path like 'crates/%' "
                     "and path not like '%/tests/%' order by path, line", (qual,)).fetchall()

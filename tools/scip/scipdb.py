#!/usr/bin/env python3
"""scipdb: turn a rust-analyzer SCIP index into a small sqlite table of occurrences, and query it.

  scipdb.py build INDEX.scip DB.sqlite     one row per occurrence: name, qual (the enclosing item), path, line, def
  scipdb.py refs DB NAME [QUAL]            files and lines that reference NAME (optionally only QUAL::NAME)

name is the last identifier of the SCIP symbol's descriptors, qual the one before it (a type for methods, fields and
variants; a module for free items). Paths use `/` on every platform. Lines are 1-based. Local symbols (`local N`) are skipped.
"""
import sys as _sys
if _sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    _sys.exit(0)
import os, re, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scip_pb2

IDENT = re.compile(r"`[^`]+`|[A-Za-z_][A-Za-z0-9_]*")


def name_qual(symbol):
    if symbol.startswith("local "):
        return None
    parts = symbol.split(" ", 4)
    if len(parts) < 5:
        return None
    toks = [t.strip("`") for t in IDENT.findall(parts[4])]
    toks = [t for t in toks if t != "impl"]
    if not toks:
        return None
    return toks[-1], (toks[-2] if len(toks) > 1 else None), parts[2]


def build(index, db):
    idx = scip_pb2.Index()
    with open(index, "rb") as fh:
        idx.ParseFromString(fh.read())
    con = sqlite3.connect(db)
    con.execute("drop table if exists occ")
    con.execute("create table occ (name text, qual text, crate text, path text, line int, def int)")
    rows = []
    for doc in idx.documents:
        for o in doc.occurrences:
            nq = name_qual(o.symbol)
            if nq:
                rows.append((nq[0], nq[1], nq[2], doc.relative_path.replace("\\", "/"), o.range[0] + 1, o.symbol_roles & 1))
        if len(rows) > 200_000:
            con.executemany("insert into occ values (?,?,?,?,?,?)", rows); rows = []
    con.executemany("insert into occ values (?,?,?,?,?,?)", rows)
    con.execute("create index occ_name on occ(name)")
    con.commit()
    n = con.execute("select count(*), count(distinct path) from occ").fetchone()
    print(f"{db}: {n[0]} occurrences in {n[1]} files")


def refs(db, name, qual=None):
    con = sqlite3.connect(db)
    q = "select path, line from occ where name=? and def=0" + (" and qual=?" if qual else "")
    out = {}
    for p, l in con.execute(q, (name, qual) if qual else (name,)):
        out.setdefault(p, []).append(l)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3])
    else:
        for p, ls in sorted(refs(*sys.argv[2:]).items()):
            print(p, ",".join(map(str, sorted(set(ls)))))

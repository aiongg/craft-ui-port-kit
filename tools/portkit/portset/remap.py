"""`port-set remap`: move every framework line reference in the sheets and contract parts from the commit in
plan.linebase to the current framework writing base, then write that commit into plan.linebase.

Run it after every move of the framework writing base: after the last stub stage (process/04-contract-stubs.md), after
the stub refresh (process/05-plancheck-decide.md) and from tools/move-base.

A reference is `path:N`, `path:N-M`, `path:N, :M` (also backticked `:N` continuations after a full path in the same
cell) or a bare `name.rs:N` that resolves to one framework file (a sheet's own Files rows first, then a unique file
name). Only framework files that changed between the two commits are rewritten. A line inside a changed hunk goes to
the hunk's new start; lines after a hunk move by its size. App references are never touched: app line numbers refer to
app.writing_base, which remap does not move.
"""
from __future__ import annotations

import os
import re

from .bundle import continuations
from .context import ctx, git
from .sheet import PATH_RE, SUFFIX_RE, base_files
from .write import Outcome


def hunks(repo_dir, old: str, new: str, path: str) -> list[tuple[int, int, int, int]]:
    out = git(repo_dir, "diff", "-U0", "--no-renames", old, new, "--", path)
    return [tuple(int(x) if x else 1 for x in m.groups())
            for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", out, re.M)]


def map_line(hs, n: int) -> int:
    """Line n of the old file in the new one; a line inside a changed hunk goes to the hunk's new start."""
    delta = 0
    for a, b, c, d in hs:
        start = a if b else a + 1
        if n >= start + b:
            delta += d - b
        elif n >= start:
            return c if d else c + 1
        else:
            break
    return n + delta


def remap_text(text: str, mapper, own_repo: str | None = None) -> str:
    """Rewrite `path:N[-M][, N]` and bare `name.rs:N` references through mapper(path, n) (None leaves a ref alone)."""
    fw, app = base_files("fw"), base_files("app")
    own_files = set(re.findall(r"^\| `([^`]+)` \|", text, re.M))   # a sheet's Files rows resolve bare names first
    by_name = {}
    for f in fw:
        by_name.setdefault(os.path.basename(f), []).append(f)

    def fw_path(p):
        return p in fw and (p not in app or own_repo == "fw")

    def tail_sub(path, tail):
        return re.sub(r"(\d+)", lambda n: str(mapper(path, int(n.group(1))) or n.group(1)), tail)

    def full(m):
        path, tail = m.group(1), m.group(2)
        return path + tail_sub(path, tail) if tail and fw_path(path) else m.group(0)

    # continuations first: their spans are found on the unchanged text
    for path, (lo, hi) in reversed(continuations(text)):
        if fw_path(path):
            text = text[:lo] + tail_sub(path, text[lo:hi]) + text[hi:]
    text = PATH_RE.sub(full, text)

    def suffix(m):
        name = m.group(1)
        if name.startswith(("crates/", "apps/")):
            return m.group(0)
        pool = [p for p in own_files if p.endswith("/" + name) or p == name] or \
               [p for p in by_name.get(os.path.basename(name), []) if p.endswith("/" + name) or p == name]
        if len(pool) != 1 or not fw_path(pool[0]):
            return m.group(0)
        return name + tail_sub(pool[0], m.group(2))

    return SUFFIX_RE.sub(suffix, text)


def cmd_remap(a) -> Outcome:
    linebase = ctx.cfg.path("plan.linebase")
    if not linebase.exists() or not linebase.read_text().split():
        raise SystemExit(f"{linebase} is missing or empty: write the commit the line numbers refer to into it "
                         "(init-workspace writes plan.base there)")
    repo = ctx.repo_dir("fw")
    old = git(repo, "rev-parse", linebase.read_text().split()[0]).strip()
    new = git(repo, "rev-parse", ctx.base("fw")).strip()
    if old == new:
        print(f"line refs already at {new[:10]} ({ctx.base('fw')})")
        return Outcome(f"already at {new[:10]}", data={"files": 0, "from": old, "to": new})
    changed = set(git(repo, "diff", "--name-only", "--no-renames", old, new).splitlines())
    cache = {}

    def mapper(path, n):
        if path not in changed:
            return None
        if path not in cache:
            cache[path] = hunks(repo, old, new, path)
        return map_line(cache[path], n)

    rewritten = []
    for f in sorted(ctx.sheets.glob("*.md")) + sorted(ctx.parts.glob("*.md")):
        t = f.read_text()
        own = None
        if f.parent == ctx.sheets:
            own = "app" if re.search(r"^- Repo:\s*`?app\b", t, re.M) else "fw"
        u = remap_text(t, mapper, own)
        if u != t:
            rewritten.append(f.name)
            if not a.dry_run:
                f.write_text(u)
    if not a.dry_run:
        linebase.write_text(new + "\n")
    verb = "would rewrite" if a.dry_run else "rewrote"
    print(f"{verb} {len(rewritten)} files: framework line refs {old[:10]} -> {new[:10]}"
          + "".join(f"\n  {n}" for n in rewritten if a.dry_run))
    return Outcome(f"{verb} {len(rewritten)} files, {old[:10]} -> {new[:10]}",
                   data={"files": len(rewritten), "from": old, "to": new, "dry_run": a.dry_run})


def register(sub) -> None:
    s = sub.add_parser("remap", help="move framework line refs in sheets and contract parts to the writing base")
    s.add_argument("--dry-run", action="store_true", help="list the files it would rewrite; change nothing")
    s.set_defaults(func=cmd_remap, owns_state=False)

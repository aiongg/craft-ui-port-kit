"""The scripted self-check of a written set (check.md) and its rust-analyzer check (racheck.md).

check.md has a `rust-analyzer:` line (racheck's error count, or "not run"), an `## Errors` section (scripted errors,
then rust-analyzer's) and a `## Warnings` section, one item per paragraph, `none` when empty. Batch runners read
it: an item starting `untouched:` or `test not deleted:` gets an agent round; items starting
`compile error (rust-analyzer)` are cross-set errors that wait for the batch recheck.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from portkit import config

from . import scip
from .context import ctx, dependencies, git
from .sheet import Sheet, base_files, unquote

RA_PREFIX = "compile error (rust-analyzer)"
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def base_of(sheet: Sheet, repo: str) -> str:
    """The commit the set's tree in `repo` started from (<set dir>/base-<repo>, written by `port-set tree`)."""
    f = ctx.sets / sheet.id / f"base-{repo}"
    if not f.exists():
        raise SystemExit(f"{f} is missing: the set's {repo} tree was not made by `port-set tree`")
    return f.read_text().strip()


def touched(sheet: Sheet) -> set[str]:
    """Paths the set changed against its base commits, uncommitted and untracked files included."""
    changed = set()
    for repo in sheet.repos():
        tree = sheet.tree(repo)
        changed |= set(git(tree, "diff", "--name-only", base_of(sheet, repo)).splitlines())
        changed |= set(git(tree, "ls-files", "--others", "--exclude-standard").splitlines())
    return changed


def grep_trees(sheet: Sheet, *args, paths=None) -> str:
    """`git grep ARGS` over the set's trees (only `paths` when given); hits outside the set's repo are tagged."""
    out = []
    for repo in sheet.repos():
        tree = sheet.tree(repo)
        scope = None
        if paths is not None:
            scope = [p for p in paths if sheet.repo_of(p) == repo and (tree / p).exists()]
            if not scope:
                continue
        hits = git(tree, "grep", *args, *(["--", *scope] if scope else []), check=False).strip()
        if hits:
            out.append(hits if repo == sheet.repo else "\n".join(f"[{repo}] {h}" for h in hits.splitlines()))
    return "\n".join(out)


@lru_cache(maxsize=None)
def stub_changed() -> frozenset[str]:
    """Framework files the contract stubs changed since plan.base: a row there may already be done by a stub."""
    try:
        base = ctx.plan_base
    except config.ConfigError:
        return frozenset()
    return frozenset(git(ctx.repo_dir("fw"), "diff", "--name-only", "--no-renames", base, ctx.base("fw"),
                         check=False).splitlines())


def added_lines(sheet: Sheet, p: str, text: list[str]) -> list[int]:
    """1-based numbers of the lines of p the set added or changed (every line of a file new to git)."""
    repo = sheet.repo_of(p)
    tree = sheet.tree(repo)
    if git(tree, "ls-files", "--others", "--exclude-standard", "--", p).strip():
        return list(range(1, len(text) + 1))
    out, n = [], None
    for line in git(tree, "diff", "-U0", "--no-color", "--no-renames", base_of(sheet, repo), "--", p).splitlines():
        if m := HUNK.match(line):
            n = int(m.group(1))
        elif n is not None and line.startswith("+") and not line.startswith("+++"):
            out.append(n)
            n += 1
    return out


def under(p: str, dirs) -> bool:
    return any(p == d or p.startswith(d + "/") for d in dirs)


@lru_cache(maxsize=None)
def direct_deps(tree: Path, start: Path) -> frozenset[str]:
    """Crate idents the Cargo package holding `start` lists as its own dependencies."""
    import tomllib
    d = start
    while True:
        m = d / "Cargo.toml"
        if m.exists():
            try:
                man = tomllib.loads(m.read_text())
            except tomllib.TOMLDecodeError:
                man = {}
            if "package" in man:
                out = set()
                for name, spec in dependencies(man).items():
                    out.add(name.replace("-", "_"))
                    if isinstance(spec, dict) and spec.get("package"):
                        out.add(spec["package"].replace("-", "_"))
                return frozenset(out)
        if d == tree or d.parent == d:
            return frozenset()
        d = d.parent


def facade_errors(sheet: Sheet, p: str, text: list[str]) -> list[str]:
    """App code in app.facade_dirs reaches framework crates through the facade, unless its own package lists the
    crate as a direct dependency."""
    if sheet.repo_of(p) != "app" or not under(p, ctx.facade_dirs):
        return []
    tree = sheet.tree("app")
    direct = direct_deps(tree, (tree / p).parent)
    names = [i for i in ctx.facade_members if i not in direct]
    if not names:
        return []
    pat = re.compile(r"\b(" + "|".join(sorted(names, key=len, reverse=True)) + r")::")
    out = []
    for n, line in enumerate(text, 1):
        if m := pat.search(line):
            out.append(f"{p}:{n}: `{m.group(1)}` is a framework crate: {ctx.app_name} code reaches it through the "
                       f"`{ctx.facade}` facade (`{ctx.facade}::..`), not by crate name")
    return out


def lint_hits(p: str, text: list[str], lines: list[int]) -> tuple[list[str], list[str]]:
    """(errors, warnings) of the lints over the given lines."""
    errs, warns = [], []
    for lint in ctx.lints:
        pat = re.compile(lint["pattern"])
        for n in lines:
            if n <= len(text) and pat.search(text[n - 1]):
                (errs if lint["level"] == "error" else warns).append(f"{p}:{n}: {lint['why']}")
    return errs, warns


def plan_known(plan_text: str) -> list[str]:
    """`Type::item` names in PLAN notes that the framework index defines: guesses one lookup would have settled."""
    out, seen = [], set()
    for line in plan_text.splitlines():
        if "// PLAN:" not in line:
            continue
        for t, item in re.findall(r"\b([A-Z]\w+)::([a-z_]\w*)\b", line.split("// PLAN:", 1)[1]):
            if (t, item) in seen:
                continue
            seen.add((t, item))
            hits = scip.defs(item, t)
            if hits:
                out.append(f"`{t}::{item}` is defined at {hits[0][0]}:{hits[0][1]}")
    return out


def decision_misses(sheet: Sheet) -> list[str]:
    """Backticked new-looking names in decisions.md (Type::item, Type) that appear in none of the set's trees."""
    f = ctx.sets / sheet.id / "decisions.md"
    if not f.exists():
        return []
    names = []
    for line in f.read_text().splitlines():
        if not line.startswith("- "):
            continue
        for span in re.findall(r"`([^`\n]+)`", line):
            for m in re.finditer(r"\b([A-Z]\w{2,})(?:::([a-z_]\w{2,}|[A-Z]\w{2,}))?", span):
                names.append(m.group(2) or m.group(1))
    return [f"`{n}`" for n in dict.fromkeys(names) if not grep_trees(sheet, "-lw", n)]


def syntax_error(path: Path) -> str | None:
    if not shutil.which("rustfmt"):
        return None
    r = subprocess.run(["rustfmt", "--check", "--edition", ctx.edition, str(path)], capture_output=True, text=True)
    if r.returncode != 0 and "error" in r.stderr:   # --check: never rewrites the file
        return r.stderr.strip().splitlines()[0][:300]
    return None


def check(sheet: Sheet) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    changed = touched(sheet)
    globbed = set(sheet.deleted())
    stubbed = stub_changed()
    if not shutil.which("rustfmt"):
        warns.append("rustfmt is not on PATH: no syntax check")
    for p, act in sheet.files:
        if act in ("edit", "rewrite", "new") and p not in changed:
            if sheet.repo_of(p) == "fw" and p in stubbed:
                warns.append(f"untouched: {p} ({act}); the contract stubs edited it, so its row may be done already")
            else:
                errs.append(f"untouched: {p} ({act})")
        if act == "delete" and not any(c in p for c in "*?[") and sheet.fp(p).exists():
            errs.append(f"not deleted: {p}")
    for i in sheet.writes:
        hits = grep_trees(sheet, "-nF", f'todo!("{i}")')
        if hits:
            errs.append(f"stub left for {i}:\n{hits[:400]}")
    hits = grep_trees(sheet, "-nF", f"P3({sheet.id})")
    if hits:
        errs.append("P3 markers left:\n" + hits[:800])
    for p in sorted(changed):
        f = sheet.fp(p)
        if not (p.endswith(".rs") and f.exists()):
            continue
        if err := syntax_error(f):
            errs.append(f"syntax: {p}: {err}")
        text = f.read_text(errors="replace").splitlines()
        mods, cfgs = [], []
        for line in text:
            line = line.strip()
            if line.startswith("#[cfg"):
                cfgs.append(line)
            elif m := re.match(r"(?:pub(?:\([^)]*\))?\s+)?mod (\w+);", line):
                mods.append((m[1], frozenset(cfgs)))
            if not line.startswith("#["):
                cfgs = []
        # Declarations under different, both non-empty cfg gates are alternates (wasm vs native), not duplicates.
        dup = sorted({a for i, (a, ca) in enumerate(mods) for b, cb in mods[i + 1:]
                      if a == b and (ca == cb or not ca or not cb)})
        if dup:
            errs.append(f"duplicate mod declaration in {p}: {', '.join(dup)}")   # rust-analyzer does not report E0428
        e, w = lint_hits(p, text, added_lines(sheet, p, text))
        errs += e
        warns += w
        errs += facade_errors(sheet, p, text)
    plan = grep_trees(sheet, "-nF", "// PLAN:", paths=sorted(changed))
    if plan:
        warns.append("PLAN notes (plan errors the writer met):\n" + plan[:1500])
        known = plan_known(plan)
        if known:
            warns.append("PLAN notes naming items the framework already defines (read them, drop the guess):\n"
                         + "\n".join(known[:20]))
    pc_md = ctx.sets / sheet.id / "plancheck.md"
    if pc_md.exists() and re.search(r"hit your .{0,20}limit|usage limit", pc_md.read_text()):
        errs.append("plancheck.md was cut off by a usage limit: rerun the plan check")
    missing = decision_misses(sheet)
    if missing:
        warns.append("decisions.md names items that are nowhere in the set's trees (a decided item not written, or "
                     "another set's):\n" + "\n".join(missing[:25]))
    owned = sheet.owned()
    for row in sheet.tests:
        if len(row) < 3:
            continue
        f, name, verdict = unquote(row[0]), re.sub(r"\s*\(:\d+\)", "", unquote(row[1])), row[2].strip()
        path = next((p for p in owned if p.endswith(f)), f)
        fpath = sheet.fp(path)
        if not fpath.exists() or not re.match(r"^\w+$", name):
            continue
        present = re.search(rf"\bfn {re.escape(name)}\b", fpath.read_text())
        if verdict == "new" and not present:
            errs.append(f"test missing: {path} {name}")
        if verdict == "delete" and present:
            if path in owned:
                errs.append(f"test not deleted: {path} {name}")
            else:
                warns.append(f"test in another set's file, deleted by that file's owner: {path} {name}")
    for row in sheet.replaced:
        mech = row[0] if row else ""
        if not re.search(r"removed|\bgoes\b|deleted", mech):
            continue
        for name in re.findall(r"`([^`]+)`", mech):
            ident = re.split(r"::|\.", name.strip("()"))[-1]
            if not re.match(r"^[A-Za-z_]\w{3,}$", ident):
                continue
            hits = grep_trees(sheet, "-nw", ident, paths=sorted(owned - globbed))
            if hits:
                warns.append(f"removed name `{ident}` still in owned files:\n{hits[:400]}")
    return errs, warns


def write_check(sheet: Sheet, errs, warns, ra: list[str] | None) -> list[str]:
    """check.md: the scripted errors with rust-analyzer's (`ra`, None when no daemon ran) and the warnings. The
    `rust-analyzer:` line under the title always states racheck's count, or that it did not run."""
    out = ctx.set_dir(sheet.id) / "check.md"
    errs = list(errs) + list(ra or [])
    line = "rust-analyzer: not run (no daemon)" if ra is None else f"rust-analyzer: {len(ra)} errors (racheck.md)"
    out.write_text("# check\n\n" + line + "\n\n## Errors\n\n" + ("\n\n".join(errs) or "none") + "\n\n## Warnings\n\n"
                   + ("\n\n".join(warns) or "none") + "\n")
    print(f"check: {len(errs)} errors ({'racheck not run' if ra is None else f'{len(ra)} from racheck'}), "
          f"{len(warns)} warnings ({out})")
    return errs


def racheck_set(sheet: Sheet) -> list[str] | None:
    """rust-analyzer errors in the files the set committed, as check-error lines; writes racheck.md. None when a
    repo's daemon is not running (the caller goes on without it)."""
    tools = Path(__file__).resolve().parents[2]
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import racheck
    errs, warns, lines, t0 = [], [], [], time.time()
    mine = {p for row in sheet.replaced for p in re.findall(r"(?:crates|apps)/[\w./-]+\.rs", " ".join(row))}
    for repo in sheet.repos():
        tree = sheet.tree(repo)
        changed = sorted(f for f in set(git(tree, "diff", "--name-only", base_of(sheet, repo), "HEAD").splitlines())
                         if f.endswith(".rs"))
        also = sorted(p for p in mine - set(changed) if p in base_files(repo) and (tree / p).exists())
        r = racheck.query(ctx.cfg, repo, {"tree": str(tree), "changed": changed, "also": also})
        if r is None:
            print(f"racheck: daemon for {repo} died or is not running (restart: {tools}/racheck.py serve {repo})")
            return None
        if not r["ok"]:
            print(f"racheck {repo}: {r['error']}")
            return None
        for d in r["diagnostics"]:
            (errs if d["severity"] == "error" else warns).append((repo, d))
        lines.append(f"{repo}: {len(changed)} changed + {len(also)} also files, {r['seconds']} s")
    body = ["# racheck (rust-analyzer diagnostics; no cargo check, so no borrowck)", "", *lines, "",
            f"## Errors ({len(errs)})", ""]
    for key in dict.fromkeys((e[0], e[1]["path"]) for e in errs):
        items = [e for e in errs if (e[0], e[1]["path"]) == key]
        body.append(f"### {key[1]}" + (" (not changed by the set)" if items[0][1].get("also") else "")
                    + (f" [{key[0]}]" if key[0] != sheet.repo else ""))
        body += [f"- :{d['line']} {d.get('code') or ''} {d['message']}" for _, d in sorted(items, key=lambda e: e[1]["line"])]
        body.append("")
    body += [f"## Warnings: {len(warns)}", ""]
    out = ctx.set_dir(sheet.id) / "racheck.md"
    out.write_text("\n".join(body) + "\n")
    print(f"racheck: {len(errs)} errors, {len(warns)} warnings in {time.time() - t0:.1f} s ({out})")
    return [f"{RA_PREFIX}: {d['path']}:{d['line']} {d.get('code') or ''} {d['message']}" for _, d in errs]


def checks(sheet: Sheet) -> list[str]:
    """The scripted check plus rust-analyzer's errors when its daemons run; writes check.md. Returns the errors.
    Every writer of check.md goes through here, so its count always includes racheck's."""
    errs, warns = check(sheet)
    return write_check(sheet, errs, warns, racheck_set(sheet))


UNWRITTEN_PREFIXES = ("untouched:", "test missing:")


def unwritten(errs) -> list[str]:
    """Check errors that mean the set was not written: a planned row left untouched, or a new test that is not there."""
    return [e for e in errs if e.startswith(UNWRITTEN_PREFIXES)]


def scripted(errs: list[str]) -> list[str]:
    """The errors the writer itself must fix: everything except rust-analyzer's, which may name another set's items."""
    return [e for e in errs if not e.startswith(RA_PREFIX)]

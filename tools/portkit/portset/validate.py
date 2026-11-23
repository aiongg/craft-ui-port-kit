"""`port-set validate`: parse every sheet the way the writing commands do and report what they cannot place.

Problems (each stops a set from being written as planned): a sheet the parser rejects (no `Repo: fw|app`), no Files
rows, an unknown action, a path listed twice, an edit/rewrite/keep/delete of a path in neither repo, a contract id with
no contract row, a Tests verdict that is not keep/rewrite/move/delete/new, a `move` row whose
Reason does not start `to <path> <test fn>`, a set id whose area is not in port.toml's
[[areas]], a stories file in neither the Files table nor the tree. Warnings: head keys the sheet template has that the
sheet lacks. Without readable repos (example sheets checked on their own) the path checks are skipped and said so.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from portkit import config

from .audit import STORIES_KEY, stories_line
from .context import ctx
from .plan import expand_ids
from .sheet import ACTIONS, ID, Sheet, SheetError, base_files
from .write import Outcome

HEAD_KEYS = ("Contract items it writes", "Contract items and", "Map sections", "Waits on")
VERDICTS = ("keep", "rewrite", "move", "delete", "new")
MOVE_TARGET = re.compile(r"^\s*to\s+`?[\w./-]+\.rs`?(\s*\((fw|app)\))?\s+`?\w+")


def repos_readable() -> str | None:
    """None when both repos list their writing bases, else why not."""
    try:
        for r in ("fw", "app"):
            base_files(r)
    except (subprocess.CalledProcessError, config.ConfigError, OSError) as e:
        return str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    return None


def contract_ids(parts: Path) -> set[str]:
    ids = set()
    for part in parts.glob("*.md"):
        ids |= set(re.findall(rf"^\| ({ID}) \|", part.read_text(), re.M))
    return ids


def validate_sheet(s: Sheet, rows: set[str] | None, trees: bool) -> tuple[list[str], list[str]]:
    problems, warns = [], []
    for k in HEAD_KEYS:
        if not any(h.startswith(k) for h in s.head):
            warns.append(f"{s.id}: no `- {k}...:` head line")
    maps = s.head.get("Map sections", "").strip().strip(".").lower()
    if maps and maps != "none" and "Look reference" not in s.head:
        warns.append(f"{s.id}: no `- Look reference:` head line (write `none` for a set with no visible part)")
    if ctx.cfg.areas:
        try:
            ctx.cfg.area_of(s.id)
        except config.ConfigError as e:
            problems.append(f"{s.id}: {e}")
    if rows is not None:
        calls_key = next((k for k in s.head if k.startswith("Contract items and")), None)
        for i in sorted(expand_ids(s.head.get("Contract items it writes", "")) |
                        (expand_ids(s.head.get(calls_key, "")) if calls_key else set())):
            if i not in rows:
                problems.append(f"{s.id}: {i} has no contract row")
    if not s.files:
        problems.append(f"{s.id}: no Files rows")
    seen = set()
    for p, act in s.files:
        if p in seen:
            problems.append(f"{s.id}: {p}: listed twice")
        seen.add(p)
        if act not in ACTIONS:
            problems.append(f"{s.id}: {p}: unknown action {act!r} (one of {', '.join(ACTIONS)})")
            continue
        if not trees or any(c in p for c in "*?[") or p.endswith("/"):
            continue
        exists = p in base_files(s.repo_of(p))
        if act in ("edit", "rewrite", "keep", "delete") and not exists:
            problems.append(f"{s.id}: {act} {p}: in neither repo at its writing base")
    for r in s.tests:
        if len(r) < 3:
            continue
        v = r[2].strip().lower().split()[0].strip("`*.,;") if r[2].strip() else ""
        if v not in VERDICTS:
            problems.append(f"{s.id}: Tests row {r[1][:60]}: verdict {r[2][:30]!r} is not {', '.join(VERDICTS)}")
        elif v == "move" and not MOVE_TARGET.match(r[3] if len(r) > 3 else ""):
            problems.append(f"{s.id}: Tests row {r[1][:60]}: a `move` names its target first in the Reason cell: "
                            f"`to <path> <test fn>`")
    _, files = stories_line(s)
    owned = {p for p, _ in s.files}
    for f in sorted(files - owned):
        if not trees or f not in base_files(s.repo_of(f)):
            problems.append(f"{s.id}: {STORIES_KEY} names `{f}`, which is not in the Files table"
                            + ("" if trees else " (tree not read)"))
    return problems, warns


def cmd_validate(a) -> Outcome:
    sheets_dir = Path(a.sheets) if a.sheets else ctx.sheets
    parts = Path(a.parts) if a.parts else ctx.parts
    paths = sorted(sheets_dir.glob("*.md"))
    if not paths:
        raise SystemExit(f"no sheets in {sheets_dir}")
    why = repos_readable()
    trees = why is None
    rows = contract_ids(parts) if parts.is_dir() and any(parts.glob("*.md")) else None
    problems, warns, n_files, mixed = [], [], 0, []
    for f in paths:
        try:
            s = Sheet(f.stem, f)
        except SheetError as e:
            problems.append(f"{f.stem}: {e}")
            continue
        n_files += len(s.files)
        if trees and len(s.repos()) > 1:
            mixed.append(s.id)
        p, w = validate_sheet(s, rows, trees)
        problems += p
        warns += w
    print(f"{len(paths)} sheets, {n_files} file rows" + (f"; {len(mixed)} sets span both repos: {', '.join(mixed)}"
                                                       if mixed else ""))
    if not trees:
        print(f"path checks skipped: the repos are not readable ({why})")
    if rows is None:
        print(f"contract checks skipped: no contract parts in {parts}")
    print(f"{len(problems)} problems" + "".join(f"\n  {p}" for p in problems))
    if warns:
        print(f"{len(warns)} warnings" + "".join(f"\n  {w}" for w in warns))
    return Outcome(f"{len(paths)} sheets: {len(problems)} problems, {len(warns)} warnings", ok=not problems,
                   data={"sheets": len(paths), "problems": len(problems), "warnings": len(warns),
                         "path_checks": trees, "contract_checks": rows is not None})


def register(sub) -> None:
    s = sub.add_parser("validate", help="parse every sheet and report what the writing commands cannot place")
    s.add_argument("--sheets", metavar="DIR", help="sheets to check (default work.sheets)")
    s.add_argument("--parts", metavar="DIR", help="contract parts to check ids against (default work.parts)")
    s.set_defaults(func=cmd_validate, owns_state=False, fail_exit=True)

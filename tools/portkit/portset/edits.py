"""The edits format a one-shot writer answers in, and applying it to the set's trees.

Blocks (full text in bundle.FORMAT): `@@@ EDIT <path>` with SEARCH/REPLACE pairs, `@@@ NEW <path>` ... `@@@ END`,
`@@@ DELETE <path>`, and `@@@ BLOCKED` ... `@@@ END` (nothing is applied). Before the blocks, the moves in
<set dir>/moves.tsv run as `git mv` and the sheet's `delete` rows are removed.
"""
from __future__ import annotations

import re

from .context import ctx, git
from .sheet import Sheet

PREFIX = re.compile(r"^\s*\d+│ ?")
MARKUP = re.compile(r"^\s*</?(parameter|invoke|antml:\w+)\b[^>]*>\s*$")


def strip_prefix(text: str) -> str:
    return "\n".join(PREFIX.sub("", l) for l in text.split("\n"))


def parse_edits(text: str) -> list[tuple]:
    """[(kind, path, body)]: NEW body is the file text, EDIT body is (search, replace), DELETE body is None."""
    ops, cur = [], None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^@@@ (EDIT|NEW|DELETE) (\S+)\s*$", line)
        if m:
            kind, path = m.groups()
            if kind == "NEW":
                body = []
                i += 1
                while i < len(lines) and lines[i].strip() != "@@@ END":
                    body.append(lines[i])
                    i += 1
                ops.append(("NEW", path, "\n".join(body) + "\n"))
            elif kind == "DELETE":
                ops.append(("DELETE", path, None))
            else:
                cur = path
            i += 1
            continue
        if line.startswith("<<<<<<< SEARCH") and cur:
            search, replace, j = [], [], i + 1
            while j < len(lines) and lines[j] != "=======":
                search.append(lines[j])
                j += 1
            j += 1
            while j < len(lines) and not lines[j].startswith(">>>>>>> REPLACE"):
                replace.append(lines[j])
                j += 1
            # A model sometimes closes a block with tool-call markup; it is never file text.
            for part in (search, replace):
                while part and MARKUP.match(part[-1]):
                    part.pop()
            ops.append(("EDIT", cur, ("\n".join(search), "\n".join(replace))))
            i = j + 1
            continue
        i += 1
    return ops


def blocked_reason(text: str) -> str | None:
    m = re.search(r"^@@@ BLOCKED\s*\n(.*?)(?:^@@@ END|\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else None


def locate(text: str, search: str):
    """(offset, length) of the one place SEARCH matches, else None. Falls back to a line match that ignores trailing
    whitespace."""
    if search and text.count(search) == 1:
        return text.index(search), len(search)
    want = [l.rstrip() for l in search.split("\n")]
    while want and not want[-1]:
        want.pop()
    if not want:
        return None
    lines = text.split("\n")
    have = [l.rstrip() for l in lines]
    hits = [i for i in range(len(have) - len(want) + 1) if have[i:i + len(want)] == want]
    if len(hits) != 1:
        return None
    start = sum(len(l) + 1 for l in lines[:hits[0]])
    end = start + sum(len(l) + 1 for l in lines[hits[0]:hits[0] + len(want)]) - 1
    return start, end - start


def remove(sheet: Sheet, p: str) -> bool:
    tree = sheet.tree(sheet.repo_of(p))
    if (tree / p).exists():
        git(tree, "rm", "-q", "-f", p)
        return True
    return False


def moves(sheet: Sheet) -> list[tuple[str, str]]:
    """(from, to) pairs in <set dir>/moves.tsv: files moved with `git mv` before the blocks apply, so their kept lines
    stay byte for byte; the writer's EDIT blocks name the destination."""
    f = ctx.sets / sheet.id / "moves.tsv"
    return [tuple(l.split("\t")) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []


def apply_edits(sheet: Sheet, edits_text: str, also=()):
    """Apply the blocks to the set's trees. `also`: paths outside the Files table the edits may touch (files a review
    finding names). Returns (report lines, failure lines)."""
    owned = sheet.owned() | set(also)
    report, fails = [], []
    for src, dst in moves(sheet):
        tree = sheet.tree(sheet.repo_of(src))
        if (tree / src).exists() and not (tree / dst).exists():
            (tree / dst).parent.mkdir(parents=True, exist_ok=True)
            git(tree, "mv", src, dst)
            report.append(f"moved {src} -> {dst}")
    for p in sheet.deleted():
        if remove(sheet, p):
            report.append(f"deleted {p} (sheet)")
    for kind, path, body in parse_edits(edits_text):
        if path not in owned:
            fails.append(f"{kind} {path}: not in this set's Files table; skipped")
            continue
        f = sheet.fp(path)
        if kind == "DELETE":
            remove(sheet, path)
            report.append(f"deleted {path}")
        elif kind == "NEW":
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(strip_prefix(body) if PREFIX.match(body) else body)
            report.append(f"wrote {path}")
        else:
            if not f.exists():
                fails.append(f"EDIT {path}: file does not exist")
                continue
            search, replace = body
            text = f.read_text()
            if PREFIX.match(search):
                search, replace = strip_prefix(search), strip_prefix(replace)
            # A rerun of the same edits leaves blocks that are already applied alone.
            if replace.strip() and search not in replace and replace in text and not locate(text, search):
                report.append(f"already applied: {path}")
                continue
            if replace.strip() and search in replace and replace != search and replace in text:
                report.append(f"already applied: {path}")   # an insertion around its anchor is already there
                continue
            hit = locate(text, search)
            if not hit:
                n = text.count(search) if search else 0
                fails.append(f"EDIT {path}: SEARCH matched {n} places:\n{search[:600]}")
                continue
            at, ln = hit
            f.write_text(text[:at] + replace + text[at + ln:])
            report.append(f"edited {path}")
    return report, fails


def write_apply(sheet: Sheet, report, fails) -> list[str]:
    out = ctx.set_dir(sheet.id) / "apply.md"
    out.write_text("# apply\n\n" + "\n".join(f"- {r}" for r in report) + "\n\n## Failed\n\n"
                   + ("\n\n".join(fails) or "none") + "\n")
    print(f"apply: {len(report)} done, {len(fails)} failed ({out})")
    return fails


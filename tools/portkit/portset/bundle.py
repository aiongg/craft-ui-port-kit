"""The writer bundle: one Markdown file with everything a one-shot writer needs.

Order: instructions (task, framework notes, code rules, output format), the writer's view of the sheet, what the plan
check and the decision pass settled, framework definitions (sets that write only app code), contract rows, the
current text of each file the set edits (whole, or outline plus the named parts for a big file), then excerpts of the
other places the sheet names, within pipeline.bundle.excerpt_budget.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from . import scip
from .context import REPOS, ctx
from .edits import moves
from .sheet import PATH_RE, SUFFIX_RE, Sheet, base_files, contract_rows, idents_of, spans_of, writer_sheet

OUTLINE_RE = re.compile(r"^\s*(?:#\[cfg\(test\)\]|(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe|extern \"C\")\s+)*"
                        r"(?:fn|struct|enum|trait|impl|mod|type|union|macro_rules!)\b)")
CONT_RE = re.compile(r"((?:crates|apps)/[\w./-]+\.rs)(?=[:`])|`(:\d+(?:-\d+)?)`")
CONTRACT_HEAD = ("| Id | Kind | Signature | Behaviour | Replaces | Writer | Also | Used by | Source | Resolution |\n"
                 "|---|---|---|---|---|---|---|---|---|---|")


def numbered(lines, start=1):
    return "\n".join(f"{i:>5}│ {l}" for i, l in enumerate(lines, start))


# ---------------------------------------------------------------- places the sheet names

def continuations(text):
    """(path, span) for each backticked `:N` that follows a full path in the same table cell or line."""
    out = []
    for seg in re.finditer(r"[^|\n]+", text):
        last = None
        for m in CONT_RE.finditer(seg.group(0)):
            if m.group(1):
                last = m.group(1)
            elif last:
                out.append((last, (seg.start() + m.start(2), seg.start() + m.end(2))))
    return out


def references(sheet: Sheet) -> dict[str, list[tuple[int, int]]]:
    """path -> line ranges named anywhere in the sheet, over every file of both repos at their writing bases."""
    files = set()
    for repo in REPOS:
        files |= base_files(repo)
    by_name = {}
    for f in files:
        by_name.setdefault(os.path.basename(f), []).append(f)
    owned = sheet.owned()
    refs = {}

    def add(path, lo, hi):
        refs.setdefault(path, []).append((lo, hi or lo))

    for m in PATH_RE.finditer(sheet.text):
        path, tail = m.group(1), m.group(2)
        if path not in files or not tail:
            continue
        for n in re.finditer(r"(\d+)(?:-(\d+))?", tail):
            add(path, int(n.group(1)), int(n.group(2)) if n.group(2) else None)
    for path, (lo, hi) in continuations(sheet.text):
        if path in files:
            n = re.match(r":(\d+)(?:-(\d+))?", sheet.text[lo:hi])
            add(path, int(n.group(1)), int(n.group(2)) if n.group(2) else None)
    # Partial paths (`ui-widgets/src/popover/drop_veil.rs:121-191`) and bare names (`area.rs:596`): resolved by a
    # unique suffix, the set's own files first.
    for m in SUFFIX_RE.finditer(sheet.text):
        name = m.group(1)
        if name.startswith(("crates/", "apps/")):
            continue
        pool = [p for p in owned if p.endswith("/" + name) or p == name] or \
               [p for p in by_name.get(os.path.basename(name), []) if p.endswith("/" + name) or p == name]
        if len(pool) == 1:
            for n in re.finditer(r"(\d+)(?:-(\d+))?", m.group(2)):
                add(pool[0], int(n.group(1)), int(n.group(2)) if n.group(2) else None)
    return refs


def excerpt_path(sheet: Sheet, p: str) -> Path | None:
    """Where to read a referenced file: the set's tree in the repo that has it, else a base checkout."""
    for repo in sheet.repos():
        if (sheet.tree(repo) / p).exists():
            return sheet.tree(repo) / p
    for repo in REPOS:
        if p in base_files(repo):
            for root in (ctx.ref_tree(repo), ctx.repo_dir(repo)):
                if (root / p).exists():
                    return root / p
    return None


def snippet(path: Path, ranges, context=None, cap=None) -> str | None:
    context = ctx.bundle("context") if context is None else context
    cap = ctx.bundle("snippet_cap") if cap is None else cap
    lines = path.read_text(errors="replace").splitlines()
    spans = []
    for lo, hi in sorted(ranges):
        lo, hi = max(1, lo - context), min(len(lines), hi + context)
        if lo > len(lines):
            continue
        if spans and lo <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    out, total = [], 0
    for lo, hi in spans:
        if total > cap:
            out.append("  … (more ranges cut; Read the file if needed)")
            break
        out.append(numbered(lines[lo - 1:hi], lo))
        out.append("  …")
        total += hi - lo + 1
    return "\n".join(out) if out else None


def outline(lines) -> str:
    """Item signature lines with their numbers: the map of a file the bundle shows only in parts."""
    return "\n".join(f"{i:>5}│ {l.rstrip()[:150]}" for i, l in enumerate(lines, 1) if OUTLINE_RE.match(l))


def marker_lines(sheet: Sheet, lines):
    """Lines the contract stubs left for this set: its P3 markers and the todo!() stubs of the items it writes."""
    keys = [f"P3({sheet.id})"] + [f'todo!("{i}' for i in sheet.writes]
    return [(i, i) for i, l in enumerate(lines, 1) if any(k in l for k in keys)]


def row_size(row) -> int:
    return sum(int(re.sub(r"\D", "", c) or 0) for c in row[2:4]) if len(row) > 3 else 0


def ident_lines(row, text):
    """Lines that name an item the Files row's description mentions (the first three per name)."""
    names = {n for sp in spans_of(row[-1] if len(row) > 2 else "") for n, _ in idents_of(sp)}
    if not names:
        return []
    pat = re.compile(r"\b(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")\b")
    seen, out = {}, []
    for i, l in enumerate(text, 1):
        for n in set(pat.findall(l)):
            if seen.get(n, 0) < 3:
                seen[n] = seen.get(n, 0) + 1
                out.append((i, i))
    return out


def file_section(sheet: Sheet, p: str, action: str | None, refs) -> str:
    path = sheet.fp(p)
    text = path.read_text(errors="replace").splitlines()
    row = sheet.rows.get(p, [])
    big, small = ctx.bundle("big"), ctx.bundle("small")
    whole = action in ("rewrite", "new") or len(text) <= small or (len(text) <= big and row_size(row) >= ctx.bundle("small_edit"))
    ranges = [] if whole else refs.get(p, []) + marker_lines(sheet, text) + ident_lines(row, text)
    if whole or (not ranges and len(text) <= big):
        return f"## File {p} (current text, {len(text)} lines)\n\n{numbered(text)}"
    parts = snippet(path, ranges, ctx.bundle("big_context"), ctx.bundle("big_cap")) if ranges else None
    return (f"## File {p} (shown in part: {len(text)} lines)\n\nYou get this file's outline and the parts your sheet "
            "names or the contract stubs marked for you. Read it (with a line range) for any other part you edit; "
            f"SEARCH text is still copied exactly from the file.\n\n### Outline\n\n{outline(text)}\n\n### Parts\n\n"
            f"{parts or '(none named)'}")


# ---------------------------------------------------------------- instructions

FORMAT = """\
## Output format

Reply with nothing but blocks, in this format. A script applies them; prose outside blocks is ignored.

@@@ EDIT <path>
<<<<<<< SEARCH
<exact lines of the file as they are now, enough to match one place only>
=======
<the lines that replace them>
>>>>>>> REPLACE
(more SEARCH/REPLACE pairs for the same file may follow)

@@@ NEW <path>
<the whole content of a new file, or of a file you rewrite completely>
@@@ END

@@@ DELETE <path>

@@@ BLOCKED
<why you cannot write this set as planned: the sheet contradicts the code, a signature cannot work, something essential is missing. Name the sheet line or contract id.>
@@@ END

Use BLOCKED instead of edit blocks when the set cannot be written as the sheet says without a design decision. Then write no other blocks. A small local mismatch is not a block: handle it with a `// PLAN:` note (below).

Rules for the blocks:
- SEARCH text is copied exactly from the file text in this bundle WITHOUT the line-number prefix (`  123│ `). It must match exactly one place in the file. Keep each SEARCH short (the lines that change plus one or two unchanged lines to make it unique).
- Never edit a path outside this set's Files table. Files the table marks `delete` are deleted by the script; don't repeat them.
- Use NEW for a whole-file rewrite (action `rewrite`, or a `new` file the contract stubs already created) instead of many EDIT blocks.
- Blocks are applied in order; a later SEARCH sees the text after earlier blocks.
"""


def moves_text(sheet: Sheet) -> str:
    m = moves(sheet)
    if not m:
        return ""
    lines = "\n".join(f"- `{a}` -> `{b}`" for a, b in m)
    return ("\nMoved files: the script runs `git mv` for these before your blocks apply. Write EDIT blocks against the "
            "destination path, matching the source file's text in the bundle; no NEW or DELETE block for either path.\n"
            + lines + "\n")


def task_text(sheet: Sheet) -> str:
    """What every writer of the set does: the pipeline's own rules, then the framework notes (rules/writer-notes.md)."""
    against = "" if "fw" in sheet.repos() else f"; for the framework, the code in {ctx.ref_tree('fw')}"
    return f"""\
What to do:
- Write complete code for every row of your Files table and every Tests row, following the sheet's Writer notes. Never leave stubs.
- The trees may hold markers left for this set: replace every `todo!("<id>")` of the items you write ({', '.join(sheet.writes) or 'none'}) with the real body, and every line marked `P3({sheet.id})` (including `#[allow(dead_code)] // P3({sheet.id})`) with the proper code; drop the marker.
- Delete the old code the sheet marks as going. Nothing old stays beside the new.
- Move every reader the "Replaced mechanisms" table assigns to this set.
- Every new public item gets a doc comment. Comments say why, never history ("now", "changed from").
- Tests: write the `new` and `rewrite` tests as the Tests table says (a `rewrite` keeps its name and file); write each `move` row's target test where its Reason names it, then remove the moved test; remove the `delete` ones. Each trial drives what its Tests row names (through the real input path, not a direct call) and asserts something that fails when that behaviour breaks.
- A rule (a validation, a name check, an index scheme) lives in one place; callers use it. For an index scheme over several items, work one example through by hand before writing it.
- If the sheet and the code disagree, or a contract signature cannot work, do what the sheet intends and add one line `// PLAN: <what was wrong>` at that place.
- Never fill a `todo!` or `P3(<set>)` body whose set is not yours, and never write a caller in a file outside your Files table; if you need one, leave a `// PLAN:` line naming the owner set.
- Every new test file `tests/it/<x>.rs` you write gets its `mod <x>;` line in its parent, written by you, whatever a marker in the parent says.
- A geometry rule applied at release (a snap, a nudge, a constraint) states the case where nothing moved: a click with no drag changes nothing.
- A rule that relies on an event for an edge case cites the code that emits it; a rule keyed on "the size changed" says which size changes the feature itself causes.

Framework notes:
{ctx.writer_notes}
{moves_text(sheet)}
You cannot compile. Read your code back once before you answer: types match the signatures in the files{against}; every name you call exists in the bundle or in your own edits.
"""


def fw_note(sheet: Sheet) -> str:
    """For a set that writes no framework code: where the framework source is, and how to code against sibling sets."""
    if "fw" in sheet.repos():
        return ""
    ref = ctx.ref_tree("fw")
    return (f"\nThe framework crates this code uses are not in this tree. Their current source, with the contract's "
            f"signatures, is in {ref} (read only). The bundle's section \"Framework definitions your sheet names\" holds "
            "the definitions and public methods of the framework items your sheet names: code against those. Read or "
            "Grep there only for an item that section lacks.\n"
            f"Other {ctx.app_name} sets are written beside yours, so their new items are not in your tree yet: code "
            "against the signatures your sheet and contract rows give for them (the \"Waits on\" sets). Where neither "
            "gives one, write the call you need and add `// PLAN: assumed <signature>` there. Answer BLOCKED only for an "
            "open design choice, never for a sibling signature you cannot see.\n")


def instructions(sheet: Sheet) -> str:
    return f"""\
# Writer: {sheet.id}

You write set `{sheet.id}` of the {ctx.app_name} port in one reply. This bundle holds everything you need: your sheet (the plan for your files), the contract rows you write and call, the current text of every file you edit, the code the sheet points at, and the code rules. If something you need is truly missing, you may Read a file or search with `git grep -n <pattern>` (a few times at most); prefer the bundle.

{task_text(sheet)}{fw_note(sheet)}
## Code rules

{ctx.code_rules}

{FORMAT}"""


# ---------------------------------------------------------------- framework definitions for app-only sets

DEF_CAP = 3               # a name defined in more framework places than this is too common to pick one
ITEM_CAP = 40             # lines per type definition
METHODS_CAP = 30          # method signatures per type
FW_DEFS_BUDGET = 60_000   # chars, for the items the text names
FW_DEFS_MORE = 40_000     # chars, for the types their definitions name


def candidates(text):
    """Names the text writes in code spans: `Type`, `Type::item`, `module::func`."""
    out = []
    for span in re.findall(r"`([^`\n]+)`", text):
        for m in re.finditer(r"\b([A-Z]\w*)(?:::([a-z_]\w*|[A-Z]\w*))?", span):
            out.append((m.group(1), m.group(2)))
        for m in re.finditer(r"\b([a-z_]\w*)::([a-z_]\w*)\b", span):
            out.append((None, m.group(2)))
    return list(dict.fromkeys(out))


@lru_cache(maxsize=None)
def fw_lines(path):
    f = ctx.ref_tree("fw") / path
    return f.read_text().splitlines() if f.exists() else None


@lru_cache(maxsize=None)
def item_text(path, line):
    """(kind, lines) of the item defined at path:line (1-based): its first doc lines and signature; a type's fields or
    variants; a trait's method signatures."""
    lines = fw_lines(path)
    if lines is None:
        return None
    i = line - 1
    if i >= len(lines):
        return None
    start = i
    while start > 0 and lines[start - 1].lstrip().startswith(("#[", "///")):
        start -= 1
    doc = [l for l in lines[start:i] if l.lstrip().startswith("///")][:2]
    head = lines[i]
    kind = re.search(r"\b(fn|struct|enum|trait|type|const|static|union|mod)\b", head)
    if not kind:
        return None
    kind = kind.group(1)
    out = doc + [head]
    if kind == "fn":
        j = i
        while "{" not in lines[j] and ";" not in lines[j] and j < i + 15 and j + 1 < len(lines):
            j += 1
            out.append(lines[j])
        out[-1] = re.sub(r"\s*\{.*$", " { … }", out[-1]) if "{" in out[-1] else out[-1]
        return kind, out
    if kind in ("struct", "enum", "trait", "union") and "{" in head and not head.rstrip().endswith("}"):
        depth = head.count("{") - head.count("}")
        j = i
        body = []
        while depth > 0 and j + 1 < len(lines):
            j += 1
            l = lines[j]
            depth += l.count("{") - l.count("}")
            s = l.strip()
            if s.startswith("//") and not s.startswith("///"):
                continue
            if kind == "trait" and depth > 1:
                continue
            body.append(l)
        if len(body) > ITEM_CAP:
            body = body[:ITEM_CAP] + [f"    // … {len(body) - ITEM_CAP} more lines: {path}:{line}"]
        if kind == "trait":
            body = [re.sub(r"\s*\{\s*$", ";", l) for l in body]
        return kind, out + body
    return kind, out


@lru_cache(maxsize=None)
def methods(name):
    """Public method signatures of a framework type."""
    out = []
    for path, line in scip.member_defs(name):
        ls = fw_lines(path)
        if ls is None or line - 1 >= len(ls):
            continue
        l = ls[line - 1]
        if re.search(r"\bpub(\(crate\))?\s+(const\s+|async\s+|unsafe\s+)*fn\b", l) and "pub(crate)" not in l and "pub(super)" not in l:
            sig = l.strip()
            j = line - 1
            while "{" not in sig and ";" not in sig and j < line + 10 and j + 1 < len(ls):
                j += 1
                sig += " " + ls[j].strip()
            out.append("    " + re.sub(r"\s*(\{.*|where .*)$", ";", sig))
    return out


def narrow(d, words):
    """Of several definitions, the ones in crates the text names (`<dir>` or `<facade>-<dir>` among its words)."""
    if len(d) <= 1:
        return d
    return [(p, l) for p, l in d if p.split("/")[1] in words or f"{ctx.facade}-{p.split('/')[1]}" in words]


def fw_defs(text, budget=FW_DEFS_BUDGET):
    """Definitions of the framework items the text names, then (budget left) of the types those definitions name."""
    picked, blocks = set(), []
    left = fw_defs_pass(text, budget, picked, blocks) + FW_DEFS_MORE
    seen = 0
    for _ in range(3):   # the types in fields, variants and signatures, level by level, while the budget lasts
        named = " ".join(f"`{n}`" for b in blocks[seen:]
                         for n in re.findall(r"\b[A-Z]\w+", re.split(r"\nimpl \S+ \{  // public methods",
                                                                     b.split("```rust", 1)[-1])[0]))
        seen = len(blocks)
        left = fw_defs_pass(named, left, picked, blocks, text, types_only=True)
        if len(blocks) == seen:
            break
    return blocks


def fw_defs_pass(text, budget, picked, blocks, scope=None, types_only=False):
    """One pass of fw_defs over the names in text; returns the budget left. scope: the text that narrows a name with
    several definitions (default: text)."""
    words = set(re.findall(r"[\w-]+", scope or text))
    for typ, member in candidates(text):
        targets = []
        if typ:
            d = scip.defs(typ)
            if 1 <= len(d) <= DEF_CAP and typ not in picked:
                targets.append((typ, d, True))
            if member and member[0].islower():
                dm = scip.defs(member, typ)
                if 1 <= len(dm) <= DEF_CAP and f"{typ}::{member}" not in picked:
                    targets.append((f"{typ}::{member}", dm, False))
        elif member:
            d = scip.defs(member)
            if len(d) == 1 and member not in picked:
                targets.append((member, d, False))
        for key, d, is_type in targets:
            picked.add(key)
            for path, line in narrow(d, words):
                it = item_text(path, line)
                if not it:
                    continue
                kind, lines = it
                if types_only and kind not in ("struct", "enum", "trait", "union", "type"):
                    continue
                if is_type and kind in ("struct", "enum", "trait", "union", "type"):
                    m = methods(key)
                    if m:
                        if len(m) > METHODS_CAP:
                            m = m[:METHODS_CAP] + [f"    // … {len(m) - METHODS_CAP} more"]
                        lines = lines + [f"impl {key} {{  // public methods"] + m + ["}"]
                b = f"### `{key}` — {path}:{line}\n\n```rust\n" + "\n".join(lines) + "\n```"
                if len(b) > budget:
                    return budget
                budget -= len(b)
                blocks.append(b)
    return budget


# ---------------------------------------------------------------- the bundle

def settled(sheet: Sheet) -> str:
    """What the plan check and the decision pass settled for this set: the STUB and RULE items of plancheck.md and the
    whole of decisions.md. The writer reads them beside the sheet."""
    od = ctx.sets / sheet.id
    out = []
    pc = od / "plancheck.md"
    if pc.exists():
        m = re.search(r"^@@@ ITEMS\s*\n(.*?)(?:^@@@ END|\Z)", pc.read_text(), re.M | re.S)
        items = [l for l in (m.group(1) if m else "").splitlines() if re.match(r"^- \[(STUB|RULE)\]", l)]
        if items:
            out.append("Found by the plan check (STUB: already in the tree; RULE: the option the rules pick):\n\n"
                       + "\n".join(items))
    dec = od / "decisions.md"
    if dec.exists() and dec.read_text().strip():
        out.append("Decided for this set (these override the sheet where they differ):\n\n" + dec.read_text().strip())
    return f"## Settled before writing ({sheet.id})\n\n" + "\n\n".join(out) if out else ""


def build_bundle(sheet: Sheet) -> str:
    parts = [instructions(sheet), f"## Your sheet ({sheet.id})\n\n{writer_sheet(sheet.text)}"]
    if s := settled(sheet):
        parts.append(s)
    rows = contract_rows(sheet.writes + sheet.calls)
    if fw_note(sheet) and scip.con("fw"):
        d = fw_defs(sheet.text + "\n" + "\n".join(rows))
        if d:
            parts.append(f"## Framework definitions your sheet names\n\nFrom {ctx.ref_tree('fw')} (read only): the "
                         "definition and public methods of each framework item your sheet and contract rows name.\n\n"
                         + "\n\n".join(d))
    if rows:
        parts.append(f"## Contract rows you write or call\n\n{CONTRACT_HEAD}\n" + "\n".join(rows))
    full = [p for p in sheet.in_bundle() if sheet.fp(p).exists()]
    missing = [p for p, a in sheet.files if a in ("edit", "rewrite", "keep") and not sheet.fp(p).exists()]
    refs = references(sheet)
    action = dict(sheet.files)
    for p in full:
        parts.append(file_section(sheet, p, action.get(p), refs))
    # Excerpts: the files the sheet names most often first, within the budget; the rest by location only.
    budget, rest = ctx.bundle("excerpt_budget"), []
    for p in sorted((p for p in refs if p not in full and refs[p]), key=lambda p: (-len(refs[p]), p)):
        where = excerpt_path(sheet, p)
        s = snippet(where, refs[p]) if where else None
        if not s:
            continue
        if len(s) > budget:
            rest.append(f"{p}:" + ",".join(f"{lo}" if lo == hi else f"{lo}-{hi}" for lo, hi in sorted(set(refs[p]))))
            continue
        budget -= len(s)
        parts.append(f"## Excerpt {p}\n\n{s}")
    if rest:
        parts.append("## More places your sheet names\n\nNot excerpted (bundle budget); Read them if you need them:\n\n"
                     + "\n".join(f"- {r}" for r in rest))
    if missing:
        parts.append("## Note\n\nFiles the sheet edits that do not exist in the tree: " + ", ".join(missing))
    return "\n\n".join(parts) + "\n"

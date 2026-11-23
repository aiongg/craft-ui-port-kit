#!/usr/bin/env python3
"""coverage.py: the plan's coverage check (process/03-plan.md, "Coverage"). Read only; no model call.

usage: coverage.py [--from sheets|plan] [--out FILE] [--tsv FILE] [--done FILE] [--config PORT.TOML]

Seven checks, each counted as gaps:
  1. Map sections: every entry section of every area map ([[areas]] `map`, default <work.maps>/<area>.md) is named
     by a writer set, or listed in --done (work already finished, one `<area> <section>` per line).
  2. Files: every .rs file under app.ui_dirs (in app.snapshot, else app.checkout at plan.app_base) has an action in
     an app set, or a plan line that says it gets no edit.
  3. Tests: every #[test] fn in those files has a verdict (keep, rewrite, move, delete) or its file is deleted.
  4. No path is in two writer sets (directory entries included).
  5. Settled decisions carried: every row of work.settled whose id is `S-...` or `L-...` and whose text names a set
     id has that id in the set's sheet or <work.sets>/<set>/decisions.md (with --from plan: in the set's section of
     work.ownership). One gap per row and set.
  6. No open-question marker in a set's sheet, decisions.md or ownership section, outside code spans: TBD, TODO,
     "open question", "undecided", "to be decided", "(open)", "??", or a table cell or line that is only an
     unfilled template field (`<lowercase words>`). One gap per line.
  7. Map citations: every `Symbol` (path:line) citation in an area map names a file that exists (in the framework
     snapshot or the app's UI files), a line inside it, and that line contains the symbol's last name segment. One
     gap per citation that fails. Citations of other forms (a bare `:236`, a symbol after the path) are not read.

Two sources for the sets (--from; default `sheets` when work.sheets holds sheets, else `plan`):
  sheets  the writer sheets (templates/sheet.md): each sheet's Repo, `Map sections` head line and Files table; test
          verdicts from its Tests table, matched by file and name. A `Map sections` value names sections of the
          set's own area; `<area> <ids>` names another area's, until the next `;`.
  plan    work.ownership before the sheets exist: `#### <set>` headings, a `- Repo <fw|app>` line, `- Map sections
          (<area>): <ids>` lines and file lines `  - \\`path\\` (<action>)`. Test verdicts come from the plan text
          (area plans, chunk plans, ownership, conflicts, contract, settled, sizing), matched by name, line number,
          position, wildcard, whole-file verdict or remainder line; each class is counted on its own.

Section ids are the first word of an area map heading (`## A1. Name`, `### G2 Name`, `### 3.1 Name`): capital
letters followed by digits, or dotted numbers. References expand ranges (`A1-A5`, `3.1-3.4`, `2-5`) and pairs
(`A1/A2`); `B1a` counts for `B1` when the map has no `B1a`. The report also lists references that name no heading,
the ids of infra rows (tables under a heading with "Infra") and the gap, hook and app-change ids of the maps and
their index (FG-, SG-, PC-, CH-, AC-, H-, G-) that no plan text names.

Writes the report (default <work.plan>/eval-coverage.md), prints a JSON summary, posts one `coverage` event.
Exit 0 when the seven checks have no gaps, 1 otherwise, 2 when an input is missing.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, track  # noqa: E402

DASH = "[–-]"
SEC_RE = re.compile(r"^(#{2,4})\s+([A-Z]{1,3}\d+[a-z]?w?|\d+(?:\.\d+)*)\.?\s+(\S.*)")
GAP_ID = re.compile(r"\b((?:FG|SG|PC|CH|AC|H|G)-\d+)\b")
FN_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)")


def die(msg: str):
    print(f"coverage.py: {msg}", file=sys.stderr)
    raise SystemExit(2)


def read(path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def cells_of(line: str):
    if not line.lstrip().startswith("|"):
        return None
    return [p.strip() for p in line.strip().strip("|").split("|")]


# ---------------------------------------------------------------- map sections

def sec_key(i: str):
    m = re.match(r"([A-Z]*)(\d+(?:\.\d+)*)", i)
    return m.group(1), tuple(int(x) for x in m.group(2).split("."))


def map_sections(path: Path):
    """Entry sections (id, title, line) and the other headings (title, line)."""
    entries, other = [], []
    for n, line in enumerate(read(path).splitlines(), 1):
        if not line.startswith("#"):
            continue
        m = SEC_RE.match(line)
        if m and m.group(1) != "#":
            entries.append((m.group(2), m.group(3).strip(), n))
        else:
            other.append((line.lstrip("#").strip(), n))
    return entries, other


def expand_ref(tok: str, ids: list[str]):
    """The section ids one reference token names."""
    tok = tok.strip().strip(".").strip("`").strip()
    m = re.match(rf"^([A-Z]*)(\d+(?:\.\d+)*)[a-z]?w?\s*{DASH}\s*([A-Z]*)(\d+(?:\.\d+)*)", tok)
    if m and m.group(3) in ("", m.group(1)):
        pre = m.group(1)
        lo = tuple(int(x) for x in m.group(2).split("."))
        hi = tuple(int(x) for x in m.group(4).split("."))
        if len(lo) == len(hi):
            return [i for i in ids if sec_key(i)[0] == pre and len(sec_key(i)[1]) == len(lo) and lo <= sec_key(i)[1] <= hi]
    m = re.match(r"^([A-Z]*\d+(?:\.\d+)*[a-z]?w?)/([A-Z]*\d+(?:\.\d+)*[a-z]?w?)\b", tok)
    if m:
        return [i for i in (m.group(1), m.group(2)) if i in ids]
    m = re.match(r"^([A-Z]*\d+(?:\.\d+)*)([a-z]?w?)\b", tok)
    if m:
        whole = m.group(1) + m.group(2)
        if whole in ids:
            return [whole]
        return [m.group(1)] if m.group(1) in ids else []
    return []


def split_refs(text: str) -> list[str]:
    text = re.sub(r"\([^()]*\)", "", text)
    text = re.sub(r"\([^()]*$", "", text)   # an unclosed parenthesis
    return [t for t in re.split(r",|;| and ", text) if t.strip()]


# ---------------------------------------------------------------- sets

def sets_from_ownership(path: Path) -> dict:
    sets, cur = {}, None
    for n, line in enumerate(read(path).splitlines(), 1):
        if line.startswith("## Dissolved"):
            cur = None
            continue
        m = re.match(r"^#### (\S+)", line)
        if m:
            cur = m.group(1)
            sets[cur] = {"repo": None, "files": [], "maps": [], "line": n, "src": path.name, "text": [line]}
            continue
        if cur is None:
            continue
        sets[cur]["text"].append(line)
        m = re.match(r"^- Repo:? `?(\w+)", line)
        if m:
            sets[cur]["repo"] = m.group(1)
            continue
        m = re.match(r"^- Map sections \(([\w-]+)\): (.*)", line)
        if m:
            sets[cur]["maps"].append((m.group(1), m.group(2), n))
            continue
        m = re.match(r"^\s+- `([^`]+)` \((\w+)\)", line)
        if m:
            sets[cur]["files"].append((m.group(1), m.group(2), n))
    for d in sets.values():
        d["text"] = "\n".join(d["text"])
    return sets


def sets_from_sheets(sheets, areas: list[str]) -> dict:
    sets = {}
    for s in sheets:
        own_area = re.sub(r"-w\d+[a-z]?$", "", s.id)
        lines = s.text.splitlines()
        files = []
        for p, act in s.files:
            n = next((k for k, l in enumerate(lines, 1) if f"`{p}`" in l), 0)
            files.append((p, act, n))
        maps = []
        v = s.head.get("Map sections", "")
        n = next((k for k, l in enumerate(lines, 1) if l.startswith("- Map sections")), 0)
        for seg in v.split(";"):
            seg = seg.strip()
            m = re.match(r"^([a-z][a-z0-9-]*)\s+(.*)$", seg)
            if m and m.group(1) in areas:
                maps.append((m.group(1), m.group(2), n))
            elif seg:
                maps.append((own_area, seg, n))
        sets[s.id] = {"repo": s.repo, "files": files, "maps": maps, "line": 0, "src": f"sheets/{s.id}.md",
                      "tests": s.tests, "text": s.text}
    return sets


# ---------------------------------------------------------------- settled decisions and open markers

SETTLED_ROW = re.compile(r"^\s*(?:\|\s*|[-*]\s+)(?:\*\*|`)?([SL]-[A-Za-z0-9]+)\b")
MARKER = re.compile(r"\bTBD\b|\bTODO\b|\bopen questions?\b|\bundecided\b|\bto be decided\b|\(open\)|\?\?", re.I)
PLACEHOLDER = re.compile(r"<[a-z][^<>]*>")
LIST_HEAD = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")


def _word(token: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])")


def settled_not_carried(sets: dict, settled: Path, sets_dir: Path) -> list[tuple[str, str, int]]:
    """(decision id, set, line in settled) for each settled row naming a set whose sheet and decisions.md lack the id."""
    if not settled.is_file():
        return []
    pats = {s: _word(s) for s in sets}
    out = []
    for n, line in enumerate(read(settled).splitlines(), 1):
        m = SETTLED_ROW.match(line)
        if not m:
            continue
        rid = _word(m.group(1))
        for s, pat in pats.items():
            if not pat.search(line):
                continue
            dec = sets_dir / s / "decisions.md"
            where = sets[s].get("text", "") + ("\n" + read(dec) if dec.is_file() else "")
            if not rid.search(where):
                out.append((m.group(1), s, n))
    return out


def open_markers(sets: dict, sets_dir: Path) -> list[tuple[str, str, int, str]]:
    """(set, file, line, text) for each line of a set's sheet text or decisions.md with an open-question marker."""
    out = []
    for s, d in sets.items():
        docs = [(d["src"], d.get("text", ""), d.get("line", 0))]
        dec = sets_dir / s / "decisions.md"
        if dec.is_file():
            docs.append((f"{s}/decisions.md", read(dec), 0))
        for src, text, first in docs:
            for k, line in enumerate(text.splitlines()):
                bare = re.sub(r"`[^`]*`", "", line)
                cells = [c.strip() for c in bare.strip().strip("|").split("|")] if bare.lstrip().startswith("|") else []
                only = LIST_HEAD.sub("", bare).strip().rstrip(".")
                if (MARKER.search(bare) or any(PLACEHOLDER.fullmatch(c) for c in cells)
                        or (not cells and PLACEHOLDER.fullmatch(only))):
                    out.append((s, src, first + k if first else k + 1, line.strip()[:160]))
    return out


# ---------------------------------------------------------------- app files and tests

def tests_in(text: str):
    """[(name, fn_line, attr_line)] for every #[test] fn, in file order."""
    out, pending = [], None
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if re.match(r"^#\[test\]", s):
            pending = n
            m = FN_RE.match(s[len("#[test]"):].strip())
            if m:
                out.append((m.group(1), n, n))
                pending = None
            continue
        if pending is not None:
            m = FN_RE.match(line)
            if m:
                out.append((m.group(1), n, pending))
                pending = None
            elif s and not (s.startswith("#[") or s.startswith("//") or s.startswith("#![")) and n - pending > 6:
                pending = None
    return out


def app_files(cfg, ui_dirs: list[str]) -> tuple[dict[str, str], str]:
    """{path relative to the app root: text} of every .rs file under the UI dirs, and where they were read."""
    snap = cfg.get("app.snapshot")
    if snap and Path(snap).is_dir():
        out = {}
        for d in ui_dirs:
            for p in sorted((Path(snap) / d).rglob("*.rs")):
                out[str(p.relative_to(snap))] = read(p)
        return out, f"the planning snapshot {snap}"
    base = cfg.get("plan.app_base")
    repo = cfg.get("app.checkout")
    if not base or not repo:
        die("no app.snapshot checkout, and plan.app_base or app.checkout is unset")
    names = [p for p in subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", base, "--", *ui_dirs],
                                       capture_output=True, text=True, check=True).stdout.splitlines() if p.endswith(".rs")]
    batch = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], input="".join(f"{base}:{p}\n" for p in names).encode(),
                           capture_output=True, check=True).stdout
    out, i = {}, 0
    for p in names:
        head_end = batch.index(b"\n", i)
        size = int(batch[i:head_end].split()[2])
        out[p] = batch[head_end + 1:head_end + 1 + size].decode("utf-8", "replace")
        i = head_end + 1 + size + 1
    return out, f"{repo} at {base}"


# ---------------------------------------------------------------- plan text

PATH_TOKEN = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.rs)\b")
BRACE_TOKEN = re.compile(r"((?:[\w.-]+/)*)\{([^{}]+)\}(\.rs)?")


def path_refs(line: str) -> list[str]:
    refs = []
    for m in BRACE_TOKEN.finditer(line):
        pre, body, ext = m.group(1), m.group(2), m.group(3) or ""
        for part in body.split(","):
            part = part.strip()
            if part and not part.endswith(".rs") and ext:
                part += ext
            if part.endswith(".rs"):
                refs.append(pre + part)
    refs += [m.group(1) for m in PATH_TOKEN.finditer(line)]
    return [re.sub(r"^(?:app:|app )", "", r) for r in refs]


class Resolver:
    """A plan path reference -> the app UI files it names: the exact path, or a unique path suffix."""

    def __init__(self, rels):
        self.rels = set(rels)
        self.by_base = defaultdict(list)
        for r in sorted(rels):
            self.by_base[r.rsplit("/", 1)[-1]].append(r)
        self.cache = {}

    def resolve(self, ref: str) -> list[str]:
        if ref not in self.cache:
            if ref in self.rels:
                self.cache[ref] = [ref]
            else:
                self.cache[ref] = [r for r in self.by_base.get(ref.rsplit("/", 1)[-1], []) if r.endswith("/" + ref)]
        return self.cache[ref]


VERDICT_WORD = re.compile(
    r"\b(keep|keeps|kept|rewrite|rewrites|rewritten|delete|deletes|deleted|"
    r"move|moves|moved|merge|merged|merges|fold|folds|folded|absorb|absorbs|absorbed|"
    r"drop|dropped|table row|row of|rows of|one table|into one)\b", re.I)
VERDICT_START = re.compile(
    r"^\**\s*(all\s+(\d+\s+)?)?(keep|kept|rewrite|rewritten|delete|deleted|move|moved|"
    r"merge|merged|drop|dropped|row of|rows of|one table|into one|table)\b", re.I)
CLASS_OF = [
    (re.compile(r"\b(keep|kept)\b", re.I), "keep"),
    (re.compile(r"\b(rewrite|rewritten|move|moved|merge|merged|row of|rows of|table|into one)\b", re.I), "rewrite"),
    (re.compile(r"\b(delete|deleted|drop|dropped)\b", re.I), "delete"),
]
NOT_HERE = re.compile(r"not this chunk|other chunk|other area|not here|counted (in|once)|"
                      r"no verdict|gave no verdict|outside the merged|is owned by", re.I)
NO_EDIT = re.compile(r"no edit|no set\b|belong to no set|unchanged|untouched|not touched|"
                     r"no change|unaffected|as is\b|stays\b|stay\b|\bkeep\b|kept|needs? no", re.I)


def classes(text: str) -> set[str]:
    return {c for rx, c in CLASS_OF if rx.search(text)}


def verdicts_from_sheets(sets: dict, test_index: dict, resolver: Resolver, owned_delete):
    """Per test: (class, evidence) from the sheets' Tests tables (file cell and backticked test name)."""
    status = {}
    for sid, d in sets.items():
        for r in d.get("tests", []):
            if len(r) < 3:
                continue
            v = r[2].strip().lower().split()[0].strip("`*.,;") if r[2].strip() else ""
            if v not in ("keep", "rewrite", "move", "delete"):
                continue
            files = [f for ref in path_refs(r[0]) for f in resolver.resolve(ref) if f in test_index]
            names = {re.sub(r"\(.*$", "", sp.split("::")[-1]).strip() for sp in re.findall(r"`([^`]+)`", r[1])}
            for f in files:
                for t in test_index[f]:
                    if t[0] in names:
                        status.setdefault((f, t[0], t[1]), ("name", f"{sid} ({v})"))
    result = {}
    for rel, tests in test_index.items():
        for t in tests:
            key = (rel, t[0], t[1])
            result[key] = status.get(key) or (("file deleted", owned_delete(rel)) if owned_delete(rel) else ("gap", ""))
    return result, {}


def verdicts_from_plan(plan_docs, plan_root: Path, test_index: dict, resolver: Resolver, owned_delete):
    """Per test: (class, evidence) from free plan text; the classes, strongest first: name, line, position,
    wildcard, file, remainder. Also returns the count-only lines per file."""
    names = defaultdict(set)
    for rel, tests in test_index.items():
        for nm, _, _ in tests:
            names[nm].add(rel)
    name_rx = re.compile(r"(?<![\w])([a-z_][a-z0-9_]{2,})(?![\w])")
    wild_rx = re.compile(r"`([a-z0-9_]*\*[a-z0-9_*]*)`")
    order = {"name": 0, "line": 1, "position": 2, "wildcard": 3, "file": 4, "remainder": 5}
    status, summaries = {}, defaultdict(list)

    def mark(rel, t, cls, ev):
        key = (rel, t[0], t[1])
        if key not in status or order[cls] < order[status[key][0]]:
            status[key] = (cls, ev)

    def uniq(line):
        out = []
        for r in path_refs(line):
            res = [f for f in resolver.resolve(r) if f in test_index]
            if len(res) == 1:
                out.append(res[0])
        return out

    remainders, complements = [], []
    REMAINDER = re.compile(r"\b((the other|the remaining|remaining)\s+\d+|the rest\b|all other\b|every other\b|the others\b)", re.I)
    COUNT_AFTER_VERDICT = re.compile(r"\b(keep|rewrite|delete|table)\s+(\d+)\b", re.I)

    for doc in plan_docs:
        short = str(Path(doc).relative_to(plan_root)) if str(doc).startswith(str(plan_root)) else Path(doc).name
        ctx, header = [], None
        lines = read(doc).splitlines()
        for ln, line in enumerate(lines, 1):
            if line.startswith("#"):
                ctx, header = uniq(line), None
                continue
            if not line.strip():
                header = None
                continue
            hc = cells_of(line)
            if hc is not None and ln < len(lines) and re.match(r"^\s*\|[-: |]+\|\s*$", lines[ln]):
                header = [c.lower() for c in hc]
                continue
            count_row = False
            if hc and header:   # count tables: "| file (13) | 13 | 0 | 0 |" under Keep/Rewrite/Delete headers
                cols = {k: i for i, h in enumerate(header) for k in ("keep", "rewrite", "delete") if h.startswith(k)}
                if len(cols) >= 2:
                    fr = [x for r in path_refs(hc[0]) for x in resolver.resolve(r) if x in test_index]
                    vals = {}
                    for k, i in cols.items():
                        m = re.match(r"^~?(\d+)", hc[i]) if i < len(hc) else None
                        vals[k] = int(m.group(1)) if m else None
                    if len(set(fr)) == 1 and all(v is not None for v in vals.values()):
                        f = fr[0]
                        count_row = True
                        complements.append((f, vals, f"{short}:{ln}"))
                        nz = [k for k, v in vals.items() if v]
                        if len(nz) == 1 and vals[nz[0]] >= len(test_index[f]):
                            for t in test_index[f]:
                                mark(f, t, "file", f"{short}:{ln}")
                        else:
                            summaries[f].append(f"{short}:{ln}: {line.strip()[:160]}")
            ev = f"{short}:{ln}"
            refs = uniq(line)   # only references that name one file set the scope
            cells = cells_of(line)
            if cells and all(re.fullmatch(r"[-: ]*", c) for c in cells):
                continue
            if cells:
                vidx = next((i for i, c in enumerate(cells) if i > 0 and VERDICT_START.match(c)), None)
                if vidx is None:
                    name_text = line if (VERDICT_WORD.search(line) or count_row) else ""
                else:
                    name_text = " | ".join(cells[:vidx + 1])
                    for c in cells[vidx + 1:]:   # names absorbed or replaced in later cells count too
                        for m in re.finditer(r"(absorbs?|replaces?|merges?|folds?)\b[^.;|]*", c, re.I):
                            name_text += " | " + m.group(0)
            else:
                name_text = line if VERDICT_WORD.search(line) else ""
            if refs:
                ctx = refs
            scope = refs or ctx
            if name_text:
                clean = re.sub(r"(covered by|covers|see|by) `?[a-z0-9_:]+`?", " ", name_text)
                for m in name_rx.finditer(clean):
                    nm = m.group(1)
                    if nm not in names or (len(nm) < 8 and "_" not in nm and f"`{nm}`" not in clean):
                        continue
                    files = names[nm]
                    pick = [f for f in files if f in scope] or (list(files) if len(files) == 1 else [])
                    tag = ""
                    if not pick and files:   # a name several files share, with no file in scope: all, flagged
                        pick, tag = list(files), " ambiguous"
                    for f in pick:
                        for t in test_index[f]:
                            if t[0] == nm:
                                mark(f, t, "name", ev + tag)
                for m in wild_rx.finditer(clean):
                    rx = re.compile("^" + m.group(1).replace("*", "[a-z0-9_]*") + "$")
                    for f in scope:
                        for t in test_index[f]:
                            if rx.match(t[0]):
                                mark(f, t, "wildcard", ev)
                for m in re.finditer(r"([a-z][a-z0-9_]{5,})(?:…|\.\.\.)", clean):   # truncated names
                    for f in scope:
                        for t in test_index[f]:
                            if t[0].startswith(m.group(1)):
                                mark(f, t, "wildcard", ev)
                if REMAINDER.search(clean) and not NOT_HERE.search(line) and scope and VERDICT_WORD.search(clean):
                    remainders += [(f, ev) for f in set(scope)]
                if len(set(scope)) == 1:
                    cnts = [(m.group(1).lower(), int(m.group(3))) for m in
                            re.finditer(r"\b(keep|rewrite|delete)\s+(about\s+|~)?(\d+)\b", line, re.I)]
                    if cnts:
                        complements.append((scope[0], {f"{k}{i}": n for i, (k, n) in enumerate(cnts)}, ev))
                bare = COUNT_AFTER_VERDICT.sub(" ", clean)
                bare = re.sub(r"#\d+|\(\d+\)|\d+\s*(%|pt|px|ms|bit|ppi|°)|\b\d+\.\d+\b|\b\d+\s*[x×]\s*\d+|[A-Za-z]-?\d+", " ", bare)
                for m in re.finditer(r"(?<![\w./:-])(\d{2,5})(?![\w./-])", bare):
                    n = int(m.group(1))
                    for f in scope:
                        for t in test_index[f]:
                            if t[2] - 1 <= n <= t[1] + 1:
                                mark(f, t, "line", ev)
                nums = []
                for m in re.finditer(r"([\w./-]+\.rs)?\s?:(\d{1,5}(?:/\d{1,5})*)", clean):
                    fs = [x for x in resolver.resolve(m.group(1)) if x in test_index] if m.group(1) else scope
                    nums += [(fs, int(n)) for n in m.group(2).split("/")]
                for m in re.finditer(r"(?<![\w:./])(\d{2,5}(?:/\d{2,5})+)(?![\w/])", clean):
                    nums += [(scope, int(n)) for n in m.group(1).split("/")]
                for fs, n in nums:
                    for f in fs:
                        for t in test_index[f]:
                            if t[2] - 1 <= n <= t[1] + 1:
                                mark(f, t, "line", ev)
                if cells:   # positions: "`file.rs` 1, 21, 22" or "same, 12, 13" in the first cell
                    first = cells[0]
                    m = re.match(r"^(?:`[^`]+\.rs`(?:\s+`[^`]+`)?|same),?\s+((?:\d+(?:[–-]\d+)?(?:\s*\([^)]*\))?(?:,\s*|;\s*|\s+and\s+|\s*$))+)", first)
                    pos_files = refs[:1] or (ctx[:1] if first.startswith("same") else [])
                    if m and pos_files:
                        f = pos_files[0]
                        for p in re.finditer(r"(\d+)(?:[–-](\d+))?", re.sub(r"\([^)]*\)", "", m.group(1))):
                            lo, hi = int(p.group(1)), int(p.group(2) or p.group(1))
                            for k in range(lo, hi + 1):
                                if 1 <= k <= len(test_index[f]):
                                    mark(f, test_index[f][k - 1], "position", ev)
            for f in set(refs):   # whole-file verdicts
                file_names = {t[0] for t in test_index[f]}
                if any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", line) for n in file_names) or NOT_HERE.search(line):
                    continue
                if cells:
                    vidx = next((i for i, c in enumerate(cells) if i > 0 and VERDICT_START.match(c)), None)
                    if vidx is None:
                        if VERDICT_WORD.search(line):
                            summaries[f].append(f"{ev}: {line.strip()[:160]}")
                        continue
                    if not any(f in [x for r in path_refs(c) for x in resolver.resolve(r)] for c in cells[:vidx]):
                        continue
                    vt = re.split(r"[;.(]| — ", cells[vidx])[0]
                    if len(classes(vt)) == 1 and not re.search(r"\d+\s*/\s*\d+|keep\s+\d+.*(delete|rewrite)\s+\d+", vt, re.I):
                        for t in test_index[f]:
                            mark(f, t, "file", ev)
                    else:
                        summaries[f].append(f"{ev}: {line.strip()[:160]}")
                    continue
                base = re.escape(f.rsplit("/", 1)[-1])
                m = re.search(rf"{base}`?(?:\s+inline)?(?:\s*\((?:\d+|all)[^)]*\))?[,:]?\s+(?:all\s+(?:\d+\s+)?)?"
                              r"(keep|kept|rewrite|rewritten|delete|deleted|delete all|all delete)\b", line, re.I)
                hit = re.search(rf"{base}`?\s*\(\d+[^)]*\),\s*all\s+(keep|rewrite|delete)", line, re.I) or m
                if hit:
                    if re.match(r"\s*\d+\s*,?\s*(keep|rewrite|delete)", line[hit.end():hit.end() + 40], re.I):
                        summaries[f].append(f"{ev}: {line.strip()[:160]}")
                        continue
                    for t in test_index[f]:
                        mark(f, t, "file", ev)
                    continue
                prs = path_refs(line)   # "`a.rs` (4), `b.rs` (8): keep 12": the verdict after the last file named
                last = max((line.rfind(r) for r in prs if line.rfind(r) >= 0), default=-1)
                tail = re.sub(r"^[\w./-]+\.rs`?\s*(\([^)]*\))?[\s,:*]*", "", line[last:] if last >= 0 else "")
                tm = re.match(r"^(all\s+(\d+\s+)?)?(keep|kept|rewrite|rewritten|delete|deleted)\b\s*(\d+)?", tail, re.I)
                if tm and len(classes(re.split(r"[;.(]", tail)[0])) == 1:
                    for t in test_index[f]:
                        mark(f, t, "file", ev)
                elif VERDICT_WORD.search(line) and re.search(r"\(\d+\)", line):
                    summaries[f].append(f"{ev}: {line.strip()[:160]}")

    for f, ev in remainders:
        for t in test_index[f]:
            if (f, t[0], t[1]) not in status:
                mark(f, t, "remainder", ev)
    for f, vals, ev in complements:
        left = [t for t in test_index[f] if (f, t[0], t[1]) not in status]
        if left and sum(1 for v in vals.values() if v == len(left)) == 1:
            for t in left:
                mark(f, t, "remainder", ev + " (count)")
    count_rx = re.compile(r"\b(keep|rewrite|delete|table)\s+(about\s+|~)?\d+|\.rs`?\s*\((\d+)[^)]*\)\s*[|:,]|\|\s*\d+\s*\|\s*\d+\s*\|", re.I)
    summaries = {f: [x for x in v if count_rx.search(x)] for f, v in summaries.items()}
    summaries = {f: v for f, v in summaries.items() if v}
    result = {}
    for rel, tests in test_index.items():
        for t in tests:
            key = (rel, t[0], t[1])
            result[key] = status.get(key) or (("file deleted", owned_delete(rel)) if owned_delete(rel) else ("gap", ""))
    return result, summaries


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="coverage.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="source", choices=("sheets", "plan"))
    ap.add_argument("--out")
    ap.add_argument("--tsv", help="also write one line per test: file, name, line, class, evidence")
    ap.add_argument("--done", help="sections finished outside the plan, one `<area> <section>` per line")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    try:
        cfg = config.load(a.config)
        ui_dirs = [d.strip("/") for d in cfg.require("app.ui_dirs")]
        plan_root = cfg.path("work.plan")
    except config.ConfigError as e:
        print(f"coverage.py: {e}", file=sys.stderr)
        return 2
    with track.recorded("coverage") as rec:
        summary, out_path = run(a, cfg, ui_dirs, plan_root)
        gaps = summary["gaps"]
        rec.result(f"{gaps} gaps (sections {summary['map_section_gaps']}, files {summary['files_unowned']}, tests "
                   f"{summary['test_gaps']}, paths in two sets {summary['paths_in_two_sets'] + summary['dir_overlaps']}, "
                   f"settled not carried {summary['settled_not_carried']}, open markers {summary['open_markers']})",
                   log=out_path, data=summary, ok=gaps == 0)
    print(json.dumps(summary))
    return 0 if gaps == 0 else 1


CITE = re.compile(r"`?([A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)`?\s*\(\s*`?((?:[\w.-]+/)*[\w.-]+\.rs):(\d+)(?:-(\d+))?")


def citation_drift(maps: dict, app_texts: dict[str, str], fw_root: Path | None) -> tuple[list[str], int]:
    """Citations `Symbol (path:line)` of the area maps that no longer hold: (one message per failure, citations read).
    A path resolves to the file whose path ends with it, in the framework snapshot or among the app UI files."""
    fw_files: dict[str, list[Path]] = defaultdict(list)
    if fw_root and fw_root.is_dir():
        for p in fw_root.rglob("*.rs"):
            rel = p.relative_to(fw_root).parts
            if "target" not in rel and ".git" not in rel:
                fw_files[p.name].append(p)
    texts: dict[str, list[str]] = {}

    def lines_of(key, loader):
        if key not in texts:
            texts[key] = loader().splitlines()
        return texts[key]

    def candidates(path):
        found = [(str(p), lambda p=p: read(p)) for p in fw_files.get(path.rsplit("/", 1)[-1], []) if str(p).endswith("/" + path)]
        found += [(rel, lambda t=t: t) for rel, t in app_texts.items() if rel == path or rel.endswith("/" + path)]
        return found

    out, n_read = [], 0
    for area, mp in sorted(maps.items()):
        for n, line in enumerate(read(mp).splitlines(), 1):
            for m in CITE.finditer(line):
                sym, path, lo = m.group(1).split("::")[-1], m.group(2), int(m.group(3))
                n_read += 1
                where = f"{mp.name}:{n}: `{m.group(1)}` ({path}:{lo})"
                cands = candidates(path)
                if not cands:
                    out.append(f"{where}: no such file in the framework snapshot or the app UI files")
                    continue
                short = [lines_of(k, ld) for k, ld in cands]
                if all(lo > len(ls) for ls in short):
                    out.append(f"{where}: the file has {len(short[0])} lines")
                elif not any(lo <= len(ls) and re.search(rf"\b{re.escape(sym)}\b", ls[lo - 1]) for ls in short):
                    ref = next(ls for ls in short if lo <= len(ls))
                    out.append(f"{where}: line {lo} reads `{ref[lo - 1].strip()[:80]}`")
    return out, n_read


def run(a, cfg, ui_dirs, plan_root):
    areas = [ar["id"] for ar in cfg.areas]
    maps = {ar["id"]: Path(ar["map"]) for ar in cfg.areas if Path(ar["map"]).exists()}
    sheets_dir = cfg.path("work.sheets")
    source = a.source or ("sheets" if sheets_dir.is_dir() and any(sheets_dir.glob("*.md")) else "plan")
    ownership = cfg.path("work.ownership")
    plan_docs = sorted((plan_root / "areas").glob("*.md")) + sorted((plan_root / "chunks").glob("*/plan.md"))
    plan_docs += [p for p in (ownership, plan_root / "conflicts.md", plan_root / "contract.md",
                              cfg.path("work.settled"), plan_root / "sizing.md") if p.exists()]
    if source == "sheets":
        from portkit.portset.context import ctx
        from portkit.portset.plan import all_sheets
        ctx.load(cfg)
        sheets = all_sheets()
        sets = sets_from_sheets(sheets, areas)
        plan_docs += [s.path for s in sheets]
    else:
        if not ownership.exists():
            die(f"no sheets in {sheets_dir} and no {ownership}")
        sets = sets_from_ownership(ownership)
    out_path = Path(a.out) if a.out else plan_root / "eval-coverage.md"
    report = []
    W = report.append

    # ---- 4. paths in two sets
    by_path = defaultdict(list)
    for s, d in sets.items():
        for p, act, n in d["files"]:
            by_path[(d["repo"], p)].append((s, act, n))
    dup_cross = {k: v for k, v in by_path.items() if len({s for s, _, _ in v}) > 1}
    dup_within = {k: v for k, v in by_path.items() if len(v) > 1 and len({s for s, _, _ in v}) == 1}
    dir_overlap = []
    for (repo, dp), v in by_path.items():
        if not dp.endswith("/"):
            continue
        for ds in {s for s, _, _ in v}:
            for (r2, p2), v2 in by_path.items():
                if r2 == repo and p2 != dp and p2.startswith(dp):
                    dir_overlap += [(repo, dp, ds, p2, s2, act2) for s2, act2, _ in v2 if s2 != ds]

    # ---- 1. map sections
    ids_by_area, other_heads, entries = {}, {}, {}
    for ar, mp in maps.items():
        e, o = map_sections(mp)
        entries[ar], other_heads[ar] = e, o
        ids_by_area[ar] = [i for i, _, _ in e]
    covered = defaultdict(lambda: defaultdict(list))
    dangling = []
    for s, d in sets.items():
        for area, text, n in d["maps"]:
            if area not in ids_by_area:
                # an area with no map (a hub area): bare ids resolve to the one area that has them
                for tok in split_refs(text):
                    hits = {ar: expand_ref(tok, ids) for ar, ids in ids_by_area.items()}
                    hits = {ar: g for ar, g in hits.items() if g}
                    if len(hits) == 1:
                        ar, got = next(iter(hits.items()))
                        for i in got:
                            covered[ar][i].append(s)
                    else:
                        dangling.append((s, d["src"], n, area, tok.strip()))
                continue
            for tok in split_refs(text):
                got = expand_ref(tok, ids_by_area[area])
                for i in got:
                    covered[area][i].append(s)
                if not got:
                    dangling.append((s, d["src"], n, area, tok.strip()))
    done = defaultdict(set)
    if a.done:
        for line in read(a.done).splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] in ids_by_area:
                for i in expand_ref(parts[1], ids_by_area[parts[0]]):
                    done[parts[0]].add(i)
    sec_rows, sec_gaps = [], []
    for ar in maps:
        for i, title, n in entries[ar]:
            if covered[ar].get(i):
                cls = "set"
            elif i in done[ar]:
                cls = "done"
            else:
                cls = "gap"
                sec_gaps.append((ar, i, title, n))
            sec_rows.append((ar, i, cls))
    plan_text = "\n".join(read(p) for p in plan_docs)
    infra_rows = []
    for ar, mp in maps.items():
        in_infra = False
        for n, line in enumerate(read(mp).splitlines(), 1):
            if line.startswith("#"):
                in_infra = "Infra" in line
                continue
            cells = cells_of(line)
            if in_infra and cells and re.fullmatch(r"[A-Z]{0,3}\d+(?:\.\d+)*[a-z]?", cells[0]):
                iid = cells[0]
                named = any(iid in [t.strip().split(" ")[0] for t in split_refs(text)]
                            for d in sets.values() for a2, text, _ in d["maps"] if a2 == ar)
                found = bool(re.search(rf"(?<![\w.]){re.escape(iid)}(?![\w])", plan_text))
                infra_rows.append((ar, iid, (cells[1] if len(cells) > 1 else "")[:70], n, named, found))
    gap_ids = []
    index = cfg.path("work.maps") / "README.md"
    for src in list(maps.values()) + ([index] if index.exists() else []):
        for gid in sorted(set(GAP_ID.findall(read(src)))):
            gap_ids.append((src.name, gid, bool(re.search(rf"\b{re.escape(gid)}\b", plan_text))))

    # ---- 2. files
    files, where = app_files(cfg, ui_dirs)
    rels = sorted(files)
    app_entries = [(p, act, s, n) for s, d in sets.items() if d["repo"] == "app" for p, act, n in d["files"]]

    def owner_of(path):
        hits = [e for e in app_entries if e[0] == path]
        return hits or [e for e in app_entries if e[0].endswith("/") and path.startswith(e[0])]

    def owned_delete(rel):
        for p, act, s, n in owner_of(rel):
            if act == "delete":
                return f"{sets[s]['src']}:{n} ({s})"
        return ""

    resolver = Resolver(rels)
    file_rows, unowned = [], []
    for rel in rels:
        hits = owner_of(rel)
        (file_rows.append((rel, hits)) if hits else unowned.append(rel))
    ref_index = defaultdict(list)
    for p in plan_docs:
        short = str(p.relative_to(plan_root)) if str(p).startswith(str(plan_root)) else p.name
        for n, line in enumerate(read(p).splitlines(), 1):
            for r in path_refs(line):
                res = resolver.resolve(r)
                if len(res) == 1:   # a bare `tests.rs` names no one file
                    ref_index[res[0]].append((short, n, line))

    def writes(rel, l):
        strong = r"no edit|belong to no set|unchanged|untouched|not this chunk|other chunk"
        cells = cells_of(l)
        if cells:
            v = next((c for c in cells[1:4] if VERDICT_START.match(c) or re.match(r"^(edit|new)\b", c)
                      or re.match(r"^one table\b", c, re.I)), None)
            if v is None:
                return False
            v = re.split(r"[;(]| — |: ", v)[0] if not re.match(r"^(keep|rewrite|delete)\s+\d", v) else v
            if re.search(strong, v, re.I):
                return False
            return bool(classes(v) & {"rewrite", "delete"}) or bool(re.match(r"^(edit|new)\b", v))
        near = " ".join(m.group(0) for m in re.finditer(rf"{re.escape(rel.rsplit('/', 1)[-1])}.{{0,100}}", l))
        return not re.search(strong, near, re.I) and bool(classes(near) & {"rewrite", "delete"})

    u_writer, u_reason, u_mentioned, u_silent = [], [], [], []
    for rel in unowned:
        mentions = ref_index.get(rel, [])
        needs = [m for m in mentions if writes(rel, m[2])]
        reason = [m for m in mentions if NO_EDIT.search(m[2])]
        if needs:
            u_writer.append((rel, needs[0]))
        elif reason:
            u_reason.append((rel, reason[0]))
        elif mentions:
            u_mentioned.append((rel, mentions[0]))
        else:
            u_silent.append(rel)

    # ---- 3. tests
    test_index = {rel: t for rel in rels if (t := tests_in(files[rel]))}
    if source == "sheets":
        result, summaries = verdicts_from_sheets(sets, test_index, resolver, owned_delete)
    else:
        result, summaries = verdicts_from_plan(plan_docs, plan_root, test_index, resolver, owned_delete)
    cnt = Counter(c for c, _ in result.values())
    gaps_by_file = defaultdict(list)
    for (r, nm, ln), (c, _) in result.items():
        if c == "gap":
            gaps_by_file[r].append((ln, nm))
    ambiguous = sum(1 for (c, ev) in result.values() if ev.endswith("ambiguous"))

    # ---- report
    sec_cnt = Counter(c for _, _, c in sec_rows)
    uncarried = settled_not_carried(sets, cfg.path("work.settled"), cfg.path("work.sets"))
    markers = open_markers(sets, cfg.path("work.sets"))
    fw_snap = cfg.get("framework.snapshot")
    drift, cites = citation_drift(maps, files, Path(fw_snap) if fw_snap else None)
    total_gaps = (len(drift) + sec_cnt["gap"] + len(u_writer) + len(u_mentioned) + len(u_silent) + cnt["gap"] + len(dup_cross)
                  + len(dir_overlap) + len(uncarried) + len(markers))
    W("# Plan coverage")
    W("")
    W(f"Script: `tools/coverage.py --from {source}` (read only). Sets from "
      + ("the writer sheets" if source == "sheets" else f"`{ownership.name}`") + f". App files: {where}. Plan text read: "
      + ", ".join(f"`{str(p.relative_to(plan_root)) if str(p).startswith(str(plan_root)) else p.name}`" for p in plan_docs[:12])
      + (f" and {len(plan_docs) - 12} more" if len(plan_docs) > 12 else "") + ".")
    W("")
    W("## Gap counts")
    W("")
    W("| Check | Units | Covered | Gaps |")
    W("|---|---|---|---|")
    W(f"| Map sections named by a writer set (or listed as done) | {len(sec_rows)} | {sec_cnt['set'] + sec_cnt['done']} | **{sec_cnt['gap']}** |")
    W(f"| `.rs` files under {', '.join(f'`{d}`' for d in ui_dirs)} with an action in an app set | {len(rels)} | {len(file_rows)} | "
      f"**{len(unowned)}** without: **{len(u_writer)}** with a plan line that rewrites or deletes their tests (no writer), "
      f"{len(u_reason)} with a keep or no-edit line, **{len(u_mentioned)}** named without a reason, **{len(u_silent)}** never named |")
    W(f"| `#[test]` functions with a verdict | {len(result)} | {len(result) - cnt['gap']} | **{cnt['gap']}** |")
    W(f"| Paths in two writer sets | {len(by_path)} paths | - | **{len(dup_cross)}** exact, **{len(dir_overlap)}** under another set's directory entry |")
    W(f"| Settled decisions that name a set, carried in its sheet or decisions.md | - | - | **{len(uncarried)}** |")
    W(f"| Lines with an open-question marker in a set's sheet or decisions.md | - | - | **{len(markers)}** |")
    W("")
    W(f"Gaps in total: {total_gaps} (files with a keep or no-edit line are not gaps; read the line to judge the reason).")
    W("")
    W("## 1. Map sections")
    W("")
    W(f"Entry sections: {len(sec_rows)} ({', '.join(f'{ar} {len(ids_by_area[ar])}' for ar in maps) or 'no area maps found'}). "
      f"Named by a set: {sec_cnt['set']}. Done outside the plan: {sec_cnt['done']}. Gaps: {sec_cnt['gap']}.")
    missing_maps = [ar for ar in areas if ar not in maps]
    if missing_maps:
        W("")
        W("Areas with no map file (their sets' bare section ids resolve to the one area that has them): " + ", ".join(missing_maps) + ".")
    W("")
    if sec_gaps:
        W("### Sections no writer set names")
        W("")
        W("| Area | Section | Map line |")
        W("|---|---|---|")
        for ar, i, title, n in sec_gaps:
            W(f"| {ar} | {i} {title[:70]} | {maps[ar].name}:{n} |")
        W("")
    W("### Section references that name no heading")
    W("")
    W("Tokens in the sets' map-section lists that match no entry heading of that area's map (task ids, infra row ids, hook ids, typos).")
    W("")
    W("| Set | Line | Area | Token |")
    W("|---|---|---|---|")
    for s, src, n, ar, t in dangling:
        W(f"| {s} | {src}:{n} | {ar} | {t[:60]} |")
    W("")
    miss_infra = [r for r in infra_rows if not r[5]]
    W("### Infra rows")
    W("")
    W(f"{len(infra_rows)} rows with ids in the maps' Infra tables. Named in a set's map sections: {sum(1 for r in infra_rows if r[4])}. "
      f"Id found anywhere in the plan text: {sum(1 for r in infra_rows if r[5])}. Not found: {len(miss_infra)}.")
    W("")
    if miss_infra:
        W("| Area | Row | Map line |")
        W("|---|---|---|")
        for ar, iid, txt, n, _, _ in miss_infra:
            W(f"| {ar} | {iid} {txt} | {maps[ar].name}:{n} |")
        W("")
    miss_gid = [g for g in gap_ids if not g[2]]
    W("### Gap, hook and app-change ids")
    W("")
    W(f"{len(gap_ids)} ids across the maps and their index; {len(gap_ids) - len(miss_gid)} appear in the plan text. Not found: "
      + (", ".join(f"{src} {g}" for src, g, _ in miss_gid) or "none") + ".")
    W("")
    W("### Other headings")
    W("")
    W("Headings that are not entry sections (reading guides, corrections, gap tables). Their work items are checked above by id where they have ids.")
    W("")
    for ar in maps:
        W(f"- {ar}: " + "; ".join(f"{t} (:{n})" for t, n in other_heads[ar]))
    W("")
    W("## 2. Files")
    W("")
    acts = Counter(h[0][1] for _, h in file_rows)
    W(f"{len(rels)} `.rs` files. With an action in an app set (exact path or under a directory entry): {len(file_rows)} "
      f"({', '.join(f'{k} {v}' for k, v in acts.most_common()) or 'none'}). Without: {len(unowned)}.")
    W("")

    def mention_row(rel, m):
        return f"| `{rel}` | {m[0]}:{m[1]} `{m[2].strip()[:110].replace('|', '/').replace('`', '')}` |"

    W(f"### Files without a set whose tests a plan line rewrites or deletes ({len(u_writer)})")
    W("")
    W("A plan line gives these files' tests a rewrite or delete verdict, but no set owns the file, so no one makes the change.")
    W("")
    W("| File | Line |")
    W("|---|---|")
    report.extend(mention_row(rel, m) for rel, m in u_writer)
    W("")
    W(f"### Files without a set, named in the plan without a no-edit reason ({len(u_mentioned)})")
    W("")
    W("| File | First mention |")
    W("|---|---|")
    report.extend(mention_row(rel, m) for rel, m in u_mentioned)
    W("")
    W(f"### Files without a set, never named in the plan ({len(u_silent)})")
    W("")
    by_dir = defaultdict(list)
    for rel in u_silent:
        by_dir[rel.rsplit("/", 1)[0] if "/" in rel else "(root)"].append(rel.rsplit("/", 1)[-1])
    for d in sorted(by_dir):
        W(f"- `{d}/`: " + ", ".join(sorted(by_dir[d])))
    W("")
    W(f"### Files without a set, with a keep or no-edit line ({len(u_reason)})")
    W("")
    W("The line was found by a phrase match (\"no edit\", \"unchanged\", \"keep\", ...); read it to judge the reason.")
    W("")
    W("| File | Line |")
    W("|---|---|")
    report.extend(mention_row(rel, m) for rel, m in u_reason)
    W("")
    W("## 3. Tests")
    W("")
    W(f"{len(result)} `#[test]` functions in {len(test_index)} files.")
    W("")
    W("| How the verdict was found | Tests |")
    W("|---|---|")
    labels = {"name": "by name" + (" in a sheet's Tests table" if source == "sheets" else ", on a line with a verdict"),
              "line": "by line number in a file-scoped line", "position": "by position (\"`file.rs` 1, 21, 22\")",
              "wildcard": "by a wildcard or truncated name", "file": "by a single-verdict line or count row for the whole file",
              "remainder": "by a remainder line (\"the other 59\", \"the rest\") in the file's scope",
              "file deleted": "only by its file's deletion", "gap": "**none (gap)**"}
    for k, label in labels.items():
        if k == "gap" or cnt.get(k) or source == "plan":
            W(f"| {label} | {cnt.get(k, 0)} |")
    W("")
    if source == "plan":
        W(f"Of the name matches, {ambiguous} credit a name that several files share where no file was in scope (every file with that name is credited).")
        W("")
    gap_files = sorted(gaps_by_file, key=lambda r: (-len(gaps_by_file[r]), r))
    W(f"Gaps fall in {len(gap_files)} files. Files whose plan line gives only counts (\"keep 12, delete 17\") are marked \"count only\".")
    W("")
    for r in gap_files:
        g = sorted(gaps_by_file[r])
        own = ", ".join(f"{s} ({act})" for _, act, s, _ in owner_of(r)) or "no set"
        W(f"#### `{r}` ({len(g)} of {len(test_index[r])}; {own})")
        W("")
        if summaries.get(r):
            W(f"- count only: {summaries[r][0]}")
        W("- " + ", ".join(f"`{nm}` :{ln}" for ln, nm in g))
        W("")
    W("## 4. Paths in two writer sets")
    W("")
    W(f"{len(by_path)} distinct (repo, path) entries in {len(sets)} sets. In two or more sets: {len(dup_cross)}. "
      f"Listed twice in one set: {len(dup_within)}. Under a directory entry of another set: {len(dir_overlap)}.")
    W("")
    for (repo, p), v in sorted(dup_cross.items()):
        W(f"- {repo} `{p}`: " + ", ".join(f"{s} ({act}, :{n})" for s, act, n in v))
    for repo, dp, ds, p2, s2, a2 in dir_overlap:
        W(f"- {repo} `{p2}` ({s2}, {a2}) is under `{dp}` ({ds})")
    if dup_within:
        W("")
        W("Listed twice in one set (no conflict): " + "; ".join(f"{v[0][0]} `{p}`" for (repo, p), v in sorted(dup_within.items())))
    W("")
    W("## 5. Settled decisions carried")
    W("")
    W(f"Rows of `{cfg.path('work.settled').name}` that name a set whose {'sheet' if source == 'sheets' else 'ownership section'} "
      f"and decisions.md do not cite the row's id: {len(uncarried)}.")
    W("")
    for rid, s, n in uncarried:
        W(f"- {rid} (settled :{n}) names {s}; carry it into {sets[s]['src']} or {s}/decisions.md, citing {rid}")
    W("")
    W("## 6. Open-question markers")
    W("")
    W(f"Lines with TBD, TODO, an open question, `??` or an unfilled template field: {len(markers)}.")
    W("")
    for s, src, n, line in markers:
        W(f"- {s} {src}:{n}: {line}")
    W("")
    W("## 7. Map citations")
    W("")
    W(f"`Symbol` (path:line) citations read in the area maps: {cites}. Failing: {len(drift)}.")
    W("")
    for d in drift:
        W(f"- {d}")
    W("")
    W("## Limits of the check")
    W("")
    if source == "plan":
        W("- Matching is textual. A test counts as judged when a plan line names it, its line number or position in a file-scoped "
          "row, a wildcard or truncated name, or a verdict for its whole file. The check does not judge whether the verdict is right.")
        W("- The weaker classes can credit a test no verdict meant: \"line\", \"remainder\" and \"position\". Their counts are in section 3.")
    else:
        W("- A test counts as judged when a Tests row names its file and its name with verdict keep, rewrite or delete. The check "
          "does not judge whether the verdict is right.")
    W("- A reference by bare file name resolves only when one app UI file has that name.")
    W("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    if a.tsv:
        with open(a.tsv, "w", encoding="utf-8") as f:
            for (r, nm, ln), (c, ev) in sorted(result.items()):
                f.write(f"{r}\t{nm}\t{ln}\t{c}\t{ev}\n")
    print(f"coverage: {out_path}", file=sys.stderr)
    summary = {
        "source": source, "gaps": total_gaps, "map_sections": len(sec_rows), "map_section_gaps": sec_cnt["gap"],
        "files": len(rels), "files_unowned": len(unowned), "files_unowned_need_writer": len(u_writer),
        "files_unowned_no_reason": len(u_mentioned) + len(u_silent), "files_unowned_never_named": len(u_silent),
        "tests": len(result), "test_gaps": cnt["gap"], "test_classes": dict(cnt),
        "test_gaps_count_only": sum(len(gaps_by_file[r]) for r in gaps_by_file if summaries.get(r)),
        "paths_in_two_sets": len(dup_cross), "dir_overlaps": len(dir_overlap), "dangling_section_refs": len(dangling),
        "infra_rows_not_in_plans": len(miss_infra), "gap_ids_not_in_plans": len(miss_gid),
        "settled_not_carried": len(uncarried), "open_markers": len(markers), "citations": cites,
        "citations_failing": len(drift),
    }
    return summary, out_path


if __name__ == "__main__":
    sys.exit(main())

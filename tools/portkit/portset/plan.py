"""The whole plan as port-set's plan-level commands read it: every sheet, the contract table, the writers of each
contract id, the owner of each file, and a read-only index of the two code trees at their writing bases.

audit, collect, validate and status use it. Nothing here writes a file.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from .context import OTHER, REPOS, ctx, git, toml_at
from .sheet import ID, RUST_KW, Sheet, base_files

SET_ID = re.compile(r"\b[a-z][a-z0-9-]*-w\d+[a-z]?\b")
TOK = re.compile(r"[A-Za-z_]\w*")


def sheet_ids(sheets_dir: Path | None = None) -> list[str]:
    return sorted(p.stem for p in (sheets_dir or ctx.sheets).glob("*.md"))


def all_sheets(sheets_dir: Path | None = None) -> list[Sheet]:
    d = sheets_dir or ctx.sheets
    return [Sheet(i, d / f"{i}.md") for i in sheet_ids(d)]


def area_of(set_id: str) -> str:
    """The area of a set id `<area>-w<n>[a-z]` (validate reports a set whose area is not in [[areas]])."""
    return re.sub(r"-w\d+[a-z]?$", "", set_id)


def expand_ids(text: str) -> set[str]:
    """Contract ids in a text, with ranges such as `cw.C16-C24` (or an en dash) expanded."""
    ids = set(re.findall(ID, text))
    for m in re.finditer(r"\b([a-z]{2}\.|[A-Z]{2}-)([A-Z]+)(\d+)\s*[–-]\s*(?:[A-Z]+)?(\d+)\b", text):
        a, b = int(m.group(3)), int(m.group(4))
        if a < b <= a + 200:
            ids |= {f"{m.group(1)}{m.group(2)}{i}" for i in range(a, b + 1)}
    return ids


# ---------------------------------------------------------------- contract

# Manifests that name a crate: the framework's under crates/; the app's anywhere up to three levels, its root included.
MANIFEST = {"fw": re.compile(r"crates/[^/]+(?:/[^/]+)?/Cargo\.toml"), "app": re.compile(r"(?:[^/]+/){0,3}Cargo\.toml")}
APP_HEADING = re.compile(r"\s*\(app\)\s*$")


@lru_cache(maxsize=None)
def crate_dirs(repo: str = "fw") -> dict[str, str]:
    """Package name -> crate directory (`""` for a root package), from a repo's Cargo manifests at its writing base."""
    out = {}
    for f in base_files(repo):
        if MANIFEST[repo].fullmatch(f):
            name = (toml_at(ctx.repo_dir(repo), ctx.base(repo), f).get("package") or {}).get("name")
            if name:
                out[name] = f.rsplit("/", 1)[0] if "/" in f else ""
    return out


def crate_dir(name: str, repo: str = "fw") -> str | None:
    name = name.strip().strip("`").split()[0] if name.strip() else ""
    if not name:
        return None
    dirs = crate_dirs(repo)
    if name in dirs:
        return dirs[name]
    for cand in (name, name.split("-", 1)[-1]):   # a heading may name the directory instead of the package
        if f"crates/{cand}/Cargo.toml" in base_files(repo):
            return f"crates/{cand}"
    return None


def heading_files(d: str, heading: str) -> list[str]:
    """Paths a `#### ` heading names: `a/b.rs`, then bare `c.rs` in the first one's directory, or a `dir/`."""
    toks = re.findall(r"`([^`]+)`", heading) or [heading]
    out, base = [], None
    for t in toks:
        t = t.strip()
        if not re.fullmatch(r"[\w./-]+", t):
            continue
        if "/" not in t and base is not None:
            t = base + "/" + t
        if base is None:
            base = t.rsplit("/", 1)[0] if "/" in t else ""
        out.append(t if not d or t.startswith(d + "/") else f"{d}/{t}")
    return out


@lru_cache(maxsize=None)
def contract_table() -> dict[str, dict]:
    """id -> row. A row (10 cells, templates/contract-part.md) gives kind, sig, beh, repl, writer, the files of its
    `####` heading, its crate dir and its repo: `app` under a `### <crate> (app)` heading, else `fw`. The first part
    that has an id wins."""
    rows = {}
    for part in sorted(ctx.parts.glob("*.md")):
        crate = fil = None
        repo = "fw"
        for line in part.read_text().splitlines():
            if line.startswith("### "):
                head = line[4:].strip()
                repo = "app" if APP_HEADING.search(head) else "fw"
                crate, fil = APP_HEADING.sub("", head).strip("`"), None
            elif line.startswith("#### "):
                fil = line[5:].strip()
            m = re.match(rf"^\| ({ID}) \|", line)
            if not m:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if len(cells) >= 10:
                d = crate_dir(crate or "", repo)
                rows.setdefault(cells[0], dict(kind=cells[1], sig=cells[2], beh=cells[3], repl=cells[4],
                                               writer=cells[5], used_by=cells[7],
                                               file=heading_files(d, fil) if d is not None and fil else [],
                                               crate_dir=d, repo=repo, part=part.name))
            elif len(cells) >= 5:
                # The 5-cell app interface row (Id | File | Signature | Behaviour | Writer) predates the app part;
                # parts of ports planned before it still carry such rows.
                rows.setdefault(cells[0], dict(kind="app", sig=cells[2], beh=cells[3], repl="", writer=cells[4],
                                               used_by="", file=[cells[1].strip("`")], crate_dir=None, repo="app",
                                               part=part.name))
    return rows


@lru_cache(maxsize=None)
def writers() -> dict[str, frozenset[str]]:
    """id -> the sets that write it: each sheet's `Contract items it writes` (ranges expanded) and the set ids in the
    contract row's Writer cell."""
    w: dict[str, set[str]] = {}
    ids = set(sheet_ids())
    for s in all_sheets():
        for i in expand_ids(s.head.get("Contract items it writes", "")):
            w.setdefault(i, set()).add(s.id)
    for cid, row in contract_table().items():
        for tok in SET_ID.findall(row.get("writer", "")):
            if tok in ids:
                w.setdefault(cid, set()).add(tok)
    return {k: frozenset(v) for k, v in w.items()}


def calls_of(s: Sheet) -> set[str]:
    """Contract ids a sheet calls (ranges expanded), minus the ones it writes."""
    key = next((k for k in s.head if k.startswith("Contract items and")), None)
    return (expand_ids(s.head.get(key, "")) if key else set()) - set(s.writes)


# ---------------------------------------------------------------- owners

class Owners:
    """(repo, path) -> owning sets over every sheet's Files table (exact paths, `dir/` entries and globs)."""

    def __init__(self, sheets: list[Sheet]):
        self.exact: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self.dirs, self.globs = [], []
        for s in sheets:
            for p, a in s.files:
                repo = s.repo_of(p)
                if any(c in p for c in "*?["):
                    self.globs.append((repo, p, s.id, a))
                elif p.endswith("/"):
                    self.dirs.append((repo, p, s.id, a))
                else:
                    self.exact.setdefault((repo, p), []).append((s.id, a))

    def rows(self, repo: str, p: str) -> list[tuple[str, str]]:
        """(set, action) for every Files row that covers the path."""
        o = list(self.exact.get((repo, p), []))
        o += [(sid, a) for r, d, sid, a in self.dirs if r == repo and p.startswith(d)]
        o += [(sid, a) for r, g, sid, a in self.globs if r == repo and fnmatch.fnmatch(p, g)]
        return o

    def of(self, repo: str, p: str) -> list[str]:
        return list(dict.fromkeys(sid for sid, _ in self.rows(repo, p)))


# ---------------------------------------------------------------- code trees

class Trees:
    """Read-only view of both repos at their writing bases: the racheck base checkouts when they exist, else the
    integration repos through `git show`. File texts are cached; `scan` builds a one-pass identifier index."""

    def __init__(self):
        self.files = {r: sorted(f for f in base_files(r) if f.endswith(".rs")) for r in REPOS}
        self._text, self._lines = {}, {}
        self.hits = {r: {} for r in REPOS}   # repo -> ident -> {path: [line numbers]}
        self.scanned = {r: set() for r in REPOS}
        self.roots = {}
        for r in REPOS:
            try:
                ref = ctx.ref_tree(r)
            except Exception:
                ref = None
            self.roots[r] = ref if ref and (ref / ".git").exists() else None

    def text(self, repo: str, p: str) -> str | None:
        k = (repo, p)
        if k not in self._text:
            root = self.roots[repo]
            if root is not None:
                try:
                    self._text[k] = (root / p).read_text(errors="replace")
                except OSError:
                    self._text[k] = None
            else:
                self._load(repo)
                self._text.setdefault(k, None)
        return self._text[k]

    def _load(self, repo: str) -> None:
        """Every .rs file of a repo at its writing base, read with one `git cat-file --batch`."""
        if ("loaded", repo) in self._text:
            return
        self._text[("loaded", repo)] = None
        names = self.files[repo]
        out = subprocess.run(["git", "-C", str(ctx.repo_dir(repo)), "cat-file", "--batch"],
                             input="".join(f"{ctx.base(repo)}:{p}\n" for p in names).encode(),
                             capture_output=True, check=True).stdout
        i = 0
        for p in names:
            end = out.index(b"\n", i)
            head = out[i:end].split()
            if len(head) < 3 or head[1] != b"blob":   # "<name> missing"
                i = end + 1
                continue
            size = int(head[2])
            self._text[(repo, p)] = out[end + 1:end + 1 + size].decode("utf-8", "replace")
            i = end + 1 + size + 1

    def lines(self, repo: str, p: str) -> list[str] | None:
        k = (repo, p)
        if k not in self._lines:
            t = self.text(repo, p)
            self._lines[k] = None if t is None else t.split("\n")
        return self._lines[k]

    def scan(self, wanted: set[str]) -> None:
        """Index every wanted identifier (whole word) over all .rs files of both trees, once per identifier."""
        for repo in REPOS:
            new = set(wanted) - self.scanned[repo]
            if not new:
                continue
            for p in self.files[repo]:
                t = self.text(repo, p)
                if not t:
                    continue
                present = set(TOK.findall(t)) & new
                if not present:
                    continue
                for n, line in enumerate(self.lines(repo, p), 1):
                    for tok in set(TOK.findall(line)) & present:
                        self.hits[repo].setdefault(tok, {}).setdefault(p, []).append(n)
            self.scanned[repo] |= new

    def where(self, ident: str) -> dict[tuple[str, str], list[int]]:
        """(repo, path) -> line numbers of an identifier scanned before, both trees."""
        return {(r, p): ls for r in REPOS for p, ls in self.hits[r].get(ident, {}).items()}

    @lru_cache(maxsize=None)
    def words(self, repo: str) -> frozenset[str]:
        """Every identifier of three or more characters in a repo's .rs files."""
        out = set()
        for p in self.files[repo]:
            out |= set(re.findall(r"[A-Za-z_]\w{2,}", self.text(repo, p) or ""))
        return frozenset(out)


ITEM = re.compile(r"\b(fn|struct|enum|trait|type|const|static|mod|union)\s+(\w+)")


def sig_items(sig: str) -> list[tuple[str, str]]:
    """(kind, name) of every Rust item a contract signature names, in order; `field` for `pub name: Type`."""
    out = []
    code = " ".join(re.findall(r"`([^`]+)`", sig)) or sig
    for m in ITEM.finditer(code):
        k, n = m.groups()
        if n in RUST_KW or n == "_":
            continue
        if k in ("struct", "enum", "trait", "union", "type") and not n[0].isupper():
            continue
        if k in ("const", "static") and not n.isupper():
            continue
        out.append((k, n))
    for m in re.finditer(r"\bpub(?:\([^)]*\))?\s+(\w+)\s*:\s*[A-Za-z&\[(<'_]", code):
        n = m.group(1)
        if n not in RUST_KW and len(n) > 1:
            out.append(("field", n))
    return out


def def_regex(kind: str, name: str) -> re.Pattern:
    n = re.escape(name)
    if kind == "field":
        return re.compile(rf"\b{n}\s*:")
    return re.compile(rf"\b{kind}\s+{n}\b")


def row_files(row: dict, trees: Trees) -> list[str]:
    """The files of its repo a contract row's heading names, directories expanded."""
    out = []
    for f in row["file"]:
        if f.endswith("/") or not f.endswith(".rs"):
            out += [x for x in trees.files[row["repo"]] if x.startswith(f.rstrip("/") + "/")]
        else:
            out.append(f)
    return out


def set_dir_text(set_id: str, name: str) -> str:
    p = ctx.sets / set_id / name
    return p.read_text() if p.exists() else ""


__all__ = ["OTHER", "REPOS", "SET_ID", "TOK", "Owners", "Trees", "all_sheets", "area_of", "calls_of", "contract_table",
           "crate_dir", "def_regex", "expand_ids", "git", "row_files", "set_dir_text", "sheet_ids", "sig_items",
           "writers"]

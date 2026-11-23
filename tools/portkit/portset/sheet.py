"""The writer sheet: the parser port-set and its checks read sheets with (format: templates/sheet.md).

Head keys port-set reads (lines `- Key: value` before the first table):
  Repo                       `fw` or `app`: the set's own repo (the first word of the value)
  Contract items it writes   contract ids (`<code>.<Kind><n>`) whose bodies the set writes
  Contract items and ...     contract ids the set calls (the key's wording after "and" is free)
Tables: `## Files` (Path | Action | Write | Delete | What changes), `## Replaced mechanisms ...`, `## Tests`.
A Files path that exists in both repos carries `(fw)` or `(app)` after its backticks.
"""
from __future__ import annotations

import glob as globmod
import re
from functools import lru_cache
from pathlib import Path

from .context import OTHER, ctx, git

# A contract id: `<code>.<Kind><n>` as the template writes it, or `<CODE>-<Kind><n>` as some plans write it.
ID = r"(?:[a-z]{2}\.|[A-Z]{2}-)[A-Z]+\d+[a-z]?"
ACTIONS = ("new", "edit", "rewrite", "delete", "keep")
# Workspace paths a sheet names, with optional line suffixes (`:12`, `:12-40`, `:12, :80`).
PATH_RE = re.compile(r"((?:crates|apps|tools|docs|migration)/[\w./-]+\.(?:rs|toml|md|svg|json))"
                     r"((?::\d+(?:-\d+)?)(?:,\s*:?\d+(?:-\d+)?)*)?")
SUFFIX_RE = re.compile(r"(?<![\w/.-])([\w./-]+\.rs)((?::\d+(?:-\d+)?)(?:,\s*:?\d+(?:-\d+)?)*)")
HEADER_CELLS = ("Path", "Mechanism (removed or changed)", "File", "To set (or \"unowned\")")

RUST_KW = {"pub", "fn", "struct", "enum", "trait", "impl", "type", "const", "static", "mod", "use", "crate", "self",
           "super", "mut", "let", "async", "unsafe", "dyn", "for", "where", "ref", "as", "in", "if", "else", "match"}
# Words too common to locate an item by: a backticked span naming only one of these says nothing.
STOP = set("""new default from into show state value name text size rect color frame data item items list path type kind
mode self true false none some ok err option result string vec box with get set add remove clear len iter map open close
paint draw build update apply field fields label title style theme input output event events action actions id ids key keys
index count flag flags bool f32 f64 u32 u64 usize i32 i64 str char impl trait struct enum test tests tool tools panel panels
dialog dialogs dock widget widgets canvas layer layers app main run call calls code file files line lines call mechanism
reader readers which that this when then than also same each every only like such other more most less kept keep keeps
gains gain unchanged signature removed renamed changed body bodies stays stay nothing none""".split())


class SheetError(SystemExit):
    pass


@lru_cache(maxsize=None)
def base_files(repo: str) -> frozenset[str]:
    """Every tracked path of a repo at its writing base."""
    return frozenset(git(ctx.repo_dir(repo), "ls-tree", "-r", "--name-only", ctx.base(repo)).splitlines())


def sheet_path(set_id: str) -> Path:
    return ctx.sheets / f"{set_id}.md"


class Sheet:
    def __init__(self, set_id: str, path: Path | None = None):
        self.id = set_id
        self.path = path or sheet_path(set_id)
        if not self.path.exists():
            raise SheetError(f"no sheet {self.path}")
        self.text = self.path.read_text()
        self.shared = False   # True: read the read-only base checkouts instead of the set's worktrees
        self.head = {m.group(1): m.group(2) for m in re.finditer(r"^- ([^:\n]+): (.*)$", self.text, re.M)}
        m = re.match(r"\s*`?(fw|app)\b", self.head.get("Repo", ""))
        if not m:
            raise SheetError(f"{self.path}: the head needs `- Repo: fw` or `- Repo: app`, got "
                             f"{self.head.get('Repo', '(none)')!r}")
        self.repo = m.group(1)
        self.writes = sorted(set(re.findall(ID, self.head.get("Contract items it writes", ""))))
        calls_key = next((k for k in self.head if k.startswith("Contract items and")), None)
        self.calls = sorted(set(re.findall(ID, self.head.get(calls_key, ""))) - set(self.writes)) if calls_key else []
        self.files, self.hint, self.rows = [], {}, {}
        for r in self.table("Files"):
            if len(r) < 2:
                continue
            p = unquote(r[0])
            self.rows[p] = r
            m = re.search(r"\((fw|app)\)", r[0])
            if m:
                self.hint[p] = m.group(1)
            self.files.append((p, r[1].strip()))
        self.replaced = self.table("Replaced mechanisms")
        self.tests = self.table("Tests")

    def table(self, heading: str) -> list[list[str]]:
        """Body rows of the first table under the `## <heading>` section (header and rule rows dropped)."""
        m = re.search(rf"^## {re.escape(heading)}.*?$(.*?)(?=^## |\Z)", self.text, re.M | re.S)
        rows = []
        for line in (m.group(1) if m else "").splitlines():
            if not line.startswith("|") or re.match(r"^\|[\s|:-]+\|$", line):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            if cells and cells[0] in HEADER_CELLS:
                continue
            rows.append(cells)
        return rows

    def repo_of(self, p: str) -> str:
        """The repo a path lives in: its `(fw)`/`(app)` tag, else the set's repo if the path is there, else the other
        repo if only that one has it, else (a new file) the set's repo."""
        if p in self.hint:
            return self.hint[p]
        if p in base_files(self.repo):
            return self.repo
        if p in base_files(OTHER[self.repo]):
            return OTHER[self.repo]
        return self.repo

    def repos(self) -> list[str]:
        """Repos the set writes, its own first."""
        return sorted({self.repo} | {self.repo_of(p) for p, _ in self.files}, key=lambda r: r != self.repo)

    def tree(self, repo: str | None = None) -> Path:
        """The set's worktree in a repo: `<trees>/<set>` for its own repo, `<trees>/<set>-<repo>` for the other."""
        repo = repo or self.repo
        if self.shared:
            return ctx.ref_tree(repo)
        return ctx.trees / (self.id if repo == self.repo else f"{self.id}-{repo}")

    def branch(self, repo: str) -> str:
        return f"port/set/{self.id}" if repo == self.repo else f"port/set/{self.id}-{repo}"

    def fp(self, p: str) -> Path:
        return self.tree(self.repo_of(p)) / p

    def owned(self) -> set[str]:
        return {p for p, _ in self.files}

    def deleted(self) -> list[str]:
        """Paths the sheet deletes, globs expanded in the path's tree."""
        out = []
        for p, a in self.files:
            if a != "delete":
                continue
            if any(c in p for c in "*?["):
                root = self.tree(self.repo_of(p))
                out += [str(Path(f).relative_to(root)) for f in globmod.glob(str(root / p))]
            else:
                out.append(p)
        return out

    def in_bundle(self) -> list[str]:
        """Files whose current text the writer gets: edits, rewrites, kept files, and new files the stubs created."""
        return [p for p, a in self.files if a in ("edit", "rewrite", "keep") or (a == "new" and self.fp(p).exists())]


def unquote(cell: str) -> str:
    m = re.search(r"`([^`]+)`", cell)
    return (m.group(1) if m else cell).strip()


def writer_sheet(text: str) -> str:
    """The sheet as writers see it: the Files table without its Write and Delete columns (planning size estimates,
    which a writer would read as targets)."""
    out, cols = [], None
    for line in text.splitlines():
        if line.startswith("| Path | Action | Write | Delete |"):
            cols = True
        elif cols and not line.startswith("|"):
            cols = None
        if cols and line.startswith("|"):
            cells = line.split(" | ")
            if len(cells) >= 5:
                line = " | ".join(cells[:2] + cells[4:])
        out.append(line)
    return "\n".join(out)


def spans_of(cell: str) -> list[str]:
    return re.findall(r"`([^`]+)`", cell)


def idents_of(span: str) -> list[tuple[str, str | None]]:
    """The item a backticked span stands for: the last segment of its first path expression, plus its qualifier."""
    if "/" in span or ".rs" in span or span.startswith(("#[", "//")):
        return []
    s = re.sub(r"^(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe)\s+)*(?:fn|struct|enum|trait|type|impl)\s+", "",
               span.strip())
    m = re.match(r"[A-Za-z_]\w*(?:(?:::|\.)[A-Za-z_]\w*)*", s)
    if not m:
        return []
    parts = re.split(r"::|\.", m.group(0))
    name = parts[-1]
    qual = parts[-2] if len(parts) > 1 else None
    if len(name) < 4 or name.lower() in STOP or name in RUST_KW:
        return []
    return [(name, qual)]

"""Scrub patterns and scanners shared by tools/kit-check and tools/land/scan-range.py.

GENERIC holds the patterns that ship with the kit: only shapes that identify no one (home and cache paths, emails,
addresses, private hostname suffixes). Everything that names a person, a machine or its setup (names, handles, hosts,
local tool and tree names, tracker ids) comes from the private patterns file, one Python regex per line, matched
case-insensitively, `#` comments and blank lines ignored, and never ships.

This file defines the generic patterns, so kit-check exempts it from the generic scan (not from the private one).
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PRIVATE_DEFAULT = "~/.config/craft-ui-port-kit/private-patterns.txt"
PRIVATE_ENV = "PORT_KIT_PRIVATE_PATTERNS"


@dataclass(frozen=True)
class Pattern:
    name: str
    rx: re.Pattern
    keep: object = None   # optional predicate on the matched text: False drops the match

    def finditer(self, line: str):
        for m in self.rx.finditer(line):
            if self.keep is None or self.keep(m.group(0)):
                yield m


def _p(name, rx, flags=0, keep=None):
    return Pattern(name, re.compile(rx, flags), keep)


GENERIC: list[Pattern] = [
    _p("home-path", r"/home/[a-z]"),
    _p("home-path", r"/Users/"),
    _p("home-path", r"C:\\Users"),
    _p("cache-path", r"\.cache/"),
    _p("scratch-path", r"/tmp/claude-"),
    _p("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", keep=lambda s: "noreply" not in s.lower()),
    _p("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", keep=lambda s: s != "127.0.0.1"),
    _p("private-host", r"\b[\w-]+\.(?:dev|lan|local|internal|ts\.net)\b"),
]


@dataclass(frozen=True)
class Hit:
    where: str      # file path, or "@ident <sha>" / "@message <sha>" for commit metadata
    line: int       # 0 for commit metadata
    pattern: str
    text: str       # the whole line
    start: int
    end: int

    def show(self, width: int = 160) -> str:
        loc = f"{self.where}:{self.line}" if self.line else self.where
        return f"{loc}: [{self.pattern}] {self.text.strip()[:width]}"


def private_path(explicit: str | None = None) -> Path:
    return Path(os.path.expanduser(explicit or os.environ.get(PRIVATE_ENV) or PRIVATE_DEFAULT))


def load_private(path: Path) -> list[Pattern]:
    out = []
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        try:
            out.append(Pattern(f"private:{n}", re.compile(s, re.I)))
        except re.error as e:
            raise ValueError(f"{path}:{n}: bad regex {s!r}: {e}") from None
    return out


def scan_line(where: str, n: int, line: str, patterns: list[Pattern]):
    for p in patterns:
        for m in p.finditer(line):
            yield Hit(where, n, p.name, line, m.start(), m.end())


def scan_text(where: str, text: str, patterns: list[Pattern]):
    for n, line in enumerate(text.splitlines(), 1):
        yield from scan_line(where, n, line, patterns)


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:8000]


def git(repo: str, *args: str, input: bytes | None = None) -> bytes:
    r = subprocess.run(["git", "-C", repo, *args], input=input, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def tracked_files(repo: str, rev: str | None):
    """(path, bytes) of every tracked file: the working tree's tracked files, or the files of `rev`."""
    if rev is None:
        names = git(repo, "ls-files", "-z").decode().split("\0")
        for name in filter(None, names):
            p = Path(repo, name)
            if p.is_file() and not p.is_symlink():
                yield name, p.read_bytes()
        return
    listing = git(repo, "ls-tree", "-r", "-z", rev).decode().split("\0")
    entries = []
    for e in filter(None, listing):
        meta, name = e.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "blob" and mode != "120000":
            entries.append((name, sha))
    if not entries:
        return
    out = git(repo, "cat-file", "--batch", input="".join(f"{sha}\n" for _, sha in entries).encode())
    pos = 0
    for name, _ in entries:
        nl = out.index(b"\n", pos)
        size = int(out[pos:nl].split()[2])
        yield name, out[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1


def history(repo: str, revs: list[str]):
    """Yield (where, line_no, text) for authors, committers, messages and added lines of the commits `revs` selects
    (arguments to git log, e.g. ["A..B"] or ["B", "--not", "--remotes"])."""
    out = git(repo, "log", "--reverse", "-p", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
              "--format=%x01%H%x02%an <%ae>%x02%cn <%ce>%x02%B%x03", *revs).decode(errors="replace")
    for chunk in out.split("\x01")[1:]:
        head, _, diff = chunk.partition("\x03")
        sha, author, committer, msg = head.split("\x02", 3)
        s = sha[:10]
        yield f"@ident {s}", 0, author
        if committer != author:
            yield f"@ident {s}", 0, committer
        for line in msg.splitlines():
            yield f"@message {s}", 0, line
        cur, n = "?", 0
        for line in diff.splitlines():
            if line.startswith("+++ "):
                cur = line[6:] if line.startswith("+++ b/") else line[4:]
            elif line.startswith("@@"):
                m = re.match(r"@@ -\S+ \+(\d+)", line)
                n = int(m.group(1)) if m else 0
            elif line.startswith("+"):
                yield f"{cur} ({s})", n, line[1:]
                n += 1


def scan_history(repo: str, revs: list[str], patterns: list[Pattern]):
    for where, n, text in history(repo, revs):
        yield from scan_line(where, n, text, patterns)


class Allow:
    """Exact exceptions: lines `path<TAB>string`. A hit in `path` passes when an occurrence of `string` in its line
    covers the matched text. For history hits, `path` is the file path; commit metadata uses `@ident` or `@message`."""

    def __init__(self, path: Path | None):
        self.file = path
        self.entries: dict[str, list[str]] = {}
        self.rows: list[tuple[int, str, str]] = []
        if path and path.is_file():
            for n, raw in enumerate(path.read_text().splitlines(), 1):
                if not raw.strip() or raw.lstrip().startswith("#"):
                    continue
                if "\t" not in raw:
                    raise ValueError(f"{path}:{n}: expected path<TAB>string")
                p, s = raw.split("\t", 1)
                if not s:
                    raise ValueError(f"{path}:{n}: empty string")
                self.entries.setdefault(p, []).append(s)
                self.rows.append((n, p, s))

    def allows(self, hit: Hit) -> bool:
        key = hit.where.split(" (", 1)[0].split(" ", 1)[0]
        for s in self.entries.get(key, ()):
            i = hit.text.find(s)
            while i >= 0:
                if i <= hit.start and hit.end <= i + len(s):
                    return True
                i = hit.text.find(s, i + 1)
        return False

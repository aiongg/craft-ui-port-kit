"""Test logs and red-round tracks, shared by compare-runs.py and diag-cut.py.

framework_binaries(text) and app_binaries(build_text, run_text) give each test binary's status (ok, failed, crashed,
not run) and its counts from its own result line, for test-run.

parse(path) reads a test run log in either format cl can produce:
  - libtest (`cargo test`): `Running ... (target/.../deps/<bin>-<hash>)`, `test <name> ... ok|FAILED|ignored`,
    `---- <name> stdout ----` sections, `thread '<name>' (<tid>) panicked at <file:line:col>:` and the message
    on the next line;
  - nextest: `PASS|FAIL|SKIP|TIMEOUT|SIGSEGV|... [ <time>] <binary> <name>` status lines and
    `--- STDOUT: <binary> <name> ---` / `--- STDERR: ...` sections.
A test is keyed by its full name (`module::tests::name`). Every line holding `DIAG <ident>` is kept under the
ident: fixers print `eprintln!("DIAG <test fn name>: ...")` (prompts/p7-red-fixer.md).

load_tracks(path) reads which tests each red-round track owns, from:
  - a directory written by split-failures.py: every `*.md` but index.md is one track named after the file
    (`g3.md` -> `g3`); its tests are the `### <name>` headings;
  - a `.tsv` file: `<track><TAB><test>` per line;
  - a Markdown file (the round's groups.md): one track per `## <track id> ...` heading; its tests are `### <name>`
    headings and the first backticked name of each list item or table row in the section.
Test names in a track may be full or short (the function name); resolve() maps them onto a run's names.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

RUNNING = re.compile(r"^\s+Running (?:unittests )?(\S+) \((\S+)\)")
LIBTEST = re.compile(r"^test (\S+) \.\.\. (ok|FAILED|ignored)")
STDOUT = re.compile(r"^---- (\S+) stdout ----$")
PANIC = re.compile(r"^thread '([^']+)'(?: \(\d+\))? panicked at (.*?):?$")
NEXTEST = re.compile(r"^\s*(PASS|FAIL|SKIP|TIMEOUT|SIGSEGV|SIGABRT|SIGKILL|ABORT|LEAK|LEAK-FAIL|FLAKY)\s+\[[^\]]*\]\s+(?:\(\s*\d+/\d+\)\s+)?(\S+)\s+(\S+)\s*$")
NEXTEST_SECTION = re.compile(r"^\s*(?:-{3}|─{2,})\s*STD(?:OUT|ERR):\s+(\S+)\s+(\S+)")
DIAG = re.compile(r"\bDIAG ([A-Za-z_][A-Za-z0-9_]*)\b")
FAILING = {"FAIL", "TIMEOUT", "SIGSEGV", "SIGABRT", "SIGKILL", "ABORT", "LEAK-FAIL"}


@dataclass
class Failure:
    name: str
    binary: str = ""
    site: str = ""
    message: str = ""
    output: list[str] = field(default_factory=list)


@dataclass
class Run:
    path: Path
    status: dict[str, str] = field(default_factory=dict)     # name -> ok | FAILED | ignored
    failures: dict[str, Failure] = field(default_factory=dict)
    diag: dict[str, list[str]] = field(default_factory=dict)  # DIAG ident -> lines

    @property
    def passed(self) -> int:
        return sum(1 for s in self.status.values() if s == "ok")

    @property
    def failed(self) -> list[str]:
        return sorted(n for n, s in self.status.items() if s == "FAILED")

    def by_short(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for n in self.status:
            out.setdefault(short(n), []).append(n)
        return out


def short(name: str) -> str:
    return name.rsplit("::", 1)[-1]


def parse(path: Path) -> Run:
    run = Run(Path(path))
    lines = Path(path).read_text(errors="replace").split("\n")
    binary = ""
    cur: Failure | None = None
    for i, raw in enumerate(lines):
        line = raw.rstrip("\r")
        for m in DIAG.finditer(line):
            seen = run.diag.setdefault(m.group(1), [])
            text = line.strip()[:400]
            if not seen or seen[-1] != text:
                seen.append(text)
        m = RUNNING.match(line)
        if m:
            binary = f"{m.group(1)} ({Path(m.group(2)).name})"
            cur = None
            continue
        m = LIBTEST.match(line)
        if m:
            name, st = m.group(1), m.group(2)
            if run.status.get(name) != "FAILED":
                run.status[name] = st
            if st == "FAILED":
                run.failures.setdefault(name, Failure(name, binary))
            continue
        m = NEXTEST.match(line)
        if m:
            st, nbin, name = m.groups()
            mapped = "FAILED" if st in FAILING else ("ignored" if st == "SKIP" else "ok")
            if run.status.get(name) != "FAILED":
                run.status[name] = mapped
            if mapped == "FAILED":
                f = run.failures.setdefault(name, Failure(name, nbin))
                if st != "FAIL" and not f.message:
                    f.message = st
            cur = None
            continue
        m = STDOUT.match(line) or NEXTEST_SECTION.match(line)
        if m:
            name = m.group(1) if m.re is STDOUT else m.group(2)
            cur = run.failures.setdefault(name, Failure(name, binary if m.re is STDOUT else m.group(1)))
            continue
        m = PANIC.match(line)
        if m:
            f = run.failures.get(m.group(1)) or cur
            if f is not None and not f.site:
                f.site = m.group(2)
                f.message = lines[i + 1].strip()[:300] if i + 1 < len(lines) else ""
        if cur is not None:
            if line.startswith("failures:") or line.startswith("test result:"):
                cur = None
            elif len(cur.output) < 40 and line.strip():
                cur.output.append(line[:300])
    # A section header alone (a captured stdout of a passing test under --show-output) is not a failure.
    for n in [n for n in run.failures if run.status.get(n) not in (None, "FAILED")]:
        del run.failures[n]
    for n in run.failures:
        run.status.setdefault(n, "FAILED")
    return run


def find_log(arg: str, runs_dir: Path | None) -> Path:
    """A run label (a directory under work.runs), a run directory, or a log file -> the log file."""
    p = Path(arg).expanduser().resolve()
    for d in ([p] if p.exists() else []) + ([runs_dir / arg] if runs_dir else []):
        if d.is_file():
            return d
        if d.is_dir():
            if (d / "app.log").is_file():
                return d / "app.log"
            logs = sorted(x for x in d.glob("*.log") if not x.name.endswith(".build.log"))
            if len(logs) == 1:
                return logs[0]
            raise SystemExit(f"{d}: no app.log and {len(logs)} other logs; name the log file")
    raise SystemExit(f"no run log at {arg}" + (f" or {runs_dir / arg}" if runs_dir else ""))


BACKTICK = re.compile(r"`([A-Za-z_][A-Za-z0-9_:]*)`")


def load_tracks(path: Path) -> dict[str, list[str]]:
    path = Path(path)
    tracks: dict[str, list[str]] = {}
    if path.is_dir():
        for f in sorted(path.glob("*.md")):
            if f.name == "index.md":
                continue
            tracks[f.stem] = [l[4:].strip() for l in f.read_text().split("\n") if l.startswith("### ")]
        return tracks
    text = path.read_text()
    if path.suffix == ".tsv":
        for l in text.split("\n"):
            parts = l.split("\t")
            if len(parts) >= 2 and parts[0].strip() and not l.startswith("#"):
                tracks.setdefault(parts[0].strip(), []).append(parts[1].strip())
        return tracks
    cur = None
    for l in text.split("\n"):
        if l.startswith("## "):
            tid = l[3:].split()[0].rstrip(":") if l[3:].split() else ""
            cur = tracks.setdefault(tid, []) if tid else None
            continue
        if cur is None:
            continue
        if l.startswith("### "):
            cur.append(l[4:].split()[0].strip("`"))
        elif l.lstrip().startswith(("- ", "* ", "|")):
            m = BACKTICK.search(l)
            if m:
                cur.append(m.group(1))
    return {t: list(dict.fromkeys(ns)) for t, ns in tracks.items()}


def resolve(names: list[str], *runs: Run) -> list[str]:
    """Full test names for a track's list: a full name stays; a short name maps to every full name with it."""
    full: set[str] = set()
    shorts: dict[str, list[str]] = {}
    for r in runs:
        full.update(r.status)
        for s, ns in r.by_short().items():
            shorts.setdefault(s, []).extend(ns)
    out: list[str] = []
    for n in names:
        if n in full or "::" in n:
            out.append(n)
        else:
            out.extend(sorted(set(shorts.get(n, [n]))))
    return list(dict.fromkeys(out))


# ---------------------------------------------------------------- binaries

EXECUTABLE = re.compile(r"^\s*Executable (.+) \((\S+)\)\s*$")
LIB_RESULT = re.compile(r"^test result: \w+\. (\d+) passed; (\d+) failed")
CL_TEST_FAILED = re.compile(r"^cl: test failed: (.+) \((\S+)\) exited with (-?\d+)")
# cl's app mode: one line per binary or shard, `ok|FAILED <package> <lib|target>[ shard i/n]: P passed, F failed, S s`.
CL_STATUS = re.compile(r"^\s*(ok|FAILED) (\S+ \S+?)(?: shard \d+/\d+)?: (\d+) passed, (\d+) failed, \d+ s\s*$")
CL_NO_RESULT = re.compile(r"^\s+(\S+ \S+?)(?: shard \d+/\d+)? \(exit (-?\d+), no test result\)\s*$")


@dataclass
class Binary:
    key: str              # framework: the source (`unittests src/lib.rs`, `tests/x.rs`); app: `<package> <lib|target>`
    exe: str = ""         # path as cl printed it, relative to the tree it ran in
    status: str = "not run"   # ok | failed | crashed | not run
    passed: int = 0
    failed: int = 0


def executables(text: str) -> dict[str, str]:
    """{binary key: executable path} from cl's `Executable <key> (<path>)` lines, in order."""
    return {m.group(1).strip(): m.group(2) for m in map(EXECUTABLE.match, text.split("\n")) if m}


def framework_binaries(text: str) -> dict[str, Binary]:
    """Per-binary results of a `cl test <crate>` log (libtest output). Counts come from each binary's own
    `test result:` line. A binary that started and printed no result line crashed; one cl listed but never started
    (cl stops at the first failing binary) did not run."""
    out = {k: Binary(k, exe) for k, exe in executables(text).items()}
    cur = None
    for line in text.split("\n"):
        m = RUNNING.match(line)
        if m:
            key = line.strip()[len("Running "):].rsplit(" (", 1)[0]
            cur = out.setdefault(key, Binary(key, m.group(2)))
            cur.status = "crashed"
            continue
        m = LIB_RESULT.match(line)
        if m and cur is not None:
            cur.passed, cur.failed = int(m.group(1)), int(m.group(2))
            cur.status = "failed" if cur.failed else "ok"
            cur = None
            continue
        m = CL_TEST_FAILED.match(line)
        if m and m.group(1) in out and out[m.group(1)].status == "ok":
            out[m.group(1)].status = "failed"   # a nonzero exit after a clean result line (a panic outside a test)
    return out


def app_binaries(build_text: str, run_text: str) -> dict[str, Binary]:
    """Per-binary results of a `cl test all` run in cl's app mode: the binaries its `--no-run` build listed, each
    with the counts of its own status lines (shards added up). A binary whose run gave no test result crashed; one
    with no status line did not run."""
    out = {k: Binary(k, exe) for k, exe in executables(build_text).items()}
    crashed = {m.group(1) for m in map(CL_NO_RESULT.match, run_text.split("\n")) if m}
    seen = set()
    for m in map(CL_STATUS.match, run_text.split("\n")):
        if not m:
            continue
        st, key, p, f = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        b = out.setdefault(key, Binary(key))
        if key not in seen:
            b.status, b.passed, b.failed = "ok", 0, 0
            seen.add(key)
        b.passed += p
        b.failed += f
        if st == "FAILED" and b.status != "crashed":
            b.status = "crashed" if key in crashed else "failed"
    return out


def failing_names(text: str) -> list[str]:
    """Names of failed tests in libtest output (`test <name> ... FAILED`), sorted."""
    return sorted({m.group(1) for m in map(LIBTEST.match, text.split("\n")) if m and m.group(2) == "FAILED"})

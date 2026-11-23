#!/usr/bin/env python3
"""test-ledger.py: every test of the baseline with its plan verdict and its status now, and the land gate's check.

usage: test-ledger.py [--check] [--json] [--config PORT.TOML]
       test-ledger.py stale TEST --task TASK WHY... [--config PORT.TOML]

Rows: one per test name the baseline listed (<work.runs>/baseline.json names each part's baseline run; its
`<part>.tests.tsv` the tests), for the `app` part and for each `fw:<crate>` part whose crate owns a file changed
between plan.base and the HEAD of framework.integration. Written to <work.runs>/ledger.tsv with the columns
  part, binary, test, set, verdict, target, target_status, source, status, run
  - verdict: the plan's (`keep`, `rewrite`, `move`, `delete`) from the sheets' Tests tables (work.sheets), or the
    phase 7 triage's from <work.runs>/triage.tsv, which overrides the plan's `keep` for the tests it judged (`cut`
    and `cut-fix` are recorded as `delete`; `move` takes its target from the row's 6th column). Empty: no verdict.
  - target: a `move` verdict's target, `<path> <test fn>` (the sheet's Reason cell starts `to <path> <test fn>`).
    target_status: `pass` when a test of that file and name is listed in the latest runs and not failing, else
    `fail`, `missing` or empty.
  - source: `sheet` or `triage`.
  - status: from the latest unfiltered run of the part (<work.runs>/test-runs.tsv): `pass`, `fail`, `gone` (not
    listed any more), `not run` (its binary crashed, did not run, or could not list its tests). run: that run.
A sheet row's file is matched to tests through its package (the nearest Cargo.toml in the snapshot, else the
integration tree) and module path: `src/lib.rs` and `src/main.rs` are the crate root, `src/a/b.rs` and
`src/a/b/mod.rs` the module `a::b`, `tests/t.rs` the integration binary `t`. The test is `<module>::...::<fn>` in a
binary of that package. A row whose file maps to no test matches its function name in the package when that name
is unique there.

--check: exit 1 when a `gone` row has no `delete` verdict and no `move` target that passes; it prints those rows.
The phase 8 exit and both landing tools run this check (tools/portkit/gates.py, tools/land/exit-gate.py).

stale: a red fixer's report that a `keep` test's premise is stale. Appends `test<TAB>task<TAB>why` to
<work.runs>/stale.tsv and posts a `fix` event on TASK. Phase 7 triage judges exactly these tests
(process/08-tests-and-red-rounds.md).

Last stdout line: `test-ledger: <n> tests in <k> parts; pass n, fail n, gone n, not run n; gone without a verdict n`.
Exit 0; 1 refused (--check); 2 no baseline or a usage error. Posts one `test-ledger` event.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, gates, track  # noqa: E402

COLS = ("part", "binary", "test", "set", "verdict", "target", "target_status", "source", "status", "run")
TRIAGE_AS = {"keep": "keep", "cut": "delete", "cut-fix": "delete", "move": "move"}
MOVE_TO = re.compile(r"^\s*to\s+`?([\w./-]+\.rs)`?(?:\s*\((fw|app)\))?\s+`?(\w+)")


# ---------------------------------------------------------------- runs

def read_tests(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            k, _, t = line.partition("\t")
            out.setdefault(k, []).append(t)
    return out


def tests_file(runs: Path, label: str, part: str) -> Path:
    return runs / label / (part.replace(":", "-") + ".tests.tsv")


def latest_runs(runs: Path) -> dict[str, str]:
    """{part: label of its latest unfiltered run}."""
    f = runs / "test-runs.tsv"
    out = {}
    for r in (l.split("\t") for l in (f.read_text().splitlines() if f.is_file() else [])):
        if len(r) >= 4 and r[3] == "0":
            out[r[2]] = r[1]
    return out


def run_state(runs: Path, label: str, part: str) -> dict:
    """{"tests": {binary: [test]}, "failing": set, "bad": set of binaries not run or unlistable}."""
    try:
        p = next(x for x in json.loads((runs / label / "summary.json").read_text())["parts"] if x["part"] == part)
    except (OSError, ValueError, KeyError, StopIteration):
        p = {}
    bins = p.get("binaries") or {}
    bad = {k for k, b in bins.items() if b.get("status") in ("crashed", "not run") or b.get("tests") is None}
    return {"tests": read_tests(tests_file(runs, label, part)), "failing": set(p.get("failing") or []), "bad": bad}


# ---------------------------------------------------------------- files to tests

def package_dir(roots: list[Path], rel: str) -> tuple[str, str] | None:
    """(package name, file path relative to the package dir) from the nearest Cargo.toml with a [package]."""
    for root in roots:
        d = (root / rel).parent
        while True:
            m = d / "Cargo.toml"
            if m.is_file():
                try:
                    name = tomllib.loads(m.read_text()).get("package", {}).get("name")
                except tomllib.TOMLDecodeError:
                    name = None
                if name:
                    return name, str((root / rel).relative_to(d))
            if d == root or d == d.parent:
                break
            d = d.parent
    return None


def module_of(inner: str) -> tuple[str, str] | None:
    """("unit" | <integration binary>, module prefix) of a file path inside its package."""
    parts = inner[:-3].split("/") if inner.endswith(".rs") else []
    if len(parts) >= 2 and parts[0] == "src":
        mods = parts[1:]
        if mods[-1] == "mod" or (len(mods) == 1 and mods[0] in ("lib", "main")):
            mods = mods[:-1]
        return "unit", "::".join(mods)
    if len(parts) >= 2 and parts[0] == "tests":
        mods = parts[1:]
        if mods[-1] == "mod":
            mods = mods[:-1]
        return mods[0], "::".join(mods[1:])
    return None


def binary_package(part: str, key: str) -> str:
    return part[3:] if part.startswith("fw:") else key.split(" ", 1)[0]


def binary_kind(part: str, key: str) -> str:
    """"unit" for a library or binary's unit tests, else the integration test's name."""
    if part.startswith("fw:"):
        m = re.match(r"^tests/(.+)\.rs$", key)
        return m.group(1).split("/")[0] if m else "unit"
    words = key.split()
    return "unit" if len(words) < 2 or words[1] in ("lib", "bin") or words[1] == words[0].replace("-", "_") else words[-1]


class Index:
    """Tests of a set of runs, looked up by package, binary kind, module prefix and function name."""

    def __init__(self, entries: list[tuple[str, str, str]]):
        self.by_pkg: dict[str, list[tuple[str, str, str]]] = {}
        for part, key, test in entries:
            self.by_pkg.setdefault(binary_package(part, key), []).append((part, key, test))

    def find(self, pkg: str, kind: str | None, prefix: str, fn: str) -> list[tuple[str, str, str]]:
        cands = [e for e in self.by_pkg.get(pkg, []) if e[2] == fn or e[2].endswith("::" + fn)]
        if kind is not None:
            exact = [e for e in cands if binary_kind(e[0], e[1]) == kind
                     and (not prefix or e[2] == f"{prefix}::{fn}" or e[2].startswith(prefix + "::"))]
            if exact:
                return exact
        return cands if len(cands) == 1 else []


def locate(roots: dict[str, list[Path]], repo: str, path: str, fn: str, index: Index) -> list[tuple[str, str, str]]:
    pd = package_dir(roots[repo], path)
    if pd is None:
        return []
    mod = module_of(pd[1])
    return index.find(pd[0], mod[0] if mod else None, mod[1] if mod else "", fn)


# ---------------------------------------------------------------- verdicts

def sheet_rows(cfg) -> list[tuple[str, str, str, str, str, str]]:
    """(set, repo, path, test fn, verdict, reason) for every Tests row of every sheet."""
    from portkit.portset.sheet import Sheet, SheetError, unquote
    d = cfg.path("work.sheets")
    out = []
    for f in sorted(d.glob("*.md")) if d.is_dir() else []:
        try:
            s = Sheet(f.stem, f)
        except SheetError:
            continue
        for r in s.tests:
            if len(r) < 3 or not r[2].strip():
                continue
            v = r[2].strip().lower().split()[0].strip("`*.,;")
            m = re.search(r"\((fw|app)\)", r[0])
            path = unquote(r[0])
            for fn in re.findall(r"`([^`]+)`", r[1]) or [r[1].strip()]:
                fn = re.sub(r"\(.*$", "", fn.split("::")[-1]).strip()
                if fn:
                    out.append((s.id, m.group(1) if m else s.repo, path, fn, v, r[3] if len(r) > 3 else ""))
    return out


def triage_rows(runs: Path) -> list[list[str]]:
    f = runs / "triage.tsv"
    return [r for r in (l.split("\t") for l in (f.read_text().splitlines() if f.is_file() else [])) if len(r) >= 3]


# ---------------------------------------------------------------- build

def build(cfg) -> tuple[list[dict], list[str]]:
    runs = cfg.path("work.runs")
    bf = runs / "baseline.json"
    if not bf.is_file():
        raise SystemExit(2)
    base = json.loads(bf.read_text())
    fw_tree = cfg.path("framework.integration") if cfg.get("framework.integration") else None
    rows, notes = [], []
    changed = set()
    if fw_tree and cfg.get("plan.base") and any(p.startswith("fw:") for p in base):
        try:
            changed = {p for f in gates.changed_files(fw_tree, cfg.get("plan.base"))
                       if (p := gates.package_of(fw_tree, f))}
        except subprocess.CalledProcessError as e:
            notes.append(f"framework parts left out: git diff {cfg.get('plan.base')} failed in {fw_tree} ({e.returncode})")
    parts = [p for p in base if p == "app" or (p.startswith("fw:") and p[3:] in changed)]
    latest = latest_runs(runs)
    states = {p: run_state(runs, latest[p], p) for p in latest}
    for part in parts:
        st = states.get(part) or {"tests": {}, "failing": set(), "bad": set()}
        now = {(k, t) for k, ts in st["tests"].items() for t in ts}
        for key, tests in read_tests(tests_file(runs, base[part], part)).items():
            for t in tests:
                if (key, t) in now:
                    status = "not run" if key in st["bad"] else "fail" if t in st["failing"] else "pass"
                else:
                    status = "not run" if key in st["bad"] else "gone"
                rows.append({"part": part, "binary": key, "test": t, "set": "", "verdict": "", "target": "",
                             "target_status": "", "source": "", "status": status, "run": latest.get(part, "")})
    by_id = {(r["part"], r["binary"], r["test"]): r for r in rows}
    roots = {"fw": [cfg.path(k) for k in ("framework.snapshot", "framework.integration") if cfg.get(k)],
             "app": [cfg.path(k) for k in ("app.snapshot", "app.integration") if cfg.get(k)]}
    base_index = Index(list(by_id))
    now_index = Index([(p, k, t) for p, st in states.items() for k, ts in st["tests"].items() for t in ts])

    def target_status(spec: str) -> str:
        m = MOVE_TO.match("to " + spec)
        if not m:
            return "missing"
        repo = m.group(2) or ("fw" if package_dir(roots["fw"], m.group(1)) else "app")
        hits = locate(roots, repo, m.group(1), m.group(3), now_index)
        if not hits:
            return "missing"
        ok = any(p in states and t not in states[p]["failing"] and k not in states[p]["bad"] for p, k, t in hits)
        return "pass" if ok else "fail"

    for sid, repo, path, fn, v, reason in sheet_rows(cfg):
        hits = locate(roots, repo, path, fn, base_index)
        if len(hits) > 1:
            notes.append(f"{sid}: `{path}` {fn} matches {len(hits)} tests; the verdict is given to each")
        for h in hits:
            r = by_id[h]
            if r["source"]:
                continue
            m = MOVE_TO.match(reason) if v == "move" else None
            target = f"{m.group(1)}{' (' + m.group(2) + ')' if m.group(2) else ''} {m.group(3)}" if m else ""
            r.update(set=sid, verdict=v, source="sheet", target=target)
    short: dict[str, list[dict]] = {}
    for r in rows:
        short.setdefault(r["test"], []).append(r)
        short.setdefault(r["test"].rsplit("::", 1)[-1], []).append(r)
    for t in triage_rows(runs):
        v = TRIAGE_AS.get(t[2].strip())
        hits = short.get(t[0].strip(), [])
        if not v or len(hits) != 1:
            continue
        r = hits[0]
        if r["verdict"] in ("", "keep"):
            r.update(verdict=v, source="triage", target=t[5].strip() if v == "move" and len(t) > 5 else "")
    for r in rows:
        if r["verdict"] == "move":
            r["target_status"] = target_status(r["target"]) if r["target"] else "missing"
    return rows, notes


def refused(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["status"] == "gone" and r["verdict"] != "delete"
            and not (r["verdict"] == "move" and r["target_status"] == "pass")]


def write(cfg, rows: list[dict]) -> Path:
    f = cfg.path("work.runs") / "ledger.tsv"
    f.write_text("\t".join(COLS) + "\n" + "".join("\t".join(r[c] for c in COLS) + "\n" for r in rows))
    return f


def counts(rows: list[dict]) -> dict:
    out = {"tests": len(rows), "parts": len({r["part"] for r in rows}), "refused": len(refused(rows))}
    for s in ("pass", "fail", "gone", "not run"):
        out[s] = sum(1 for r in rows if r["status"] == s)
    for v in ("keep", "rewrite", "move", "delete", ""):
        out["verdict " + (v or "none")] = sum(1 for r in rows if r["verdict"] == v)
    return out


def summary(c: dict) -> str:
    return (f"test-ledger: {c['tests']} tests in {c['parts']} parts; pass {c['pass']}, fail {c['fail']}, "
            f"gone {c['gone']}, not run {c['not run']}; gone without a verdict {c['refused']}")


def cmd_stale(cfg, a) -> int:
    track.check_task(a.task)
    f = cfg.path("work.runs") / "stale.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    why = " ".join(a.why).replace("\t", " ").replace("\n", " ")
    with open(f, "a") as fh:
        fh.write(f"{a.test}\t{a.task}\t{why}\n")
    track.event("fix", f"{a.test}: keep test marked stale: {why}", task=a.task, data={"stale": a.test})
    print(f"stale: {a.test} ({a.task}) recorded in {f}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["stale"]:
        ap = argparse.ArgumentParser(prog="test-ledger.py stale")
        ap.add_argument("test")
        ap.add_argument("--task", required=True)
        ap.add_argument("why", nargs="+")
        ap.add_argument("--config")
        a = ap.parse_args(argv[1:])
        return cmd_stale(config.load(a.config), a)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    try:
        rows, notes = build(cfg)
    except SystemExit:
        print(f"test-ledger: no baseline ({cfg.path('work.runs') / 'baseline.json'}); run test-run --baseline first",
              file=sys.stderr)
        return 2
    f = write(cfg, rows)
    c = counts(rows)
    bad = refused(rows)
    with track.recorded("test-ledger") as rec:
        for n in notes[:20]:
            print(f"note: {n}")
        if a.check and bad:
            print(f"{len(bad)} tests left the suite without a `delete` verdict or a passing `move` target:")
            for r in bad[:40]:
                print(f"  {r['part']} {r['binary']} {r['test']} ({r['set'] or 'no set'}): "
                      + (f"{r['verdict']}" if r["verdict"] else "no verdict")
                      + (f" to {r['target'] or '?'} ({r['target_status']})" if r["verdict"] == "move" else ""))
            if len(bad) > 40:
                print(f"  ... {len(bad) - 40} more in {f}")
        if a.json:
            print(json.dumps({"ledger": str(f), **c}))
        line = summary(c)
        print(line)
        rec.result(line, log=str(f), data=c, ok=not (a.check and bad))
    return 1 if a.check and bad else 0


if __name__ == "__main__":
    sys.exit(main())

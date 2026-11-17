#!/usr/bin/env python3
"""compare-runs.py: compare a test run with the previous one, per red-round track, and attribute new failures.

usage: compare-runs.py NEW [OLD] [--tracks SRC] [--baseline FILE] [--branch TRACK=REPO:RANGE]... [--out FILE]
                       [--round N] [--task-prefix P] [--config PORT.TOML]

NEW and OLD are run labels (directories under work.runs, as test-run writes them), run directories or log files
(libtest or nextest output; see tools/portkit/testlog.py). OLD defaults to the run recorded before NEW in
<work.runs>/rounds.tsv; with no OLD, the comparison is against the baseline alone.

--tracks names the round's tracks: the split-failures.py output directory, a groups.md with one `## <track>`
section per track, or a `track<TAB>test` TSV. --baseline (default work.baseline_failures, when it exists) lists the
tests that already fail on the unported app: they are never counted as new.

The report (stdout, and --out FILE; default <NEW run dir>/compare.md when NEW is a run directory):
  - the counts: failing and passing now and before, and how many of the failures are baseline failures;
  - per track: its tests, failing before, failing now, fixed since, new failures; then each failing test with its
    panic line, the tests not run, and the fixed ones;
  - new failures (failing now, not before, not in the baseline), each with the track whose change most likely
    caused it: a track whose --branch diff (`git -C REPO diff --name-only RANGE`, several per track allowed)
    touched the file of the panic site or the test's module is `likely`; else the track whose tests share the
    longest module path with it is `maybe`; else `unattributed`;
  - failures of OLD outside every track that pass or are gone now, and the tests that are new since OLD.

Dashboard: with --round N it posts round N (pass, fail, and in its data the new failures and the per-track
counts). Without --round it posts a `compare` event with the same numbers: test-run already posted the round for
a full run it recorded, and one round must not appear twice. Track tasks are `<P><track>` (--task-prefix); each
gets an event when it has new failures attributed to it.
Exit 0; 2 when a log or the tracks cannot be read.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, track  # noqa: E402
from portkit.testlog import Run, find_log, load_tracks, parse, resolve, short  # noqa: E402


def previous_label(runs: Path, new_log: Path) -> str | None:
    f = runs / "rounds.tsv"
    if not f.is_file():
        return None
    rows = [l.split("\t") for l in f.read_text().split("\n") if l.strip()]
    labels = [r[1] for r in rows if len(r) > 1]
    for i, lab in enumerate(labels):
        if (runs / lab) in (new_log.parent, new_log) and i > 0:
            return labels[i - 1]
    return None


def module(name: str) -> list[str]:
    return name.split("::")[:-1]


def shared_prefix(a: list[str], b: list[str]) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def changed_files(spec: str) -> list[str]:
    repo, _, rng = spec.partition(":")
    r = subprocess.run(["git", "-C", repo, "diff", "--name-only", rng], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"compare-runs: --branch {spec}: {r.stderr.strip()}")
    return [l for l in r.stdout.split("\n") if l]


def attribute(name: str, run: Run, tracks: dict[str, list[str]], changes: dict[str, list[str]]) -> tuple[str, str]:
    f = run.failures.get(name)
    site = f.site.rsplit(":", 2)[0] if f and f.site else ""
    mod = module(name)
    for t, files in changes.items():
        for c in files:
            if site and (site.endswith(c) or c.endswith(site)):
                return t, f"likely: its change touched {c}, the panic site"
            stem = Path(c).stem
            if stem in mod and c.endswith(".rs"):
                return t, f"likely: its change touched {c}, module {stem}"
    best, depth = None, 0
    for t, ns in tracks.items():
        for n in ns:
            d = shared_prefix(mod, module(n))
            if d > depth:
                best, depth = t, d
    if best:
        return best, f"maybe: shares module {'::'.join(mod[:depth])} with its tests"
    return "", "unattributed"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new")
    ap.add_argument("old", nargs="?")
    ap.add_argument("--tracks")
    ap.add_argument("--baseline")
    ap.add_argument("--branch", action="append", default=[], metavar="TRACK=REPO:RANGE")
    ap.add_argument("--out")
    ap.add_argument("--round")
    ap.add_argument("--task-prefix", default="")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    runs = Path(cfg.get("work.runs"))

    with track.recorded("compare-runs") as rec:
        new_log = find_log(a.new, runs)
        old_label = a.old or previous_label(runs, new_log)
        new = parse(new_log)
        old = parse(find_log(old_label, runs)) if old_label else Run(Path("-"))
        base_file = Path(a.baseline) if a.baseline else Path(cfg.get("work.baseline_failures"))
        baseline = set()
        if base_file.is_file():
            baseline = {l.strip() for l in base_file.read_text().split("\n") if l.strip()}
        elif a.baseline:
            raise SystemExit(f"compare-runs: no baseline file {base_file}")
        tracks = {t: resolve(ns, new, old) for t, ns in (load_tracks(Path(a.tracks)).items() if a.tracks else [])}
        changes: dict[str, list[str]] = {}
        for spec in a.branch:
            t, _, rest = spec.partition("=")
            if not rest:
                raise SystemExit(f"compare-runs: --branch needs TRACK=REPO:RANGE: {spec}")
            changes.setdefault(t, []).extend(changed_files(rest))

        nf, of = set(new.failed), set(old.failed)
        in_base = lambda n: n in baseline or short(n) in baseline  # noqa: E731
        new_fail = sorted(n for n in nf if n not in of and not in_base(n))
        L = [f"# Compare: {new_log}" + (f" against {old_label}" if old_label else " (no earlier run)"), ""]
        L.append(f"Failing now: {len(nf)} ({sum(map(in_base, nf))} of them baseline failures). "
                 f"Passing now: {new.passed}." + (f" Before: {len(of)} failing, {old.passed} passing." if old_label else ""))
        by_track = {}
        if tracks:
            L += ["", "| track | tests | fail before | fail now | fixed since | new fail |", "|---|---|---|---|---|---|"]
            for t, ns in tracks.items():
                row = {"tests": len(ns), "before": sum(n in of for n in ns), "now": sum(n in nf for n in ns),
                       "fixed": sum(n in of and new.status.get(n) == "ok" for n in ns),
                       "new": sum(n in nf and n not in of for n in ns)}
                by_track[t] = row
                L.append(f"| {t} | {row['tests']} | {row['before']} | {row['now']} | {row['fixed']} | {row['new']} |")
            for t, ns in tracks.items():
                fails = [n for n in ns if n in nf]
                fixed = [n for n in ns if n in of and new.status.get(n) == "ok"]
                gone = [n for n in ns if n not in new.status]
                L += ["", f"## {t}: {len(ns)} tests, {len(fails)} failing, {len(fixed)} fixed since, {len(gone)} not run", ""]
                for n in fails:
                    f = new.failures.get(n)
                    where = f"{f.site} {f.message}".strip() if f else ""
                    L.append(f"- FAIL{' (new)' if n not in of else ''} `{n}`: {where or '(no panic line found)'}")
                L += [f"- not run `{n}`" for n in gone]
                if fixed:
                    L.append("- fixed: " + ", ".join(f"`{short(n)}`" for n in fixed))
        L += ["", f"## New failures ({len(new_fail)})", ""]
        blame: dict[str, list[str]] = {}
        for n in new_fail:
            t, why = attribute(n, new, tracks, changes)
            f = new.failures.get(n)
            was = "absent before" if n not in old.status else "passed before"
            L.append(f"- `{n}` ({was}){': ' + f.site + ' ' + f.message if f and f.site else ''}. "
                     f"{('Track ' + t + ', ') if t else ''}{why}")
            if t:
                blame.setdefault(t, []).append(n)
        owned = {n for ns in tracks.values() for n in ns}
        if tracks:
            loose = sorted(n for n in nf if n not in owned and n not in new_fail)
            L += ["", f"## Failing now outside every track, not new ({len(loose)})", ""]
            L += [f"- `{n}`{' (baseline)' if in_base(n) else ''}" for n in loose]
        if old_label:
            back = sorted(n for n in of if n not in nf and n not in owned)
            L += ["", f"## Earlier failures outside the tracks that pass or are gone now ({len(back)})", ""]
            L += [f"- `{n}`: {'pass' if new.status.get(n) == 'ok' else 'not run'}" for n in back]
            fresh = [n for n in new.status if n not in old.status]
            L += ["", f"## Tests new since {old_label} ({len(fresh)}): {sum(new.status[n] == 'ok' for n in fresh)} pass, "
                  f"{sum(n in nf for n in fresh)} fail"]
        report = "\n".join(L) + "\n"

        out = Path(a.out) if a.out else (new_log.parent / "compare.md" if new_log.parent.is_relative_to(runs) else None)
        if out:
            out.write_text(report)
        sys.stdout.write(report)

        summary = (f"{len(nf)} failing, {new.passed} passing, {len(new_fail)} new" +
                   (f" against {old_label} ({len(of)} failing)" if old_label else ""))
        data = {"new": len(new_fail), "fail_before": len(of) if old_label else None, "by_track": by_track or None}
        if a.round is not None:
            track.round(a.round, new.passed, len(nf), log=str(new_log), data=data)
        else:
            track.event("compare", summary, data=data, links={"report": str(out)} if out else None)
        for t, ns in blame.items():
            track.event("new-failures", f"{len(ns)} new failures attributed to track {t}: "
                        + ", ".join(short(n) for n in ns[:8]), task=f"{a.task_prefix}{t}",
                        links={"report": str(out)} if out else None)
        rec.result(summary, log=str(out) if out else None)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            sys.exit(2)
        raise

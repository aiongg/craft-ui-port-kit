#!/usr/bin/env python3
"""diag-cut.py: cut one return packet per red-round fixer out of a full test run's log.

usage: diag-cut.py RUN --tracks SRC [--out DIR] [--task-prefix P] [--config PORT.TOML]

RUN is a run label (a directory under work.runs), a run directory or a log file (libtest or nextest output; see
tools/portkit/testlog.py). --tracks names which tests each fixer owns: the split-failures.py output directory, the
round's groups.md (one `## <track>` section per track) or a `track<TAB>test` TSV.

Fixers write `eprintln!("DIAG <test fn name>: ...")` where reading left a cause uncertain (prompts/p7-red-fixer.md).
For each track, the packet <out>/<track>.md holds:
  - the tests of its list that still fail, each with its ledger verdict (plan or triage, its set and a `move`
    target, from <work.runs>/ledger.tsv when it exists), its binary, panic site, panic message and every
    `DIAG <test fn name>` line of the run;
  - the tests that pass now (their DIAG prints are to be removed) and the tests that did not run.
The default out dir is <run dir>/packets. A summary line per track goes to stdout, then the DIAG idents that name
no test of any track (prints a fixer left behind, or a misspelt name).

Dashboard: each packet is linked on its track's task (`<P><track>`, --task-prefix) with a `packet` event.
Exit 0; 2 when the log or the tracks cannot be read.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, track  # noqa: E402
from portkit.testlog import find_log, load_tracks, parse, resolve, short  # noqa: E402


def ledger_verdicts(runs: Path) -> dict[str, str]:
    """{test name: "<verdict> (set <set>)[, to <target>]"} from <work.runs>/ledger.tsv (tools/test-ledger.py)."""
    f = runs / "ledger.tsv"
    if not f.is_file():
        return {}
    lines = f.read_text().splitlines()
    cols = lines[0].split("\t") if lines else []
    out = {}
    for line in lines[1:]:
        r = dict(zip(cols, line.split("\t")))
        v = r.get("verdict") or "no verdict (keep)"
        out[r.get("test", "")] = (f"{v}" + (f" (set {r['set']})" if r.get("set") else "")
                                  + (f", from triage" if r.get("source") == "triage" else "")
                                  + (f", to {r['target']}" if r.get("target") else ""))
    return out


def packet(t: str, label: str, names: list[str], run, verdicts: dict | None = None) -> tuple[str, dict]:
    fails = [n for n in names if run.status.get(n) == "FAILED"]
    passing = [n for n in names if run.status.get(n) == "ok"]
    ignored = [n for n in names if run.status.get(n) == "ignored"]
    gone = [n for n in names if n not in run.status]
    L = [f"# Return packet: track {t}, run {label}", "",
         f"{len(fails)} of the {len(names)} tests on your list still fail; {len(passing)} pass; "
         f"{len(gone)} did not run" + (f"; {len(ignored)} are ignored" if ignored else "") + ".", ""]
    L += [f"## Still failing ({len(fails)})", ""]
    for n in fails:
        f = run.failures.get(n)
        diag = run.diag.get(short(n), [])
        L += [f"### {n}", *([f"verdict: {verdicts[n]}"] if verdicts and n in verdicts else []),
              f"binary: {f.binary if f and f.binary else '(unknown)'}",
              f"panic: {f.site if f and f.site else '(no panic line captured)'}",
              f"message: {f.message if f else ''}"]
        if diag:
            L += [f"DIAG lines ({len(diag)}):", "```", *diag, "```"]
        else:
            L.append("DIAG lines: none")
        L.append("")
    if passing:
        L += [f"## Passing now ({len(passing)}): remove their DIAG prints", ""]
        L += [f"- `{n}`" + (f" ({len(run.diag[short(n)])} DIAG lines)" if short(n) in run.diag else "") for n in passing]
        L.append("")
    if gone:
        L += [f"## Did not run ({len(gone)})", "", *(f"- `{n}`" for n in gone), ""]
    if ignored:
        L += [f"## Ignored ({len(ignored)})", "", *(f"- `{n}`" for n in ignored), ""]
    return "\n".join(L), {"tests": len(names), "failing": len(fails), "passing": len(passing), "not_run": len(gone)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--tracks", required=True)
    ap.add_argument("--out")
    ap.add_argument("--task-prefix", default="")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    runs = Path(cfg.get("work.runs"))

    with track.recorded("diag-cut") as rec:
        log = find_log(a.run, runs)
        run = parse(log)
        tracks = {t: resolve(ns, run) for t, ns in load_tracks(Path(a.tracks)).items()}
        if not tracks:
            raise SystemExit(f"diag-cut: no tracks found in {a.tracks}")
        out = Path(a.out) if a.out else log.parent / "packets"
        out.mkdir(parents=True, exist_ok=True)
        label = log.parent.name if log.name == "app.log" else log.name
        total = 0
        verdicts = ledger_verdicts(runs)
        for t, names in tracks.items():
            text, n = packet(t, label, names, run, verdicts)
            p = out / f"{t}.md"
            p.write_text(text)
            total += n["failing"]
            print(f"{t}: {n['failing']} still failing of {n['tests']}, {n['passing']} passing, {n['not_run']} not run -> {p}")
            track.event("packet", f"return packet: {n['failing']} of {n['tests']} still failing, {n['passing']} pass",
                        task=f"{a.task_prefix}{t}", data=n, links={"packet": str(p)})
        known = {short(n) for ns in tracks.values() for n in ns}
        stray = sorted(i for i in run.diag if i not in known)
        if stray:
            print(f"DIAG idents that name no test of any track ({len(stray)}): {', '.join(stray)}")
        rec.result(f"{len(tracks)} packets in {out}, {total} tests still failing, {len(stray)} stray DIAG idents",
                   log=str(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            sys.exit(2)
        raise

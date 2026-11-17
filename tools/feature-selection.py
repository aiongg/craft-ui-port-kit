#!/usr/bin/env python3
"""feature-selection.py: derive the app's package selection for cl's app mode, with no compile.

usage: feature-selection.py [APP_DIR] [--shared CRATE]... [--exclude PACKAGE]... [--offline] [--json]
                            [--config PORT.TOML]

cl builds every app command with one fixed set of workspace packages, the selection (`selection` in
`[workspace.metadata.cl]`, process/11-build-loop.md). Cargo unifies a crate's features over the packages a command
selects, so a command that selects fewer packages builds a second copy of every shared crate whose features change,
and of everything above it. The selection is every workspace package that contributes a feature to a shared crate.

Shared crates: egui, eframe, the framework facade (framework.facade) and each --shared CRATE (the app's I/O crates,
for example). For each workspace member this runs `cargo tree -p MEMBER -e normal,build,dev` and reads the features
the member turns on in each shared crate. It prints:

  - per shared crate, the features each member turns on, and their union (what the selection builds);
  - the selection: members that reach at least one shared crate;
  - members outside it (they reach no shared crate) and members left out with --exclude;
  - other crates whose features differ between members (candidates for `tracked`: a command that misses one of
    those members rebuilds them);
  - a `[workspace.metadata.cl]` block with `selection` and `tracked`. `expected_features` is shown as a comment:
    copy the real sets from `cl doctor` after the first warm build.

APP_DIR defaults to app.integration from port.toml. `cargo metadata` and `cargo tree` resolve dependencies from
Cargo.lock and compile nothing, but resolution may need the network (to fetch the registry index or git
dependencies). --offline passes --offline to both and works when the dependencies are already fetched. CARGO names the cargo binary (default: cargo).
Exit 2 when cargo fails (the message names the command).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config  # noqa: E402

DEFAULT_SHARED = ["egui", "eframe"]


def cargo(args: list[str], cwd: str) -> str:
    exe = os.environ.get("CARGO", "cargo")
    try:
        r = subprocess.run([exe, *args], cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        raise SystemExit(f"feature-selection: cannot run {exe}: {e}")
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["(no output)"])[-1]
        raise SystemExit(f"feature-selection: `cargo {' '.join(args)}` failed in {cwd}: {tail}")
    return r.stdout


def member_features(ws: str, member: str, offline: list[str]) -> dict[str, set[str]]:
    """Package name -> features turned on, in the graph of one member (normal, build and dev edges)."""
    out = cargo(["tree", *offline, "-p", member, "-e", "normal,build,dev", "--prefix", "none", "-f", "{p}|{f}"], ws)
    feats: dict[str, set[str]] = {}
    for line in out.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        p, _, f = line.partition("|")
        f = f.removesuffix("(*)").strip()
        name = p.split(" ", 1)[0]
        feats.setdefault(name, set()).update(x for x in f.split(",") if x)
    return feats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("app_dir", nargs="?")
    ap.add_argument("--shared", action="append", default=[], metavar="CRATE")
    ap.add_argument("--exclude", action="append", default=[], metavar="PACKAGE")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args(argv)

    cfg = None
    try:
        cfg = config.load(a.config)
    except config.ConfigError as e:
        if not a.app_dir:
            raise SystemExit(f"feature-selection: {e}")
    ws = a.app_dir or (cfg.get("app.integration") if cfg else None)
    if not ws:
        raise SystemExit("feature-selection: give APP_DIR, or set app.integration (or app.checkout) in port.toml")
    facade = cfg.get("framework.facade") if cfg else "craft"
    shared = list(dict.fromkeys([*DEFAULT_SHARED, facade, *a.shared]))
    offline = ["--offline"] if a.offline else []

    meta = json.loads(cargo(["metadata", *offline, "--format-version", "1", "--no-deps"], ws))
    ids = set(meta.get("workspace_members") or [])
    members = sorted(p["name"] for p in meta["packages"] if not ids or p["id"] in ids)
    unknown = [x for x in a.exclude if x not in members]
    if unknown:
        raise SystemExit(f"feature-selection: --exclude names no workspace member: {', '.join(unknown)}")

    per: dict[str, dict[str, set[str]]] = {m: member_features(ws, m, offline) for m in members}
    selection, outside = [], []
    for m in members:
        if m in a.exclude:
            continue
        (selection if any(s in per[m] for s in shared if s != m) else outside).append(m)

    shared_report = {}
    for s in shared:
        rows = {m: sorted(per[m][s]) for m in selection if s in per[m]}
        if rows:
            shared_report[s] = {"members": rows, "union": sorted(set().union(*map(set, rows.values())))}
    missing_shared = [s for s in shared if s not in shared_report]

    differing = []
    names = set().union(*(per[m].keys() for m in selection)) if selection else set()
    for n in sorted(names - set(shared) - set(members)):
        sets = {frozenset(per[m][n]) for m in selection if n in per[m]}
        if len(sets) > 1:
            differing.append(n)

    tracked = [s for s in shared if s in shared_report]
    if a.json:
        print(json.dumps({"workspace": str(Path(ws).resolve()), "shared": shared_report, "selection": selection,
                          "outside": outside, "excluded": a.exclude, "differing": differing,
                          "shared_not_found": missing_shared, "tracked": tracked}, indent=2))
        return 0

    print(f"# workspace: {Path(ws).resolve()} ({len(members)} members)")
    for s, r in shared_report.items():
        print(f"\n## {s}: union {{{', '.join(r['union'])}}}")
        for m, f in r["members"].items():
            print(f"  {m}: {{{', '.join(f)}}}")
    if missing_shared:
        print(f"\nShared crates no member reaches: {', '.join(missing_shared)}")
    print(f"\nSelection ({len(selection)}): {', '.join(selection) or '(none)'}")
    print(f"Outside (reach no shared crate): {', '.join(outside) or '(none)'}")
    if a.exclude:
        print(f"Excluded: {', '.join(a.exclude)}")
    if differing:
        print(f"Features differ between members ({len(differing)}): {', '.join(differing)}")
    q = lambda xs: "[" + ", ".join(json.dumps(x) for x in xs) + "]"  # noqa: E731
    print("\n[workspace.metadata.cl]")
    print(f"selection = {q(selection)}")
    print(f"tracked = {q(tracked)}")
    print("# expected_features: copy the sets `cl doctor` reports after the first warm build. Projection:")
    for s, r in shared_report.items():
        print(f"#   {s} = {q(r['union'])}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            sys.exit(2)
        raise

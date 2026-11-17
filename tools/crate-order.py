#!/usr/bin/env python3
"""crate-order.py: print workspace crates in dependency order, dependencies first, with no build.

usage: crate-order.py WORKSPACE_DIR CRATE...

Reads `cargo metadata --no-deps` in WORKSPACE_DIR (it resolves nothing and needs no network) and orders the given
workspace packages so that every crate comes after the workspace crates it depends on, directly or through other
workspace crates not in the list. Normal and build dependencies count; dev-dependencies do not, because a test-only
edge does not decide which crate's errors come first and dev-dependencies may form cycles. Crates with no order
between them keep the order they were given in.

A crate may be named by its package name or its library name (`craft_ui` for `craft-ui`). Prints one package name
per line. Exit 2 for an unknown crate, a dependency cycle or a failed `cargo metadata` (the message names it);
compile-gate then uses the order it was given. CARGO names the cargo binary (default: cargo).
"""
import json
import os
import subprocess
import sys


def metadata(ws: str) -> dict:
    cargo = os.environ.get("CARGO", "cargo")
    try:
        r = subprocess.run([cargo, "metadata", "--format-version", "1", "--no-deps"], cwd=ws, capture_output=True,
                           text=True)
    except OSError as e:
        raise SystemExit(f"crate-order: cannot run {cargo}: {e}")
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["(no output)"])[-1]
        raise SystemExit(f"crate-order: cargo metadata failed in {ws}: {tail}")
    return json.loads(r.stdout)


def graph(meta: dict) -> tuple[list[str], dict[str, set[str]], dict[str, str]]:
    """Workspace package names in metadata order, their workspace dependencies, and lib-name aliases."""
    members = set(meta.get("workspace_members") or [])
    pkgs = [p for p in meta["packages"] if not members or p["id"] in members]
    names = [p["name"] for p in pkgs]
    known = set(names)
    deps: dict[str, set[str]] = {}
    alias: dict[str, str] = {}
    for p in pkgs:
        deps[p["name"]] = {d["name"] for d in p.get("dependencies", [])
                           if d.get("kind") in (None, "build") and d["name"] in known and d["name"] != p["name"]}
        alias[p["name"].replace("-", "_")] = p["name"]
        for t in p.get("targets", []):
            if any(k in ("lib", "rlib", "proc-macro", "cdylib", "dylib", "staticlib") for k in t.get("kind", [])):
                alias[t["name"]] = p["name"]
    return names, deps, alias


def order(names: list[str], deps: dict[str, set[str]], wanted: list[str]) -> list[str]:
    """Topological order of the whole workspace graph, filtered to `wanted`; ties go to the given order."""
    rank = {n: i for i, n in enumerate(wanted)}
    rank_of = lambda n: (rank.get(n, len(rank)), names.index(n))  # noqa: E731
    remaining = {n: set(deps[n]) for n in names}
    out: list[str] = []
    while remaining:
        ready = sorted((n for n, d in remaining.items() if not d), key=rank_of)
        if not ready:
            cyc = sorted(remaining)
            raise SystemExit(f"crate-order: dependency cycle among: {', '.join(cyc[:10])}")
        n = ready[0]   # one at a time, so a wanted crate is placed as soon as its dependencies allow
        out.append(n)
        del remaining[n]
        for d in remaining.values():
            d.discard(n)
    want = set(wanted)
    return [n for n in out if n in want]


def main(argv: list[str]) -> int:
    if len(argv) < 1 or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    ws, crates = argv[0], argv[1:]
    if not crates:
        return 0
    names, deps, alias = graph(metadata(ws))
    wanted, unknown = [], []
    for c in crates:
        n = c if c in deps else alias.get(c)
        if n is None:
            unknown.append(c)
        elif n not in wanted:
            wanted.append(n)
    if unknown:
        print(f"crate-order: not a package of the workspace in {ws}: {', '.join(unknown)}", file=sys.stderr)
        return 2
    for n in order(names, deps, wanted):
        print(n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            sys.exit(2)
        raise

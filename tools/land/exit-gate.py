#!/usr/bin/env python3
"""exit-gate.py: the phase 8 exit rows the landing tools run before they clone anything.

usage: exit-gate.py app|framework SHA

Runs the rows of PHASE_EXITS in tools/portkit/gates.py that belong to a landing group (LAND_GROUPS):
  look   every map section has a states file, every state has a pair captured from SHA (the commit the tool lands)
         and the other integration tree's HEAD, every difference is fixed or kept with a reason, every panel is
         accepted;
  tests  every test gone since the baseline has a `delete` verdict or a `move` target that passes
         (tools/test-ledger.py --check).
Each group passes when its rows pass, or when the latest `track phase 9 --force "reason"` was recorded over every
row that fails now; it prints that decision. The override is that one recorded decision; the landing tools take no
flag of their own. `framework` before phase 8 passes with a note: framework changes may land after any build batch
(process/10-land.md).
In a minimal port (work.mode = minimal) it runs the run gate instead: the app commit must have passed the run step
on every platform of minimal.run_platforms (`run` events with data platform, sha, result and optional row; a later row event replaces an earlier one, `track correct` replaces a result; every one must be pass or na, with at least one pass; process/minimal-port.md,
step 7); a framework fix passes. Exit 0 pass; 1 refused (one line per failing row); 2 usage or no workspace.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portkit import gates, track  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("app", "framework"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        store = track.open_store(required=True)
    except Exception as e:
        print(f"exit-gate: {e}", file=sys.stderr)
        return 2
    if store.cfg.get("work.mode") == "minimal":
        ok, lines = gates.minimal_land_check(store, argv[1], argv[2])
        for ln in lines:
            print(ln, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    all_ok = True
    for group in gates.LAND_GROUPS:
        ok, lines = gates.land_check(store, argv[1], argv[2], group)
        for ln in lines:
            print(ln, file=sys.stdout if ok else sys.stderr)
        all_ok = all_ok and ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

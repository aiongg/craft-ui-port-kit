#!/usr/bin/env python3
"""check-landed.py: build the landed clone clean before any push command prints.

usage: check-landed.py CLONE

Runs the framework's `cl check all` (build.cl) in CLONE, the scratch clone a landing tool prepared, through the same
launcher, memory cap and target dir as compile-gate. Exit 0 when it passes; 1 when it fails (the log is
`CLONE.check.log`); 2 when it cannot run: build.cl or framework.checkout is unset or missing. A landing tool never
treats 2 as a pass: its caller must give `--skip-check "reason"` to go on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portkit import config, gates  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    clone = Path(argv[1])
    cfg = config.load()
    fw, cl = cfg.get("framework.checkout"), cfg.get("build.cl")
    if not fw or not Path(fw).is_dir():
        print("check-landed: framework.checkout is unset or missing: cl cannot be found", file=sys.stderr)
        return 2
    if not cl or not Path(cl).is_file():
        print(f"check-landed: build.cl names no file ({cl})", file=sys.stderr)
        return 2
    log = Path(f"{clone}.check.log")
    print(f"cl check all in {clone} (log: {log})")
    rc = gates.run_logged(gates.cl(cfg, ["check", "all", "--message-format", "short"]), clone, log, gates.cl_env(cfg))
    if rc:
        print(f"check-landed: cl check all failed (exit {rc}); last lines:", file=sys.stderr)
        print("".join(log.read_text(errors="replace").splitlines(True)[-15:]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

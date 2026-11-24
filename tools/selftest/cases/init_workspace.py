"""init-workspace in minimal mode: a live [minimal] table, and no warning about the framework's cl."""
from __future__ import annotations

import tomllib

from lib import check


def case_minimal_mode(s):
    ws = s.root / "ws"
    fw = s.tree("fw", {"Cargo.toml": "\n"})   # no tools/cl in it
    p = s.run("init-workspace", str(ws), "--mode", "minimal", "--framework", str(fw), "--app-name", "demo")
    toml = tomllib.loads((ws / "port.toml").read_text())
    check(toml.get("work", {}).get("mode") == "minimal", "work.mode is minimal", p)
    check(toml.get("minimal", {}).get("run_platforms") == ["linux", "macos"], "an uncommented [minimal] table names run_platforms", p)
    check("the framework's cl" not in p.stdout + p.stderr, "a minimal port is not warned about a missing cl", p)

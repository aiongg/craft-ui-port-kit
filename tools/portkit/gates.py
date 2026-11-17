"""Helpers shared by compile-gate, test-run and racheck-gate: run directory, the cl command line, logged runs."""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import tomllib
from pathlib import Path

ERROR_LINE = re.compile(r"^[^ ]+\.rs:[0-9]+:[0-9]+: error")


def run_dir(cfg, label: str) -> Path:
    """<work.runs>/<label>/, created. One directory per run label holds every log of the run."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", label):
        raise SystemExit(f"run label {label!r}: use letters, digits, dot, dash and underscore")
    d = cfg.path("work.runs") / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def cl_env(cfg, base=None) -> dict:
    """Environment for cl: the launcher and runner roles (empty means run directly) and the target dir."""
    env = dict(os.environ if base is None else base)
    env["CL_LAUNCHER"] = cfg.get("build.launcher") or ""
    env["CL_RUNNER"] = cfg.get("build.runner") or ""
    target = cfg.get("build.target_dir")
    if target:
        env["CARGO_TARGET_DIR"] = str(target)
    return env


def capped(cfg, cmd: list[str]) -> list[str]:
    """cmd under build.memory_cap with {gb} = build.memory_gb; unchanged when no cap is configured."""
    cap = cfg.get("build.memory_cap") or ""
    if not cap:
        return cmd
    return shlex.split(cap.replace("{gb}", str(cfg.get("build.memory_gb")))) + cmd


def cl(cfg, args: list[str]) -> list[str]:
    """The command line for one cl call, under the memory cap."""
    return capped(cfg, [str(cfg.path("build.cl")), *args])


def run_logged(cmd: list[str], cwd: Path, log: Path, env: dict) -> int:
    """Run cmd with stdout and stderr appended to log; its exit status."""
    with open(log, "ab") as f:
        f.write(("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n").encode())
        f.flush()
        return subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


def error_lines(log: Path) -> list[str]:
    """Sorted unique `file.rs:line:col: error ...` lines of a cargo `--message-format short` log."""
    if not log.is_file():
        return []
    return sorted({l.rstrip("\n") for l in open(log, errors="replace") if ERROR_LINE.match(l)})


def package_of(tree: Path, rel: str) -> str | None:
    """Cargo package name owning the file `rel` of the tree: the nearest Cargo.toml above it that has a [package]."""
    d = (tree / rel).parent
    while True:
        m = d / "Cargo.toml"
        if m.is_file():
            try:
                name = tomllib.loads(m.read_text()).get("package", {}).get("name")
            except tomllib.TOMLDecodeError:
                name = None
            if name:
                return name
        if d == tree or d == d.parent:
            return None
        d = d.parent


def changed_files(tree: Path, base: str, suffix: str | None = None) -> list[str]:
    """Files added, modified or renamed between `base` and HEAD in the tree."""
    out = subprocess.run(["git", "-C", str(tree), "diff", "--name-only", "--diff-filter=AMR", base, "HEAD"],
                         capture_output=True, text=True, check=True).stdout.split()
    return [f for f in out if not suffix or f.endswith(suffix)]


if __name__ == "__main__":
    # `gates.py packages TREE < paths`: the cargo packages owning the given files, one per line, sorted.
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "packages":
        tree = Path(sys.argv[2]).resolve()
        print("\n".join(sorted({p for f in sys.stdin.read().split() if (p := package_of(tree, f))})))
    else:
        raise SystemExit("usage: gates.py packages TREE < paths")

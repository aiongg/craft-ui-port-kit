"""The processes a look run starts (Xvfb servers and apps), recorded so a killed run leaves none behind.

`tools/look` calls `use(run_dir)` once; `Display.start` and `control.launch` then record each process they start in
<run_dir>/procs/<pid>.json, and `Display.stop` and `App.quit` remove the record. A run killed in the middle leaves its
records. The next `look` start calls `reap`: every record whose owner process is gone gets its process group stopped
(SIGTERM, then SIGKILL) and its record removed. `prune_workdirs` then empties the launch workdirs no live process uses.
Without `use`, every call does nothing, so a driver also works outside `look`.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import time
from pathlib import Path

_dir: Path | None = None
KEEP = ("app.log", "shots")     # what a finished launch workdir keeps: the log and the captured images


def use(run_dir: Path) -> None:
    global _dir
    _dir = Path(run_dir) / "procs"
    _dir.mkdir(parents=True, exist_ok=True)


def _start_time(pid: int) -> str | None:
    """The process's start time (Linux /proc field 22), which tells a reused pid from the original process."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def alive(pid: int, start: str | None) -> bool:
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return start is None or _start_time(pid) == start


def record(kind: str, pid: int, workdir: Path | None = None) -> None:
    if _dir is None:
        return
    rec = {"kind": kind, "pid": pid, "start": _start_time(pid), "owner": os.getpid(), "owner_start": _start_time(os.getpid()),
           "workdir": str(workdir) if workdir else None}
    (_dir / f"{pid}.json").write_text(json.dumps(rec))


def forget(pid: int) -> None:
    if _dir is not None:
        (_dir / f"{pid}.json").unlink(missing_ok=True)


def _records() -> list[tuple[Path, dict]]:
    out = []
    for f in sorted((_dir or Path("/nonexistent")).glob("*.json")):
        try:
            out.append((f, json.loads(f.read_text())))
        except (OSError, ValueError):
            f.unlink(missing_ok=True)
    return out


def _stop(rec: dict) -> None:
    pid = rec["pid"]
    if not alive(pid, rec.get("start")):
        return
    for sig, wait in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 2.0)):
        try:
            os.killpg(pid, sig)       # started with start_new_session: the group is the process and its children
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                return
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if not alive(pid, rec.get("start")):
                return
            time.sleep(0.05)


def reap() -> list[str]:
    """Stop the processes of runs that died; the kinds and pids stopped, as text."""
    done = []
    for f, rec in _records():
        if alive(rec["owner"], rec.get("owner_start")):
            continue
        if alive(rec["pid"], rec.get("start")):
            _stop(rec)
            done.append(f"{rec['kind']} {rec['pid']}")
        f.unlink(missing_ok=True)
    return done


def prune_workdirs(run_dir: Path) -> int:
    """Empty every launch workdir (`<run_dir>/<panel>/<side>`) that no live recorded process uses, except `KEEP`:
    session, profile and config dirs of finished or killed launches. The next launch makes what it needs."""
    in_use = {rec["workdir"] for _, rec in _records() if rec.get("workdir") and alive(rec["pid"], rec.get("start"))}
    n = 0
    for wd in Path(run_dir).glob("*/*"):
        if not wd.is_dir() or wd.parent.name == "procs" or str(wd) in in_use or wd.name == "shots":
            continue
        for item in wd.iterdir():
            if item.name in KEEP:
                continue
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
            n += 1
    return n

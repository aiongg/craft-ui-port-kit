"""A look run killed in the middle leaves its Xvfb and app processes; the next run stops them and empties the launch
workdirs that no live process uses."""
import os
import signal
import subprocess
import sys
import time

from lib import TOOLS, check

OWNER = '''
import subprocess, sys, time
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from portkit.look import procs
procs.use(Path(sys.argv[2]))
child = subprocess.Popen(["sleep", "300"], start_new_session=True)
procs.record("xvfb", child.pid, Path(sys.argv[2]) / "Panel" / "up")
print(child.pid, flush=True)
time.sleep(300)
'''


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()[:1] != "Z"


def case_next_run_stops_what_a_killed_run_left(s):
    run_dir = s.root / "run"
    wd = run_dir / "Panel" / "up"
    (wd / "cfg").mkdir(parents=True)
    (wd / "cfg" / "session.bin").write_text("x")
    (wd / "app.log").write_text("log\n")
    owner = subprocess.Popen([sys.executable, "-I", "-c", OWNER, str(TOOLS), str(run_dir)], stdout=subprocess.PIPE, text=True)
    pid = int(owner.stdout.readline())
    try:
        owner.kill()
        owner.wait()
        check(alive(pid), "the killed run left its process behind")
        sys.path.insert(0, str(TOOLS))
        from portkit.look import procs
        procs.use(run_dir)
        check(procs.prune_workdirs(run_dir) == 0 and (wd / "cfg").exists(), "a workdir a live process uses is kept")
        stopped = procs.reap()
        time.sleep(0.2)
        check(stopped == [f"xvfb {pid}"] and not alive(pid), f"the next run stops it: {stopped}")
        check(not list((run_dir / "procs").glob("*.json")), "its record is gone")
        procs.prune_workdirs(run_dir)
        check(not (wd / "cfg").exists() and (wd / "app.log").exists(), "the workdir is emptied except the log")
    finally:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass

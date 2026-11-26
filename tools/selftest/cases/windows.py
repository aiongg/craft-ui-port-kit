"""Platform gaps: racheck without AF_UNIX, track without fcntl and with a held target file, swarm decoding UTF-8 under
a non-UTF-8 locale, SCIP paths with backslashes, combine-area without process substitution."""
import json
import os
import sqlite3
import subprocess
import sys

from lib import TOOLS, check


def py(s, code, env=None):
    """Run `code` with tools/ importable, in the scratch workspace's config."""
    pre = f"import sys; sys.path.insert(0, {str(TOOLS)!r})\n"
    s.last = subprocess.run([sys.executable, "-c", pre + code], capture_output=True, text=True,
                            env={**s.env, **(env or {})}, cwd=str(s.work))
    return s.last


def case_racheck_tcp_without_af_unix(s):
    p = py(s, """
import socket
del socket.AF_UNIX
import racheck
from portkit import config
cfg = config.load(None)
cfg.path("racheck.sockets").mkdir(parents=True)
srv = racheck.listen(cfg, "fw")
port_file = racheck.port_path(cfg, "fw")
assert open(port_file).read() == str(srv.getsockname()[1]), "port file holds the port"
assert racheck.endpoint_path(cfg, "fw") == port_file
import threading
def serve():
    c, _ = srv.accept(); c.recv(1 << 16); c.sendall(b'{"ok": true}\\n'); c.close()
threading.Thread(target=serve, daemon=True).start()
assert racheck.query(cfg, "fw", {"op": "status"}) == {"ok": True}
import os; os.unlink(port_file)
assert racheck.query(cfg, "fw", {}) is None, "no port file: no daemon"
print("ok")
""")
    check(p.returncode == 0 and "ok" in p.stdout, "tcp fallback round trip", p)


def case_track_windows_locking_and_replace(s):
    p = py(s, """
import os
from pathlib import Path
from portkit import track
track.fcntl = None
calls = []
class M:
    LK_LOCK, LK_UNLCK = 1, 0
    @staticmethod
    def locking(fd, mode, n):
        calls.append(mode)
        if len(calls) == 1:
            raise OSError("held")
track.msvcrt = M
with open("lockfile", "a") as f:
    track._lock(f); track._unlock(f)
assert calls == [1, 1, 0], calls
real, fails = os.replace, [2]
def flaky(a, b):
    if fails[0]:
        fails[0] -= 1
        raise PermissionError(13, "in use")
    return real(a, b)
track.os.replace = flaky
track._write_atomic(Path("out.json"), "{}")
assert Path("out.json").read_text() == "{}" and fails[0] == 0
print("ok")
""")
    check(p.returncode == 0 and "ok" in p.stdout, "msvcrt lock and replace retry", p)


def case_swarm_decodes_utf8_in_ascii_locale(s):
    (s.root / "claude").mkdir(exist_ok=True)
    (s.root / "claude" / "utf8").write_text("")
    (s.root / "claude" / "reply.txt").write_text("café")
    (s.work / "jobs.json").write_text(json.dumps([{"task": "t1", "prompt": "hi", "role": "red_fixer"}]))
    env = {**s.env, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "PYTHONIOENCODING": "utf-8"}
    s.last = subprocess.run([sys.executable, str(TOOLS / "swarm.py"), "jobs.json"], capture_output=True, text=True,
                            env=env, cwd=str(s.work))
    outs = list(s.work.rglob("*.out"))
    check(s.last.returncode == 0 and outs and "café" in outs[0].read_text(encoding="utf-8"),
          "the reply is decoded as UTF-8", s.last)


def case_scip_backslash_paths(s):
    db = s.work / "fw.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table occ (name text, qual text, crate text, path text, line int, def int)")
    con.execute("insert into occ values ('Foo', 'Bar', 'c', 'crates\\ui\\src\\lib.rs', 3, 1)")
    con.commit()
    con.close()
    p = py(s, f"""
from pathlib import Path
from portkit.portset import scip
scip.ctx.scip_dir = Path({str(s.work)!r})
c = scip.con("fw")
print(c.execute("select path from occ where path like 'crates/%'").fetchall())
""")
    check(p.returncode == 0 and "crates/ui/src/lib.rs" in p.stdout, "backslash paths read as /", p)


def case_combine_area_has_no_process_substitution(s):
    text = (TOOLS / "combine-area").read_text()
    check("<(" not in text, "combine-area runs in Git Bash: no process substitution")

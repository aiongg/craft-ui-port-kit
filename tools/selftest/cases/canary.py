"""Writer canary: run-area refuses to start unless each repo's racheck daemon reports 0 errors on an untouched file."""
import json
import socketserver
import threading

from lib import check


def daemon(s, diagnostics):
    """A stand-in racheck daemon on the fw socket that answers every request with `diagnostics`."""
    class H(socketserver.StreamRequestHandler):
        def handle(self):
            self.rfile.readline()
            self.wfile.write((json.dumps({"ok": True, "diagnostics": diagnostics, "files": [], "seconds": 0}) + "\n").encode())
    srv = socketserver.UnixStreamServer(str(s.work / "trees" / "racheck-fw.sock"), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def setup(s):
    root = s.work / "trees" / "racheck-fw"
    (root / "crates" / "craft" / "src").mkdir(parents=True)
    (root / "crates" / "craft" / "src" / "lib.rs").write_text("pub use craft_ui::*;\n")
    (s.work / "plan" / "sheets").mkdir(parents=True)
    (s.work / "plan" / "sheets" / "set-a.md").write_text("# set-a\n\n- Repo: fw\n")
    (s.work / "shared.txt").write_text("")
    (s.work / "default.txt").write_text("")
    (s.work / "one.txt").write_text("set-a\n")


def case_refuses_without_daemon(s):
    setup(s)
    p = s.run("run-area", "pilot", "one.txt", "default.txt")
    check(p.returncode == 2 and "daemon died or is not running" in p.stdout and "writer canary failed" in p.stderr, "refuses", p)


def case_refuses_on_errors(s):
    setup(s)
    srv = daemon(s, [{"path": "crates/craft/src/lib.rs", "line": 1, "severity": "error", "code": "E0432",
                      "message": "unresolved import `craft_ui`"}])
    try:
        p = s.run("run-area", "pilot", "one.txt", "default.txt")
    finally:
        srv.shutdown()
    check(p.returncode == 2 and "canary fw: crates/craft/src/lib.rs: 1 errors" in p.stdout, "refuses on errors", p)


def case_starts_when_clean(s):
    setup(s)
    srv = daemon(s, [])
    try:
        p = s.run("run-area", "pilot", "shared.txt", "one.txt", env={"PATH": "/usr/bin:/bin"})
    finally:
        srv.shutdown()
    check("canary fw: crates/craft/src/lib.rs: 0 errors" in p.stdout and "writer canary failed" not in p.stderr,
          "a clean canary lets the batch start", p)


def case_daemon_dying_mid_reply_is_not_running(s):
    setup(s)

    class H(socketserver.StreamRequestHandler):
        def handle(self):
            self.rfile.readline()   # closes without a reply
    srv = socketserver.UnixStreamServer(str(s.work / "trees" / "racheck-fw.sock"), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        p = s.run("run-area", "pilot", "one.txt", "default.txt")
    finally:
        srv.shutdown()
    check(p.returncode == 2 and "daemon died or is not running" in p.stdout, "a closed socket is a dead daemon, no crash", p)

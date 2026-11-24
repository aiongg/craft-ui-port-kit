"""Talk to a craft app through its control channel (craft-automation), for look drivers.

The wire format is craft-automation's: one JSON request per line, `{"id", "method", "params"}`, and one reply per
line, `{"id", "ok", "result" | "error"}`. The first request authenticates: `auth {"token"}`. An app started with
`--control 0` picks a free port and prints `control server listening on 127.0.0.1:<port>`; `launch` reads that line
from the app's log. craft-libs docs/porting.md, "6.4 Compare old and new", describes the app side.

    from portkit.look import control
    app = control.launch("port", [binary, "--control", "0", "--control-token-file", str(work / "token")],
                         work, env={"DISPLAY": ":5"}, token_file=work / "token")
    app.call("ui.resize", {"width": 1440, "height": 900})
    control.run_steps(app, state["steps"])
    control.screenshot(app, "shot.png", write_root, out_png)
    app.quit()

Method names other than `auth`, `ui.screenshot` and `app.quit` are the app's own.
"""
from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path

from . import procs

LISTENING = r"control server listening on 127\.0\.0\.1:(\d+)"


class ControlError(RuntimeError):
    pass


class App:
    """One running app instance and its authenticated control connection."""

    def __init__(self, side: str, proc: subprocess.Popen, workdir: Path, log_path: Path):
        self.side, self.proc, self.work, self.log_path = side, proc, workdir, log_path
        self.sock: socket.socket | None = None
        self.f = None
        self.next_id = 1
        self.notes: list[str] = []   # optional steps that failed since the driver last took them (`look pair` prints them)
        self.extra: dict = {}        # driver state between shots (for example the setup that last ran)

    def connect(self, port: int, token: str | None, timeout: float = 90) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.f = self.sock.makefile("rw", encoding="utf-8", newline="\n")
        if token is not None:
            self.call("auth", {"token": token})

    def call(self, method: str, params: dict | None = None):
        """Send one request and return its result; a reply with `ok: false` raises ControlError."""
        if self.f is None:
            raise ControlError(f"{self.side}: not connected")
        i = self.next_id
        self.next_id += 1
        self.f.write(json.dumps({"id": i, "method": method, "params": params or {}}) + "\n")
        self.f.flush()
        while True:
            line = self.f.readline()
            if not line:
                raise ControlError(f"{self.side}: control connection closed during {method} (log: {self.log_path})")
            reply = json.loads(line)
            if reply.get("id") in (i, None):
                break
        if reply.get("ok") is not True:
            raise ControlError(f"{self.side}: {method}: {reply.get('error')}")
        return reply.get("result")

    def quit(self, method: str | None = "app.quit", wait: float = 15) -> None:
        """Ask the app to quit, then kill its process group if it is still running after `wait` seconds."""
        if method:
            try:
                self.call(method)
            except Exception:
                pass
        try:
            if self.sock is not None:
                self.sock.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                pass
            self.proc.wait()
        procs.forget(self.proc.pid)


def launch(side: str, argv: list[str], workdir: Path, env: dict | None = None, token_file: Path | None = None,
           token: str | None = None, ready: str = LISTENING, timeout: float = 120) -> App:
    """Start the app, wait for its control port line in the log, connect and authenticate.

    `workdir` must exist; the app's output goes to `<workdir>/app.log`. The token comes from `token`, or from
    `token_file` once the app has written it. The app runs in its own process group."""
    workdir = Path(workdir)
    log_path = workdir / "app.log"
    log = open(log_path, "wb")
    proc = subprocess.Popen([str(a) for a in argv], env={**os.environ, **(env or {})}, stdout=log,
                            stderr=subprocess.STDOUT, start_new_session=True, cwd=workdir)
    log.close()
    procs.record("app", proc.pid, workdir)
    app = App(side, proc, workdir, log_path)
    pat = re.compile(ready)
    port = None
    deadline = time.monotonic() + timeout
    try:
        while port is None:
            if proc.poll() is not None:
                raise ControlError(f"{side}: the app exited with status {proc.returncode} before it listened; "
                                   f"see {log_path}")
            if time.monotonic() > deadline:
                raise ControlError(f"{side}: no control port line within {timeout:.0f} s; see {log_path}")
            m = pat.search(log_path.read_text(errors="replace"))
            if m:
                port = int(m.group(1))
            else:
                time.sleep(0.3)
        if token is None and token_file is not None:
            while not Path(token_file).is_file() or not Path(token_file).read_text().strip():
                if time.monotonic() > deadline:
                    raise ControlError(f"{side}: no token in {token_file}")
                time.sleep(0.1)
            token = Path(token_file).read_text().strip()
        app.connect(port, token)
    except BaseException:
        app.quit(method=None, wait=2)
        raise
    return app


def run_steps(app: App, steps: list[dict]) -> None:
    """Send each step's request in order. `{"method": "@sleep", "params": {"seconds": S}}` waits instead. A step with
    `"optional": true` that fails is recorded in `app.notes` and the run goes on; any other failure raises."""
    for s in steps or []:
        m, p = s["method"], s.get("params") or {}
        if m == "@sleep":
            time.sleep(float(p.get("seconds", 1)))
        elif s.get("optional"):
            try:
                app.call(m, p)
            except ControlError as e:
                app.notes.append(f"optional step {m} failed: {e}")
        else:
            app.call(m, p)


def screenshot(app: App, name: str, write_root: Path, out_png: Path, params: dict | None = None,
               timeout: float = 10) -> dict:
    """`ui.screenshot {path: name}` (a path relative to the folder the app lets automation write to, `write_root`),
    then move the file to `out_png`. The reply gives the image's width and height."""
    src = Path(write_root) / name
    if src.exists():
        src.unlink()
    reply = app.call("ui.screenshot", {"path": name, **(params or {})}) or {}
    deadline = time.monotonic() + timeout
    last = -1
    while True:     # the file exists and its size held for one poll: the app finished writing it
        size = src.stat().st_size if src.exists() else -1
        if size > 0 and size == last:
            break
        if time.monotonic() > deadline:
            raise ControlError(f"{app.side}: ui.screenshot wrote no complete {src}")
        last = size
        time.sleep(0.1)
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    src.replace(out_png)
    return reply

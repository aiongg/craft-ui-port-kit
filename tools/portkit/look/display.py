"""A display for one app instance, for look drivers.

On Linux each instance gets its own Xvfb server. Xvfb picks a free display number itself (`-displayfd`), so two
instances started at the same moment never race for one number. On macOS and Windows the app opens a normal window
on the desktop, and this helper does nothing.

    from portkit.look.display import Display
    disp = Display(screen="1920x1200x24")
    env = disp.start()          # {"DISPLAY": ":5"} on Linux, {} elsewhere
    ...launch the app with os.environ | env...
    disp.stop()
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

from . import procs


class DisplayError(RuntimeError):
    pass


class Display:
    def __init__(self, screen: str = "1920x1200x24", headless: bool | None = None, timeout: float = 20,
                 screens: int = 1):
        """`screen` is Xvfb's `WxHxDEPTH`; keep it larger than every window a states file asks for.
        `headless=None` means: headless on Linux, the desktop elsewhere. `screens=2` adds a second screen of the same
        size to the right of the first, joined by Xinerama, for apps with a window on a second monitor."""
        self.screen = screen
        self.screens = screens
        self.headless = sys.platform.startswith("linux") if headless is None else headless
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self.name: str | None = None

    def argv(self, xvfb: str, fd: int) -> list[str]:
        screens = [a for i in range(self.screens) for a in ("-screen", str(i), self.screen)]
        return [xvfb, "-displayfd", str(fd), *screens, *(["+xinerama"] if self.screens > 1 else []),
                "-nolisten", "tcp", "-noreset"]

    def start(self) -> dict[str, str]:
        if not self.headless:
            return {}
        xvfb = shutil.which("Xvfb")
        if not xvfb:
            raise DisplayError("Xvfb not found: install it (Debian and Ubuntu: package xvfb) or run with a desktop")
        r, w = os.pipe()
        try:
            self.proc = subprocess.Popen(
                self.argv(xvfb, w),
                pass_fds=(w,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        finally:
            os.close(w)
        buf = b""
        deadline = time.monotonic() + self.timeout
        try:
            os.set_blocking(r, False)
            while b"\n" not in buf:
                if self.proc.poll() is not None:
                    raise DisplayError(f"Xvfb exited with status {self.proc.returncode} before it named a display")
                if time.monotonic() > deadline:
                    raise DisplayError(f"Xvfb named no display within {self.timeout:.0f} s")
                try:
                    chunk = os.read(r, 64)
                except BlockingIOError:
                    time.sleep(0.05)
                    continue
                if not chunk:
                    time.sleep(0.05)
                buf += chunk
        except BaseException:
            self.stop()
            raise
        finally:
            os.close(r)
        procs.record("xvfb", self.proc.pid)
        self.name = ":" + buf.split(b"\n", 1)[0].decode().strip()
        return {"DISPLAY": self.name}

    def stop(self) -> None:
        if self.proc is None:
            return
        procs.forget(self.proc.pid)
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc = None

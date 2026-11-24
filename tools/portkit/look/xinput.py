"""For drivers and hand-driven run rows on Linux: real X input through XTEST (python-xlib), for what the control
channel cannot reach (modifier keys, held drags, the wheel with modifiers, the window's close button).

Needs `python-xlib` (`uv run --with python-xlib ...`, or `pip install python-xlib`); standard library otherwise.
Use it on the private display of `portkit.look.display.Display`: `XInput(env["DISPLAY"])`. Xvfb runs no window
manager, so nothing gives the app keyboard focus: call `set_input_focus()` once the window is mapped, or every key is
lost. See tools/look.md, "Driving rows by hand"."""
from __future__ import annotations

import time

from Xlib import X, XK, display as xdisplay, protocol
from Xlib.ext import xtest


class XInput:
    def __init__(self, display_name: str, scale: float = 1.0):
        """`scale` is pixels per point. The pointer methods take points, as `ui.inspect` reports them, and send
        pixels: at interface scale 1.5 a point 100 is pixel 150."""
        self.x = xdisplay.Display(display_name)
        self.scale = scale

    def _sync(self, wait: float = 0.15) -> None:
        self.x.sync()
        time.sleep(wait)

    def top_windows(self) -> list:
        """The viewable top-level windows of the display, oldest first."""
        root = self.x.screen().root
        return [w for w in root.query_tree().children if w.get_attributes().map_state == X.IsViewable]

    def set_input_focus(self) -> int:
        """Give the newest top-level window the keyboard focus, as a window manager would. Returns how many
        top-level windows there are (0: none is mapped yet; try again)."""
        wins = self.top_windows()
        if wins:
            self.x.set_input_focus(wins[-1], X.RevertToParent, X.CurrentTime)
            self._sync(0.5)
        return len(wins)

    # pointer ---------------------------------------------------------------------------------------------
    def move(self, x: float, y: float) -> None:
        xtest.fake_input(self.x, X.MotionNotify, x=int(round(x * self.scale)), y=int(round(y * self.scale)))
        self._sync()

    def click(self, x: float, y: float, button: int = 1) -> None:
        self.move(x, y)
        xtest.fake_input(self.x, X.ButtonPress, button)
        self._sync(0.08)
        xtest.fake_input(self.x, X.ButtonRelease, button)
        self._sync(0.4)

    def drag_hold(self, x0: float, y0: float, x1: float, y1: float, steps: int = 24):
        """Press at (x0, y0) and move to (x1, y1) in `steps` steps without releasing. Returns a function that
        releases the button, so a state can be captured mid-drag."""
        self.move(x0, y0)
        xtest.fake_input(self.x, X.ButtonPress, 1)
        self._sync(0.2)
        for i in range(1, steps + 1):
            self.move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        time.sleep(0.5)

        def release() -> None:
            xtest.fake_input(self.x, X.ButtonRelease, 1)
            self._sync(0.8)
        return release

    def drag(self, x0: float, y0: float, x1: float, y1: float, steps: int = 24) -> None:
        self.drag_hold(x0, y0, x1, y1, steps)()

    def wheel(self, x: float, y: float, up: bool = True, mods=(), clicks: int = 3) -> None:
        """Wheel clicks at (x, y) with modifier keys held (key names as in `key`, for example `Control_L`)."""
        self.move(x, y)
        codes = [self._code(m) for m in mods]
        for c in codes:
            xtest.fake_input(self.x, X.KeyPress, c)
        self._sync(0.05)
        button = 4 if up else 5
        for _ in range(clicks):
            xtest.fake_input(self.x, X.ButtonPress, button)
            xtest.fake_input(self.x, X.ButtonRelease, button)
            self._sync(0.1)
        for c in reversed(codes):
            xtest.fake_input(self.x, X.KeyRelease, c)
        self._sync(0.5)

    # keyboard --------------------------------------------------------------------------------------------
    def _code(self, name: str) -> int:
        sym = XK.string_to_keysym(name)
        if not sym:
            raise ValueError(f"unknown key {name}")
        return self.x.keysym_to_keycode(sym)

    def key(self, combo: str, hold: float = 0.08, settle: float = 0.4) -> None:
        """Press the keys of `combo` in order and release them in reverse: `Control_L+Shift_L+Tab`, `Escape`,
        `F6`, `Alt_L+1`. Names are X keysym names."""
        codes = [self._code(n) for n in combo.split("+")]
        for c in codes:
            xtest.fake_input(self.x, X.KeyPress, c)
            self._sync(0.03)
        time.sleep(hold)
        for c in reversed(codes):
            xtest.fake_input(self.x, X.KeyRelease, c)
            self._sync(0.03)
        time.sleep(settle)

    def type(self, text: str, gap: float = 0.0) -> None:
        """Type `text` one character at a time: press and release back to back (`gap` seconds between characters),
        one sync at the end, so a burst lands inside one frame. Characters on the shifted level press Shift."""
        shift = self._code("Shift_L")
        for ch in text:
            sym = XK.string_to_keysym(ch) or ord(ch)
            code = self.x.keysym_to_keycode(sym)
            if not code:
                raise ValueError(f"no key types {ch!r}")
            shifted = self.x.keycode_to_keysym(code, 0) != sym
            if shifted:
                xtest.fake_input(self.x, X.KeyPress, shift)
            xtest.fake_input(self.x, X.KeyPress, code)
            xtest.fake_input(self.x, X.KeyRelease, code)
            if shifted:
                xtest.fake_input(self.x, X.KeyRelease, shift)
            if gap:
                self.x.sync()
                time.sleep(gap)
        self._sync(0.3)

    # window ----------------------------------------------------------------------------------------------
    def wm_close(self) -> int:
        """Send WM_DELETE_WINDOW to every top-level window, as a window manager's close button does. Returns how
        many windows it went to."""
        delete = self.x.intern_atom("WM_DELETE_WINDOW")
        protocols = self.x.intern_atom("WM_PROTOCOLS")
        wins = self.top_windows()
        for w in wins:
            w.send_event(protocol.event.ClientMessage(window=w, client_type=protocols,
                                                      data=(32, [delete, X.CurrentTime, 0, 0, 0])))
        self._sync(1.0)
        return len(wins)

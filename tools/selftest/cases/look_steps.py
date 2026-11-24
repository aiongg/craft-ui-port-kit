"""`look pair`'s capture loop: a failed capture counts as failed on any side and a good one does not; each state's
capture time and the notes of failed optional steps are recorded; an optional step that fails does not fail the
state."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

from lib import TOOLS, check

sys.path.insert(0, str(TOOLS))
from portkit.look import control, states  # noqa: E402


def load_look():
    loader = importlib.machinery.SourceFileLoader("look_tool", str(TOOLS / "look"))
    spec = importlib.util.spec_from_loader("look_tool", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FakeApp:
    def __init__(self):
        self.notes = []

    def call(self, method, params=None):
        if method == "ui.key":
            raise control.ControlError("synthetic input was not delivered")
        return {}


class Driver:
    def start(self, side, binary, workdir, window):
        return FakeApp()

    def shoot(self, app, side, state, window, out_png):
        control.run_steps(app, state["reset"])
        if state["id"] == "bad":
            raise RuntimeError("no shot")
        Path(out_png).write_bytes(b"png")

    def stop(self, app):
        pass


def case_capture_loop(s):
    look = load_look()
    doc = {"reset": [{"method": "ui.key", "params": {"key": "Escape"}, "optional": True}],
           "states": [{"id": "good", "steps": []}, {"id": "bad", "steps": []}]}
    states.check(doc)
    check(_rejects({"reset": [{"method": "a", "optional": "yes"}], "states": []}), "optional must be a boolean")
    todo = [states.for_side(doc, st, "port", (100, 50)) for st in doc["states"]]
    shots = s.root / "shots"
    shots.mkdir()
    info = {}
    got = look.run_side(Driver(), "port", Path("bin"), s.root / "work", shots, todo, info)
    check(isinstance(got["good"], Path) and isinstance(got["bad"], str), "the failing state is an error string")
    check(look.count_failed({"up": {"good": got["good"]}, "port": got}) == 1, "one failed capture counts once")
    check(look.count_failed({"up": {"good": got["good"]}, "port": {"good": got["good"]}}) == 0,
          "captured port states are not failures")
    check(look.count_failed({"up": {"good": "boom"}, "port": {"good": got["good"]}}) == 1, "a production failure counts")
    check(all(isinstance(i["seconds"], float) for i in info.values()), "every state records its capture time", info)
    check(info["good"]["notes"] and "ui.key" in info["good"]["notes"][0], "the failed optional step is noted", info)


def _rejects(doc):
    try:
        states.check(doc)
    except states.StatesError:
        return True
    return False

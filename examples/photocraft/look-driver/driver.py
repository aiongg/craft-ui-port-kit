"""PhotoCraft's look driver: a worked example of the driver interface in tools/look.md.

`tools/look pair` loads this file (port.toml `look.driver`) and calls, once per side and in parallel:

    start(side, binary, workdir, window) -> app
    shoot(app, side, state, window, out_png)      once per state
    stop(app)

`side` is "up" (production) or "port". `state` is one state of the panel's states file as tools/look resolves it for
the side: `id`, `title`, `steps` (this side's), `setup` (a step list) and `setup_key` (names it), `reset`, `theme`,
`window`, `crop`, plus any other field the state has.

Linux runs each instance on its own Xvfb, rendering through lavapipe (Mesa's CPU Vulkan driver), so production and
the port render the same way on any machine. On macOS the app opens a normal window.

What is PhotoCraft's own here, and would change for another app:
  - the command line: `--control 0 --new-instance --control-token-file F --automation-write-root D
    --automation-read-root D2`, and a fresh config dir whose preferences allow agent control;
  - the methods: `ui.resize`, `ui.set {theme}`, `ui.inspect`, `ui.dialog.cancel`, `engine.execute`;
  - `clear_startup`: every launch on a software adapter shows a "switched to CPU rendering" dialog and a display
    profile toast; they are dismissed by position, so a layout change in either breaks it (the shot then shows
    the dialog, and the pair makes that obvious).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from portkit.look import control
from portkit.look.display import Display

SCREEN = "1920x1200x24"     # Xvfb screen; larger than every window a states file asks for
LAVAPIPE = "/usr/share/vulkan/icd.d/lvp_icd.json"
SETTLE = 1.0                # seconds after the steps before the shot
# The toast's close button, from the window's bottom-right corner. Production and the port draw the same toast.
TOAST_CLOSE = (31, 132)


def start(side, binary, workdir, window):
    work = Path(workdir)
    for d in ("cfg", "shots", "files"):
        (work / d).mkdir(parents=True, exist_ok=True)
    (work / "token").unlink(missing_ok=True)
    (work / "cfg" / "preferences.json").write_text(json.dumps({"integrations": {"allowAgentControl": True}}))
    disp = Display(screen=SCREEN)
    env = disp.start()
    env.update(PHOTOCRAFT_CONFIG_DIR=str(work / "cfg"),
               CRAFT_SUITE_DIR=str(work / "suite"))   # each run its own theme suite: runs never share a selection
    if env.get("DISPLAY") and Path(LAVAPIPE).is_file():
        env.update(VK_ICD_FILENAMES=LAVAPIPE, WGPU_BACKEND="vulkan")
    argv = [binary, "--control", "0", "--new-instance", "--control-token-file", str(work / "token"),
            "--automation-write-root", str(work / "shots"), "--automation-read-root", str(work / "files")]
    if os.environ.get("SAFE_GPU"):
        argv.append("--safe-gpu")
    try:
        app = control.launch(side, argv, work, env=env, token_file=work / "token")
    except BaseException:
        disp.stop()
        raise
    app.extra.update(display=disp, setup=None)
    app.call("ui.resize", {"width": window[0], "height": window[1]})
    time.sleep(2)
    clear_startup(app, first=True)
    return app


def shoot(app, side, state, window, out_png):
    cancel_dialogs(app)
    if any(s.get("params", {}).get("command") == "file.new" for s in state["steps"]):
        # A state that opens its own document starts from none, so tabs from earlier states don't pile up.
        try:
            app.call("engine.execute", {"command": "file.closeAll", "params": {}})
        except control.ControlError:
            pass    # no document open
        app.extra["setup"] = None
    if state["setup_key"] is not None and state["setup_key"] != app.extra["setup"]:
        control.run_steps(app, state["setup"])
        app.extra["setup"] = state["setup_key"]
    control.run_steps(app, state["reset"])
    app.call("ui.resize", {"width": window[0], "height": window[1]})
    if state.get("theme"):
        app.call("ui.set", {"theme": state["theme"]})
    control.run_steps(app, state["steps"])
    time.sleep(SETTLE)
    clear_startup(app)
    control.screenshot(app, f"{state['id']}.png", app.work / "shots", out_png, {"focus": False})


def stop(app):
    try:
        app.quit()
    finally:
        app.extra["display"].stop()


def cancel_dialogs(app):
    for d in app.call("ui.inspect").get("dialogs", []):
        try:
            app.call("ui.dialog.cancel", {"dialog": d["id"]})
        except control.ControlError:
            pass


def _selection(inspect):
    doc = inspect.get("document") or {}
    return doc.get("activeLayer"), doc.get("selectedLayers")


def clear_startup(app, first=False):
    """Dismiss the software-rendering notice and the toasts every headless launch shows.

    A build older than the update server's release also opens the update prompt over the notice; its backdrop takes
    clicks, so Escape ("Later") closes it first. The notice is clicked only on the first call, so a later click
    cannot land on whatever a state opened."""
    if first:
        app.call("ui.key", {"key": "Escape"})
        time.sleep(0.5)
    for _ in range(3):
        i = app.call("ui.inspect")
        w, h = i["window"]["width"], i["window"]["height"]
        if first and i.get("gpuFallbackNotice"):
            # The notice's "Keep Using CPU" button sits at the window's centre; hover first so the click registers.
            x, y = w / 2 - 129, h / 2 + 83
            app.call("ui.move", {"x": x, "y": y})
            time.sleep(0.4)
            app.call("ui.click", {"x": x, "y": y})
            time.sleep(0.6)
        elif i.get("notices"):
            before = _selection(i)
            dx, dy = TOAST_CLOSE
            app.call("ui.click", {"x": w - dx, "y": h - dy})
            time.sleep(0.5)
            after = _selection(app.call("ui.inspect"))
            if after != before:
                # A click that misses the close button falls through the toast to the Layers panel.
                raise RuntimeError(f"the toast close click changed the layer selection: {before} -> {after}")
        else:
            return

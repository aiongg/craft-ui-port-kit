"""The look items of the phase gate, the landing tools' look gate, and `look brief`.

Every case builds the same port: one area map (fixtures/look/core-map.md), the example Layers panel states file
(examples/photocraft/look-driver/LayersPanel.json) with its states tied to section A1, and a compare page for it as
`look pair` writes one (manifest.json and stand-in images), captured from the scratch trees' current heads.
"""
from __future__ import annotations

import json
import shutil
import struct

from lib import FIXTURES, KIT, check, git

PANEL = "LayersPanel"


def setup(s, phase: int = 8):
    app = s.tree("app", {"src/lib.rs": "\n"})
    fw = s.tree("fw", {"Cargo.toml": "\n"})
    look = s.work / "look"
    (look / "states").mkdir(parents=True)
    (look / "driver.py").write_text("")
    (look / "production").write_text("")
    shutil.copy(FIXTURES / "look" / "core-map.md", s.work / "core-map.md")
    shutil.copy(FIXTURES / "look" / "differences.md", look / "differences.md")
    doc = json.loads((KIT / "examples/photocraft/look-driver/LayersPanel.json").read_text())
    for st in doc["states"]:
        st["map"] = "core A1"
    (look / "states" / f"{PANEL}.json").write_text(json.dumps(doc))
    f = s.config({"look.driver": str(look / "driver.py"), "look.production_binary": str(look / "production")})
    f.write_text(f.read_text() + f'[[areas]]\nid = "core"\ncode = "co"\nmap = "{s.work / "core-map.md"}"\n')
    s.run("track", "phase", "0")
    for n in range(1, phase + 1):
        s.run("track", "phase", str(n), "--force", "scratch walk")
    s.page = s.work / "track" / "site" / "look" / PANEL
    s.page.mkdir(parents=True)
    s.heads = {"app": git(app, "rev-parse", "HEAD").strip(), "framework": git(fw, "rev-parse", "HEAD").strip()}
    s.app, s.fw = app, fw
    write_page(s)
    s.run("track", "status", f"look-{PANEL}", "done")
    s.run("track", "round", "1", "--pass", "5", "--fail", "0")


def write_page(s, drop: str | None = None, head: dict | None = None):
    """The page of the last `look pair`: `sample` differs (one region), `structure` matches. `drop` leaves that
    state's port shot out."""
    states = []
    for sid, visible in (("sample", 1.5), ("structure", 0.0)):
        st = {"id": sid, "title": sid, "up": {"shot": f"up-{sid}.png"},
              "port": {"shot": f"port-{sid}.png", "head": {**s.heads, **(head or {}), "dirty": False}},
              "diff": {"file": f"diff-{sid}.png", "visible": visible, "same_size": True}, "regions": 0, "crops": []}
        if visible:
            st["regions"] = 1
            st["crops"] = [{"file": f"crop-{sid}-1.png", "box": [10, 20, 74, 52], "px": 210}]
        if sid == drop:
            del st["port"]
        states.append(st)
        for name in (f"up-{sid}.png", f"port-{sid}.png", f"diff-{sid}.png"):
            (s.page / name).write_text("")
    (s.page / "up-sample.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + struct.pack(">II", 2880, 1800))
    sides = {"up": {"scale": 2.0}, "port": {"scale": 2.0}}
    (s.page / "manifest.json").write_text(json.dumps({"panel": PANEL, "title": "Layers panel", "sides": sides,
                                                      "states": states}))


def phase9(s, ok: bool, needle: str):
    (s.work / "STATE.md").write_text("# state\n")
    r = s.run("track", "phase", "9")
    check((r.returncode == 0) == ok and needle in r.stdout + r.stderr, f"track phase 9: expected {needle!r}", r)


def land(s, ok: bool, needle: str, which: str = "app"):
    r = s.run("land/look-gate.py", which, s.heads["app" if which == "app" else "framework"])
    check((r.returncode == 0) == ok and needle in r.stdout + r.stderr, f"look-gate {which}: expected {needle!r}", r)


def case_phase8_gate(s):
    setup(s)
    write_page(s, drop="structure")
    phase9(s, False, f"{PANEL} structure: no pair")
    land(s, False, "no pair")
    write_page(s, head={"app": "0" * 40})
    phase9(s, False, f"{PANEL} sample: captured at app 0000000000")
    write_page(s)
    (s.work / "look/differences.md").write_text((s.work / "look/differences.md").read_text().replace(
        "| - | kept: the framework's one focus ring |", "| focus | fix |"))
    phase9(s, False, f"{PANEL} sample: differs, a row is still `fix`")
    shutil.copy(FIXTURES / "look" / "differences.md", s.work / "look/differences.md")
    s.run("track", "status", f"look-{PANEL}", "review")
    phase9(s, False, f"not accepted (track status look-<Panel> done): look-{PANEL}")
    s.run("track", "status", f"look-{PANEL}", "done")
    phase9(s, True, "exit of phase 8")
    land(s, True, "4 of 4 look checks passed")
    land(s, True, "4 of 4 look checks passed", which="framework")


def case_land_override(s):
    setup(s)
    phase9(s, True, "exit of phase 8")
    write_page(s, drop="structure")
    land(s, False, 'track phase 9 --force "<reason>"')
    r = s.run("track", "phase", "9", "--force", "structure pair waits on a driver fix")
    check(r.returncode == 0 and "forced" in r.stdout, "a forced re-record of phase 9 runs the phase 8 items", r)
    land(s, True, "forced by the decision of")
    land(s, True, "structure pair waits on a driver fix")
    s.run("track", "status", f"look-{PANEL}", "review")
    land(s, False, "it covers only the checks failing when it is recorded")


def case_early_framework_landing(s):
    setup(s, phase=5)
    write_page(s, drop="structure")
    land(s, True, "early framework landing in phase 5", which="framework")
    land(s, False, "no pair")


def case_look_brief(s):
    setup(s)
    d = s.work / "look/differences.md"
    d.write_text(d.read_text() + "| LayersPanel | sample | row height 28, production 32 | production better | "
                 "ListRow default | row-height | fix |\n")
    r = s.run("look", "brief", "row-height")
    check(r.returncode == 0, "look brief writes the brief", r)
    brief = (s.work / "briefs/look-fix-row-height.md").read_text()
    for needle in ("# Task look-fix-row-height", "## Look evidence", "row height 32 (`panels/layers.rs:88`)",
                   str(s.page / "crop-sample-1.png") + ": box 10,20,74,52 (64x32), 210 px",
                   f"tools/look pair {PANEL} --only sample`", "porting-rules.md", "contact sheet",
                   "one interface pixel is 2.0 image pixels on both sides",
                   str(s.page / "up-sample.png") + " (2880x1800, page only)"):
        check(needle in brief, f"the brief lacks {needle!r}:\n{brief}")
    check("{{LOOK}}" not in brief and "## The brief" not in brief, f"the brief is not the filled block:\n{brief}")
    check("focus ring" not in brief, "a kept row of another class went into the brief")
    st = json.loads((s.work / "track/state.json").read_text())
    check("look-fix-row-height" in st["tasks"], "look brief put no task on the board")
    r = s.run("look", "brief", "row-height")
    check(r.returncode == 2 and "exists" in r.stderr, "look brief replaced a brief without --force", r)
    r = s.run("look", "brief", "row-height", "--force")
    check(r.returncode == 0, "look brief --force replaces the brief", r)
    r = s.run("look", "brief", "spacing")
    check(r.returncode == 2 and "no row of class spacing" in r.stderr, "an unknown class exits 2", r)

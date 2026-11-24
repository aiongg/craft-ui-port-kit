"""`look calibrate`: the scale of each side's capture, the fonts each build embedded (from its craft-fonts
build-script output), and the production build's revision against the installed release.

A stub driver writes a PNG header at the window size times the side's scale; each binary sits in a cargo profile
dir with a build-script output beside it; production's binary sits in a git tree with a release tag."""
from __future__ import annotations

import json
import os

from lib import check, git

DRIVER = '''import os, struct
def start(side, binary, workdir, window):
    return {"side": side}
def shoot(app, side, state, window, out_png):
    k = float(os.environ["STUB_SCALE_" + side.upper()])
    head = b"\\x89PNG\\r\\n\\x1a\\n\\0\\0\\0\\rIHDR" + struct.pack(">II", int(window[0] * k), int(window[1] * k))
    open(out_png, "wb").write(head)
def stop(app):
    pass
'''

FONTS_OK = ("cargo::rerun-if-env-changed=CRAFT_FONTS_DIR\ncargo::rerun-if-env-changed=CRAFT_FONTS_REQUIRED\n"
            "cargo::rerun-if-changed=/fonts-checkout/fonts/manifest.txt\n")
FONTS_NO_UI = FONTS_OK + ("cargo::warning=craft-fonts: not embedding any CJK face for the interface: "
                          "/fonts-checkout/fonts/manifest.txt has no interface face (role `ui`); use a craft-fonts "
                          "checkout that has them\n")


def binary(root, profile: str, fonts: str):
    b = root / "target" / profile / "app"
    b.parent.mkdir(parents=True)
    b.write_text("#!/bin/sh\n")
    os.chmod(b, 0o755)
    out = root / "target" / profile / "build" / "app-0123456789abcdef" / "output"
    out.parent.mkdir(parents=True)
    out.write_text(fonts)
    return b


def setup(s, port_fonts: str, installed: str | None):
    prod = s.tree("prod", {".gitignore": "target/\n", "src/main.rs": "\n"})
    git(prod, "tag", "v1.0")
    s.commit(prod, {"src/main.rs": "// hooks\n"}, "control hooks")
    up = binary(prod, "release", FONTS_OK)
    port = binary(s.root / "port", "debug", port_fonts)
    (s.work / "driver.py").write_text(DRIVER)
    keys = {"look.driver": str(s.work / "driver.py"), "look.production_binary": str(up),
            "look.port_binary": str(port), "look.window": "100x50"}
    if installed:
        keys["look.installed_version"] = installed
    s.config(keys)


def report(s) -> dict:
    return json.loads((s.work / "look" / "run" / "calibrate.json").read_text())


def case_problems_reported(s):
    setup(s, FONTS_NO_UI, None)
    r = s.run("look", "calibrate", env={"STUB_SCALE_UP": "2", "STUB_SCALE_PORT": "1"})
    check(r.returncode == 1, "problems make exit 1", r)
    rep = report(s)
    check(rep["sides"]["up"]["scale"] == 2.0 and rep["sides"]["port"]["scale"] == 1.0, f"scales: {rep['sides']}", r)
    check(rep["sides"]["up"]["fonts"]["status"] == "interface faces"
          and rep["sides"]["up"]["fonts"]["checkout"] == "/fonts-checkout", "production's fonts and checkout", r)
    check(rep["sides"]["port"]["fonts"]["status"] == "no interface face", "the port's missing interface face", r)
    probs = "\n".join(rep["problems"])
    for needle in ("different scales: production 2.0x, port 1.0x", "port: built with no interface face",
                   "look.installed_version is not set"):
        check(needle in probs, f"problem {needle!r} missing: {rep['problems']}", r)
    check("build warning: craft-fonts: not embedding" in r.stdout, "the build warning is printed", r)


def case_clean_with_revision(s):
    setup(s, FONTS_OK, "1.0")
    r = s.run("look", "calibrate", env={"STUB_SCALE_UP": "2", "STUB_SCALE_PORT": "2"})
    check(r.returncode == 0, "a clean calibration exits 0", r)
    rep = report(s)
    check(rep["problems"] == [], f"no problems: {rep['problems']}", r)
    rev = rep["revision"]
    check(rev["ahead"] == 1 and rev["behind"] == 0 and "1 commit(s) after and 0 before the installed release 1.0"
          in r.stdout, f"production is one commit after the release: {rev}", r)
    r = s.run("look", "calibrate", "--side", "up", env={"STUB_SCALE_UP": "2", "STUB_SCALE_PORT": "2"})
    check(r.returncode == 0 and list(report(s)["sides"]) == ["up"], "--side up captures production only", r)


def case_target_dir_per_side(s):
    """A binary copied out of its target dir reads its fonts from look.production_target_dir / look.port_target_dir."""
    setup(s, FONTS_NO_UI, None)
    port_bin = s.root / "copies" / "app"
    port_bin.parent.mkdir()
    port_bin.write_text("#!/bin/sh\n")
    os.chmod(port_bin, 0o755)
    s.config({"look.driver": str(s.work / "driver.py"), "look.production_binary": str(s.root / "prod/target/release/app"),
              "look.port_binary": str(port_bin), "look.window": "100x50",
              "look.port_target_dir": str(s.root / "port" / "target")})
    r = s.run("look", "calibrate", env={"STUB_SCALE_UP": "2", "STUB_SCALE_PORT": "2"})
    rep = report(s)
    check(rep["sides"]["port"]["fonts"]["status"] == "no interface face", f"port fonts from its target dir: {rep['sides']['port']['fonts']}", r)
    check("production" in r.stdout and rep["revision"]["describe"], "the revision names a describe string", r)

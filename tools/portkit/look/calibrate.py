"""The facts `look calibrate` reports before any pair is trusted: the scale of each side's capture, whether each
build has the craft-fonts interface faces, and the production build's revision against the release the developer
runs (tools/look.md, "look calibrate"). Standard library only."""
from __future__ import annotations

import re
import struct
import subprocess
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"
FONTS_ENV = "rerun-if-env-changed=CRAFT_FONTS_DIR"
MANIFEST_RE = re.compile(r"rerun-if-changed=(.+)/fonts/manifest\.txt\s*$")
WARN_RE = re.compile(r"^cargo::?warning=(.*)$")
NO_UI = ("has no interface face", "not embedding the interface faces")
NO_CHECKOUT = "building without craft-fonts"

FONT_OK = "interface faces"
FONT_NO_UI = "no interface face"
FONT_NONE = "no craft-fonts checkout"
FONT_UNKNOWN = "unknown"


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from a PNG's header."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIG or head[12:16] != b"IHDR":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def scale(size: tuple[int, int], window) -> float | None:
    """Image pixels per window pixel, when both axes agree; None when they do not."""
    sx, sy = size[0] / window[0], size[1] / window[1]
    return round(sx, 2) if abs(sx - sy) < 0.01 else None


def build_outputs(binary: Path) -> list[Path]:
    """The build-script output files of the cargo profile dir that holds `binary` (target/<profile>/<bin>, or
    .../examples/<bin>): the newest one per package that reads CRAFT_FONTS_DIR."""
    for prof in (binary.parent, binary.parent.parent):
        bdir = prof / "build"
        if not bdir.is_dir():
            continue
        newest: dict[str, Path] = {}
        for out in bdir.glob("*/output"):
            try:
                text = out.read_text(errors="replace")
            except OSError:
                continue
            if FONTS_ENV not in text:
                continue
            pkg = re.sub(r"-[0-9a-f]{16}$", "", out.parent.name)
            if pkg not in newest or out.stat().st_mtime > newest[pkg].stat().st_mtime:
                newest[pkg] = out
        return sorted(newest.values())
    return []


def fonts(binary: Path) -> dict:
    """What the build that made `binary` embedded, from its craft-fonts build-script output:
    {status, checkout, warnings, outputs}."""
    outs = build_outputs(binary)
    if not outs:
        return {"status": FONT_UNKNOWN, "checkout": None, "warnings": [], "outputs": []}
    checkout, warnings = None, []
    for out in outs:
        for line in out.read_text(errors="replace").splitlines():
            m = MANIFEST_RE.search(line)
            if m:
                checkout = m.group(1)
            w = WARN_RE.match(line)
            if w and ("craft-fonts" in w.group(1)) and w.group(1) not in warnings:
                warnings.append(w.group(1))
    if any(NO_CHECKOUT in w for w in warnings) or checkout is None:
        status = FONT_NONE
    elif any(k in w for w in warnings for k in NO_UI):
        status = FONT_NO_UI
    else:
        status = FONT_OK
    return {"status": status, "checkout": checkout, "warnings": warnings, "outputs": [str(o) for o in outs]}


def _git(tree: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def tree_of(binary: Path) -> Path | None:
    """The git work tree that holds `binary`, if any."""
    top = _git(binary.parent, "rev-parse", "--show-toplevel")
    return Path(top) if top else None


def revision(tree: Path, installed: str | None) -> dict:
    """Production's revision in `tree` against the installed release: {tree, head, describe, installed,
    installed_commit, ahead, behind, text}."""
    out = {"tree": str(tree), "head": _git(tree, "rev-parse", "HEAD"),
           "describe": _git(tree, "describe", "--tags", "--always"), "installed": installed,
           "installed_commit": None, "ahead": None, "behind": None}
    if not installed or installed == "none":
        out["text"] = f"production {out['describe']}; " + ("the developer runs no installed release" if installed
                                                            else "look.installed_version is not set")
        return out
    for ref in (f"v{installed}", installed):
        c = _git(tree, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
        if c:
            out["installed_commit"] = c
            break
    if not out["installed_commit"] or not out["head"]:
        out["text"] = f"production {out['describe']}; installed {installed} names no commit in {tree}"
        return out
    counts = _git(tree, "rev-list", "--left-right", "--count", f"{out['installed_commit']}...{out['head']}")
    behind, ahead = (int(x) for x in counts.split()) if counts else (None, None)
    out["ahead"], out["behind"] = ahead, behind
    if out["installed_commit"] == out["head"]:
        out["text"] = f"production {out['describe']} is the installed release {installed}"
    else:
        out["text"] = (f"production {out['describe']} is {ahead} commit(s) after and {behind} before the installed "
                       f"release {installed}: differences between the installed app and the port may be production's own")
    return out


def problems(sides: dict, rev: dict) -> list[str]:
    """The facts that make pairs untrustworthy. sides: {side: {scale, fonts}} for the sides captured."""
    out = []
    scales = {s: d.get("scale") for s, d in sides.items() if not d.get("error")}
    for s, d in sides.items():
        if d.get("error"):
            out.append(f"{s}: no capture: {d['error']}")
        elif d.get("scale") is None:
            out.append(f"{s}: the capture's width and height scale differently against the window")
    if len(scales) == 2 and None not in scales.values() and len(set(scales.values())) > 1:
        out.append(f"the sides capture at different scales: production {scales.get('up')}x, port {scales.get('port')}x")
    status = {s: d["fonts"]["status"] for s, d in sides.items() if d.get("fonts")}
    for s, st in status.items():
        if st in (FONT_NO_UI, FONT_NONE):
            out.append(f"{s}: built with {st} (rebuild with a craft-fonts checkout that has the interface faces)")
    known = {st for st in status.values() if st != FONT_UNKNOWN}
    if len(known) > 1:
        out.append(f"the sides embed different fonts: {', '.join(f'{s} {st}' for s, st in status.items())}")
    if rev.get("installed") is None and "up" in sides:
        out.append("look.installed_version is not set: ask the developer which release they run (or `none`)")
    return out

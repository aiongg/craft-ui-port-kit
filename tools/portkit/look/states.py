"""States files: the states of one panel or dialog that `look pair` captures in production and in the port.

Format (tools/look.md, "States files"):

    {
      "title": "Layers panel",
      "size": {"width": 1440, "height": 900},        optional; default look.window
      "theme": "pro",                                optional; the driver sets it before every state
      "crop": [x0, y0, x1, y1],                      optional; pixels of the full-window shot; null = whole window
      "setups": {"sample": [STEP, ...]},             optional named setups
      "reset": [STEP, ...],                          optional; sent before every state (a state's own "reset" replaces it, [] opts out)
      "states": [
        {"id": "structure", "title": "...", "setup": "sample" | [STEP, ...], "steps": [STEP, ...],
         "up_steps": [...], "port_steps": [...],     optional per-side steps that replace `steps`
         "theme": ..., "size": ..., "crop": ...,     optional per-state overrides
         "needs": "CH-3" | "steps", "note": "..."}   a state with `needs` is not captured yet
      ]
    }

STEP is one control request, `{"method": ..., "params": {...}}`, or `{"method": "@sleep", "params": {"seconds": S}}`.
This is craft-libs docs/porting.md's states file plus setups, reset, crop and needs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
SIDES = ("up", "port")


class StatesError(ValueError):
    pass


# ------------------------------------------------------------------------------------------- load and check

def parse_window(v, where: str = "window") -> tuple[int, int]:
    """`{"width", "height"}`, `[w, h]` or `"WxH"` -> (w, h)."""
    try:
        if isinstance(v, dict):
            w, h = v["width"], v["height"]
        elif isinstance(v, (list, tuple)):
            w, h = v
        else:
            w, h = str(v).lower().split("x")
        w, h = int(w), int(h)
    except (KeyError, ValueError, TypeError):
        raise StatesError(f"{where}: not a window size: {v!r} (use {{\"width\": W, \"height\": H}} or \"WxH\")")
    if w <= 0 or h <= 0:
        raise StatesError(f"{where}: window size must be positive: {v!r}")
    return w, h


def _check_steps(steps, where: str) -> None:
    if not isinstance(steps, list):
        raise StatesError(f"{where}: steps must be a list")
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or not isinstance(s.get("method"), str) or not s["method"]:
            raise StatesError(f"{where}: step {i + 1} needs a method")
        if "params" in s and not isinstance(s["params"], dict):
            raise StatesError(f"{where}: step {i + 1}: params must be an object")
        if "optional" in s and not isinstance(s["optional"], bool):
            raise StatesError(f"{where}: step {i + 1}: optional must be true or false")


def _check_crop(box, where: str) -> None:
    if box is None:
        return
    if (not isinstance(box, list) or len(box) != 4 or not all(isinstance(v, int) for v in box)
            or box[0] >= box[2] or box[1] >= box[3]):
        raise StatesError(f"{where}: crop must be [x0, y0, x1, y1] with x0 < x1 and y0 < y1, or null")


def check(doc: dict, name: str = "states file", strict: bool = True) -> dict:
    """Raise StatesError naming the first problem; return the document. `strict` (what `look pair` uses) also
    refuses a state to be captured whose named setup is still empty."""
    if not isinstance(doc, dict) or not isinstance(doc.get("states"), list):
        raise StatesError(f"{name}: needs a \"states\" list")
    if "size" in doc:
        parse_window(doc["size"], f"{name}: size")
    _check_crop(doc.get("crop"), f"{name}")
    setups = doc.get("setups", {})
    if not isinstance(setups, dict):
        raise StatesError(f"{name}: setups must be an object of named step lists")
    for k, v in setups.items():
        _check_steps(v, f"{name}: setup {k}")
    _check_steps(doc.get("reset", []), f"{name}: reset")
    seen = set()
    for i, st in enumerate(doc["states"]):
        where = f"{name}: state {i + 1}"
        if not isinstance(st, dict):
            raise StatesError(f"{where}: not an object")
        sid = st.get("id")
        if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
            raise StatesError(f"{where}: id {sid!r}: lowercase letters, digits and . _ -, at most 64")
        if sid in seen:
            raise StatesError(f"{where}: id {sid!r} appears twice")
        seen.add(sid)
        where = f"{name}: state {sid}"
        for key in ("steps", "reset", *(f"{s}_steps" for s in SIDES)):
            if key in st:
                _check_steps(st[key], f"{where}: {key}")
        if "steps" not in st and not st.get("needs"):
            raise StatesError(f"{where}: needs steps (an empty list for the panel as it opens) or a needs field")
        setup = st.get("setup")
        if isinstance(setup, str):
            if setup not in setups:
                raise StatesError(f"{where}: setup {setup!r} is not in setups")
            if strict and not setups[setup] and not st.get("needs"):
                raise StatesError(f"{where}: setup {setup!r} has no steps yet (write them in setups.{setup})")
        elif setup is not None:
            _check_steps(setup, f"{where}: setup")
        if "size" in st:
            parse_window(st["size"], f"{where}: size")
        _check_crop(st.get("crop"), where)
    return doc


def load(path: Path, strict: bool = True) -> dict:
    path = Path(path)
    try:
        doc = json.loads(path.read_text())
    except OSError as e:
        raise StatesError(f"cannot read {path}: {e.strerror}")
    except json.JSONDecodeError as e:
        raise StatesError(f"{path}: not JSON: {e}")
    return check(doc, str(path), strict)


def for_side(doc: dict, st: dict, side: str, default_window: tuple[int, int]) -> dict:
    """The state as a driver gets it: one side's steps, the setup as a step list plus a key that names it, the
    state's own reset (else the file's), theme, window and crop resolved. Other fields of the state are passed through."""
    out = {k: v for k, v in st.items() if not k.endswith("_steps")}
    out["steps"] = st.get(f"{side}_steps", st.get("steps", []))
    setup = st.get("setup")
    if isinstance(setup, str):
        out["setup"], out["setup_key"] = doc.get("setups", {}).get(setup, []), setup
    elif setup:
        out["setup"], out["setup_key"] = setup, json.dumps(setup, sort_keys=True)
    else:
        out["setup"], out["setup_key"] = [], None
    out["reset"] = st["reset"] if "reset" in st else doc.get("reset", [])
    out["theme"] = st.get("theme", doc.get("theme"))
    out["window"] = list(parse_window(st["size"]) if "size" in st else
                         parse_window(doc["size"]) if "size" in doc else default_window)
    out["crop"] = st.get("crop", doc.get("crop"))
    return out


# --------------------------------------------------------------------------------- from an area map section

HEADING = re.compile(r"^#{2,3}\s+([A-Za-z]{1,4}\d+[a-z]?)\.?\s+(.+?)\s*$")
FIELD = re.compile(r"^\s*-\s+\*\*([A-Za-z][A-Za-z ]*)\*\*\s*:?\s*(.*)$")
HOOK = re.compile(r"\bCH-\d+\b")


def sections(text: str) -> list[tuple[str, str, dict[str, str]]]:
    """Every section of an area map: (section id, part name, {field name in lower case: text})."""
    out = []
    cur = None
    field = None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            cur = (m.group(1), m.group(2).strip(), {})
            field = None
            out.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("#"):
            cur = None
            continue
        f = FIELD.match(line)
        if f:
            field = f.group(1).strip().lower()
            cur[2][field] = f.group(2).strip()
        elif field and line.strip():
            cur[2][field] += "\n" + line.rstrip()
    return out


def find_section(text: str, section: str) -> tuple[str, str, dict[str, str]]:
    """(section id, part name, {field name: text}) of the map section with that id (case-insensitive)."""
    for sec in sections(text):
        if sec[0].lower() == section.lower():
            return sec
    raise StatesError(f"no section {section} in the map (headings `## <ID>. <name>` or `### <ID> <name>`)")


def map_files(cfg) -> dict[str, Path]:
    """The map file of each area that has one (framework-only areas have none)."""
    return {ar["id"]: Path(ar["map"]) for ar in cfg.areas if ar.get("map") and ar.get("repos") != ["fw"]}


def shows_nothing(fields: dict[str, str]) -> bool:
    """A section whose **States** field says `none` (a reason may follow) has nothing to capture."""
    return re.match(r"\s*none\b", fields.get("states", ""), re.I) is not None


def panel_name(part: str, framework_field: str) -> str:
    """The states file's name: the framework's panel or dialog type the section names, else its first backticked
    type name, else the part name in CamelCase."""
    ids = re.findall(r"`([A-Z][A-Za-z0-9]+)", framework_field or "")
    for i in ids:
        if i.endswith(("Panel", "Dialog")):
            return i
    if ids:
        return ids[0]
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"\(.*", "", part))
    return "".join(w[:1].upper() + w[1:] for w in words[:4]) or "Panel"


def _balanced(s: str, i: int) -> int:
    """Index after the bracket that closes s[i] (`{` or `[`), skipping JSON strings; -1 when unbalanced."""
    pairs = {"{": "}", "[": "]"}
    stack, j, in_str = [], i, False
    while j < len(s):
        c = s[j]
        if in_str:
            if c == "\\":
                j += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in pairs:
            stack.append(pairs[c])
        elif c in "]}":
            if not stack or stack.pop() != c:
                return -1
            if not stack:
                return j + 1
        j += 1
    return -1


def _json_at(s: str, i: int):
    end = _balanced(s, i)
    if end < 0:
        return None, i + 1
    try:
        return json.loads(s[i:end]), end
    except json.JSONDecodeError:
        return None, i + 1


def _is_steps(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, dict) and isinstance(x.get("method"), str) for x in v)


def _state_objects(text: str) -> list[dict]:
    """State objects written as JSON in the field: `{"id": ..., "steps": [...]}`, alone or in a list."""
    out, i = [], 0
    while i < len(text):
        if text[i] not in "{[":
            i += 1
            continue
        v, end = _json_at(text, i)
        if isinstance(v, dict) and isinstance(v.get("id"), str):
            out.append(v)
            i = end
        elif isinstance(v, list) and v and all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in v):
            out.extend(v)
            i = end
        else:
            i += 1
    return out


def _split_items(text: str) -> list[str]:
    """Top-level items of a state list: list lines, else `;`-separated parts (outside brackets and backticks)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if sum(1 for ln in lines if re.match(r"\s*[-*]\s", ln)) >= 2:
        items, cur = [], ""
        for ln in lines:
            if re.match(r"\s*[-*]\s", ln):
                if cur.strip():
                    items.append(cur)
                cur = re.sub(r"^\s*[-*]\s+", "", ln)
            else:
                cur += " " + ln.strip()
        if cur.strip():
            items.append(cur)
        return [x.strip() for x in items]
    flat = " ".join(ln.strip() for ln in lines)
    items, depth, tick, cur = [], 0, False, ""
    for c in flat:
        if c == "`":
            tick = not tick
        elif not tick and c in "[{":
            depth += 1
        elif not tick and c in "]}":
            depth = max(0, depth - 1)
        if c == ";" and depth == 0 and not tick:
            items.append(cur)
            cur = ""
        else:
            cur += c
    items.append(cur)
    return [x.strip().rstrip(".") for x in items if x.strip()]


def _slug(s: str, words: int = 5) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", s.lower())[:words])[:64].strip("-")


def _item_state(item: str) -> dict:
    steps, rest = None, item
    k = item.find("[")
    while k >= 0:
        v, end = _json_at(item, k)
        if _is_steps(v):
            steps = [{"method": x["method"], "params": x.get("params") or {}} for x in v]
            rest = (item[:k] + item[end:]).replace("``", "")
            break
        k = item.find("[", k + 1)
    setup = None
    sm = re.search(r"`?setup\s*:\s*\"?([A-Za-z0-9_-]+)\"?`?\s*,?", rest)
    if sm:
        setup, rest = sm.group(1), rest[:sm.start()] + rest[sm.end():]
    sid = None
    m = re.match(r"\s*`([^`]+)`\s*:?\s*(.*)$", rest, re.S)
    if m and ID_RE.fullmatch(_slug(m.group(1), 8) or "-"):
        sid, rest = _slug(m.group(1), 8), m.group(2)
    else:
        m = re.match(r"\s*([A-Za-z][^:\[\]{}]{0,40}):\s*(.*)$", rest, re.S)
        if m:
            sid, rest = _slug(m.group(1)), m.group(2)
    title = re.sub(r"\s+", " ", rest).strip(" ,.:") or None
    sid = sid or _slug(HOOK.sub("", re.sub(r"\(.*?\)", "", title or "")) or "state")
    st = {"id": sid, "title": title or sid}
    if setup:
        st["setup"] = setup
    hooks = HOOK.findall(item)
    if hooks:
        st.update(steps=steps or [], needs=",".join(dict.fromkeys(hooks)), note=item.strip()[:400])
    elif steps is not None:
        st["steps"] = steps
    elif sid == "default":
        st["steps"] = []        # the panel as the app opens it
    else:
        st.update(steps=[], needs="steps", note="steps not given in the map: " + item.strip()[:380])
    return st


def from_map_field(text: str) -> list[dict]:
    """States from a map section's **States** field: JSON state objects when it has them, else one state per list
    item. An item without a step list waits with `needs: "steps"` (except `default`, the panel as it opens); an
    item that names a missing control hook (`CH-n`) waits with `needs: "CH-n"`."""
    objs = _state_objects(text)
    if objs:
        out = []
        for o in objs:
            st = dict(o)
            st["id"] = _slug(st["id"], 8) or "state"
            st.setdefault("title", st["id"])
            if "steps" not in st and not st.get("needs"):
                st.update(steps=[], needs="steps")
            out.append(st)
    else:
        out = [_item_state(it) for it in _split_items(text)]
    seen: dict[str, int] = {}
    for st in out:      # ids must be unique in a file
        n = seen.get(st["id"], 0)
        seen[st["id"]] = n + 1
        if n:
            st["id"] = f"{st['id']}-{n + 1}"
    return out


HEAD_ORDER = ("title", "size", "theme", "crop", "setups", "reset", "states")


def ordered(doc: dict) -> dict:
    """The file's keys in the documented order, others after them."""
    return {**{k: doc[k] for k in HEAD_ORDER if k in doc}, **{k: v for k, v in doc.items() if k not in HEAD_ORDER}}


def merge(old: dict | None, head: dict, new_states: list[dict], force: bool) -> tuple[dict, int, int, int]:
    """Add new states to an existing file. A state whose id is already there is kept as it is (it may have been
    edited by hand) unless `force`. Returns (doc, added, replaced, kept)."""
    doc = dict(old) if old else dict(head)
    doc.setdefault("states", [])
    by_id = {s["id"]: i for i, s in enumerate(doc["states"])}
    added = replaced = kept = 0
    for st in new_states:
        if st["id"] in by_id:
            if force:
                doc["states"][by_id[st["id"]]] = st
                replaced += 1
            else:
                kept += 1
        else:
            by_id[st["id"]] = len(doc["states"])
            doc["states"].append(st)
            added += 1
    setups = doc.setdefault("setups", {})
    for st in doc["states"]:     # a setup the map names but does not spell out: an empty entry to fill in
        if isinstance(st.get("setup"), str):
            setups.setdefault(st["setup"], [])
    if not setups:
        del doc["setups"]
    return ordered(doc), added, replaced, kept

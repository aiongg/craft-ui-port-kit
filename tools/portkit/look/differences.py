"""The differences file (`look.differences`): one Markdown table row per look difference the lead judged.

Format (tools/look.md, "The differences file"):

    | Panel | State | What differs | Judgement | Cause | Class | Outcome |
    |---|---|---|---|---|---|---|
    | LayersPanel | structure | row height 28, production 32 | production better | ListRow default | row-height | fix |

Outcome is `fix` (a class task fixes it), `fixed` (the new pair shows it fixed) or `kept: <reason>` (the difference
stays, for that reason). `look brief CLASS` reads the `fix` rows of a class; the phase 8 gate wants a `kept` row for
every state that still differs.
"""
from __future__ import annotations

import re
from pathlib import Path

COLUMNS = ("panel", "state", "what differs", "judgement", "cause", "class", "outcome")
CLASS_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().strip("`").strip() for c in s.split("|")]


def read(path: Path) -> list[dict]:
    """Every row of every table in the file whose header names Panel and State, as {column: text}. A missing file
    has no rows."""
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return []
    rows, head = [], None
    for n, line in enumerate(lines, 1):
        if not line.lstrip().startswith("|"):
            head = None
            continue
        cells = _cells(line)
        if head is None:
            names = [c.lower() for c in cells]
            if "panel" in names and "state" in names:
                head = names
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        row = {name: (cells[i] if i < len(cells) else "") for i, name in enumerate(head)}
        row["line"] = n
        rows.append(row)
    return rows


def outcome(row: dict) -> tuple[str, str]:
    """(`fix` | `fixed` | `kept` | `bad`, the reason of a kept row or the text of a bad one)."""
    text = row.get("outcome", "").strip()
    low = text.lower()
    if low in ("fix", "fixed"):
        return low, ""
    m = re.match(r"kept\s*:\s*(\S.*)$", text, re.I)
    if m:
        return "kept", m.group(1).strip()
    return "bad", text


def for_state(rows: list[dict], panel: str, state: str) -> list[dict]:
    return [r for r in rows if r.get("panel") == panel and r.get("state") == state]


def state_verdict(rows: list[dict]) -> str | None:
    """None when a differing state's rows let it stay (a kept row, no open one), else why not."""
    if not rows:
        return "differs, no row in the differences file"
    kinds = [outcome(r) for r in rows]
    bad = [t for k, t in kinds if k == "bad"]
    if bad:
        return f"outcome {bad[0]!r} is not fix, fixed or kept: <reason>"
    if any(k == "fix" for k, _ in kinds):
        return "differs, a row is still `fix`"
    if not any(k == "kept" for k, _ in kinds):
        return "marked fixed, but the pair still differs"
    return None

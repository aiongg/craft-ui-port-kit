"""Claude Code session files: where a session's transcript is, its last context size, its recorded cost.

Claude Code keeps each session's transcript at `<config dir>/projects/<encoded cwd>/<session id>.jsonl`, where the
config dir is CLAUDE_CONFIG_DIR (default ~/.claude) and the encoded cwd is the session's starting directory with
every character that is not a letter or a digit written as `-`. One JSON record per line:
  - `assistant` records hold `message.usage`: `input_tokens`, `cache_creation_input_tokens`,
    `cache_read_input_tokens`, `output_tokens`. The three input counts of the last one are the context the next
    turn starts from. Records with `isSidechain` true belong to subagents and are skipped.
  - `cost-state` records hold the session's running totals: `totalCostUSD` (subagents run inside the session
    included) and `modelUsage` per model. The last one is the session's cost so far.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ENV_SESSION = "CLAUDE_CODE_SESSION_ID"   # set by Claude Code in the shells it runs tools in


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def encode_cwd(cwd: str | Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def session_file(sid: str, cwd: str | Path | None = None) -> Path | None:
    """The transcript of session `sid`: under the encoded cwd when given and present, else any project dir."""
    if not sid or "/" in sid:
        return None
    projects = config_dir() / "projects"
    if cwd:
        f = projects / encode_cwd(cwd) / f"{sid}.jsonl"
        if f.is_file():
            return f
    return next(iter(sorted(projects.glob(f"*/{sid}.jsonl"))), None)


def _records(f: Path):
    try:
        with open(f, errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    yield d
    except OSError:
        return


def last_context(sid: str, cwd: str | Path | None = None) -> int | None:
    """Tokens of context at the session's last main-thread assistant turn; None when unknown."""
    f = session_file(sid, cwd)
    if f is None:
        return None
    last = None
    for d in _records(f):
        if d.get("type") != "assistant" or d.get("isSidechain"):
            continue
        u = (d.get("message") or {}).get("usage")
        if isinstance(u, dict):
            last = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                       "cache_read_input_tokens"))
    return last


def last_cost(sid: str, cwd: str | Path | None = None) -> dict | None:
    """{"cost_usd", "models": {model: cost}} from the session's last cost-state record; None when it has none."""
    f = session_file(sid, cwd)
    if f is None:
        return None
    last = None
    for d in _records(f):
        if d.get("type") == "cost-state" and d.get("totalCostUSD") is not None:
            last = d
    if last is None:
        return None
    models = {m: round(float((v or {}).get("costUSD") or 0), 4) for m, v in (last.get("modelUsage") or {}).items()}
    return {"cost_usd": round(float(last["totalCostUSD"]), 4), "models": models}

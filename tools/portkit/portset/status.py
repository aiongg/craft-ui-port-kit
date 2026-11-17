"""`port-set status`: where every set stands, read from its set dir, beside its dashboard state.

Stages, from the files port-set and the batch tools write in <work.sets>/<set>/ (the latest that applies wins):

| Stage | Read from | Means |
|---|---|---|
| planned | no plancheck.md | the sheet exists; no plan check yet |
| decide | plancheck.md with DECIDE items and no newer decisions.md | waiting for the decision pass |
| ready | plancheck.md clear, or decisions.md newer than it | ready to write |
| open | open.md newer than decisions.md | `port-set run` stopped on DECIDE items |
| blocked | blocked.md newer than check.md | the writer answered BLOCKED |
| written | check.md | written; the detail gives check and rust-analyzer error counts |
| reviewed | review-*.md | an area review covered it; the detail names the review files |
| combined | landed | the combine took its net change into the integration branch |

`--post` moves each set's dashboard task to the state its stage implies when they differ (planned and ready: todo;
decide and open: review; blocked: blocked on lead; written: done when check.md has no errors, else review; combined:
done). Tasks that are running, and reviewed sets, are left alone: a command or a person owns those.
"""
from __future__ import annotations

import json
import re

from portkit import track

from .context import ctx
from .plan import all_sheets, area_of

STAGES = ("planned", "decide", "ready", "open", "blocked", "written", "reviewed", "combined")


def mtime(p):
    return p.stat().st_mtime if p.exists() else None


def newer(a, b) -> bool:
    """a exists and is newer than b (or b is missing)."""
    ta, tb = mtime(a), mtime(b)
    return ta is not None and (tb is None or ta > tb)


def check_counts(d) -> tuple[int, int]:
    """(scripted errors, rust-analyzer errors) in check.md."""
    text = (d / "check.md").read_text() if (d / "check.md").exists() else ""
    m = re.search(r"^## Errors\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    body = m.group(1).strip() if m else ""
    items = [] if body in ("", "none") else [x for x in re.split(r"\n\s*\n", body) if x.strip()]
    ra = sum(1 for x in items if x.startswith("compile error (rust-analyzer)"))
    return len(items) - ra, ra


def stage_of(set_id: str) -> tuple[str, str]:
    d = ctx.sets / set_id
    dec = d / "decisions.md"
    if (d / "landed").exists():
        return "combined", f"landed at {(d / 'landed').read_text().strip()[:10]}"
    reviews = sorted(p.name for p in d.glob("review-*.md"))
    if reviews:
        return "reviewed", ", ".join(reviews)
    if newer(d / "blocked.md", d / "check.md"):
        return "blocked", (re.sub(r"^# .*\n+", "", (d / "blocked.md").read_text()).strip().splitlines() or [""])[0][:120]
    if (d / "check.md").exists():
        e, ra = check_counts(d)
        return "written", f"{e} check errors, {ra} rust-analyzer errors"
    if newer(d / "open.md", dec):
        n = len(re.findall(r"^- \[DECIDE\]", (d / "open.md").read_text(), re.M))
        return "open", f"{n} DECIDE items (open.md)"
    if (d / "plancheck.md").exists():
        n = len(re.findall(r"^- \[DECIDE\]", (d / "plancheck.md").read_text(), re.M))
        if n and not newer(dec, d / "plancheck.md"):
            return "decide", f"{n} DECIDE items (plancheck.md)"
        return "ready", "decided (decisions.md)" if dec.exists() else "plan check clear"
    return "planned", ""


def board_state(stage: str, detail: str) -> tuple[str, str | None] | None:
    if stage in ("planned", "ready"):
        return "todo", None
    if stage in ("decide", "open"):
        return "review", None
    if stage == "blocked":
        return "blocked", "lead"
    if stage == "written":
        return ("done" if detail.startswith("0 check errors") else "review"), None
    if stage == "combined":
        return "done", None
    return None


def board_tasks() -> dict:
    try:
        store = track.open_store(str(ctx.cfg.file) if ctx.cfg.file else None)
        return store.state().get("tasks", {}) if store else {}
    except Exception as e:   # the dashboard is optional: status still prints the stages
        print(f"port-set status: dashboard not read: {e}")
        return {}


def cmd_status(a) -> None:
    sheets = all_sheets()
    ids = [s.id for s in sheets]
    for x in a.sets:
        if x not in ids:
            raise SystemExit(f"no sheet {x} in {ctx.sheets}")
    ids = [i for i in ids if (not a.sets or i in a.sets) and (not a.area or area_of(i) == a.area)]
    tasks = board_tasks()
    rows = []
    for sid in ids:
        stage, detail = stage_of(sid)
        if a.stage and stage != a.stage:
            continue
        tk = tasks.get(sid) or {}
        rows.append({"set": sid, "stage": stage, "detail": detail, "board": tk.get("state"),
                     "board_note": tk.get("note"), "updated": tk.get("updated")})
    posted = 0
    if a.post:
        for r in rows:
            want = board_state(r["stage"], r["detail"])
            if want is None or r["board"] == "running" or r["board"] == want[0]:
                continue
            track.status(r["set"], want[0], f"port-set status: {r['stage']}" + (f", {r['detail']}" if r["detail"] else ""),
                         on=want[1])
            r["board"] = want[0]
            posted += 1
    if a.json:
        print(json.dumps(rows, indent=1))
        return None
    counts = {st: sum(1 for r in rows if r["stage"] == st) for st in STAGES}
    w = max([len(r["set"]) for r in rows] + [3])
    print(f"{'set':<{w}}  {'stage':<9} {'board':<8} detail")
    for r in rows:
        print(f"{r['set']:<{w}}  {r['stage']:<9} {r['board'] or '-':<8} {r['detail']}")
    print(f"# {len(rows)} sets: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v)
          + (f"; {posted} dashboard tasks moved" if a.post else ""))
    return None


def register(sub) -> None:
    s = sub.add_parser("status", help="each set's stage from its set dir, beside its dashboard state")
    s.add_argument("sets", nargs="*", metavar="SET")
    s.add_argument("--area", help="only the sets of this area")
    s.add_argument("--stage", choices=STAGES, help="only sets at this stage")
    s.add_argument("--json", action="store_true", help="one JSON list instead of the table")
    s.add_argument("--post", action="store_true", help="move dashboard tasks to the state each stage implies")
    s.set_defaults(func=cmd_status, owns_state=False, record=False)

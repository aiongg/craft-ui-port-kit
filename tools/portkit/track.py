"""Progress dashboard: the store, the derived state, and the Python API kit tools use.

The store lives in the port workspace (port.toml `track.dir`):

  events.jsonl   append-only, one JSON object per line. Every writer appends with one O_APPEND write per event, so
                 several agents and tools can write at once without a lock server.
  state.json     derived: a fold over every event, rewritten after each write. Never edited by hand; delete it and
                 `track publish` rebuilds it.
  .lock          serialises the fold and the publish (fcntl.flock). Appends never take it.
  .folded        byte offset of events.jsonl that state.json covers; a writer whose event is already covered skips
                 its own fold.

After every write the state is published to `track.out_dir`: the page (dashboard/), `state.json` and `state.js` (the
same data as a script, for a page opened from the file system). tools/track.md documents the event and state formats.

Python API (never raises; does nothing when no store is configured):

    from portkit import track
    track.event(kind, text, task=None, data=None, links=None)
    with track.recorded(kind, task=None) as rec:      # posts "<kind> ok|failed (<duration>): <text>" at exit
        ...
        rec.result(text, log=None, data=None, ok=None)
    track.status(task, state, note=None, on=None)
    track.round(n, passed, failed, log=None, data=None)

A store is configured when a port.toml is found (PORT_KIT_CONFIG, ./port.toml or a parent directory) or
PORT_KIT_TRACK_DIR is set.
"""
from __future__ import annotations

import builtins
import contextlib
import json
import os
import re
import secrets
import statistics
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # no flock: folds may race, the events stay correct and the next write repairs the state
    fcntl = None

from . import config as _config

KIT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = KIT_ROOT / "dashboard"
PAGE_FILES = ("index.html", "app.js", "app.css")

STATES = ("todo", "running", "review", "waiting", "blocked", "failed", "done")
STEPS = ("plan", "write", "compile", "test", "fix", "merge")
ASK_FOR = ("developer", "lead")
# Kinds the fold gives a meaning; `track event` and track.event() take any other lowercase kind.
RESERVED = ("status", "step", "task", "ask", "answer", "round", "phase", "pause", "resume", "head")
KIND_RE = re.compile(r"[a-z][a-z0-9-]{0,39}")
TASK_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,79}")
PHASES = {0: "Setup", 1: "Inventory and map", 2: "Plan", 3: "Contract stubs", 4: "Plan check and decisions",
          5: "Write", 6: "Review, combine, compile", 7: "Tests and red rounds", 8: "Look and behaviour", 9: "Land"}
TEXT_CAP = 2000          # characters kept of one text field
HISTORY_CAP = 40         # state changes kept per task in state.json (events.jsonl keeps all)
LOG_CAP = 400            # newest events the page's log gets
STATE_VERSION = 1


class TrackError(Exception):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def parse_t(s) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def duration(seconds: float) -> str:
    s = int(builtins.round(seconds))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


def _cap(v):
    if isinstance(v, str):
        return v if len(v) <= TEXT_CAP else v[:TEXT_CAP - 1] + "…"
    return v


def linkval(v) -> str | None:
    """URLs stay as they are. A relative path that exists under track.out_dir stays relative (the page resolves it
    against itself); any other path that exists from here becomes absolute, so the page shows where it is."""
    if not v:
        return None
    v = str(v)
    if "://" in v:
        return v
    p = Path(v).expanduser()
    if not p.is_absolute() and not v.startswith("~"):
        s = _store()
        if s is not None and (s.out_dir / p).exists():
            return v
    return str(p.resolve()) if p.exists() else v


def new_event(kind: str, **fields) -> dict:
    """An event record: time, a random id, the kind, and the fields that are set."""
    rec = {"t": iso(now_utc()), "id": secrets.token_hex(6), "kind": kind}
    for k, v in fields.items():
        if v is None or v == {} or v == []:
            continue
        rec[k] = _cap(v)
    return rec


def check_task(task: str) -> str:
    if not isinstance(task, str) or not TASK_RE.fullmatch(task):
        raise TrackError(f"task id {task!r}: letters, digits and . _ / -, starting with a letter or digit")
    return task


def check_kind(kind: str) -> str:
    if not KIND_RE.fullmatch(kind or ""):
        raise TrackError(f"event kind {kind!r}: lowercase letters, digits and dashes")
    if kind in RESERVED:
        raise TrackError(f"event kind {kind!r} is reserved; use the `track {kind}` command")
    return kind


# ---------------------------------------------------------------- the store

class Store:
    def __init__(self, cfg: _config.Config):
        self.cfg = cfg
        self.dir = Path(cfg.require("track.dir"))
        self.out_dir = Path(cfg.require("track.out_dir"))
        self.stale_min = int(cfg.get("track.stale_min", 20))
        self.events_path = self.dir / "events.jsonl"
        self.state_path = self.dir / "state.json"
        self.lock_path = self.dir / ".lock"
        self.folded_path = self.dir / ".folded"

    # ---- writing
    def append(self, rec: dict) -> int:
        """Append one event with one O_APPEND write; returns the file offset just past it."""
        self.dir.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        fd = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            n = os.write(fd, data)
            if n != len(data):   # a short write on a regular file means the disk is full; the fold skips the torn line
                raise TrackError(f"short write to {self.events_path}: {n} of {len(data)} bytes")
            return os.lseek(fd, 0, os.SEEK_CUR)
        finally:
            os.close(fd)

    def write(self, recs: list[dict], need_state: bool = False) -> dict | None:
        """Append the events, then fold and publish unless another writer's fold already covered them."""
        end = 0
        for r in recs:
            end = self.append(r)
        return self.refresh(upto=None if need_state else end)

    @contextlib.contextmanager
    def _locked(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def refresh(self, upto: int | None = None) -> dict | None:
        """Fold events.jsonl into state.json and publish. With `upto`, skip when the state already covers that offset."""
        with self._locked():
            if upto is not None and self._folded() >= upto:
                return None
            events, size, bad = self.read_events()
            moved = self._heads_moved(events)
            if moved:
                for r in moved:
                    self.append(r)
                events, size, bad = self.read_events()
            state = fold(events, now_utc(), stale_min=self.stale_min)
            state.update(bytes=size, bad_lines=bad, app=self.cfg.get("app.name") or "",
                         how_served=self.cfg.get("track.how_served"))
            _write_atomic(self.state_path, _dumps(state))
            self.publish(state)
            _write_atomic(self.folded_path, str(size))
            return state

    def _folded(self) -> int:
        try:
            return int(self.folded_path.read_text().strip() or 0)
        except (OSError, ValueError):
            return 0

    # ---- reading
    def read_events(self) -> tuple[list[dict], int, int]:
        """Every complete event line, the byte offset after the last one, and the count of unreadable lines."""
        try:
            raw = self.events_path.read_bytes()
        except FileNotFoundError:
            return [], 0, 0
        end = raw.rfind(b"\n") + 1     # a line still being written has no newline yet
        events, bad = [], 0
        for line in raw[:end].splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if not isinstance(e, dict) or "kind" not in e or "t" not in e:
                    raise ValueError
                events.append(e)
            except ValueError:
                bad += 1
        return events, end, bad

    def state(self) -> dict:
        """state.json, folded first when it is missing or behind the events."""
        try:
            size = self.events_path.stat().st_size
        except FileNotFoundError:
            size = 0
        if self.state_path.exists() and self._folded() >= size:
            try:
                return json.loads(self.state_path.read_text())
            except ValueError:
                pass
        return self.refresh()

    # ---- derived extras
    def heads(self) -> list[tuple[str, str, str]]:
        out = []
        for item in self.cfg.get("track.heads", []) or []:
            label, eq, rest = item.partition("=")
            path, colon, ref = rest.rpartition(":")
            if eq and colon and label and path and ref:
                out.append((label.strip(), path, ref))
        return out

    def _heads_moved(self, events: list[dict]) -> list[dict]:
        known = {}
        for e in events:
            if e.get("kind") == "head":
                known[e.get("label")] = e.get("sha")
        out = []
        for label, path, ref in self.heads():
            if not os.path.isdir(path):
                continue
            try:
                r = subprocess.run(["git", "-C", path, "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                                   capture_output=True, text=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                continue
            sha = r.stdout.strip()
            if r.returncode or not sha or known.get(label) == sha:
                continue
            out.append(new_event("head", label=label, sha=sha, ref=ref, path=path, prev=known.get(label)))
        return out

    # ---- publishing
    def publish(self, state: dict) -> None:
        """Write the page and its data into out_dir. Page files are copied only when they changed."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for name in PAGE_FILES:
            src = DASHBOARD / name
            if not src.is_file():
                continue
            data = src.read_bytes()
            dst = self.out_dir / name
            try:
                if dst.read_bytes() == data:
                    continue
            except OSError:
                pass
            _write_atomic(dst, data)
        text = _dumps(state)
        if self.out_dir.resolve() != self.dir.resolve():
            _write_atomic(self.out_dir / "state.json", text)
        # A page opened as a file cannot fetch(); it loads this script instead.
        _write_atomic(self.out_dir / "state.js", "window.TRACK_STATE = " + text + ";\n")


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1)


def _write_atomic(path: Path, data) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if isinstance(data, str):
        data = data.encode()
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------- the fold

def _new_task(tid: str, t: str) -> dict:
    return {"id": tid, "title": "", "group": "", "state": "todo", "step": None, "note": None, "on": None,
            "links": {}, "model": None, "calls": 0, "runs": [], "created": t, "updated": t, "changed": t,
            "started": None, "ended": None, "last": None, "history": []}


def summary(e: dict) -> str:
    """One line describing an event, for the log, `track show` and STATUS.md."""
    k = e.get("kind")
    if k == "status":
        s = e.get("state", "")
        if e.get("on"):
            s += f" on {e['on']}"
        return s + (f": {e['note']}" if e.get("note") else "")
    if k == "step":
        return f"step {e.get('step')}" + (f": {e['note']}" if e.get("note") else "")
    if k == "task":
        return "added" + (f": {e['title']}" if e.get("title") else "")
    if k == "ask":
        return f"{e.get('qid', 'question')} for {e.get('for', 'lead')}: {e.get('text', '')}"
    if k == "answer":
        return f"{e.get('qid')} answered by {e.get('by', 'lead')}: {e.get('text', '')}"
    if k == "round":
        return f"round {e.get('n')}: {e.get('pass')} pass, {e.get('fail')} fail"
    if k == "phase":
        n = e.get("n")
        return f"phase {n} {PHASES.get(n, '')}".rstrip() + (f": {e['note']}" if e.get("note") else "")
    if k in ("pause", "resume"):
        return ("paused" if k == "pause" else "resumed") + (f": {e['note']}" if e.get("note") else "")
    if k == "head":
        sha = (e.get("sha") or "")[:10]
        prev = (e.get("prev") or "")[:10]
        return f"{e.get('label')} at {sha}" + (f" (was {prev})" if prev else "")
    return e.get("text", "")


def fold(events: list[dict], now: datetime, stale_min: int = 20) -> dict:
    """Derive the whole state from the event list, in file order."""
    tasks: dict[str, dict] = {}
    questions: list[dict] = []
    rounds: list[dict] = []
    heads: dict[str, dict] = {}
    phase = None
    paused = {"on": False, "note": None, "t": None}
    log: deque = deque(maxlen=LOG_CAP)
    first_run: dict[str, datetime] = {}
    done_at: dict[str, datetime] = {}
    spans: dict[str, list[float]] = {}     # step or state label -> minutes spent, from measured events
    cur: dict[str, tuple[str, datetime]] = {}

    def task(tid, t):
        if tid not in tasks:
            tasks[tid] = _new_task(tid, t)
        return tasks[tid]

    def set_state(tk, t, state, step, note, on, explicit_step=False):
        old = (tk["state"], tk["step"])
        if state in ("todo", "done"):
            step = None
        elif not explicit_step:
            step = tk["step"]
        if note:
            tk["note"] = note
        elif (state, step) != old:
            tk["note"] = None    # a note belongs to the state it was written for
        if state in ("waiting", "blocked"):
            if on:
                tk["on"] = on
        else:
            tk["on"] = None
        tk["state"], tk["step"] = state, step
        td = parse_t(t)
        if (state, step) != old:
            tk["changed"] = t
            prev = cur.pop(tk["id"], None)
            if prev and td:
                spans.setdefault(prev[0], []).append((td - prev[1]).total_seconds() / 60)
            if state in ("running", "review") and td:
                cur[tk["id"]] = (step or state, td)
        if state == "running":
            tk["started"] = tk["started"] or t
            if td and tk["id"] not in first_run:
                first_run[tk["id"]] = td
        tk["ended"] = t if state == "done" else None
        if state == "done" and td:
            done_at[tk["id"]] = td
        if (state, step) != old or note:
            h = {"t": t, "state": state, "step": step, "note": note, "on": tk["on"]}
            tk["history"].append({k: v for k, v in h.items() if v})
            del tk["history"][:-HISTORY_CAP]

    for e in events:
        k, t = e.get("kind"), e.get("t")
        tk = None
        if e.get("task"):
            tk = task(str(e["task"]), t)
            tk["updated"] = t
            if e.get("links") and isinstance(e["links"], dict):
                tk["links"].update({str(a): str(b) for a, b in e["links"].items()})
            if e.get("model"):
                tk["model"] = e["model"]
        if k == "status" and tk is not None and e.get("state") in STATES:
            set_state(tk, t, e["state"], None, e.get("note"), e.get("on"))
            if isinstance(e.get("calls"), int):
                tk["runs"].append({"calls": e["calls"], "t": t, "step": tk["step"]})
                tk["calls"] = sum(r["calls"] for r in tk["runs"])
        elif k == "step" and tk is not None and e.get("step"):
            state = tk["state"] if tk["state"] in ("waiting", "blocked") else "running"
            set_state(tk, t, state, e["step"], e.get("note"), None, explicit_step=True)
        elif k == "task" and tk is not None:
            for f in ("title", "group"):
                if e.get(f):
                    tk[f] = e[f]
        elif k == "ask":
            qid = f"q{len(questions) + 1}"
            q = {"id": qid, "task": e.get("task"), "text": e.get("text", ""), "options": e.get("options") or [],
                 "for": e.get("for") if e.get("for") in ASK_FOR else "lead", "t": t, "answer": None,
                 "event": e.get("id")}
            questions.append(q)
            e = {**e, "qid": qid}
            if tk is not None and tk["state"] != "done":
                set_state(tk, t, "waiting", None, f"{qid}: {q['text'][:200]}", q["for"])
        elif k == "answer":
            q = next((q for q in questions if q["id"] == e.get("qid")), None)
            if q is not None:
                q["answer"] = {"text": e.get("text", ""), "by": e.get("by", "lead"), "t": t}
                if not e.get("task") and q.get("task") in tasks:
                    e = {**e, "task": q["task"]}
                    tasks[q["task"]]["updated"] = t
        elif k == "round":
            rounds.append({"n": e.get("n"), "pass": e.get("pass"), "fail": e.get("fail"), "log": e.get("log"),
                           "data": e.get("data") or {}, "t": t, "task": e.get("task")})
        elif k == "phase":
            phase = {"n": e.get("n"), "name": PHASES.get(e.get("n"), ""), "note": e.get("note"), "t": t}
        elif k in ("pause", "resume"):
            paused = {"on": k == "pause", "note": e.get("note"), "t": t}
        elif k == "head":
            heads[e.get("label")] = {"sha": e.get("sha"), "ref": e.get("ref"), "path": e.get("path"),
                                     "prev": e.get("prev"), "since": t}
        elif tk is not None and k not in RESERVED:
            tk["last"] = {"kind": k, "text": e.get("text", ""), "ok": e.get("ok"), "t": t}
        item = {"t": t, "kind": k, "task": e.get("task"), "text": summary(e)}
        for f in ("ok", "links", "data", "by"):
            if e.get(f) not in (None, {}, ""):
                item[f] = e[f]
        log.append(item)

    counts = {s: 0 for s in STATES}
    for tk in tasks.values():
        counts[tk["state"]] += 1
    stale = []
    for tk in tasks.values():
        u = parse_t(tk["updated"])
        if tk["state"] in ("running", "review") and u and (now - u).total_seconds() >= stale_min * 60:
            stale.append({"task": tk["id"], "state": tk["state"], "step": tk["step"], "updated": tk["updated"],
                          "min": int((now - u).total_seconds() // 60)})
    stale.sort(key=lambda x: -x["min"])
    return {
        "version": STATE_VERSION, "generated": iso(now), "events": len(events), "stale_min": stale_min,
        "phase": phase, "paused": paused, "counts": counts, "tasks": tasks, "questions": questions,
        "rounds": rounds, "heads": heads, "stale": stale,
        "eta": eta(tasks, first_run, done_at, spans, now), "log": list(reversed(log)),
    }


def eta(tasks: dict, first_run: dict, done_at: dict, spans: dict, now: datetime) -> dict:
    """Projected finish from measured throughput (tasks done per hour) and the median time per step."""
    done = [i for i, tk in tasks.items() if tk["state"] == "done"]
    left = [i for i, tk in tasks.items() if tk["state"] != "done"]
    t0 = min(first_run.values(), default=now)
    span_h = max((now - t0).total_seconds() / 3600, 1.0)
    window_h = min(24.0, span_h)
    recent = sum(1 for i in done if i in done_at and done_at[i] >= now - timedelta(hours=window_h))
    rate_recent, rate_all = recent / window_h, len(done) / span_h
    times = [(done_at[i] - first_run[i]).total_seconds() / 3600 for i in done if i in done_at and i in first_run]
    rates = [r for r in (rate_recent, rate_all) if r > 0]
    if not left:
        low = high = iso(now)
    elif rates:
        low = iso(now + timedelta(hours=len(left) / max(rates)))
        high = iso(now + timedelta(hours=len(left) / min(rates)))
    else:
        low = high = None
    groups: dict[str, dict] = {}
    for tk in tasks.values():
        g = groups.setdefault(tk["group"] or "", {"total": 0, "left": 0})
        g["total"] += 1
        g["left"] += tk["state"] != "done"
    steps = {s: {"median_min": builtins.round(statistics.median(v), 1), "n": len(v)} for s, v in sorted(spans.items())}
    basis = (f"{len(done)} done; {recent} in the last {window_h:.0f} h ({rate_recent:.2f}/h), "
             f"{rate_all:.2f}/h since {t0.strftime('%m-%d %H:%M')} UTC" if done else "no task done yet")
    return {"done": len(done), "left": len(left), "rate_recent": builtins.round(rate_recent, 3),
            "rate_all": builtins.round(rate_all, 3), "window_h": builtins.round(window_h, 1),
            "median_task_h": builtins.round(statistics.median(times), 2) if times else None,
            "finish_low": low, "finish_high": high, "groups": groups, "steps": steps, "since": iso(t0),
            "basis": basis}


# ---------------------------------------------------------------- text views

def _age(t: str | None, now: datetime) -> str:
    d = parse_t(t)
    if not d:
        return "?"
    m = int((now - d).total_seconds() // 60)
    return f"{m} min" if m < 120 else f"{m // 60} h" if m < 2880 else f"{m // 1440} d"


def is_stale(tk: dict, now: datetime, stale_min: int) -> int | None:
    u = parse_t(tk.get("updated"))
    if tk.get("state") in ("running", "review") and u:
        m = int((now - u).total_seconds() // 60)
        if m >= stale_min:
            return m
    return None


def alert_lines(state: dict, now: datetime | None = None, stale_min: int | None = None) -> list[str]:
    now = now or now_utc()
    stale_min = state.get("stale_min", 20) if stale_min is None else stale_min
    out = []
    if (state.get("paused") or {}).get("on"):
        out.append("paused" + (f": {state['paused']['note']}" if state["paused"].get("note") else ""))
    tasks = state.get("tasks", {})
    for tk in tasks.values():
        m = is_stale(tk, now, stale_min)
        if m is not None:
            out.append(f"stale {tk['id']}: {tk['state']}" + (f" ({tk['step']})" if tk.get("step") else "")
                       + f", no update for {m} min (limit {stale_min})" + (f": {tk['note']}" if tk.get("note") else ""))
    for tk in tasks.values():
        if tk["state"] in ("blocked", "failed"):
            out.append(f"{tk['state']} {tk['id']}" + (f" on {tk['on']}" if tk.get("on") else "")
                       + (f": {tk['note']}" if tk.get("note") else ""))
    for q in state.get("questions", []):
        if not q.get("answer"):
            out.append(f"question {q['id']} for {q['for']} ({q.get('task') or '-'}, {_age(q['t'], now)}): {q['text']}"
                       + (f" [options: {' | '.join(q['options'])}]" if q.get("options") else ""))
        elif q.get("task") in tasks and tasks[q["task"]]["state"] == "waiting":
            a = q["answer"]
            out.append(f"answered {q['id']} ({q['task']} still waiting) by {a['by']}: {a['text']}")
    return out


def show_text(state: dict, task: str | None = None, now: datetime | None = None) -> str:
    now = now or now_utc()
    sm = state.get("stale_min", 20)
    tasks = state.get("tasks", {})
    if task:
        tk = tasks.get(task)
        if not tk:
            raise TrackError(f"no task {task}")
        L = [f"{tk['id']}  {tk.get('title') or ''}".rstrip(),
             f"  state: {tk['state']}" + (f" ({tk['step']})" if tk.get("step") else "")
             + (f" on {tk['on']}" if tk.get("on") else "") + f", updated {_age(tk['updated'], now)} ago"
             + (" STALE" if is_stale(tk, now, sm) is not None else "")]
        for f in ("note", "group", "model", "started", "ended"):
            if tk.get(f):
                L.append(f"  {f}: {tk[f]}")
        if tk.get("calls"):
            L.append(f"  calls: {tk['calls']} over {len(tk['runs'])} run(s)")
        for name, v in tk.get("links", {}).items():
            L.append(f"  link {name}: {v}")
        if tk.get("last"):
            L.append(f"  last tool event: {tk['last']['kind']}: {tk['last']['text']}")
        L.append("  history:")
        for h in tk.get("history", []):
            L.append(f"    {h['t']}  {h['state']}" + (f" ({h['step']})" if h.get("step") else "")
                     + (f" on {h['on']}" if h.get("on") else "") + (f": {h['note']}" if h.get("note") else ""))
        qs = [q for q in state.get("questions", []) if q.get("task") == task]
        for q in qs:
            L.append(f"  {q['id']}: {q['text']}" + (f" -> {q['answer']['text']}" if q.get("answer") else " (open)"))
        return "\n".join(L)
    ph = state.get("phase") or {}
    L = [f"{state.get('app') or 'Port'}: " + (f"phase {ph['n']} {ph.get('name', '')}".rstrip() if ph else "phase not set")
         + (f" ({ph['note']})" if ph.get("note") else "")]
    if (state.get("paused") or {}).get("on"):
        L.append("PAUSED" + (f": {state['paused']['note']}" if state["paused"].get("note") else ""))
    c = state.get("counts", {})
    L.append("tasks: " + ", ".join(f"{s} {c.get(s, 0)}" for s in STATES if c.get(s)) if tasks else "tasks: none yet")
    if state.get("rounds"):
        r = state["rounds"][-1]
        L.append(f"latest round {r['n']}: {r['pass']} pass, {r['fail']} fail")
    e = state.get("eta") or {}
    if e.get("left") and e.get("finish_low"):
        L.append(f"eta: {e['left']} left, finish {e['finish_low']} .. {e['finish_high']} ({e['basis']})")
    if state.get("how_served"):
        L.append(f"page: {state['how_served']}")
    for s in ("blocked", "failed", "waiting", "running", "review", "todo"):
        rows = [tk for tk in tasks.values() if tk["state"] == s]
        if not rows:
            continue
        L.append(f"\n{s} ({len(rows)})")
        for tk in rows[:200]:
            st = is_stale(tk, now, sm)
            L.append(f"  {tk['id']:<22} " + (f"[{tk['step']}] " if tk.get("step") else "")
                     + (f"on {tk['on']} " if tk.get("on") else "") + (tk.get("note") or tk.get("title") or "")
                     + f"  ({_age(tk['updated'], now)}" + (", STALE" if st is not None else "") + ")")
        if len(rows) > 200:
            L.append(f"  ... {len(rows) - 200} more")
    if c.get("done"):
        L.append(f"\ndone ({c['done']})")
    open_q = [q for q in state.get("questions", []) if not q.get("answer")]
    if open_q:
        L.append(f"\nopen questions ({len(open_q)})")
        for q in open_q:
            L.append(f"  {q['id']} for {q['for']} ({q.get('task') or '-'}): {q['text']}"
                     + (f" [options: {' | '.join(q['options'])}]" if q.get("options") else ""))
    return "\n".join(L)


def md_text(state: dict, now: datetime | None = None) -> str:
    """STATUS.md: phase, tasks by state, questions and rounds, for the app's port branch."""
    now = now or now_utc()
    ph = state.get("phase") or {}
    esc = lambda s: str(s or "").replace("|", "\\|").replace("\n", " ")
    L = [f"# {state.get('app') or 'Port'} port status", "",
         f"Generated by `track md` at {iso(now)} from the progress dashboard. Do not edit by hand.", "",
         (f"- Phase: {ph['n']} {ph.get('name', '')}".rstrip() if ph else "- Phase: not set") + (f" ({esc(ph['note'])})" if ph.get("note") else "")]
    if (state.get("paused") or {}).get("on"):
        L.append("- Paused" + (f": {esc(state['paused'].get('note'))}" if state["paused"].get("note") else ""))
    c = state.get("counts", {})
    L.append("- Tasks: " + (", ".join(f"{s} {c[s]}" for s in STATES if c.get(s)) or "none"))
    e = state.get("eta") or {}
    if e.get("left") and e.get("finish_low"):
        L.append(f"- Projected finish: {e['finish_low']} to {e['finish_high']} ({esc(e['basis'])})")
    tasks = state.get("tasks", {})
    for s in ("blocked", "failed", "waiting", "running", "review", "todo", "done"):
        rows = [tk for tk in tasks.values() if tk["state"] == s]
        if not rows:
            continue
        L += ["", f"## {s.capitalize()} ({len(rows)})", "", "| Task | Step | On | Note | Updated |", "|---|---|---|---|---|"]
        for tk in rows:
            L.append(f"| {esc(tk['id'])} | {esc(tk.get('step'))} | {esc(tk.get('on'))} | "
                     f"{esc(tk.get('note') or tk.get('title'))} | {tk['updated']} |")
    qs = state.get("questions", [])
    if qs:
        L += ["", "## Questions", "", "| Id | Task | For | Question | Answer |", "|---|---|---|---|---|"]
        for q in qs:
            a = q.get("answer")
            L.append(f"| {q['id']} | {esc(q.get('task'))} | {q['for']} | {esc(q['text'])} | "
                     + (f"{esc(a['text'])} ({a['by']})" if a else "open") + " |")
    if state.get("rounds"):
        L += ["", "## Rounds", "", "| Round | Pass | Fail | When | Log |", "|---|---|---|---|---|"]
        for r in state["rounds"]:
            L.append(f"| {esc(r['n'])} | {r['pass']} | {r['fail']} | {r['t']} | {esc(r.get('log'))} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- Python API

_STORE: Store | None | bool = False     # False: not looked up yet
_WARNED = False


def open_store(config_file: str | None = None, required: bool = False) -> Store | None:
    """The configured store, or None when no port.toml is found and PORT_KIT_TRACK_DIR is unset."""
    cfg = _config.load(config_file)
    if cfg.file is None and not os.environ.get(_config.env_name("track.dir")):
        if required:
            raise TrackError("no port workspace: run inside it, or set PORT_KIT_CONFIG or PORT_KIT_TRACK_DIR")
        return None
    return Store(cfg)


def _store() -> Store | None:
    global _STORE
    if _STORE is False:
        _STORE = open_store()
    return _STORE


def _warn(e: BaseException) -> None:
    global _WARNED
    if not _WARNED:
        _WARNED = True
        print(f"track: event not recorded: {e}", file=sys.stderr)


def _post(recs: list[dict]) -> None:
    try:
        s = _store()
        if s is not None:
            s.write(recs)
    except Exception as e:  # recording progress must never break the tool that records it
        _warn(e)


def event(kind, text, task=None, data=None, links=None):
    """Record a free event (merge, landing, decision, a tool's result). Never raises."""
    try:
        check_kind(kind)
        if task is not None:
            check_task(task)
        rec = new_event(kind, task=task, text=str(text), data=dict(data) if data else None,
                        links={str(k): linkval(v) for k, v in links.items() if v} if links else None)
    except Exception as e:
        _warn(e)
        return
    _post([rec])


def status(task, state, note=None, on=None):
    """Set a task's state, for tools that own one (port-set, swarm.py). Never raises."""
    try:
        check_task(task)
        if state not in STATES:
            raise TrackError(f"state {state!r}: one of {', '.join(STATES)}")
        rec = new_event("status", task=task, state=state, note=note, on=on)
    except Exception as e:
        _warn(e)
        return
    _post([rec])


def round(n, passed, failed, log=None, data=None):  # noqa: A001 (the fixed API name)
    """Record a full test run's result; the page draws the trend. Never raises."""
    try:
        rec = new_event("round", n=str(n), log=linkval(log), data=dict(data) if data else None,
                        **{"pass": int(passed), "fail": int(failed)})
    except Exception as e:
        _warn(e)
        return
    _post([rec])


class Recording:
    """What `recorded()` yields: set the result line, and optionally the outcome, before the block ends."""

    def __init__(self):
        self.text = None
        self.log = None
        self.data = None
        self.links = None
        self.ok = None

    def result(self, text, log=None, data=None, ok=None, links=None):
        """`ok=False` records a failure without raising (a gate that found errors). `links` is as in `event`."""
        self.text, self.log, self.data, self.ok, self.links = str(text), log, data, ok, links


@contextlib.contextmanager
def recorded(kind, task=None):
    """Post one event when the block ends: "<kind> ok|failed (<duration>): <text>", also on exceptions and exits.

    The block's outcome is failed when it raises, exits non-zero, or calls rec.result(..., ok=False)."""
    rec = Recording()
    t0 = time.monotonic()
    ok, why = True, None
    try:
        yield rec
    except SystemExit as e:
        ok = e.code in (None, 0)
        if not ok:
            why = f"exit {e.code}" if isinstance(e.code, int) else str(e.code)
        raise
    except KeyboardInterrupt:
        ok, why = False, "interrupted"
        raise
    except BaseException as e:
        ok = False
        why = (f"{type(e).__name__}: {e}".splitlines() or [type(e).__name__])[0]
        raise
    finally:
        if ok and rec.ok is False:
            ok = False
        secs = time.monotonic() - t0
        text = rec.text or ("done" if ok else "")
        if why:
            text = f"{text}; {why}" if text else why
        data = {**(rec.data or {}), "seconds": builtins.round(secs, 1)}
        try:
            check_kind(kind)
            if task is not None:
                check_task(task)
            links = {str(k): linkval(v) for k, v in (rec.links or {}).items() if v}
            if rec.log:
                links["log"] = linkval(rec.log)
            r = new_event(kind, task=task, ok=ok, text=f"{kind} {'ok' if ok else 'failed'} ({duration(secs)}): {text}",
                          data=data, links=links or None)
            _post([r])
        except Exception as e:
            _warn(e)

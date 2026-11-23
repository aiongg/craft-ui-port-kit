"""Helpers shared by compile-gate, test-run and racheck-gate: run directory, the cl command line, logged runs.

Also the phase exit table that `track phase` runs (PHASE_EXITS, below the build helpers)."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tomllib
from pathlib import Path

ERROR_LINE = re.compile(r"^[^ ]+\.rs:[0-9]+:[0-9]+: error")


def run_dir(cfg, label: str) -> Path:
    """<work.runs>/<label>/, created. One directory per run label holds every log of the run."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", label):
        raise SystemExit(f"run label {label!r}: use letters, digits, dot, dash and underscore")
    d = cfg.path("work.runs") / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def cl_env(cfg, base=None) -> dict:
    """Environment for cl: the launcher and runner roles (empty means run directly) and the target dir."""
    env = dict(os.environ if base is None else base)
    env["CL_LAUNCHER"] = cfg.get("build.launcher") or ""
    env["CL_RUNNER"] = cfg.get("build.runner") or ""
    target = cfg.get("build.target_dir")
    if target:
        env["CARGO_TARGET_DIR"] = str(target)
    return env


def capped(cfg, cmd: list[str]) -> list[str]:
    """cmd under build.memory_cap with {gb} = build.memory_gb; unchanged when no cap is configured."""
    cap = cfg.get("build.memory_cap") or ""
    if not cap:
        return cmd
    return shlex.split(cap.replace("{gb}", str(cfg.get("build.memory_gb")))) + cmd


def cl(cfg, args: list[str]) -> list[str]:
    """The command line for one cl call, under the memory cap."""
    return capped(cfg, [str(cfg.path("build.cl")), *args])


def run_logged(cmd: list[str], cwd: Path, log: Path, env: dict) -> int:
    """Run cmd with stdout and stderr appended to log; its exit status."""
    with open(log, "ab") as f:
        f.write(("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n").encode())
        f.flush()
        return subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode


def error_lines(log: Path) -> list[str]:
    """Sorted unique `file.rs:line:col: error ...` lines of a cargo `--message-format short` log."""
    if not log.is_file():
        return []
    return sorted({l.rstrip("\n") for l in open(log, errors="replace") if ERROR_LINE.match(l)})


# Lines cargo prints around errors that are no error of their own.
NOT_A_CAUSE = ("error: could not compile", "error: aborting due to", "error: build failed")


def plain_errors(log: Path) -> list[str]:
    """`error...` lines without a file position (resolution, manifest, linker, a tool's own failure), in log order,
    unique. They name the cause when a nonzero exit left no `file:line:col: error` line."""
    if not log.is_file():
        return []
    out = [l.rstrip("\n") for l in open(log, errors="replace")
           if l.startswith("error") and not ERROR_LINE.match(l) and not l.startswith(NOT_A_CAUSE)]
    return list(dict.fromkeys(out))


def by_package(tree: Path, errors: list[str]) -> dict[str, list[str]]:
    """Error lines grouped by the cargo package owning each line's file (`?` when no package owns it)."""
    out: dict[str, list[str]] = {}
    for e in errors:
        out.setdefault(package_of(tree, e.split(":", 1)[0]) or "?", []).append(e)
    return out


def write_summary(rd: Path, data: dict) -> Path:
    """<run dir>/summary.json, the machine-readable result of a gate or test run."""
    f = rd / "summary.json"
    f.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    return f


def package_of(tree: Path, rel: str) -> str | None:
    """Cargo package name owning the file `rel` of the tree: the nearest Cargo.toml above it that has a [package]."""
    d = (tree / rel).parent
    while True:
        m = d / "Cargo.toml"
        if m.is_file():
            try:
                name = tomllib.loads(m.read_text()).get("package", {}).get("name")
            except tomllib.TOMLDecodeError:
                name = None
            if name:
                return name
        if d == tree or d == d.parent:
            return None
        d = d.parent


def committed_lock(app: Path) -> dict:
    """The app's Cargo.lock as committed at HEAD (the working copy only when the lock is not tracked): a local build
    rewrites the working lock with path sources, so only the committed one still names the framework's git sources."""
    r = subprocess.run(["git", "-C", str(app), "show", "HEAD:Cargo.lock"], capture_output=True, text=True)
    text = r.stdout if r.returncode == 0 else (app / "Cargo.lock").read_text()
    return tomllib.loads(text)


def framework_packages(cfg, app: Path) -> list[str]:
    """Packages the app's committed lock takes from a framework URL (framework.patch_urls), sorted."""
    urls = [u.rstrip("/") for u in cfg.require("framework.patch_urls")]
    return sorted({p["name"] for p in committed_lock(app).get("package", [])
                   if any(p.get("source", "").startswith("git+" + u) for u in urls)})


def changed_files(tree: Path, base: str, suffix: str | None = None) -> list[str]:
    """Files added, modified or renamed between `base` and HEAD in the tree."""
    out = subprocess.run(["git", "-C", str(tree), "diff", "--name-only", "--diff-filter=AMR", base, "HEAD"],
                         capture_output=True, text=True, check=True).stdout.split()
    return [f for f in out if not suffix or f.endswith(suffix)]



# ---------------------------------------------------------------- phase exits
#
# `track phase N` runs the rows of the phase it leaves before it records N. A row checks one item of that phase's
# runbook Exit list that a script can decide without a build. Adding a row is one entry in PHASE_EXITS: a function
# that takes the GateContext and returns None when the item holds, else the reason it fails.

class GateContext:
    """What a row may read: the config, the folded board, the events since the current phase began."""

    def __init__(self, cfg, state: dict, events: list[dict], started, stale: list[str]):
        self.cfg = cfg
        self.state = state
        self.events = events          # events after the latest phase event, in file order
        self.started = started        # datetime of the latest phase event, or None
        self.stale = stale            # ids of stale tasks, against the clock
        self.heads = {}               # {"app" | "framework": sha} the look rows compare pairs with, for a landing

    def tasks(self) -> dict:
        return self.state.get("tasks", {})

    def open_questions(self) -> list[dict]:
        return [q for q in self.state.get("questions", []) if not q.get("answer")]

    def last_event(self, kind: str) -> dict | None:
        return next((e for e in reversed(self.events) if e.get("kind") == kind), None)

    def git(self, key: str, *args) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.cfg.get(key)), *args], capture_output=True, text=True)

    def tool(self, *argv) -> tuple[int, str]:
        """Run a kit tool against this port.toml; its exit status and last output line."""
        from .config import ENV_CONFIG, KIT_ROOT
        env = dict(os.environ)
        if self.cfg.file:
            env[ENV_CONFIG] = str(self.cfg.file)
        r = subprocess.run([str(KIT_ROOT / "tools" / argv[0]), *argv[1:]], capture_output=True, text=True, env=env)
        lines = (r.stdout + r.stderr).strip().splitlines()
        return r.returncode, lines[-1] if lines else ""


class ExitCheck:
    def __init__(self, phase: int | None, text: str, check, group: str | None = None):
        self.phase = phase            # the phase whose exit this row checks; None: every phase
        self.text = text              # the runbook item, as the lead reads it
        self.check = check            # GateContext -> None | reason
        self.group = group            # "look" or "tests": the rows the landing tools also run (land_check)


def context(store) -> GateContext:
    """The context for leaving the store's current phase: the events after its latest phase event."""
    from . import track as T
    st = store.state()
    events, _, _ = store.read_events()
    last = max((i for i, e in enumerate(events) if e.get("kind") == "phase"), default=-1)
    now = T.now_utc()
    return GateContext(store.cfg, st, events[last + 1:], T.parse_t((st.get("phase") or {}).get("t")),
                       [i for i, tk in st["tasks"].items() if T.is_stale(tk, now, store.stale_min) is not None])


def _ids(items, n=8) -> str:
    items = list(items)
    return ", ".join(items[:n]) + (f" and {len(items) - n} more" if len(items) > n else "")


def _missing(*paths) -> str | None:
    gone = [str(p) for p in paths if not Path(p).exists()]
    return f"missing: {_ids(gone)}" if gone else None


def _sheet_ids(ctx) -> list[str] | None:
    d = ctx.cfg.path("work.sheets")
    return sorted(p.stem for p in d.glob("*.md")) if d.is_dir() else None


def x_state_md(ctx):
    p = ctx.cfg.path("work.state")
    if not p.is_file():
        return f"{p} is missing"
    if ctx.started and p.stat().st_mtime < ctx.started.timestamp():
        return f"{p.name} was not written since the phase began"
    return None


def x_no_blocked(ctx):
    bad = [f"{t['id']} ({t['state']})" for t in ctx.tasks().values() if t["state"] in ("blocked", "failed")]
    return f"blocked or failed: {_ids(bad)}" if bad else None


def x_no_stale(ctx):
    return f"stale: {_ids(ctx.stale)}" if ctx.stale else None


def x_no_blocking_question(ctx):
    bad = [q["id"] for q in ctx.open_questions() if q.get("blocking", True)]
    return f"open blocking questions: {_ids(bad)}" if bad else None


def x_keys(ctx):
    from .config import KEYS
    unset = [k.path for k in KEYS if k.required and not ctx.cfg.get(k.path)]
    unset += [k for k in ("plan.base", "plan.app_base") if not ctx.cfg.get(k)]
    return f"unset: {_ids(unset)}" if unset else None


def x_how_served(ctx):
    return None if ctx.cfg.get("track.how_served") else "track.how_served is not set"


def x_snapshots(ctx):
    return _missing(*(ctx.cfg.path(k) for k in ("framework.snapshot", "app.snapshot", "app.production")))


def x_baseline(ctx):
    if not ctx.cfg.path("work.baseline_failures").is_file():
        return f"{ctx.cfg.path('work.baseline_failures')} is missing"
    return None if ctx.state.get("rounds") else "no test round on the board"


def x_setup_done(ctx):
    bad = [i for i, t in ctx.tasks().items() if i.startswith("setup-") and t["state"] != "done"]
    if not any(i.startswith("setup-") for i in ctx.tasks()):
        return "no setup-* task on the board"
    return f"not done: {_ids(bad)}" if bad else None


def x_areas(ctx):
    import json
    p = ctx.cfg.path("work.inventory") / "areas.json"
    if not p.is_file():
        return f"{p} is missing"
    prop = json.loads(p.read_text())
    if isinstance(prop, dict) and isinstance(prop.get("areas"), dict):
        prop = prop["areas"]
    want = {a.get("id") for a in prop.get("areas", [])}
    have = {a["id"] for a in ctx.cfg.areas if a["repos"] != ["fw"]}
    if want != have:
        return f"areas.json only: {_ids(sorted(want - have)) or '-'}; port.toml only: {_ids(sorted(have - want)) or '-'}"
    return None


def x_maps(ctx):
    return _missing(*[a["map"] for a in ctx.cfg.areas if a["repos"] != ["fw"]], ctx.cfg.path("work.maps") / "README.md")


def x_coverage(ctx):
    rc, last = ctx.tool("coverage.py")
    return None if rc == 0 else f"coverage.py exit {rc}: {last}"


def x_sheets_on_board(ctx):
    ids = _sheet_ids(ctx)
    if ids is None:
        return f"{ctx.cfg.path('work.sheets')} is missing"
    bad = [i for i in ids if i not in ctx.tasks()]
    return f"not on the board (track import sheets): {_ids(bad)}" if bad else None


def x_sizing(ctx):
    return _missing(ctx.cfg.path("work.plan") / "sizing.md")


def x_developer_answered(ctx):
    bad = [q["id"] for q in ctx.open_questions() if q.get("for") == "developer"]
    return f"open developer questions: {_ids(bad)}" if bad else None


def x_linebase(ctx):
    lb = ctx.cfg.path("plan.linebase")
    if not lb.is_file():
        return f"{lb} is missing"
    r = ctx.git("framework.integration", "rev-parse", "--verify", "-q", f"{ctx.cfg.get('framework.writing_base')}^{{commit}}")
    if r.returncode != 0:
        return f"no branch {ctx.cfg.get('framework.writing_base')} in framework.integration"
    have, head = lb.read_text().strip(), r.stdout.strip()
    return None if have and head.startswith(have) else f"{lb.name} is {have[:12] or 'empty'}, the stub head is {head[:12]}"


def x_plan_errors(ctx):
    p = ctx.cfg.path("work.plan") / "plan-errors.md"
    if not p.is_file():
        return None
    bad = []
    for line in p.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("|") or len(cells) < 2 or set(line) <= set("|-: ") or cells[0].lower() == "stage":
            continue
        if not cells[-1]:
            bad.append(cells[1] if len(cells) > 1 else line[:40])
    return f"rows without a fix: {_ids(bad)}" if bad else None


def x_plancheck(ctx):
    ids = _sheet_ids(ctx) or []
    return _missing(*(ctx.cfg.path("work.sets") / i / "plancheck.md" for i in ids)) if ids else "no sheets"


def x_audit(ctx):
    rc, last = ctx.tool("port-set", "audit")
    return None if rc == 0 else f"port-set audit exit {rc}: {last}"


def x_written_checked(ctx):
    sets = sorted({e["task"] for e in ctx.events if e.get("task") and e.get("kind") in ("port-set-run", "port-set-agent")})
    if not sets:
        return "no set was written since the phase began"
    bad = []
    for s in sets:
        p = ctx.cfg.path("work.sets") / s / "check.md"
        text = p.read_text() if p.is_file() else ""
        errs = re.search(r"^## Errors\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
        if not errs or errs.group(1).strip() != "none":
            bad.append(s)
    return f"check.md missing or with errors: {_ids(bad)}" if bad else None


def _ok_since(kind):
    def check(ctx):
        e = ctx.last_event(kind)
        if e is None:
            return f"no {kind} run since the phase began"
        return None if e.get("ok") else f"the last {kind} failed: {str(e.get('text', ''))[:160]}"
    return check


def x_all_answered(ctx):
    bad = [q["id"] for q in ctx.open_questions()]
    return f"unanswered (rule them: prompts/p-rulings.md): {_ids(bad)}" if bad else None


def x_round_since(ctx):
    if not ctx.started:
        return None if ctx.state.get("rounds") else "no test round"
    from .track import parse_t
    ok = any((parse_t(r.get("t")) or ctx.started) >= ctx.started for r in ctx.state.get("rounds", []))
    return None if ok else "no test round since the phase began"


def x_no_diag(ctx):
    hits = []
    for key in ("framework.integration", "app.integration"):
        r = ctx.git(key, "grep", "-n", "DIAG ")
        if r.returncode == 0:
            hits.append(f"{key}: {len(r.stdout.splitlines())} lines")
        elif r.returncode != 1:
            hits.append(f"{key}: git grep failed")
    return f"DIAG lines: {_ids(hits)}" if hits else None


def x_committed(ctx):
    dirty = []
    for key in ("framework.integration", "app.integration"):
        r = ctx.git(key, "status", "--porcelain", "-uno")
        if r.returncode != 0 or r.stdout.strip():
            dirty.append(key)
    return f"uncommitted changes in {_ids(dirty)}" if dirty else None


def x_triage(ctx):
    runs = ctx.cfg.path("work.runs")
    stale = {l.split("\t", 1)[0] for l in _lines(runs / "stale.tsv")}
    judged = {l.split("\t", 1)[0] for l in _lines(runs / "triage.tsv")}
    left = sorted(stale - judged)
    return f"marked stale and not triaged: {_ids(left)}" if left else None


def _lines(p: Path) -> list[str]:
    return [l for l in p.read_text().splitlines() if l.strip()] if p.is_file() else []


def x_ledger(ctx):
    rc, last = ctx.tool("test-ledger.py", "--check")
    return None if rc == 0 else (last or f"test-ledger.py exit {rc}")


# ---- look rows (tools/look.md): states files from the maps, pairs from the current port head, the differences file

def _look_files(ctx) -> dict[str, dict]:
    """{panel: states file} for every states file in look.states_dir; an unreadable one raises."""
    d = ctx.cfg.path("look.states_dir")
    out = {}
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            out[f.stem] = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(f"{f.name} does not parse: {e}")
    return out


def _look_manifest(ctx, panel: str) -> dict:
    try:
        man = json.loads((ctx.cfg.path("track.out_dir") / "look" / panel / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {st["id"]: st for st in man.get("states", [])}


def _shot_ok(ctx, panel: str, entry: dict | None) -> bool:
    return bool(entry and entry.get("shot") and not entry.get("error")
                and (ctx.cfg.path("track.out_dir") / "look" / panel / entry["shot"]).is_file())


def _port_head(ctx) -> dict:
    """The commits pairs must come from: the integration trees' HEAD, or the commit a landing tool lands."""
    out = {}
    for name, key in (("app", "app.integration"), ("framework", "framework.integration")):
        if ctx.heads.get(name):
            out[name] = ctx.heads[name]
            continue
        r = ctx.git(key, "rev-parse", "HEAD") if ctx.cfg.get(key) else None
        out[name] = r.stdout.strip() if r is not None and r.returncode == 0 else None
    return out


def x_look_setup(ctx):
    bad = []
    for key in ("look.driver", "look.production_binary"):
        v = ctx.cfg.get(key)
        if not v:
            bad.append(f"{key} is not set")
        elif not ctx.cfg.path(key).is_file():
            bad.append(f"{key}: no file {ctx.cfg.path(key)}")
    return "; ".join(bad) or None


def x_look_calibrated(ctx):
    f = ctx.cfg.path("look.run_dir") / "calibrate.json"
    try:
        rep = json.loads(f.read_text())
    except (OSError, json.JSONDecodeError):
        return f"no {f.name} in look.run_dir (run `look calibrate --side up`)"
    up = (rep.get("sides") or {}).get("up")
    b = ctx.cfg.path("look.production_binary") if ctx.cfg.get("look.production_binary") else None
    if not up or not b or not b.is_file():
        return "calibrate.json has no production side"
    st = b.stat()
    if up.get("binary") != str(b) or up.get("size") != st.st_size or up.get("mtime") != st.st_mtime:
        return "calibrate.json is from another production build (run `look calibrate` again)"
    probs = rep.get("problems") or []
    return f"{len(probs)} problem(s): {probs[0]}" if probs else None


def x_look_states(ctx):
    from .look import states as S
    named = {str(st.get("map", "")).lower() for doc in _look_files(ctx).values() for st in doc.get("states", [])}
    missing, no_field = [], []
    for area, f in S.map_files(ctx.cfg).items():
        if not f.is_file():
            continue
        for sid, _part, fields in S.sections(f.read_text()):
            if "states" not in fields:
                no_field.append(f"{area} {sid}")
            elif not S.shows_nothing(fields) and f"{area} {sid}".lower() not in named:
                missing.append(f"{area} {sid}")
    why = []
    if missing:
        why.append(f"no state names the section (look states AREA SECTION): {_ids(missing)}")
    if no_field:
        why.append(f"no **States** field (write `none` for a part with nothing to show): {_ids(no_field)}")
    return "; ".join(why) or None


def x_look_production(ctx):
    files = _look_files(ctx)
    if not files:
        return f"no states files in {ctx.cfg.path('look.states_dir')}"
    bad = []
    for panel, doc in files.items():
        man = _look_manifest(ctx, panel)
        for st in doc.get("states", []):
            if st.get("needs"):
                bad.append(f"{panel} {st['id']} needs {st['needs']}")
            elif not _shot_ok(ctx, panel, man.get(st["id"], {}).get("up")):
                bad.append(f"{panel} {st['id']}: no production shot")
    return f"production does not reach (look pair --all --side up): {_ids(bad)}" if bad else None


def x_look_pairs(ctx):
    files = _look_files(ctx)
    if not files:
        return f"no states files in {ctx.cfg.path('look.states_dir')}"
    now = _port_head(ctx)
    bad = []
    for panel, doc in files.items():
        man = _look_manifest(ctx, panel)
        for st in doc.get("states", []):
            sid = st["id"]
            got = man.get(sid, {})
            if st.get("needs"):
                bad.append(f"{panel} {sid} needs {st['needs']}")
            elif not (_shot_ok(ctx, panel, got.get("up")) and _shot_ok(ctx, panel, got.get("port"))):
                bad.append(f"{panel} {sid}: no pair")
            else:
                h = got["port"].get("head") or {}
                old = [f"{k} {str(h.get(k))[:10]} (head {str(now[k])[:10]})" for k in ("app", "framework")
                       if h.get(k) != now[k]]
                if old:
                    bad.append(f"{panel} {sid}: captured at " + ", ".join(old))
                elif h.get("dirty"):
                    bad.append(f"{panel} {sid}: captured with local changes")
    return f"rerun look pair --all: {_ids(bad)}" if bad else None


def x_look_differences(ctx):
    from .look import differences as D, page
    rows = D.read(ctx.cfg.path("look.differences"))
    bad = []
    for panel in _look_files(ctx):
        for sid, st in _look_manifest(ctx, panel).items():
            if page.state_status(st) == "differs":
                why = D.state_verdict(D.for_state(rows, panel, sid))
                if why:
                    bad.append(f"{panel} {sid}: {why}")
    return _ids(bad) if bad else None


def x_look_accepted(ctx):
    tasks = ctx.tasks()
    bad = [f"look-{p}" for p in _look_files(ctx) if (tasks.get(f"look-{p}") or {}).get("state") != "done"]
    return f"not accepted (track status look-<Panel> done): {_ids(bad)}" if bad else None


PHASE_EXITS: list[ExitCheck] = [
    ExitCheck(None, "STATE.md records the phase", x_state_md),
    ExitCheck(None, "No task is blocked or failed", x_no_blocked),
    ExitCheck(None, "No task is stale", x_no_stale),
    ExitCheck(None, "No blocking question is open", x_no_blocking_question),
    ExitCheck(0, "port.toml has every required key, plan.base and plan.app_base", x_keys),
    ExitCheck(0, "track.how_served is recorded", x_how_served),
    ExitCheck(0, "The snapshots and the production reference exist", x_snapshots),
    ExitCheck(0, "work.baseline_failures exists and the baseline counts are on the dashboard", x_baseline),
    ExitCheck(0, "Every setup task on the board is done", x_setup_done),
    ExitCheck(0, "The look driver and the production build with its control hooks exist", x_look_setup),
    ExitCheck(0, "look calibrate passed on the current production build", x_look_calibrated),
    ExitCheck(1, "[[areas]] in port.toml matches areas.json", x_areas),
    ExitCheck(1, "Every area has its map; the index exists", x_maps),
    ExitCheck(1, "Every map section has a states file", x_look_states),
    ExitCheck(1, "Production reaches every state", x_look_production),
    ExitCheck(2, "tools/coverage.py reports 0 gaps", x_coverage),
    ExitCheck(2, "Every set is on the board", x_sheets_on_board),
    ExitCheck(2, "sizing.md exists", x_sizing),
    ExitCheck(2, "No developer question is open", x_developer_answered),
    ExitCheck(3, "The line references are on the stub head", x_linebase),
    ExitCheck(3, "plan-errors.md has a fix for every row", x_plan_errors),
    ExitCheck(4, "Every set has plancheck.md", x_plancheck),
    ExitCheck(4, "port-set audit reports 0", x_audit),
    ExitCheck(4, "The line references are on the stub head", x_linebase),
    ExitCheck(5, "Every set written in the batch has a check.md with no scripted error", x_written_checked),
    ExitCheck(6, "Every question of the batch is ruled", x_all_answered),
    ExitCheck(6, "combine-lost reports nothing", _ok_since("combine-lost")),
    ExitCheck(6, "The racheck gate passes", _ok_since("racheck-gate")),
    ExitCheck(6, "tools/compile-gate passes", _ok_since("compile-gate")),
    ExitCheck(7, "The last round is on the dashboard", x_round_since),
    ExitCheck(7, "git grep -n 'DIAG ' returns nothing in either integration tree", x_no_diag),
    ExitCheck(7, "Both integration branches are committed", x_committed),
    ExitCheck(7, "Every keep test a fixer marked stale has a triage row (work.runs/stale.tsv, triage.tsv)", x_triage),
    ExitCheck(8, "Every map section has a states file", x_look_states, "look"),
    ExitCheck(8, "Every state has a pair from the current port head", x_look_pairs, "look"),
    ExitCheck(8, "Every difference is fixed or has its reason in the differences file", x_look_differences, "look"),
    ExitCheck(8, "The lead accepted every panel", x_look_accepted, "look"),
    ExitCheck(8, "The tests ran after the last fix", x_round_since),
    ExitCheck(8, "Every test gone since the baseline has a delete verdict or a passing move target "
                 "(tools/test-ledger.py --check)", x_ledger, "tests"),
]

LAND_GROUPS = ("look", "tests")   # the row groups the landing tools run (tools/land/exit-gate.py)


def exit_failures(phase: int, ctx: GateContext) -> tuple[int, list[tuple[str, str]]]:
    """Run the rows for leaving `phase`: the number run, and (item, reason) for each that fails."""
    rows = [r for r in PHASE_EXITS if r.phase is None or r.phase == phase]
    out = []
    for r in rows:
        try:
            why = r.check(ctx)
        except Exception as e:   # a row that cannot run is a failure the lead must see, not a pass
            why = f"check failed to run: {e}"
        if why:
            out.append((r.text, why))
    return len(rows), out


def land_check(store, which: str, sha: str, group: str) -> tuple[bool, list[str]]:
    """One group of phase 8 rows (`look` or `tests`) for a landing tool that lands commit `sha` of the `app` or the
    `framework`; the look pairs must come from that commit. They pass, or the latest record of phase 9 was forced
    over every row that fails now (its decision event's `forced` data). The framework may land before phase 8
    without them (process/10-land.md). Returns (ok, lines to print)."""
    st = store.state()
    cur = (st.get("phase") or {}).get("n")
    if which == "framework" and (cur is None or cur < 8):
        return True, [f"{group} gate: early framework landing in phase {cur if cur is not None else 'not set'}; "
                      f"the {group} gate applies from phase 8"]
    ctx = context(store)
    ctx.heads = {which: sha}
    rows = [r for r in PHASE_EXITS if r.group == group]
    fails = []
    for r in rows:
        try:
            why = r.check(ctx)
        except Exception as e:
            why = f"check failed to run: {e}"
        if why:
            fails.append((r.text, why))
    if not fails:
        return True, [f"{group} gate: {len(rows)} of {len(rows)} {group} checks passed"]
    events, _, _ = store.read_events()
    i = max((k for k, e in enumerate(events) if e.get("kind") == "phase" and e.get("n") == 9), default=-1)
    dec = events[i - 1] if i > 0 and events[i - 1].get("kind") == "decision" else {}
    forced = dec.get("forced") or {}
    if forced.get("to") == 9 and {t for t, _ in fails} <= set(forced.get("items", [])):
        return True, [f"{group} gate: {len(fails)} {group} check(s) fail, forced by the decision of {dec.get('t')}: "
                      f"{forced.get('reason')}"] + [f"  - {t}: {w}" for t, w in fails]
    lines = [f"{group} gate: {len(fails)} {group} check(s) fail:"] + [f"  - {t}: {w}" for t, w in fails]
    lines.append('Fix them, or record the decision: track phase 9 --force "<reason>"'
                 + (" (it covers only the checks failing when it is recorded)" if forced else ""))
    return False, lines


def runbook(phase: int) -> Path | None:
    """process/NN-*.md for a phase: runbook files are numbered one higher than their phase."""
    from .config import KIT_ROOT
    return next(iter(sorted((KIT_ROOT / "process").glob(f"{phase + 1:02d}-*.md"))), None)


def exit_list(phase: int) -> list[str]:
    """The checklist lines of the runbook's Exit section."""
    p = runbook(phase)
    if not p:
        return []
    out, inside = [], False
    for line in p.read_text().splitlines():
        if line.startswith("## "):
            inside = bool(re.match(r"##\s+(\d+\.\s+)?Exit", line))
            continue
        if inside and line.startswith("- [ ]"):
            out.append(line[6:].strip())
    return out

if __name__ == "__main__":
    # `gates.py packages TREE < paths`: the cargo packages owning the given files, one per line, sorted.
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "packages":
        tree = Path(sys.argv[2]).resolve()
        print("\n".join(sorted({p for f in sys.stdin.read().split() if (p := package_of(tree, f))})))
    else:
        raise SystemExit("usage: gates.py packages TREE < paths")

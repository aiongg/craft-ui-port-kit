#!/usr/bin/env python3
"""swarm.py: run a batch of headless agents with the claude CLI: a workflow script, or a plain job list.

usage:
  swarm.py workflows/<name>.js --args ARGS.json [options]
  swarm.py JOBS.json [options]
  swarm.py --follow-up TASK PROMPT-FILE [--run-dir DIR] [--max-turns N] [--memory-gb N] [--config FILE]

options: --parallel N  --max-turns N  --retries N  --memory-gb N  --fresh  --dry-run  --run-dir DIR  --config FILE

It stands in for the Workflow tool, so a port needs only the claude CLI (process/12-running-agents.md).

Workflow scripts
  The script in workflows/ runs unchanged under node (18 or later), with the hooks the Workflow tool gives it:
  agent(prompt, opts), parallel(thunks), pipeline(items, ...stages), phase(title), log(message), args (the --args
  file) and budget (no limit). Every agent() call becomes one job, run here as `claude -p`. agent() returns the
  checked object when opts.schema is given, else the reply text, and null when the job failed. opts.label names the
  job, opts.model or opts.role picks its model (else models.default), opts.role its tools (below), opts.inputs lists
  the files it reads (below); opts.isolation, opts.effort and opts.agentType are ignored (a note is logged).
  workflow() is not available.

Job lists
  A JSON array; each job: {"task", "prompt" | "prompt_file", "model", "role" (a [models] key), "schema" |
  "schema_file", "cwd", "add_dirs", "inputs", "title", "group", "max_turns", "tools", "allow"}. Only task and the
  prompt are required. Relative paths resolve against the list's directory. Node is not needed. The results go to
  <run dir>/results.json as {task: value or null}.

Roles
  A job's role names its model (models.<role>, unless "model" is given) and its tools, from one table, ROLE_TOOLS
  below: every role gets Read, Grep, Glob, Bash, Write and Edit, with pipeline.lookup_tools, Write, Edit and the kit's
  track command auto-approved, and a role in the table also gets its own commands (fixers and the minimal-port writer `git add` and `git commit`, code-only fixers and that writer also `rustfmt`, every role `mkdir -p`,
  phase 2 sheet fixes and reconciles coverage.py and port-set). A job's own "tools" and
  "allow" replace these.

Each job
  - runs `claude -p` with the prompt on stdin, `--model`, `--output-format json`, `--strict-mcp-config`,
    `--settings templates/claude-settings.json` (read-only allowlist, rust-analyzer plugin off), `--max-turns`
    (pipeline.job_max_turns; a job of a fixer role, compile_fix, red_fixer or red_fixer_framework, gets 1.3 times
    pipeline.fixer_calls unless --max-turns or its own max_turns says otherwise), `--add-dir` for the kit, the
    workspace and the snapshots, and `--json-schema` when it has a schema. Tools: Read, Grep, Glob, Bash, Write and Edit; auto-approved: pipeline.lookup_tools, Write, Edit
    and the kit's track command (a job list's "tools" and "allow" replace these). The kit's tools dir is on PATH and
    PORT_KIT_CONFIG names port.toml, so `track` calls in the prompt reach the dashboard. Runs under
    build.memory_cap with --memory-gb (default 4) when the key is set.
  - checks the result against the schema; on a mismatch it resumes the same session once (--retries) with the
    errors, then fails the job.
  - keeps its session id in jobs/<key>/session, so a follow-up resumes it.
  - logs the call in work.usage_log (the port-set format, `set` = the job's task) and posts a `model-call` event.
  - is one task on the dashboard: `todo` when the script asks for it, `running`, then `done` or `failed`. The
    task id is opts.task when given, else the task named in the prompt's first `track step|status|ask <id>` call,
    else the label with `:` turned into `-`.

At most `pipeline.parallel` jobs run at once (--parallel). No new job starts while the dashboard's pause switch
is on (`track pause`), or while pipeline.quota_command reports pipeline.quota_cap percent or more; running jobs go on.

Resume
  The run dir (default <work.swarm>/<script or list name>) keeps each job's prompt, raw replies and checked result
  under jobs/<key>/, where the key is a hash of the prompt, model, schema and the content of every file the job
  names in "inputs" (opts.inputs). A job whose key has a good result is not run again: rerun the same command after
  a stop, a failure or an edit, and only new or failed jobs run; a job whose input file changed runs again.
  --fresh ignores the stored results. --dry-run lists the jobs with their keys and runs none (every agent() returns
  null).

Follow-up
  --follow-up TASK PROMPT-FILE sends PROMPT-FILE to the newest job of TASK (under --run-dir, else every run dir
  under work.swarm) as a resumed session: same model, tools, working directory and schema check, so the agent keeps
  what it read and did. That holds while the session's last context (its transcript's last turn, read through
  portkit/sessions.py) is under pipeline.follow_up_max_context. At or over it, the follow-up starts a fresh session
  instead: the job's own prompt, then its last report (the newest follow-up reply, else the job's result), then
  PROMPT-FILE; the fresh session becomes the job's saved session. A context that cannot be read resumes. Its reply
  goes to jobs/<key>/followup-<n>.json, its usage to work.usage_log, and the task moves to running, then done or
  failed, on the dashboard. Prints one JSON object on stdout:
  {"task", "ok", "value" (the checked object or reply text; null on failure), "error", "session_id", "cost_usd",
  "job_dir", "context" (tokens, or null when unknown), "fresh" (true when a fresh session was started)}. Exit 0 ok, 1 the call failed, 2 no such task, no saved session, or a usage error.

Output: the run log (phase and log lines) on stdout and in <run dir>/log.txt; at the end, the script's return
value as JSON on stdout and in <run dir>/result[-<stage>].json. Exit 0 when the script returned (failed jobs are
counted in the summary and the dashboard event), 1 when it threw, 2 for a usage or setup error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, sessions, track  # noqa: E402
from portkit.schema import schema_errors  # noqa: E402

KIT = config.KIT_ROOT
SETTINGS = KIT / "templates" / "claude-settings.json"
TOOLS = "Read,Grep,Glob,Bash,Write,Edit"
USAGE_HEAD = "time\tset\tstep\tmodel\tturns\tinput\tcache_write\tcache_read\toutput\tcost_usd\tsecs\n"
MARK = "\x1eSWARM "
# Commands each job role may run on top of the base set (pipeline.lookup_tools, Write, Edit, track). `{kit}` is the
# kit root. Roles are [models] keys.
_FIXER = ["Bash(git add:*)", "Bash(git commit:*)", "Bash(git diff:*)", "Bash(git status:*)", "Bash(git log:*)"]
_CODE_ONLY = _FIXER + ["Bash(rustfmt:*)"]  # code-only fixers format their files; they run no cargo fmt
ROLE_TOOLS = {
    "compile_fix": _CODE_ONLY,
    "minimal_write": _CODE_ONLY,
    "fix": _CODE_ONLY,
    "fix_retry": _CODE_ONLY,
    "red_fixer": _FIXER + ["Bash(python3 -I {kit}/tools/diag-cut.py:*)", "Bash({kit}/tools/diag-cut.py:*)"],
    "red_fixer_framework": _FIXER + ["Bash(python3 -I {kit}/tools/diag-cut.py:*)", "Bash({kit}/tools/diag-cut.py:*)"],
    "sheet_fix": ["Bash(python3 -I {kit}/tools/coverage.py:*)", "Bash({kit}/tools/port-set:*)"],
}
# Roles whose prompt states a call budget (pipeline.fixer_calls): their jobs get FIXER_TURNS times that many turns.
FIXER_ROLES = ("compile_fix", "red_fixer", "red_fixer_framework")
FIXER_TURNS = 1.3
TASK_IN_PROMPT = re.compile(r"\btrack\s+(?:step|status|ask)\s+([A-Za-z0-9][A-Za-z0-9._/-]{0,79})\b")


def _write(path: Path, text: str) -> None:
    """Files the kit writes are UTF-8 with LF endings on every platform."""
    path.write_text(text, encoding="utf-8", newline="\n")


def json_from_text(text: str):
    text = (text or "").strip()
    for cand in (text, *re.findall(r"```(?:json)?\s*\n(.*?)\n```", text, re.S)):
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, TypeError):
            pass
    a, b = text.find("{"), text.rfind("}")
    if 0 <= a < b:
        try:
            return json.loads(text[a:b + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("the reply holds no JSON object")


# ---------------------------------------------------------------- jobs

@dataclass
class Job:
    prompt: str
    label: str
    task: str
    model: str
    schema: dict | None = None
    phase: str | None = None
    title: str | None = None
    group: str | None = None
    cwd: str | None = None
    add_dirs: list[str] = field(default_factory=list)
    max_turns: int | None = None
    tools: str | None = None
    allow: str | None = None
    role: str | None = None
    inputs: list[str] = field(default_factory=list)

    def key(self) -> str:
        files = []
        for p in self.inputs:
            try:
                files.append([p, hashlib.sha256(Path(p).read_bytes()).hexdigest()])
            except OSError:
                files.append([p, "missing"])
        h = hashlib.sha256(json.dumps([self.prompt, self.model, self.schema, *([files] if files else [])],
                                      sort_keys=True).encode())
        return h.hexdigest()[:16]

    def record(self) -> dict:
        """What job.json keeps: enough to resume the job's session with the same settings."""
        return {"task": self.task, "label": self.label, "model": self.model, "phase": self.phase, "schema": self.schema,
                "role": self.role, "cwd": self.cwd, "add_dirs": self.add_dirs, "max_turns": self.max_turns,
                "tools": self.tools, "allow": self.allow, "inputs": self.inputs}


def task_id(opts: dict, prompt: str, label: str) -> str:
    for cand in (opts.get("task"), *(m.group(1) for m in TASK_IN_PROMPT.finditer(prompt))):
        if isinstance(cand, str) and track.TASK_RE.fullmatch(cand) and "{{" not in cand:
            return cand
    t = re.sub(r"[^A-Za-z0-9._/-]+", "-", label).strip("-") or "job"
    return t[:80]


class Swarm:
    def __init__(self, cfg: config.Config, run_dir: Path, a):
        self.cfg, self.run_dir, self.a = cfg, run_dir, a
        self.pool = ThreadPoolExecutor(max_workers=a.parallel)
        self.lock = threading.Lock()
        self.gate = threading.Lock()
        self.procs: set[subprocess.Popen] = set()
        self.stats = {"jobs": 0, "ok": 0, "failed": 0, "cached": 0, "cost": 0.0}
        self.halt = threading.Event()
        self.store = None
        try:
            self.store = track.open_store()
        except Exception as e:  # the dashboard is optional; jobs run without it
            print(f"swarm: dashboard not available: {e}", file=sys.stderr)
        self.quota_checked = 0.0
        self.claude = os.environ.get("PORT_KIT_CLAUDE_BIN", "claude")
        (run_dir / "jobs").mkdir(parents=True, exist_ok=True)

    # ---- output
    def say(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S", time.gmtime())
        with self.lock:
            print(f"{stamp} {line}", flush=True)
            with open(self.run_dir / "log.txt", "a", encoding="utf-8", newline="\n") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {line}\n")

    def board(self, job: Job, state: str, note: str | None = None, new: bool = False) -> None:
        if self.store is None or self.a.dry_run:
            return
        if new:
            try:
                self.store.write([track.new_event("task", task=job.task, title=job.title or job.label,
                                                  group=job.group, model=job.model)])
            except Exception as e:
                print(f"swarm: dashboard: {e}", file=sys.stderr)
        track.status(job.task, state, note)

    # ---- waiting
    def wait_to_start(self) -> None:
        """Hold a new job while the dashboard is paused or the quota is at its cap."""
        with self.gate:
            told = False
            while not self.halt.is_set() and self.paused():
                if not told:
                    self.say("paused (track pause): no new job starts until `track resume`")
                    told = True
                self.halt.wait(15)
            cmd = self.cfg.get("pipeline.quota_command")
            cap = int(self.cfg.get("pipeline.quota_cap"))
            told = False
            while cmd and not self.halt.is_set() and time.time() - self.quota_checked > 60:
                use = self.quota(cmd)
                if use is None or use < cap:
                    self.quota_checked = time.time()
                    break
                if not told:
                    self.say(f"quota at {use:.0f} % (cap {cap} %): waiting before the next job")
                    told = True
                self.halt.wait(60)

    def paused(self) -> bool:
        if self.store is None:
            return False
        try:
            return bool(self.store.state()["paused"]["on"])
        except Exception:
            return False

    def quota(self, cmd: str) -> float | None:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            m = re.search(r"\d+(?:\.\d+)?", r.stdout)
            return float(m.group(0)) if m else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    # ---- running
    def submit(self, job: Job) -> Future:
        with self.lock:
            self.stats["jobs"] += 1
        return self.pool.submit(self.run, job)

    def run(self, job: Job):
        jd = self.run_dir / "jobs" / job.key()
        jd.mkdir(parents=True, exist_ok=True)
        res = jd / "result.json"
        if res.is_file() and not self.a.fresh:
            try:
                d = json.loads(res.read_text())
                if d.get("ok"):
                    with self.lock:
                        self.stats["cached"] += 1
                        self.stats["ok"] += 1
                    self.say(f"{job.task}: done earlier (cached result)")
                    return d.get("value")
            except json.JSONDecodeError:
                pass
        _write(jd / "prompt.md", job.prompt)
        _write(jd / "job.json", json.dumps(job.record(), indent=1))
        if self.a.dry_run:
            self.say(f"{job.task}: would run {job.model}, max_turns {self.turns(job)}, {len(job.prompt)} chars"
                     f"{', schema' if job.schema else ''}, key {job.key()} ({jd / 'prompt.md'})")
            return None
        self.board(job, "todo", f"queued ({job.model})", new=True)
        self.wait_to_start()
        if self.halt.is_set():
            self.board(job, "failed", "batch stopped before the job started")
            return None
        self.board(job, "running", f"{job.model}: {job.label}")
        self.say(f"{job.task}: running ({job.model})")
        try:
            value, err = self.call(job, jd)
        except Exception as e:  # a broken job must not stop the batch
            value, err = None, f"{type(e).__name__}: {e}"
        if err is None:
            _write(res, json.dumps({"ok": True, "task": job.task, "label": job.label, "model": job.model,
                                       "value": value}, indent=1, ensure_ascii=False))
            with self.lock:
                self.stats["ok"] += 1
            self.board(job, "done")
            self.say(f"{job.task}: done")
            return value
        with self.lock:
            self.stats["failed"] += 1
        self.board(job, "failed", err[:300])
        self.say(f"{job.task}: FAILED: {err[:300]}")
        return None

    def command(self, job: Job, resume: str | None) -> list[str]:
        cfg = self.cfg
        allow = job.allow or ",".join([cfg.get("pipeline.lookup_tools"), "Write", "Edit",
                                       f"Bash({KIT / 'tools' / 'track'}:*)", "Bash(mkdir -p:*)",
                                       *(c.replace("{kit}", str(KIT)) for c in ROLE_TOOLS.get(job.role or "", []))])
        dirs = []
        cwd = Path(job.cwd or cfg.get("work.dir"))
        cands = [str(KIT), cfg.get("work.dir"), cfg.get("framework.snapshot"), cfg.get("app.snapshot"),
                 cfg.get("app.production"), cfg.get("app.release"), *job.add_dirs]
        for d in dict.fromkeys(c for c in cands if c):
            if Path(d).is_dir() and Path(d).resolve() != cwd.resolve():
                dirs += ["--add-dir", str(d)]
        cmd = [self.claude, "-p", "--model", job.model, "--output-format", "json", "--strict-mcp-config",
               "--settings", str(SETTINGS), "--tools", job.tools or TOOLS, "--allowedTools", allow,
               "--max-turns", str(self.turns(job)), *dirs]
        if job.schema:
            cmd += ["--json-schema", json.dumps(job.schema)]
        if resume:
            cmd += ["--resume", resume]
        cap = cfg.get("build.memory_cap")
        if cap:
            cmd = shlex.split(cap.replace("{gb}", str(self.a.memory_gb))) + cmd
        return cmd

    def turns(self, job: Job) -> int:
        """The job's own max_turns, else --max-turns, else 1.3 times pipeline.fixer_calls for a fixer role, else
        pipeline.job_max_turns."""
        if job.max_turns:
            return int(job.max_turns)
        if getattr(self.a, "max_turns_given", False) or job.role not in FIXER_ROLES:
            return int(self.a.max_turns)
        return math.ceil(FIXER_TURNS * int(self.cfg.get("pipeline.fixer_calls")))

    def env(self) -> dict:
        env = dict(os.environ, CLAUDE_CODE_MAX_OUTPUT_TOKENS="64000")
        # A headless agent is not the pane or the session that started it; hooks and `track usage` read these.
        for k in ("TMUX", "TMUX_PANE", sessions.ENV_SESSION):
            env.pop(k, None)
        env["PATH"] = f"{KIT / 'tools'}{os.pathsep}{env.get('PATH', '')}"
        env[config.ENV_AGENT] = "1"
        if self.cfg.file:
            env[config.ENV_CONFIG] = str(self.cfg.file)
        return env

    def call(self, job: Job, jd: Path, resume: str | None = None, prompt: str | None = None, tag: str = ""):
        """Run the job, or with `resume` a follow-up in its session; (value, None) on success, (None, reason) on
        failure."""
        prompt, tries = prompt or job.prompt, 0
        while True:
            d, err = self.one_call(job, jd, prompt, resume, tries, tag)
            if d and d.get("session_id"):
                _write(jd / "session", d["session_id"])
            if err:
                return None, err
            if not job.schema:
                return d.get("result") or "", None
            try:
                value = d.get("structured_output")
                if value is None:
                    value = json_from_text(d.get("result", ""))
                errs = schema_errors(value, job.schema)
            except ValueError as e:
                value, errs = None, [str(e)]
            if not errs:
                return value, None
            sid = d.get("session_id")
            if tries >= self.a.retries or not sid:
                return None, "result does not match the schema: " + "; ".join(errs[:5])
            tries += 1
            resume = sid
            prompt = ("Your result does not match the required JSON schema:\n- " + "\n- ".join(errs) +
                      "\nReturn the corrected result: only the JSON object, nothing else.")
            self.say(f"{job.task}: schema mismatch ({len(errs)} errors); asking once more")

    def one_call(self, job: Job, jd: Path, prompt: str, resume: str | None, n: int, tag: str = ""):
        cmd = self.command(job, resume=resume)
        cwd = job.cwd or self.cfg.get("work.dir")
        t0 = time.time()
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace", cwd=cwd, env=self.env(),
                                 start_new_session=True)
        except OSError as e:
            return None, f"cannot start {cmd[0]}: {e}"
        with self.lock:
            self.procs.add(p)
        try:
            out, errout = p.communicate(prompt)
        finally:
            with self.lock:
                self.procs.discard(p)
        secs = time.time() - t0
        _write(jd / f"{tag or 'call'}-{n}.out", out + ("\n--- stderr ---\n" + errout if errout else ""))
        try:
            d = json.loads(out)
            if isinstance(d, list):
                d = next((x for x in reversed(d) if isinstance(x, dict) and x.get("type") == "result"), d[-1])
            if not isinstance(d, dict):
                raise ValueError("not an object")
        except (json.JSONDecodeError, ValueError, IndexError):
            tail = (errout.strip().splitlines() or out.strip().splitlines() or ["no output"])[-1]
            return None, f"claude exit {p.returncode}: {tail[:200]}"
        self.usage(job, d, secs, n, tag)
        if d.get("subtype") == "error_max_turns":
            return d, f"out of turns ({self.turns(job)})"
        if d.get("is_error") or p.returncode != 0:
            return d, f"claude reported an error ({d.get('subtype') or p.returncode}): {str(d.get('result'))[:200]}"
        return d, None

    def usage(self, job: Job, d: dict, secs: float, n: int, tag: str = "") -> None:
        u = d.get("usage") or {}
        cost = float(d.get("total_cost_usd") or 0)
        nums = {"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}
        step = (f"{job.label} {tag}" if tag else job.label) + (f" retry-{n}" if n else "")
        row = [time.strftime("%Y-%m-%dT%H:%M"), job.task, step, job.model, str(d.get("num_turns")),
               *(str(v) for v in nums.values()), f"{cost:.3f}", f"{secs:.0f}"]
        with self.lock:
            self.stats["cost"] += cost
            log = Path(self.cfg.get("work.usage_log"))
            log.parent.mkdir(parents=True, exist_ok=True)
            if not log.exists():
                _write(log, USAGE_HEAD)
            with log.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write("\t".join(row) + "\n")
        track.event("model-call", f"{step}: {d.get('num_turns')} turns, out {nums['output']}, ${cost:.2f}, "
                    f"{secs:.0f} s ({job.model})", task=job.task,
                    data={"step": step, "model": job.model, "turns": d.get("num_turns"), **nums,
                          "cost_usd": round(cost, 3), "seconds": round(secs)})

    def stop(self) -> None:
        self.halt.set()
        with self.lock:
            procs = list(self.procs)
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
        self.pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------- workflow scripts under node

RUNTIME = r"""
const fs = require('fs')
const MARK = '\u001eSWARM '
const send = o => process.stdout.write(MARK + JSON.stringify(o) + '\n')
let seq = 0
const pending = new Map()
require('readline').createInterface({ input: process.stdin }).on('line', line => {
  const m = JSON.parse(line)
  const p = pending.get(m.id)
  if (p) { pending.delete(m.id); p(m.value === undefined ? null : m.value) }
})
const ask = (op, payload) => new Promise(resolve => { const id = ++seq; pending.set(id, resolve); send({ op, id, ...payload }) })
let current = null
const log = message => send({ op: 'log', message: String(message) })
const phase = title => { current = String(title); send({ op: 'phase', title: current }) }
const agent = async (prompt, opts) => {
  if (typeof prompt !== 'string') throw new Error('agent(): prompt must be a string')
  const o = Object.assign({}, opts || {})
  if (!o.phase && current) o.phase = current
  if (o.schema && (typeof o.schema !== 'object' || o.schema.type !== 'object')) throw new Error('agent(): schema needs type "object" at its root')
  return ask('agent', { prompt, opts: o })
}
const fail = (where, e) => { log(`${where} failed: ${e && e.message ? e.message : e}`); return null }
const parallel = async thunks => Promise.all(thunks.map((t, i) => Promise.resolve().then(t).catch(e => fail(`parallel[${i}]`, e))))
const pipeline = async (items, ...stages) => Promise.all(items.map(async (item, i) => {
  let r = item
  for (const s of stages) {
    try { r = await s(r, item, i) } catch (e) { return fail(`pipeline item ${i}`, e) }
  }
  return r
}))
const budget = { total: null, spent: () => 0, remaining: () => Infinity }
const workflow = async () => { throw new Error('workflow() is not available under swarm.py: run each workflow on its own') }
const args = JSON.parse(fs.readFileSync(process.env.SWARM_ARGS, 'utf8'))
const body = fs.readFileSync(process.env.SWARM_SCRIPT, 'utf8').replace(/^\s*export\s+const\s+meta\s*=/m, 'const meta =')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const done = (o, code) => process.stdout.write(MARK + JSON.stringify(o) + '\n', () => process.exit(code))
let fn
try {
  fn = new AsyncFunction('agent', 'parallel', 'pipeline', 'phase', 'log', 'args', 'budget', 'workflow', body)
} catch (e) { done({ op: 'error', message: `script does not parse: ${e.message}` }, 1) }
if (fn) fn(agent, parallel, pipeline, phase, log, args, budget, workflow).then(
  v => done({ op: 'return', value: v === undefined ? null : v }, 0),
  e => done({ op: 'error', message: e && e.message ? e.message : String(e), stack: e && e.stack }, 1))
"""


def model_for(cfg: config.Config, opts: dict) -> str:
    if opts.get("model"):
        return str(opts["model"])
    return cfg.model(opts.get("role"))


def run_workflow(sw: Swarm, script: Path, args_file: Path, name: str):
    node = shutil.which("node")
    if not node:
        raise SystemExit("swarm: node 18 or later is needed to run a workflow script (a job list needs no node)")
    env = dict(os.environ, SWARM_SCRIPT=str(script), SWARM_ARGS=str(args_file))
    p = subprocess.Popen([node, "-e", RUNTIME], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", env=env, bufsize=1)
    wlock = threading.Lock()
    noted: set[str] = set()

    def answer(mid: int, value) -> None:
        with wlock:
            try:
                p.stdin.write(json.dumps({"id": mid, "value": value}) + "\n")
                p.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass

    outcome = None
    try:
        outcome = _read_script(sw, p, name, answer, noted)
    except KeyboardInterrupt:
        p.kill()
        raise
    p.wait()
    if outcome is None:
        outcome = {"op": "error", "message": f"node exited ({p.returncode}) without a result"}
    return outcome


def _read_script(sw: Swarm, p: subprocess.Popen, name: str, answer, noted: set[str]):
    outcome = None
    for line in p.stdout:
        if not line.startswith(MARK):
            sw.say(f"script: {line.rstrip()}")
            continue
        m = json.loads(line[len(MARK):])
        op = m.get("op")
        if op == "log":
            sw.say(m["message"])
        elif op == "phase":
            sw.say(f"== {m['title']}")
        elif op == "agent":
            opts = m.get("opts") or {}
            for k in ("isolation", "effort", "agentType"):
                if k in opts and k not in noted:
                    noted.add(k)
                    sw.say(f"note: agent option {k} is ignored under swarm.py")
            label = str(opts.get("label") or f"job-{m['id']}")
            if left := unfilled(m["prompt"]):
                sw.say(f"{label}: not run: the prompt still holds {', '.join(left)}")
                answer(m["id"], None)
                continue
            job = Job(prompt=m["prompt"], label=label, task=task_id(opts, m["prompt"], label),
                      model=model_for(sw.cfg, opts), schema=opts.get("schema"), phase=opts.get("phase"),
                      title=label, group=opts.get("phase") or name, role=opts.get("role"),
                      inputs=[str(x) for x in opts.get("inputs") or []])
            fut = sw.submit(job)
            fut.add_done_callback(lambda f, mid=m["id"]: answer(mid, None if f.cancelled() or f.exception() else f.result()))
        elif op in ("return", "error"):
            outcome = m
    return outcome


PLACEHOLDER = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")


def unfilled(prompt: str) -> list[str]:
    """Placeholders (`{{NAME}}`) a rendered prompt still holds: render-prompt leaves unknown ones in place."""
    return sorted(set(PLACEHOLDER.findall(prompt)))


def load_jobs(cfg: config.Config, path: Path) -> list[Job]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise SystemExit(f"swarm: {path}: a job list is a JSON array")
    base = path.parent
    rel = lambda v: str(v if Path(v).is_absolute() else (base / v).resolve())  # noqa: E731
    jobs, seen = [], set()
    for i, j in enumerate(data):
        if not isinstance(j, dict) or "task" not in j or not ({"prompt", "prompt_file"} & set(j)):
            raise SystemExit(f"swarm: {path}: job {i} needs task and prompt or prompt_file")
        track.check_task(j["task"])
        if j["task"] in seen:
            raise SystemExit(f"swarm: {path}: task {j['task']} appears twice")
        seen.add(j["task"])
        prompt = j.get("prompt") or Path(rel(j["prompt_file"])).read_text()
        if left := unfilled(prompt):
            src = rel(j["prompt_file"]) if j.get("prompt_file") and not j.get("prompt") else f"{path} (job {j['task']})"
            print(f"swarm: {src}: the prompt still holds {', '.join(left)}; render it with the values filled in",
                  file=sys.stderr)
            raise SystemExit(2)
        schema = j.get("schema") or (json.loads(Path(rel(j["schema_file"])).read_text()) if j.get("schema_file") else None)
        tools = j.get("tools")
        allow = j.get("allow")
        jobs.append(Job(prompt=prompt, label=j.get("title") or j["task"], task=j["task"], model=model_for(cfg, j),
                        schema=schema, title=j.get("title"), group=j.get("group") or path.stem,
                        cwd=rel(j["cwd"]) if j.get("cwd") else None, add_dirs=[rel(d) for d in j.get("add_dirs", [])],
                        max_turns=j.get("max_turns"), tools=",".join(tools) if isinstance(tools, list) else tools,
                        allow=",".join(allow) if isinstance(allow, list) else allow, role=j.get("role"),
                        inputs=[rel(x) for x in j.get("inputs", [])]))
    return jobs


# ---------------------------------------------------------------- follow-up

def session_of(jd: Path) -> str | None:
    """The job's last session id: jobs/<key>/session, else the newest call output that names one."""
    f = jd / "session"
    if f.is_file() and f.read_text().strip():
        return f.read_text().strip()
    for out in sorted(jd.glob("*.out"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(out.read_text().split("\n--- stderr ---\n")[0])
            d = next((x for x in reversed(d) if isinstance(x, dict) and x.get("type") == "result"), {}) if isinstance(d, list) else d
            if d.get("session_id"):
                return d["session_id"]
        except (ValueError, AttributeError):
            continue
    return None


def find_job(cfg: config.Config, task: str, run_dir: str | None) -> Path | None:
    """The newest job directory of `task` under run_dir, else under every run dir of work.swarm."""
    roots = [Path(run_dir)] if run_dir else sorted(Path(cfg.get("work.swarm")).glob("*"))
    found = []
    for root in roots:
        for f in root.glob("jobs/*/job.json"):
            try:
                if json.loads(f.read_text()).get("task") == task:
                    found.append(f.parent)
            except ValueError:
                continue
    return max(found, key=lambda d: max(x.stat().st_mtime for x in d.iterdir())) if found else None


def last_report(jd: Path) -> str:
    """The job's last hand-back: the newest follow-up reply, else the job's own result."""
    files = sorted(jd.glob("followup-*.json"), key=lambda f: int(f.stem.split("-")[1]) if f.stem.split("-")[1].isdigit() else 0)
    for f in [*reversed(files), jd / "result.json"]:
        try:
            v = json.loads(f.read_text()).get("value")
        except (OSError, ValueError, AttributeError):
            continue
        if v:
            return v if isinstance(v, str) else json.dumps(v, indent=1, ensure_ascii=False)
    return "(no report was saved)"


def fresh_prompt(job, jd: Path, follow: str, ctx: int) -> str:
    """A fresh session's prompt: the job's brief, its last report, then the follow-up."""
    return (f"{job.prompt.rstrip()}\n\n## Your earlier session's report\n\nAn earlier session worked on this task and "
            f"handed back this report. Its context had reached {ctx} tokens, so you start fresh: read what the "
            f"report names in your trees and keep what is right.\n\n{last_report(jd).rstrip()}\n\n## Follow-up\n\n"
            f"{follow}")


def follow_up(cfg: config.Config, a) -> int:
    task, prompt_file = a.follow_up
    out = {"task": task, "ok": False, "value": None, "error": None, "session_id": None, "cost_usd": 0.0, "job_dir": None,
           "context": None, "fresh": False, "model": None}

    def done(code: int, error: str | None = None) -> int:
        out["error"] = error
        print(json.dumps(out, ensure_ascii=False))
        return code
    try:
        prompt = Path(prompt_file).read_text()
    except OSError as e:
        return done(2, f"cannot read {prompt_file}: {e}")
    jd = find_job(cfg, task, a.run_dir)
    if jd is None:
        return done(2, f"no job of task {task} under {a.run_dir or cfg.get('work.swarm')}")
    out["job_dir"] = str(jd)
    sid = session_of(jd)
    if not sid:
        return done(2, f"{jd}: no saved session to resume")
    rec = json.loads((jd / "job.json").read_text())
    job = Job(prompt=(jd / "prompt.md").read_text() if (jd / "prompt.md").is_file() else "", label=rec.get("label") or task,
              task=task, model=rec.get("model") or cfg.get("models.default"), schema=rec.get("schema"),
              phase=rec.get("phase"), title=rec.get("label"), group=jd.parent.parent.name, cwd=rec.get("cwd"),
              add_dirs=rec.get("add_dirs") or [], max_turns=rec.get("max_turns"), tools=rec.get("tools"),
              allow=rec.get("allow"), role=rec.get("role"), inputs=rec.get("inputs") or [])
    out["model"] = job.model
    n = len(list(jd.glob("followup-*.json"))) + 1
    tag = f"followup-{n}"
    ctx = sessions.last_context(sid, job.cwd or cfg.get("work.dir"))
    limit = int(cfg.get("pipeline.follow_up_max_context"))
    fresh = ctx is not None and ctx >= limit
    out.update(context=ctx, fresh=fresh)
    if fresh:
        prompt = fresh_prompt(job, jd, prompt, ctx)
    _write(jd / f"{tag}-prompt.md", prompt)
    sw = Swarm(cfg, jd.parent.parent, a)
    with track.recorded("swarm follow-up", task=task) as r:
        sw.board(job, "running", f"follow-up {n} ({job.model})" + (f", fresh session at {ctx} tokens" if fresh else ""))
        try:
            value, err = sw.call(job, jd, resume=None if fresh else sid, prompt=prompt, tag=tag)
        except Exception as e:  # report it as the call's failure, in the same JSON shape
            value, err = None, f"{type(e).__name__}: {e}"
        sw.pool.shutdown(wait=False)
        out.update(ok=err is None, value=value, session_id=session_of(jd), cost_usd=round(sw.stats["cost"], 3))
        _write(jd / f"{tag}.json", json.dumps({k: out[k] for k in ("ok", "value", "session_id")} | {"error": err},
                                                   indent=1, ensure_ascii=False))
        sw.board(job, "done" if err is None else "failed", None if err is None else err[:300])
        r.result(f"{task} follow-up {n}: {'ok' if err is None else 'FAILED: ' + err[:200]}", log=str(jd), ok=err is None)
    return done(0 if err is None else 1, err)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", help="workflows/<name>.js or a job list (.json)")
    ap.add_argument("--follow-up", nargs=2, metavar=("TASK", "PROMPT_FILE"))
    ap.add_argument("--args", help="the workflow's args JSON file (render-prompt --workflow-args)")
    ap.add_argument("--parallel", type=int)
    ap.add_argument("--max-turns", type=int)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--memory-gb", type=int, default=4)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-dir")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    try:
        cfg = config.load(a.config)
    except (config.ConfigError, ValueError) as e:
        print(f"swarm: config: {e}", file=sys.stderr)
        return 2
    if a.config:
        os.environ[config.ENV_CONFIG] = str(Path(a.config).resolve())   # the dashboard store follows it
    par_src = (f"--parallel; pipeline.parallel is {cfg.get('pipeline.parallel')}" if a.parallel else "pipeline.parallel")
    a.parallel = a.parallel or int(cfg.get("pipeline.parallel"))
    a.max_turns_given = bool(a.max_turns)
    a.max_turns = a.max_turns or int(cfg.get("pipeline.job_max_turns"))
    if a.follow_up:
        return follow_up(cfg, a)
    if not a.source:
        print("swarm: name a workflow script or a job list, or use --follow-up TASK PROMPT-FILE", file=sys.stderr)
        return 2
    src = Path(a.source)
    if not src.is_file():
        print(f"swarm: no such file: {src}", file=sys.stderr)
        return 2
    is_workflow = src.suffix in (".js", ".mjs")
    stage = None
    if is_workflow:
        if not a.args:
            print("swarm: a workflow script needs --args (tools/render-prompt --workflow-args <workflow>)", file=sys.stderr)
            return 2
        try:
            stage = json.loads(Path(a.args).read_text()).get("stage")
        except (OSError, json.JSONDecodeError, AttributeError) as e:
            print(f"swarm: --args {a.args}: {e}", file=sys.stderr)
            return 2
    name = src.name.removesuffix(src.suffix)
    run_dir = Path(a.run_dir) if a.run_dir else Path(cfg.get("work.swarm")) / name
    run_dir.mkdir(parents=True, exist_ok=True)
    sw = Swarm(cfg, run_dir, a)
    label = name + (f" ({stage})" if stage else "")

    def on_term(signum, frame):
        sw.say(f"signal {signum}: stopping the batch")
        sw.stop()
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, on_term)

    code = 0
    with track.recorded("swarm") as rec:
        # The effective parallelism and models, stated once at the start: port.toml decides them, nothing else.
        sw.say(f"swarm {label}: {a.parallel} at a time ({par_src}), run dir {run_dir}{' (dry run)' if a.dry_run else ''}"
               + (f"; models per agent() call from [models], default {cfg.get('models.default')}" if is_workflow else ""))
        try:
            if is_workflow:
                outcome = run_workflow(sw, src.resolve(), Path(a.args).resolve(), name)
            else:
                jobs = load_jobs(cfg, src)
                models = Counter(j.model for j in jobs).most_common()
                sw.say(f"{len(jobs)} jobs; models: " + ", ".join(f"{n} {m}" for m, n in models))
                futs = {j.task: sw.submit(j) for j in jobs}
                outcome = {"op": "return", "value": {t: f.result() for t, f in futs.items()}}
        except KeyboardInterrupt:
            sw.stop()
            outcome = {"op": "error", "message": "interrupted"}
        sw.pool.shutdown(wait=True)
        st = sw.stats
        summary = (f"{label}: {st['jobs']} jobs, {st['ok']} ok ({st['cached']} cached), {st['failed']} failed, "
                   f"${st['cost']:.2f}")
        out = run_dir / ("results.json" if not is_workflow else f"result{'-' + stage if stage else ''}.json")
        if outcome["op"] == "return":
            _write(out, json.dumps(outcome["value"], indent=1, ensure_ascii=False) + "\n")
            sw.say(f"{summary}; result in {out}")
            print(json.dumps(outcome["value"], indent=1, ensure_ascii=False))
        else:
            code = 1
            sw.say(f"{summary}; the script stopped: {outcome.get('message')}")
            if outcome.get("stack"):
                print(outcome["stack"], file=sys.stderr)
        rec.result(summary + ("" if code == 0 else f"; stopped: {outcome.get('message')}"), log=str(run_dir / "log.txt"),
                   data={k: (round(v, 3) if isinstance(v, float) else v) for k, v in st.items()},
                   ok=code == 0 and st["failed"] == 0)
    return code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""phase_gate: `track phase N` runs the exit rows of the phase it leaves, refuses on a failure, and takes --force.

Runs in the current directory as its scratch dir: builds two git repos, a port.toml and a dashboard store, then
walks phases 0 to 8. For each phase it checks one refusal (a named exit item fails) and one pass. Exit 0 when every
case passes; otherwise 1 with a reason line.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[3]
TRACK = KIT / "tools" / "track"
W = Path.cwd().resolve()
CFG = W / "port.toml"


def fail(msg):
    print(f"phase_gate: FAIL: {msg}")
    sys.exit(1)


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def track(*args):
    env = dict(os.environ, PORT_KIT_CONFIG=str(CFG))
    return subprocess.run([str(TRACK), *args], capture_output=True, text=True, env=env)


def touch_state():
    (W / "STATE.md").write_text("# state\n")


def expect(n, ok, needle=None, extra=()):
    touch_state()
    r = track("phase", str(n), *extra)
    out = r.stdout + r.stderr
    if ok and r.returncode != 0:
        fail(f"phase {n} refused, expected a pass:\n{out}")
    if not ok and r.returncode != 1:
        fail(f"phase {n} exit {r.returncode}, expected a refusal (1):\n{out}")
    if needle and needle not in out:
        fail(f"phase {n}: expected {needle!r} in:\n{out}")
    return out


def repo(name):
    d = W / name
    d.mkdir()
    sh("git", "init", "-q", "-b", "main", cwd=d)
    sh("git", "-c", "user.name=selftest", "-c", "user.email=selftest", "commit", "-q", "--allow-empty", "-m", "base",
       cwd=d)
    return d


def commit(d, msg):
    sh("git", "add", "-A", cwd=d)
    sh("git", "-c", "user.name=selftest", "-c", "user.email=selftest", "commit", "-q", "-m", msg, cwd=d)


fw, app = repo("fw"), repo("app")
sh("git", "branch", "port/stubs", cwd=fw)
CFG.write_text(f"""[work]
dir = "{W}"
[framework]
checkout = "{fw}"
[app]
name = "Scratch"
checkout = "{app}"
ui_dirs = ["src"]
[plan]
base = "aaaa"
app_base = "bbbb"
[track]
how_served = "terminal only"
[[areas]]
id = "core"
code = "co"
""")

# ---- the first record: only 0
expect(3, False, "allowed are 0")
expect(0, True)

# ---- phase 0
for d in ("trees/snap-fw", "trees/snap-app", "trees/prod"):
    (W / d).mkdir(parents=True)
track("status", "setup-pin", "done")
out = expect(1, False, "baseline-failures.txt is missing")
(W / "baseline-failures.txt").write_text("")
track("round", "0", "--pass", "5", "--fail", "0")
track("status", "setup-build", "blocked", "--on", "lead")
expect(1, False, "blocked or failed: setup-build")
track("status", "setup-build", "done")
out = expect(1, True, "read now, in full:")
if "02-inventory-and-map.md" not in out or "- [ ]" not in out:
    fail(f"phase 1 pass did not print its runbook and exit list:\n{out}")

# ---- phase 1
expect(3, False, "allowed are 1, 2")
(W / "inventory").mkdir(exist_ok=True)
(W / "inventory/areas.json").write_text(json.dumps({"areas": [{"id": "core"}, {"id": "extra"}]}))
expect(2, False, "areas.json only: extra")
(W / "inventory/areas.json").write_text(json.dumps({"areas": [{"id": "core"}]}))
(W / "port-map").mkdir(exist_ok=True)
(W / "port-map/core.md").write_text("# core\n")
expect(2, False, "README.md")
(W / "port-map/README.md").write_text("# index\n")
os.utime(W / "STATE.md", (0, 0))
r = track("phase", "2")
if r.returncode != 1 or "was not written since the phase began" not in r.stderr:
    fail(f"an old STATE.md passed:\n{r.stdout}{r.stderr}")
expect(2, True)

# ---- phase 2: coverage.py has no plan to read, so the gate refuses; --force records a decision
(W / "plan/sheets").mkdir(parents=True, exist_ok=True)
(W / "plan/sheets/core-w1.md").write_text("# core-w1: scratch set\n")
expect(3, False, "not on the board (track import sheets): core-w1")
track("ask", "core-w1", "Which?", "--recommend", "A", "--for", "developer")
out = expect(3, False, "coverage.py exit")
for needle in ("sizing.md", "open developer questions: q1"):
    if needle not in out:
        fail(f"phase 3 refusal lacks {needle!r}:\n{out}")
expect(3, True, extra=("--force", "scratch plan"))
st = json.loads((W / "track/state.json").read_text())
if not any(e["kind"] == "decision" and "forced past" in e["text"] for e in st["log"]):
    fail("--force recorded no decision event")

# ---- phase 3
(W / "plan/LINEBASE").write_text("0000000\n")
(W / "plan/plan-errors.md").write_text("| Stage | Id | Owner set | Error | Fix |\n|---|---|---|---|---|\n"
                                        "| 1 | co.C1 | core-w1 | wrong type | |\n")
out = expect(4, False, "rows without a fix: co.C1")
if "the stub head is" not in out:
    fail(f"a wrong LINEBASE passed:\n{out}")
head = subprocess.run(["git", "-C", str(fw), "rev-parse", "port/stubs"], capture_output=True, text=True).stdout
(W / "plan/LINEBASE").write_text(head)
(W / "plan/plan-errors.md").write_text("| Stage | Id | Owner set | Error | Fix |\n|---|---|---|---|---|\n"
                                        "| 1 | co.C1 | core-w1 | wrong type | sheet fixed |\n")
track("answer", "q1", "A")
expect(4, True)

# ---- phase 4: port-set audit fails on the scratch plan
out = expect(5, False, "missing:")
if "port-set audit exit" not in out:
    fail(f"phase 5 refusal does not name the audit:\n{out}")
(W / "sets/core-w1").mkdir(parents=True)
(W / "sets/core-w1/plancheck.md").write_text("@@@ CLEAR\n")
expect(5, True, extra=("--force", "scratch audit", "--batch", "b1", "--area", "core"))

# ---- phase 5
expect(6, False, "no set was written since the phase began")
track("event", "port-set-run", "wrote", "--task", "core-w1")
(W / "sets/core-w1/check.md").write_text("# check\n\n## Errors\n\nmissing import\n\n## Warnings\n\nnone\n")
expect(6, False, "check.md missing or with errors: core-w1")
(W / "sets/core-w1/check.md").write_text("# check\n\n## Errors\n\nnone\n\n## Warnings\n\nnone\n")
out = expect(6, True)
if "batch b1" not in out:
    fail(f"the batch was not kept across phases:\n{out}")

# ---- phase 6
track("run", "combine-lost", "--", "true")
track("run", "racheck-gate", "--", "true")
track("run", "compile-gate", "--", "false")
track("ask", "core-w1", "Name?", "--recommend", "Foo")
out = expect(7, False, "the last compile-gate failed")
if "unanswered" not in out:
    fail(f"an open proceeding question passed the phase 6 exit:\n{out}")
track("run", "compile-gate", "--", "true")
track("answer", "q2", "Foo")
expect(7, True)

# ---- phase 7
expect(8, False, "no test round since the phase began")
(app / "lib.rs").write_text('println!("DIAG x");\n')
commit(app, "diag")
track("round", "1", "--pass", "5", "--fail", "0")
expect(8, False, "DIAG lines: app.integration")
(app / "lib.rs").write_text("\n")
expect(8, False, "uncommitted changes in app.integration")
commit(app, "no diag")
track("status", "t-1", "done", "--group", "tracks")
expect(5, False, "triage.tsv")
(W / "runs").mkdir(exist_ok=True)
(W / "runs/triage.tsv").write_text("")
expect(5, True, "06-write.md", extra=("--batch", "app-1"))

# ---- re-record keeps batch and runs no gate; a step back is refused
out = expect(5, True, "batch app-1", extra=("second note",))
expect(4, False, "allowed are 5, 6")

print("phase_gate: ok")

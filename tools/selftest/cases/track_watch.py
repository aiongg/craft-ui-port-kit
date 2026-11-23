#!/usr/bin/env python3
"""track_watch: questions that proceed on their recommendation, the alerts digest, `track answer --file`, and
`track watch` waking on a new alert and timing out.

Runs in the current directory as its scratch dir with its own port.toml and store. Exit 0 when every case passes;
otherwise 1 with a reason line.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

KIT = Path(__file__).resolve().parents[3]
TRACK = KIT / "tools" / "track"
W = Path.cwd().resolve()
CFG = W / "port.toml"
ENV = dict(os.environ, PORT_KIT_CONFIG=str(CFG))


def fail(msg):
    print(f"track_watch: FAIL: {msg}")
    sys.exit(1)


def track(*args, ok=True):
    r = subprocess.run([str(TRACK), *args], capture_output=True, text=True, env=ENV)
    if ok and r.returncode != 0:
        fail(f"track {' '.join(args)}: exit {r.returncode}: {r.stderr.strip()}")
    return r


def state(task):
    return json.loads(track("show", task, "--json").stdout)["state"]


CFG.write_text(f'[work]\ndir = "{W}"\n[framework]\ncheckout = "{W}"\n[app]\nname = "Scratch"\ncheckout = "{W}"\n'
               'ui_dirs = ["src"]\n[track]\nhow_served = "terminal only"\n')
track("status", "s-1", "running", "writing")
track("status", "s-2", "running", "writing")

# ---- every question carries a recommendation
r = track("ask", "s-1", "Which name?", ok=False)
if r.returncode != 2 or "--recommend" not in r.stderr:
    fail(f"an ask without --recommend was accepted: {r.returncode} {r.stderr}")

# ---- a first watch with nothing to report times out and says what it waited for
r = track("watch", "--timeout", "0.03", "--poll", "0.5")
if "nothing new" not in r.stdout or "blocking questions" not in r.stdout:
    fail(f"a quiet watch did not time out with its message:\n{r.stdout}")

# ---- a watch in the background: a proceeding question does not wake it, a blocking one does
w = subprocess.Popen([str(TRACK), "watch", "--timeout", "1", "--poll", "0.3"], stdout=subprocess.PIPE,
                     stderr=subprocess.PIPE, text=True, env=ENV)
time.sleep(1)
track("ask", "s-1", "Name the helper?", "--recommend", "fmt_size", "--option", "fmt_size", "--option", "size_text")
time.sleep(1.5)
if w.poll() is not None:
    fail(f"a proceeding question woke the watch:\n{w.stdout.read()}")
if state("s-1") != "running":
    fail(f"a proceeding question set its task {state('s-1')}")
track("ask", "s-2", "Change the saved file format?", "--recommend", "no", "--blocking")
try:
    out, err = w.communicate(timeout=20)
except subprocess.TimeoutExpired:
    w.kill()
    fail("the watch did not exit on a blocking question")
if w.returncode != 0 or "* question q2" not in out or "recommended: no" not in out:
    fail(f"the watch digest lacks the new blocking question (exit {w.returncode}):\n{out}{err}")
if "proceeding on their recommendation: 1 unruled (q1)" not in out:
    fail(f"the digest lacks the proceeding questions line:\n{out}")
if state("s-2") != "waiting":
    fail(f"a blocking question left its task {state('s-2')}")

# ---- the same alerts do not wake the next watch
r = track("watch", "--timeout", "0.03", "--poll", "0.5")
if "nothing new" not in r.stdout:
    fail(f"a watch woke on alerts it had already reported:\n{r.stdout}")

# ---- an ask recorded before questions carried the field still blocks its task
events = W / "track" / "events.jsonl"
with open(events, "a") as f:
    f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "id": "old1", "kind": "ask",
                        "task": "s-3", "text": "old question"}) + "\n")
track("publish")
if state("s-3") != "waiting":
    fail("an old ask event did not set its task waiting")

# ---- answers from a rulings file: one bad row records nothing
(W / "rulings.tsv").write_text("qid\truling\ttask\nq1\tfmt_size\ts-1\nq9\tx\ts-9\n")
r = track("answer", "--file", str(W / "rulings.tsv"), "--by", "rulings", ok=False)
if r.returncode != 2 or "no question q9" not in r.stderr:
    fail(f"a rulings file with an unknown question was accepted: {r.stderr}")
if "proceeding on their recommendation: 1" not in track("alerts").stdout:
    fail("a refused rulings file recorded an answer")
(W / "rulings.tsv").write_text("qid\truling\ttask\nq1\tfmt_size\ts-1\nq2\tno\ts-2\n")
track("answer", "--file", str(W / "rulings.tsv"), "--by", "rulings")
al = track("alerts").stdout
if "proceeding" in al or "answered q2 (s-2 still waiting) by rulings" not in al:
    fail(f"the rulings file did not answer both questions:\n{al}")

print("track_watch: ok")

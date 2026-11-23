# track: the progress dashboard

`tools/track` records the port's progress in one store in the workspace, and `dashboard/` shows it as one local page: the phase, every task with its state, what is blocked and on what, open questions, test counts per round, stale agents, and a log of events.

Agents and the lead record judgement (state, blockers, questions) with `track` commands. Kit tools record what they know (a gate's result, a round's counts) themselves, through `portkit.track`. Nobody keeps the page current by hand.

It needs Python 3.11 or later and nothing else: no external fonts or scripts, no account, no hosted service. It works offline.

## Contents

- [Viewing the page](#viewing-the-page)
- [Commands](#commands)
- [The phase gate](#the-phase-gate)
- [States, steps and questions](#states-steps-and-questions)
- [Keeping the dashboard current](#keeping-the-dashboard-current)
- [Python API for kit tools](#python-api-for-kit-tools)
- [Import formats](#import-formats)
- [Store format](#store-format)
- [Config keys](#config-keys)

## Viewing the page

Every write folds the events into `state.json` and publishes the page into `track.out_dir` (default `<workspace>/track/site`): `index.html`, `app.js`, `app.css`, `state.json` and `state.js`. The page re-reads its data every 4 seconds. It follows the system's light or dark setting and works at phone width.

The kit never picks a host and never exposes anything itself. In phase 0 (process/01-setup.md) the lead asks the developer which of these they want, and records the answer in port.toml as `track.how_served`:

| Option | How | Answers from the page |
|---|---|---|
| Your own static server or tunnel | Point it at `track.out_dir`. Any server that serves files works; the page only reads `state.json`. | No: answer in chat with the lead or with `track answer` |
| Open the file | Open `<out_dir>/index.html` in a browser. The page loads `state.js`, because a `file://` page cannot fetch `state.json`. | No |
| `track serve` | Serves `out_dir` on `track.serve_host:track.serve_port` (default `127.0.0.1:8765`). | Yes: option buttons and a text field on each open question |
| Terminal only | `track show`, `track eta`, `track alerts` | - |

`track serve` is a plain fallback (Python's `http.server`). It binds to localhost by default; to reach it from another device, put your own tunnel in front of it. It accepts answers only as `POST /api/answer` with a JSON body and refuses requests whose `Origin` names another site.

## Commands

Run `tools/track --help` for the summary. `--config PATH` before the command picks a port.toml; otherwise the usual resolution applies (`PORT_KIT_CONFIG`, `./port.toml`, a parent directory). Every command that writes also publishes.

### For agents

| Command | Records |
|---|---|
| `track status TASK STATE [NOTE] [--on WHAT] [--link NAME=PATH\|URL] [--model M] [--calls N]` | A state change. Creates the task if it is new. `--title` and `--group` set the task's title and group. |
| `track step TASK STEP [NOTE]` | The start of a step: `plan`, `write`, `compile`, `test`, `fix`, `merge` (any lowercase word works). Sets the task `running`, unless it is `waiting` or `blocked`. While the port is paused it records nothing and exits 3. |
| `track ask TASK "QUESTION" --recommend R [--option A]... [--blocking] [--for developer\|lead]` | A question (default `--for lead`) with the option the asker recommends (required). Prints its id (`q1`, `q2`, ...). Without `--blocking` the asker proceeds on R and the task keeps its state; with it (the always-DECIDE list in `rules/agent-common.md`, "Questions") the task is set `waiting` on whom it asks. |
| `track answer QID "ANSWER" [--by NAME]` | The answer (default `--by lead`). The task stays `waiting` until its agent or the lead moves it. |
| `track answer --file TSV [--by NAME]` | Every answer of a file of `qid<TAB>answer[<TAB>...]` lines, such as the rulings file of `prompts/p-rulings.md`. A header line starting `qid` and `#` lines are skipped. A row with an unknown question or no answer records nothing. |
| `track round N --pass P --fail F [--log PATH] [--data KEY=VALUE]...` | A full test run's result. The page draws failing tests per round. |
| `track event KIND TEXT [--task ID] [--link NAME=URL]... [--data KEY=VALUE]...` | A free event: `merge`, `landing`, `decision`, or any lowercase kind that is not a command name. |
| `track phase N [NOTE] [--batch B] [--area A] [--force REASON]` | The port's current phase, in the process/ numbering (0 Setup to 9 Land), after the exit checks of the phase it leaves ([The phase gate](#the-phase-gate)). `--batch` and `--area` name the build batch and area; phases 5 to 7 keep them until given anew. |

### For the lead and the developer

| Command | Does |
|---|---|
| `track show [TASK] [--json]` | Text view: phase, counts, tasks by state with age, open questions. With TASK: its history, links, questions and last tool event. |
| `track eta [--json]` | The cycle projection: cycles run, median cycle period, cycles per finished batch, cycles left, sets left over the measured rate, the finish, the spend so far with the projected total at the finish, and the weekly quota at the finish (`process/costs.md`, "The cycle model"). Nothing stops or asks because of spend. `--json` prints `eta.cycles`. |
| `track usage [--json]` | Records the calling lead session's cost so far (the last `cost-state` record of its Claude Code session file, found from `CLAUDE_CODE_SESSION_ID`; nothing from an agent's shell) as a `lead-cost` event, then prints the spend: the agents' calls from `work.usage_log` plus every recorded lead session (the newest cost of each, so sessions before a clear or a handoff stay counted), per hour since the first event, and at the projected finish. `tools/cycle` records the same sample each cycle. `track eta` prints the spend line too. |
| `track alerts [--stale-min N]` | One line per item that needs action (below). Always exits 0, so a poll loop never stops on it. |
| `track watch [--timeout MIN] [--poll SEC]` | Waits for the next new alert line or the timeout (below). Always exits 0. |
| `track md [--out PATH]` | Writes STATUS.md (phase, tasks by state, questions, rounds) in the workspace. Default path: `<work.dir>/STATUS.md`; a path outside `work.dir` is refused; `--out -` prints it. |
| `track publish` | Folds every event again and rewrites `out_dir`. Writes do this already; run it after changing the dashboard files or to rebuild a deleted `state.json`. |
| `track serve [--port P] [--host H]` | See [Viewing the page](#viewing-the-page). |
| `track pause [NOTE]` / `track resume [NOTE]` | The pause switch: while paused, `track step` refuses to start a step. |
| `track import sheets [DIR]` | One task per writer sheet (default `work.sheets`). |
| `track import tracks FILE [--group G]` | One task per red-round track. |

`track alerts` prints these lines, in this order:

```
paused: <note>
stale <task>: running (write), no update for 34 min (limit 20): <note>
blocked <task> on <what>: <note>
failed <task>: <note>
question q3 for developer (<task>, 12 min): <text> [A | B; recommended: A]
answered q3 (<task> still waiting) by developer: <answer>
questions proceeding on their recommendation: 12 unruled (q4 q5 ...); rule them per batch (prompts/p-rulings.md)
```

A `question` line is a blocking question. Questions asked without `--blocking` come as the one digest line at the end: their askers went on with the recommended option, and the lead rules on them per batch.

`track watch [--timeout MIN] [--poll SEC] [--stale-min N]` is the lead's monitor, run as a background task. It prints what it waits for and until when, then polls the store every SEC seconds (default 20). It exits 0 as soon as an alert line appears that it has not reported before: a blocking question, an answer to a waiting task, a stale, blocked or failed task, or a pause. It then prints every current alert line, the new ones marked `*`. With nothing new by the timeout (default 30 minutes) it prints "nothing new" and exits 0. The digest line of proceeding questions never wakes it. It keeps the keys of the lines it reported in `<track.dir>/watch-seen.json`, so the next watch wakes only on what is new; a first watch reports every current line at once. Start it again after each exit.

### For shell tools

`track run KIND [--task ID] [--log PATH] -- CMD...` runs CMD with its output passed through, then posts one event: `<kind> ok|failed (<duration>): <last output line>`, with the exit status, the duration and the command in its data, and `--log` as a link. It exits with CMD's status. Without a configured store it runs CMD and records nothing.

### Exit codes

`0` done; `1` `track phase` refused (the failing exit items are listed); `2` usage or config error (the message names it); `3` `track step` while paused. `track run` exits with the command's status (127 when it cannot start). `track alerts` and `track watch` always exit 0.

## The phase gate

`track phase N` checks the move before it records it:

- **The order.** Allowed without `--force`: the next phase, the current phase again (a new note, batch or area; no checks run), and 7 to 5 for the next build batch. With no phase recorded yet, only 0.
- **The exit items.** It runs every row of `PHASE_EXITS` in `tools/portkit/gates.py` for the phase it leaves: the items of that runbook's Exit list a script can decide without a build (files that must exist, board state, the last gate events since the phase began, `coverage.py`, `port-set audit`, `git grep 'DIAG '`), plus four rows for every phase: `STATE.md` written since the phase began, no blocked or failed task, no stale task, no open blocking question.
- **On a pass** it records the phase and prints the new runbook's path and its exit list. Read that runbook in full.
- **On a failure** it records nothing, prints each failing item with its reason, and exits 1.
- **`--force "reason"`** records the phase anyway, with a `decision` event naming every failing item and the reason. The event's `forced` field holds the same as data: `{"from": <phase left>, "to": N, "items": [<item texts>], "reason": ...}`.
- **`--force` on the current phase** runs the exit items of the phase before it again and records a new decision when any fails. Use it when an item breaks after the move: the landing tools read the latest `track phase 9` record ([tools/look.md](look.md), "The phase gate").
- **The look items** ([tools/look.md](look.md), "The phase gate"): at exit 0 the look driver and the production build exist; at exit 1 every map section has a states file and production reaches every state; at exit 8 every state has a pair from the current port head, every difference is fixed or kept with a reason, and the lead accepted every panel. The landing tools run the phase 8 look items too and accept only the phase 9 decision as an override.
- **The test ledger:** at exit 8 every test gone since the baseline has a `delete` verdict or a passing `move` target (`tools/test-ledger.py --check`); at exit 7 every `keep` test a fixer marked stale has a triage row. The landing tools run the ledger check too (`tools/land/exit-gate.py`), with the same override.

The other exit items stay the lead's to check. A new machine-checkable item is one function and one `ExitCheck` entry in `PHASE_EXITS`.

## States, steps and questions

| State | Meaning |
|---|---|
| `todo` | Created, not started |
| `running` | An agent works on it |
| `review` | Handed back; waits for the lead's review or merge |
| `waiting` | Waits on an answer or another task (`--on`) |
| `blocked` | Cannot continue until something outside it changes (`--on`) |
| `failed` | A tool or agent run failed and needs the lead (set by tools such as swarm.py) |
| `done` | Finished |

Rules the fold applies:

- A note belongs to the state it was written for. A state or step change without a note clears the old note.
- `--on` is kept only while the task is `waiting` or `blocked`.
- `todo` and `done` clear the step. Other states keep the current step.
- `track ask --blocking` sets the task `waiting` on `developer` or `lead`, unless it is `done`. A question without `--blocking` leaves the task's state alone. An `ask` event recorded without the `blocking` field counts as blocking.
- `--calls N` adds one agent run to the task; the page shows the sum over all runs.
- A task is stale when it is `running` or in `review` and no event has named it for `track.stale_min` minutes. Tool events count: a writer whose port-set calls keep posting is not stale.

## Keeping the dashboard current

These are rules, not suggestions. The dashboard is only as good as its last event.

### Agents

`rules/agent-common.md`, "Tracking", holds the agents' rules, and every prompt in `prompts/` repeats them with its own steps: `track step` at each step start (exit 3 means paused: stop and report), `track status` on every state change with `--on` for a blocker, `track ask` for every question, and `track status TASK review "summary" --calls N` on hand-back.

### The lead

`rules/lead-rules.md`, "The dashboard", holds the lead's duties: put each task on the board before its agent starts, `track phase` at each phase change, every developer question on the board and in chat, `track watch` as a background monitor, rulings per batch, `track event` for merges, landings and decisions, and `track pause` around shared-branch moves.

### Tools

Everything a script knows, the script records. Agents report only judgement.

- Every long-running kit command posts one event when it ends, success or failure, with its duration, log path and key numbers. Python tools wrap their body in `track.recorded()`; shell tools run their main command through `track run`.
- `test-run` posts `track.round()` itself for every full run (pass, fail, log); `compare-runs.py` posts the round only with `--round N`, else a `compare` event with the new failures by track.
- `diag-cut.py` links each track's packet to its task.
- `cycle` posts one `cycle` event per cycle (its seconds, batch, failing count and weekly use, which `track eta` reads), a `merge` event on each fixer's task, moves a fixer with nothing left to `done`, records the batch and area with `track phase`, and records phase 7 after the cycle that compiles a phase 6 batch (the phase gate decides).
- `port-set` sets each set's task from its own exit states (OPEN, BLOCKED, OUT OF TURNS) and records each model call's tokens on the set's task.
- `swarm.py` creates one task per job and moves it through `todo`, `running`, `done` or `failed`.
- `track publish` derives the rest: stale tasks, branch heads that moved (`track.heads`), and a projected finish.

## Python API for kit tools

```python
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # tools/
from portkit import track

track.event(kind, text, task=None, data=None, links=None)
with track.recorded(kind, task=None) as rec:
    ...
    rec.result(text, log=None, data=None, ok=None)
track.status(task, state, note=None, on=None)
track.round(n, passed, failed, log=None, data=None)
```

- None of these raise. A bad argument or a store error prints one warning to stderr per process, and the tool carries on.
- Without a configured store (no port.toml found and `PORT_KIT_TRACK_DIR` unset) they do nothing, so the tools run the same outside a port workspace.
- `recorded()` posts `<kind> ok|failed (<duration>): <text>` when the block ends. The outcome is failed when the block raises, exits non-zero, or calls `rec.result(..., ok=False)` (a gate that found errors without raising). On an exception the text ends with its first line. `data` gets `seconds`; `log` becomes a link.
- Link and log paths that exist from the current directory are stored as absolute paths, except a relative path that exists under `track.out_dir`: it stays relative, and the dashboard opens it as a link relative to the page.

## Import formats

**Sheets.** Every `*.md` file in the sheet directory is one task. The id is the file name without `.md` (`panels-w26`). The title is the first `# ` heading, without a leading `<id> —`. The group is the area (`[[areas]]` id, else the id without `-w<n>`). A `Model: <name>` in the lines before the first `## ` sets the model. The sheet path becomes the task's `sheet` link.

**Tracks.** A plain text file, one track per line: `TRACK_ID [TITLE...]`. Blank lines and lines starting with `#` are skipped. All tracks get the group `tracks`, or `--group G`.

```
# red round 3
t1 panels and docking
t2 dialogs: footer order
t3
```

Imports never change a task's state. Running one again adds only new tasks and changed titles, groups or links.

## Store format

The store is `track.dir` (default `<workspace>/track`):

| File | Content |
|---|---|
| `events.jsonl` | Every event, append-only, one JSON object per line |
| `state.json` | The fold of every event. Derived; never edit it. Delete it and any command rebuilds it. |
| `.lock` | Serialises the fold and the publish (`flock`). Appends never take it. |
| `.folded` | The byte offset of `events.jsonl` that `state.json` covers |

**Writing at once.** Each event is one `write()` to a file opened with `O_APPEND`, so lines from several writers never mix. After its append a writer takes the lock and folds, unless another writer's fold already covered its line. The last writer to fold sees every line, so `state.json` always ends consistent with the events. The fold skips a last line without a newline (still being written) and counts unreadable lines in `bad_lines`. The store needs a local file system: `O_APPEND` is not atomic over NFS.

**Events.** Every event has `t` (UTC, `YYYY-MM-DDTHH:MM:SSZ`), `id` (random hex) and `kind`. Order is file order. Text fields are capped at 2,000 characters.

| Kind | Fields |
|---|---|
| `status` | `task`, `state`, `note`, `on`, `links`, `model`, `calls` |
| `step` | `task`, `step`, `note` |
| `task` | `task`, `title`, `group`, `model`, `links` (from imports and `--title`) |
| `ask` | `task`, `text`, `options`, `for`, `recommend`, `blocking` |
| `answer` | `qid`, `text`, `by` |
| `round` | `n`, `pass`, `fail`, `log`, `data` |
| `phase` | `n`, `note`, `batch`, `area` |
| `pause`, `resume` | `note` |
| `head` | `label`, `sha`, `prev`, `ref`, `path` (posted by the fold when a watched head moved) |
| any other | `text`, `task`, `ok` (tool results), `data`, `links` |

**State.** `state.json` (and `state.js`, the same object assigned to `window.TRACK_STATE`) holds:

| Field | Content |
|---|---|
| `version`, `generated`, `events`, `bytes`, `bad_lines` | Format version, fold time, event count, bytes folded, unreadable lines |
| `app`, `how_served`, `stale_min` | From port.toml |
| `phase` | `{n, name, note, t, batch, area}` or null |
| `paused` | `{on, note, t}` |
| `counts` | Tasks per state |
| `tasks` | By id, in creation order: `title`, `group`, `state`, `step`, `note`, `on`, `links`, `model`, `calls`, `runs`, `created`, `updated` (last event naming it), `changed` (last state or step change), `started`, `ended`, `last` (last tool event), `history` (last 40 state changes) |
| `questions` | `{id, task, text, options, for, t, recommend, blocking, answer: {text, by, t} or null}` |
| `rounds` | `{n, pass, fail, log, data, t}` in order |
| `cycles` | The newest 200 `cycle` events of `tools/cycle`: `{t, ok, label, exit, phase, batch, area, mode, total_s, gap_s, errors, failing, weekly_pct}` in order |
| `heads` | By label: `{sha, prev, ref, path, since}` |
| `stale` | Stale tasks at fold time (the page and `track alerts` recompute this against the clock) |
| `eta` | Projection: `done`, `left`, `rate_recent` (tasks done per hour over the last 24 h, or since the first start when that is shorter), `rate_all`, `median_task_h` (first `running` to `done`), `finish_low` and `finish_high` (the faster and the slower rate), `groups` (left and total per group), `steps` (median minutes per step, measured from step and state changes), `basis`; `cycles`: the cycle model (`cycles`, `period_s` (median start-to-start seconds within a batch), `periods_measured`, `per_batch`, `batches_seen`, `build_batches` (`plan.build_batches`), `current_batch`, `left`, `cycle_h`, `sets_left`, `sets_per_h`, `write_h`, `total_h`, `finish`, `weekly`: `{now_pct, per_h, at_finish_pct, passes}` or null, `notes`) |
| `log` | The newest 400 events, newest first: `{t, kind, task, text, ok, links, data, by}` |

## Config keys

The `[track]` section of port.toml; process/config.md has the full table.

| Key | Default | Meaning |
|---|---|---|
| `dir` | `{work.dir}/track` | The store |
| `out_dir` | `{track.dir}/site` | Where the page and its data are published |
| `stale_min` | `20` | Minutes without an event before a running or review task is stale |
| `serve_host`, `serve_port` | `127.0.0.1`, `8765` | Where `track serve` listens |
| `how_served` | unset | How the developer opens the page, as recorded at setup |
| `heads` | the app port branch and the framework integration tree's HEAD | Heads watched for moves, `LABEL=REPO_PATH:REF` |

---
name: craft-ui-port
description: Run the port of a craft app's legacy egui UI onto the craft framework (craft-libs) with the craft-ui-port-kit, as the port's lead session. Use when the developer asks to port a craft app's UI to the framework, to start or resume a port, or names the port kit, a port workspace, port.toml, a phase of the port, or the port dashboard.
---

# Craft UI port: the lead

You are the **lead** of a port: the one session that runs the port of a craft app's UI onto the craft framework, with the process, rules, prompts and tools of this kit. You plan, launch agents in batches, review their output, decide what the rules let you decide, merge, and keep the state file and the dashboard current. You write no large code yourself. The developer picks the app, answers questions about goals, principles and architecture, looks at results, and runs anything that needs their accounts (pushes, CI).

The process: plan everything first with many small read-only agents, write all code with no builds, then build once per batch and fix in rounds. `process/00-overview.md` explains it.

## 1. Find the kit and the workspace

- **The kit root** is two directories above this file (`skills/craft-ui-port/` sits at the kit root). Check that `<kit>/process/00-overview.md` exists. If the skill was installed from the plugin and you need a clone to edit or update, it is `https://github.com/aiongg/craft-ui-port-kit`.
- **Kit paths in the docs** are relative to the kit root: `tools/port-set` means `<kit>/tools/port-set`. Call kit tools by their absolute path. `track` in the docs is `<kit>/tools/track`. The agents you launch call `track` by its bare name, with `<kit>/tools` on their `PATH` (`process/12-running-agents.md`, "Headless flags").
- **The workspace** holds the port's `port.toml`, `STATE.md`, the dashboard store and every artifact. Find it from `PORT_KIT_CONFIG`, a `port.toml` in the current directory or a parent, or `STATE.md` notes; ask the developer when none exists. Run every kit tool with `PORT_KIT_CONFIG=<workspace>/port.toml`, or from inside the workspace.
- **No workspace yet:** this is phase 0. Go to `process/01-setup.md`; its step 2 runs `tools/init-workspace <dir>`.

## 2. Read first, in this order

1. `README.md` and `process/00-overview.md`: the idea, the phase table, roles, where things live, the glossary.
2. Your standing prompt: `tools/render-prompt lead` (from `prompts/lead.md`). It covers the dashboard setup question and your board duties. It names workspace files, so render it after `tools/init-workspace` has created the workspace (`process/01-setup.md`, step 2); on a port that is already running, render it first.
3. `rules/lead-rules.md` and `rules/porting-rules.md`, in full. `rules/agent-common.md` binds you as well.
4. `STATE.md` in the workspace, then `track show`. They say which phase and step the port is in, what runs, and what waits on whom.
5. `process/lessons.md`, once per port: what went wrong on earlier ports and what changed because of it.

A session that starts without context does steps 2, 4 and 5 of this list before anything else, then reads the runbook of the current phase.

## 3. Run the current phase

Each phase has one runbook. Read it in full when the phase starts, and follow its steps and exit list. Record each phase change with `track phase N "<name>"`.

| # | Phase | Runbook | Main prompts | Main tools and runs |
|---|---|---|---|---|
| 0 | Setup | `process/01-setup.md` | `lead` | `init-workspace`, `feature-selection.py`, `test-run`, `racheck.py`, `scip/scipdb.py`, `track` |
| 1 | Inventory and map | `process/02-inventory-and-map.md` | `p1-*` | `workflows/phase1-inventory-map.js` through `swarm.py` |
| 2 | Plan | `process/03-plan.md` | `p2-*` | `workflows/phase2-*.js` through `swarm.py`; `coverage.py` |
| 3 | Contract stubs | `process/04-contract-stubs.md` | `p3-contract-stubs-stage` | `cl check`; `scip/scipdb.py` |
| 4 | Plan check and decisions | `process/05-plancheck-decide.md` | `p4-*` | `run-batch --plancheck`, `port-set collect`, `port-set remap`, `port-set audit` |
| 5 | Write | `process/06-write.md` | (port-set builds its own) | `run-area`, `run-batch`, `port-set`, `racheck.py` |
| 6 | Review, combine, compile | `process/07-review-combine-compile.md` | `p6-*` | `fix-batch`, `combine-area`, `racheck-gate`, `gate-classify.py`, `compile-gate`, `split-errors.py` |
| 7 | Tests and red rounds | `process/08-tests-and-red-rounds.md` | `p7-*` | `test-run`, `compare-runs.py`, `split-failures.py`, `diag-cut.py` |
| 8 | Look and behaviour | `process/09-look-and-behaviour.md` | `p8-task-brief` | `look` |
| 9 | Land | `process/10-land.md` | `p9-production-merge` | `land/scan-range.py`, `land/land-framework.sh`, `land/land-app.sh`, `land/pin-framework.py` |

Phases 5 to 7 repeat per build batch: the framework-side sets first, area by area, then the app sets.

Read these when the situation comes up, not up front:

| When | Read |
|---|---|
| Before any build, or when a build is slow or builds the framework twice | `process/11-build-loop.md` |
| Before launching agents; when one is stale, stuck or out of turns | `process/12-running-agents.md` |
| Before every batch, to state its cost; at the end of phase 2, for the projection | `process/costs.md` |
| When you set or look up a `port.toml` key | `process/config.md` |
| To find a tool, or what a tool reads and writes | `tools/README.md`, then the tool's `--help`; `tools/port-set.md`, `tools/track.md`, `tools/look.md` for the three large ones |
| When you start a workflow script | `workflows/README.md` |
| When you write a one-off brief | `prompts/p8-task-brief.md`, `prompts/precheck.md`, `templates/task-report.md` |
| When you need a worked example of an artifact | `examples/photocraft/README.md` |

Render every prompt with `tools/render-prompt <name> [NAME=VALUE]...`; it fills `{{...}}` from `port.toml` and names any placeholder it could not fill. Workflow args come from `tools/render-prompt --workflow-args <workflow>`.

## 4. The dashboard: rules, not suggestions

The dashboard is the developer's view of the port. Keep it current mechanically, through `track`, never from memory. `rules/lead-rules.md`, "The dashboard", is the full text; in short:

- **In phase 0, before any agent starts,** ask the developer how they want to view the page (their own server or tunnel pointed at `track.out_dir`, the file opened directly, `track serve`, or no page with `track show` in a terminal) and record the answer as `track.how_served` (`prompts/lead.md`). With no developer to ask (an unattended start), record the terminal option: `init-workspace --how-served "terminal only (track show, track alerts)"`.
- **Before launching an agent, put its task on the board** (`track import sheets`, `track import tracks FILE`, or `track status TASK todo`) and give the agent that task id.
- **At each phase change:** `track phase N "<name>"`.
- **Every question for the developer goes on the board and in chat:** `track ask TASK "..." --for developer --option A --option B`, and the same question in chat, in full, with your recommendation. Record every answer with `track answer QID "..."` and in `STATE.md` "Developer answers", in the same step, wherever it came from.
- **Run `track alerts` in your monitor loop** while agents run, and act on every stale, blocked and question line.
- **Record merges, landings and decisions** with `track event merge|landing|decision "..." --task ID`.
- **`track pause` before a shared-branch move** that agents must not start steps across, `track resume` after it.
- **Every brief you write includes the agent's `track` calls** (`rules/agent-common.md`, "Tracking") and its task id.

Kit tools post their own events (gate results, test rounds, set states, swarm jobs). Agents report only judgement.

## 5. Hard rules

- **Ask the developer only about goals, design principles and architecture.** Never layout or design detail: the old app decides what things look like. Decide everything else the rules settle, record it in `STATE.md` "Decisions", and keep agents running.
- **State the cost before every batch:** the agent count by model and the measured cost of similar runs (`process/costs.md`). No large Opus bursts; pace launches to the quota window.
- **Every brief forbids subagents and workflows**, names its files and mechanism, and fits about 150 tool calls.
- **Every cargo command goes through the framework's `cl`.** No workspace-wide builds or tests, no `--all-features`, no second feature set (`process/11-build-loop.md`).
- **Run everything that takes more than a few seconds as a background task** whose exit notifies you, and heavy jobs under `build.memory_cap`. Never wait in the foreground.
- **The UI gallery first.** Check the framework's UI gallery before planning or writing a component. Every component or variant the port adds is registered in the gallery with its stories in the same change, and its sheet names them in a `Stories` line (`rules/porting-rules.md`, "UI gallery").
- **Look at results yourself** (pairs, pages, test counts) before you tell the developer anything is done.
- **When the developer asks for the run's logs**, run `tools/collect-logs` in the workspace and on every other machine that ran agents or builds for the port, then sanitise each archive: search it for names, usernames, emails, hosts, home paths, private project names, customer data and secrets that the tool's redaction missed, remove them, and show the developer each archive's path, size, what you removed and the unchecked screenshots before they send it (README, "Sending your run's logs").
- **Kit tools never push.** Landing prepares scrubbed clones and prints the push commands; the developer pushes (`process/10-land.md`).
- **The kit is read only during a port.** Write only in the workspace and the trees `port.toml` names. A rule that should bind every port is a proposal to the kit's maintainers, not an edit.

## 6. Hand-off

Before you stop, or once your context is large: write the current state into `STATE.md` (phase, step, next action, running agents and their task ids, open questions, pointers rather than copies), run `track md`, and stop your monitors. The next session starts at section 2 of this file.

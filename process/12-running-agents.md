# Running agents

How the lead starts, paces, watches and resumes the agents of a port. It applies to every phase. The rules behind it are in `rules/lead-rules.md`; what each agent must do is in `rules/agent-common.md`.

## Three ways an agent runs

| Kind | Started by | Used for |
|---|---|---|
| Batch job | `tools/swarm.py` over a job list (`pipeline.batch_runner = "swarm"`), or a script in `workflows/` through the Workflow tool (`"workflow"`) | Phases 1 and 2 (inventory, questions, answers, chunk plans, evaluations), phase 3 stages, phase 4 decisions, phase 6 reviews and compile fixes, phase 7 triage and fixers |
| Writer call | `tools/port-set` (`run` for a one-shot write, `agent` for agent mode, `plancheck`, `fix`), alone or through `run-area`, `run-batch` and `fix-batch` | Phases 4 to 6, one set per call |
| Single agent | The lead, with a brief rendered from `prompts/` (for example `p8-task-brief.md`) | One-off tasks: a look fix, a late framework gap, an integrator, a precheck |

`swarm.py` runs `claude -p` over a job list, `pipeline.parallel` jobs at a time, with a model per job, checks each output against its schema, and resumes a stopped batch. It needs only the claude CLI. The workflow scripts read the same args (`render-prompt --workflow-args`).

## Headless flags

Every headless agent the kit starts runs `claude -p` with these settings. Use the same ones for a single agent started by hand.

| Setting | Why |
|---|---|
| Prompt on stdin, working directory = the agent's tree (the set's tree, the integration tree) | Relative paths in the prompt resolve there |
| `--model <model>` | From the `[models]` table, per step |
| `--tools <list>` | Only what the job needs. Lookup and plan-check jobs get `pipeline.lookup_tools` (read, search, `git grep`/`show`/`ls-files`, `track`); writers in agent mode also get edit tools. A `swarm.py` job's role (`role` in a job list, `opts.role` in a workflow) adds the commands that role runs, from one table, `ROLE_TOOLS` in `tools/swarm.py`: fixers `git add` and `git commit`, the red integrator the gates, phase 2 sheet fixes `coverage.py` and `port-set` |
| `--settings` with the rust-analyzer LSP plugin off, or `templates/claude-settings.json` | With the plugin on, every agent that edits starts its own rust-analyzer on the whole workspace, which multiplies memory use. Writers get diagnostics from the shared racheck daemons instead. The template also allows the read-only commands, so lookup agents do not stop on permission prompts |
| The kit's `tools/` directory first on `PATH`, and `PORT_KIT_CONFIG` naming the port's `port.toml` | Prompts call the dashboard as `track ...` by its bare name, which `templates/claude-settings.json` allows (`Bash(track:*)`). `swarm.py` sets both for its jobs |
| `--strict-mcp-config` | No MCP servers from your own config |
| `PORT_KIT_AGENT=1` in the environment | The kit plugin's SessionStart hook prints the lead's context in every session inside the workspace; with this set it prints nothing, so an agent never reads the lead's instructions. `swarm.py` and `port-set` set it |
| `--output-format json` | The result, the session id, the turn count, token usage and cost. Kit tools log each call in `work.usage_log` |
| `--max-turns <n>` | A bound per call (`pipeline.*_max_turns`). A call that runs out reports `OUT OF TURNS` and can be continued |
| Sessions kept (no `--no-session-persistence`); `--resume <session id>` for a follow-up | A follow-up resumes from the prompt cache, and the saved sessions are what `tools/collect-logs` sends when a run is reviewed. They sit under `~/.claude/projects/`, a few MB per agent |
| `--add-dir <tree>` for each other tree it reads | A set that spans both repos reads the other tree; an app set reads the framework at `racheck.fw_base` |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` raised (the kit uses 64000) | A writer's reply carries whole edited files |
| Terminal multiplexer variables (`TMUX`, `TMUX_PANE`) removed from the environment | Otherwise hooks report the headless agent as the lead's own pane |

Your own `CLAUDE.md`, skills and hooks load into every headless agent. Keep instructions that conflict with the kit's rules out of them, or run the agents with a separate `CLAUDE_CONFIG_DIR` that holds only your login.

## Background tasks

- Start every batch, gate, build and long command as a background task of the lead session, so that its exit notifies the lead. Never wait in the foreground: a foreground wait blocks the developer's messages until it returns.
- Never watch a background job with a hand-written poll (a loop on `pgrep`, a file check). It can match its own command line or miss the end, and the finished job then sits unnoticed.
- Say that background work started only after the tool result confirms it, and name what started (the task id, the command).
- Run heavy jobs (rust-analyzer daemons, builds, writer batches) under `build.memory_cap`, so an out-of-memory kill takes the job and not the lead session (`11-build-loop.md`).

## Choosing models

The `[models]` table in `port.toml` holds the model per step. Its defaults follow `rules/lead-rules.md`, "Models and cost":

| Work | Model |
|---|---|
| Inventory chunks, fact answers, lookups, builds, runs, log reading | Haiku |
| Writing sets, plan checks, review fixes, compile fixes, red-round fixers, the integrator, phase 2 sheet fixes | Sonnet |
| Area maps, question splits, chunk plans, merges, evaluations, decisions, consistency, reviews | Opus |
| Sets that change a shared mechanism, fixers whose failures have a framework cause, retries of a Sonnet failure | Opus |

Before a triage or sweep over many tests, calibrate the model against a lead reference (`rules/testing-rule.md`).

## Briefs

Every brief or prompt the lead gives an agent:

- is complete before the agent starts: the goal, the reference values, the mechanism to build on, the places (files, lines, signatures, callers), and how and when to test;
- includes `rules/agent-common.md` and the rule files the job needs, in full;
- forbids the agent to start subagents or workflows;
- gives the agent its task id and its `track` calls;
- fits one task into about 150 tool calls.

Render prompts with `tools/render-prompt`, which fills the `{{...}}` placeholders from `port.toml` and names any that stay empty.

## Quota and pacing

- State the batch's agent count by model and its projected cost before launching it (`costs.md` has the measured costs of each step).
- Pace launches to your plan's usage window: spread what is left evenly until the window resets, and keep agents running at that rate. A burst followed by a pause wastes the window.
- Set `pipeline.quota_command` to a command that prints the window's use as a percent; `swarm.py` and `run-batch` then start no new job while it reports at or above `pipeline.quota_cap`.
- A usage-limit notice decides where and when new launches go. It is not a reason to stop running work.

## The dashboard

The dashboard (`tools/track.md`) shows every task's state. Agents keep it current themselves, through the calls in `rules/agent-common.md`, "Tracking": `track step` at each step, `track status` on each state change (with `--on` for a blocker), `track ask` for each question, and `track status TASK review ... --calls N` on hand-back. Kit tools post their own results.

**The stale rule.** A task is stale when it is `running` or in `review` and no event has named it for `track.stale_min` minutes (default 20). Any event that names the task counts, tool events included, so a writer whose `port-set` calls keep posting is not stale. A stale task shows red on the page and as a line in `track alerts`.

- An agent that starts a step it expects to outlast the limit (a full build, a long run) says so in the step's note: `track step TASK compile "cl test all, about 15 min"`. Shell commands it runs through `track run KIND --task TASK -- CMD` post an event when they end.
- The lead keeps `track watch` running as a background task and starts it again after each exit (`tools/track.md`, "For the lead and the developer"). On a stale line, it reads the agent's output first, then resumes the agent or stops it and starts a fresh one with a corrected brief.
- A blocking question wakes `track watch` at its next poll. Questions that proceed on their recommendation wait for the batch's rulings. The lead never relies on the stale timer to notice a question.

## Resuming agents

- **Follow-ups go to the same agent.** After an agent hands back, its review findings, still-failing tests or a "go" on its plan go back to it, resumed with its context intact (`tools/swarm.py --follow-up TASK PROMPT-FILE` for a `swarm.py` job: it resumes the task's saved session with the same model, tools and tree, and prints one JSON line with the reply; `--resume <session id>` for another headless call; or the resume mechanism of the session that started it). The agent already knows the code it read.
- **Writer sets continue from their trees.** `port-set agent SET --continue` starts an agent that finishes an earlier agent's committed work in the set's trees, in a fresh context. `run-area` gives an agent-mode set up to `pipeline.agent_continue_rounds` such rounds while its check names an error or it ran out of turns.
- **Start a fresh agent** when the old one's context is too large (past about 150 tool calls), or when its brief was wrong. Give the fresh one a corrected brief and the old one's report.
- **Never redirect a running agent.** Stop it, and start a fresh one with a corrected brief. A correction sent mid-run mixes two briefs in one context.
- **Batches resume.** Restart a stopped batch with the same command: `swarm.py` resumes its job list (a job reruns when its prompt, model, schema or the content of a file in its `inputs` changed), `run-area` skips the sets already in its log, and `run-batch --plancheck` skips sets whose `plancheck.md` exists.

## Reports and progress files

- Single agents write their report to the file their brief names (template `templates/task-report.md`): a `## Resume` block that says where to pick up, the plan, one `## Progress` line per step, findings and open questions. The report doubles as the resume point for a fresh agent.
- Batch jobs write their output files and nothing else. Their progress shows on the dashboard through the tools.

## Hand-offs

A lead session's context grows with every turn, and every turn re-reads all of it. Hand off at a stopping point once the context is large:

1. Write the current state into `STATE.md`: phase, step, next action, running agents with their task ids, open questions, and pointers to reports. Pointers, not copies of earlier hand-offs.
2. Run `track md`, so STATUS.md in the workspace matches the board.
3. Stop `track watch`.
4. Start the next session with the kit's skill. A session that starts without context reads `STATE.md` and `track show` before anything else, then starts `track watch` again.

Background tasks belong to the session that started them. Hand off when none is running, or record each one in `STATE.md` with its output file, so the next session can find its result. Tasks on the board show their last state either way (`track show`).

# The port process

This kit ports a craft app's legacy UI onto the craft framework (craft-libs, branch `next`). One developer runs the port with one lead agent session, which plans the work and runs batches of agents. The process aims to finish a whole app in one or two days of wall time.

Read this page first. Each phase then has its own runbook (`01` to `10`); the file number is the phase number plus one (phase 0 is `01-setup.md`). `costs.md` gives measured costs to plan with.

## The idea

1. **Plan everything first**, with many small read-only agents. The plan names every file to write, every framework signature to add or change, every reader of a mechanism the port replaces, and a verdict for every test.
2. **Write all code with no builds.** Writers work in code-only trees from their plan sheet. rust-analyzer stands in for the compiler while they write.
3. **Build once per batch.** Combine a batch of written sets on one integration branch, compile it in one warm target dir, run the tests, and fix in rounds.

Why: a build-and-gate loop per task repeats the same overhead (rebuild on a moving framework, rebase, queue for a check dir, gate rounds) for every task, and most of the wall time goes to waiting. Planning first moves the judgement into cheap read-only work, and batching pays for each warm build once. `lessons.md` has the numbers from the app where this was learned.

The per-task model (one agent plans, writes, builds and gates one task) stays only for one-off work: a look fix found in phase 8, or a framework gap found late. `prompts/p8-task-brief.md` is its brief.

## Phases

| # | Phase | Starts when | Ends when | Main artifacts | Agents | Builds | Runbook |
|---|---|---|---|---|---|---|---|
| 0 | Setup | The developer picked the app and the framework rev | App port branch pins one framework rev; package selection derived and `cl doctor` clean; baseline test run recorded; racheck daemons answer; SCIP index built; dashboard served | `port.toml`, `STATE.md`, `baseline-failures.txt`, `scip/*.sqlite` | lead only | one warm app build and one full test run | [01-setup.md](01-setup.md) |
| 1 | Inventory and map | Setup done | Every UI file in a chunk; every entry in an area map section; index coverage clean; lead spot-checked each map | `inventory/chunk-NN.json`, `port-map/<area>.md`, `port-map/README.md` | Haiku per chunk; Opus per area and for the index | none | [02-inventory-and-map.md](02-inventory-and-map.md) |
| 2 | Plan | Maps accepted | Coverage has no gaps; sampled plan error rate at most `plan.max_error_rate`; fact answers under `plan.max_wrong_answers` wrong; open questions decided; sizing written | `plan/contract-parts/*.md`, `plan/sheets/<set>.md`, `ownership.md`, `settled.md`, `sizing.md` | Opus to split questions, plan, merge and evaluate; Haiku to answer; Sonnet to fix sheets | none | [03-plan.md](03-plan.md) |
| 3 | Contract stubs | Plan passed | Every contract signature compiles; every caller a stage patched is matched to a sheet | the stub branch (`framework.writing_base`), stage reports | Sonnet, one per stage in crate order | `cl check` per crate | [04-contract-stubs.md](04-contract-stubs.md) |
| 4 | Plan check and decisions | Stubs compile | No DECIDE item open; audits report 0 | `sets/<set>/plancheck.md`, `decisions.md`, `decide/<area>.md` | Sonnet per set; Opus per decision part; Opus consistency pass | none | [05-plancheck-decide.md](05-plancheck-decide.md) |
| 5 | Write | Audits clean | Every set of the batch written; each set's check has no errors; racheck errors in its own files are 0 or explained | `sets/<set>/`, set branches | Sonnet by default; Opus for shared mechanisms and retries | none (racheck only) | [06-write.md](06-write.md) |
| 6 | Review, combine, compile | A batch is written | Each set reviewed and fixed; the integration branch compiles, framework crates first, then the app | `review-*.md`, the batch's integration branch, compile logs | Opus reviewer per area and side; Sonnet fixers | one compile per batch | [07-review-combine-compile.md](07-review-combine-compile.md) |
| 7 | Tests and red rounds | The batch compiles | Kept tests pass; every triage verdict carried out; no `DIAG ` line left; formatted | run logs, triage TSV, round reports | Sonnet fixers per track (Opus for framework causes); one integrator | one build and one full run per round | [08-tests-and-red-rounds.md](08-tests-and-red-rounds.md) |
| 8 | Look and behaviour | Tests green | Every map section's states compared with the old app and accepted | states files, old/new captures | one agent per component class | incremental | [09-look-and-behaviour.md](09-look-and-behaviour.md) |
| 9 | Land | Look accepted | Framework changes on `framework.branch`; app scrubbed and pinned to the landed framework rev; CI result recorded | scan reports, landing clones | lead | CI | [10-land.md](10-land.md) |

Phases 5 to 7 repeat per **build batch**: the pilot, then the framework-side sets as one batch (two above about 60 sets), then the app sets in one or two batches written against the compiled framework. The number of build passes, not the number of sets, sets the wall time of these phases.

Two more pages apply to every phase: [11-build-loop.md](11-build-loop.md) (cl, the one feature resolution, warm target dirs) and [12-running-agents.md](12-running-agents.md) (headless agents, background tasks, quota, models).

## Roles

| Role | Who | Does |
|---|---|---|
| Developer | You | Picks the app and the framework rev; answers questions about goals, design principles and architecture; looks at results; runs anything that needs their accounts (pushes, CI). |
| Lead | One agent session opened with the kit's skill (`skills/craft-ui-port/SKILL.md`) | Runs the phases: renders prompts, launches batches, reviews outputs, decides every question the rules settle, merges, keeps `STATE.md` and the dashboard current. Writes no large code itself. |
| Agents | Headless sessions the lead starts, alone or in batches | One job each: read a chunk, answer questions, plan a chunk, write a set, review an area, fix a track. They follow `rules/agent-common.md` and report through `track`. |
| Kit tools | `tools/*` | Do everything a script can do: bundles, checks, combines, gates, runs, scrubs. Each posts its own events to the dashboard. |

The lead asks the developer only about goals, principles and architecture, never about layout or design detail: the old app decides what things look like (`rules/porting-rules.md`).

## Where things live

| Place | Holds | Config key |
|---|---|---|
| The kit | Process, rules, prompts, templates, tools. Read only during a port. | - |
| The workspace | `port.toml`, `STATE.md`, the dashboard store, inventory, maps, plan, per-set output, run logs | `work.dir` |
| Trees | Per-set worktrees and the read-only snapshot and racheck checkouts | `work.trees` |
| Framework checkout | The local craft-libs clone; its integration worktree | `framework.checkout`, `framework.integration` |
| App checkout | The local app clone; its integration worktree; the production reference | `app.checkout`, `app.integration`, `app.production` |

`port.toml` names all of these ([config.md](config.md)). Every kit tool reads it, and `tools/render-prompt` fills every prompt from it.

## The progress dashboard

A port has hundreds of agent jobs. The dashboard shows the whole port on one local page, so the developer and the lead can see at a glance:

- the current phase;
- every task with its state (`todo`, `running`, `review`, `waiting`, `blocked`, `done`, and `failed` for a tool job that failed), its agent's model, its last note and how long ago it last reported (a stale task shows in red);
- what each blocked task waits on;
- questions waiting for the developer or the lead, with their options;
- test pass and fail counts per red round, as a trend;
- an event log: merges, landings, decisions, and every kit tool run with its result.

**Who reports what.** Scripts report what scripts know; agents report judgement.

- Kit tools post their own events: every long command (gates, test runs, combines, `port-set`, `swarm.py`, landing) posts one event when it ends, with its duration, log and key numbers. `port-set` moves a set's task through its states, `swarm.py` creates one task per job, and `test-run` posts each round's counts.
- Agents report through `tools/track`: state changes, blockers, questions, and their tool-call count when they hand back.
- The lead creates a task on the board before it launches an agent, records each phase change, and watches `track alerts`.

The calls agents and the lead use (`tools/track.md` has the full reference):

| Call | When |
|---|---|
| `track step TASK STEP [NOTE]` | At the start of each step of a task (`plan`, `write`, `compile`, `test`, `fix`, `merge`, or the step a prompt names) |
| `track status TASK STATE [NOTE] [--on WHAT] [--calls N]` | On every state change; `--on` names what a blocked or waiting task waits for; `--calls` on hand-back |
| `track ask TASK "QUESTION" [--option A]... [--for developer\|lead]` | For every question; the lead also asks the developer in chat |
| `track answer QID "ANSWER"` | When a question is answered, wherever the answer came from |
| `track round N --pass P --fail F [--log PATH]` | After every full test run that a tool did not record itself |
| `track event KIND TEXT [--task ID]` | For merges, landings and decisions |
| `track phase N [NOTE]` | At each phase change (the numbering on this page) |
| `track alerts` | In the lead's monitor loop: stale tasks, unanswered questions, blocked tasks |

The dashboard is self-contained: the store lives in the workspace (`track.dir`), and `track publish` writes a static page plus `state.json` to `track.out_dir` after every write. The kit never chooses a host or exposes anything. Phase 0 asks the developer how they want to view it ([01-setup.md](01-setup.md), step 3).

## Rules

Every agent gets the rules in full, through its prompt:

- [rules/porting-rules.md](../rules/porting-rules.md): look, code, tests and efficiency rules for every agent.
- [rules/agent-common.md](../rules/agent-common.md): source precedence, scope, stop-and-report, git and report shape.
- [rules/testing-rule.md](../rules/testing-rule.md): which tests to keep, rewrite or delete, and why.
- [rules/framework-decisions.md](../rules/framework-decisions.md): decisions already taken that bind every craft app.
- [rules/lead-rules.md](../rules/lead-rules.md): for the lead only.

## Glossary

| Term | Meaning |
|---|---|
| Area | A part of the app's UI that is planned, reviewed and built as one piece (for example panels, dialogs, tools). Listed as `[[areas]]` in `port.toml`, each with a two-letter code. |
| Chunk | A slice of the app's UI code, about `plan.chunk_lines` lines, that one agent inventories in phase 1. |
| Entry | One user-visible part or piece of UI infrastructure in the inventory. Id `<chunk>.<index>`. |
| Map section | One part (or a few small parts) in an area map: its framework replacement, fit, gaps, app glue, test verdicts and states. |
| Fit | How well a framework component replaces a part: `direct`, `needs props`, `missing component` or `app-only`. |
| Plan chunk | A run of whole sections of one area map that one Opus agent plans in phase 2. |
| Shared gap | A framework change several map sections need (`SG-n` in the index). |
| Set | The files one writer completes in about 150 tool calls with no build. Id `<area>-w<n>`. Every file the port writes belongs to exactly one set. |
| Sheet | A set's plan: its files with actions and line counts, the readers of every mechanism it replaces, its test verdicts, and writer notes. Writers work from their sheet alone. |
| Contract | Every new, changed or removed framework item, with its signature, behaviour, what it replaces and its writer set. Id `<code>.<Kind><n>`. Kept in contract parts. |
| Stub head | The framework branch with every contract signature compiled as a stub (`todo!()` bodies). The writers' base: `framework.writing_base`. |
| `P3(<set>)` marker | A comment on a minimal edit made in phase 3 to keep a caller compiling; the named set's writer replaces it. |
| Plan base | The framework and app commits the plan was made against (`plan.base`, `plan.app_base`). |
| racheck | rust-analyzer diagnostics for a set's changed files from a warm daemon, with no cargo build. |
| SCIP index | A rust-analyzer index loaded into sqlite: one row per use of a named item. It answers "which files use exactly this item". |
| Plan check | A cheap per-set read of the sheet against the stubbed code that tags every item STUB (already there), RULE (the rules decide it) or DECIDE (a real choice). |
| Bucket | How a set is written: one-shot (one writer call plus a repair) for small sets, agent mode for sets over `pipeline.agent_files_over` files. |
| Build batch | The sets that are combined, compiled and tested together. |
| Owed line | A line a set not yet written must provide, added on the integration branch as a marked commit so the batch compiles. |
| Track | A group of failing tests with one likely cause, given to one fixer in a red round. |
| Red round | One cycle of phase 7: fixers write code-only fixes for their tracks, one integrator merges all of them, builds once and runs the tests once. |
| Triage verdict | The decision for a failing test: `keep` (fix the code), `cut` (delete the test), `cut-fix` (fix the bug, then delete the test), `move` (into a framework trial). |
| `track` | The kit's dashboard command (`tools/track`). |

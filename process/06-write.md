# Phase 5: write

Phase 5 writes every set from its sheet and decisions, with no builds. Each set gets code-only worktrees (one per repo it writes), a writer call or a writer agent, a scripted check and rust-analyzer diagnostics from the warm racheck daemons. The code compiles for the first time in phase 6, once per build batch.

| | |
|---|---|
| Starts when | Phase 4's audits report 0 ([05-plancheck-decide.md](05-plancheck-decide.md)). |
| Ends when | Every set of the build batch is written; each set's `check.md` has no scripted error; racheck errors in the set's own files are 0 or explained. |
| Agents | Sonnet by default (`models.write`); Opus for sets that change a shared mechanism (`models.write_shared`) and for a retry of a set Sonnet failed (`models.retry`). |
| Builds | None. racheck only. |
| Output | Per set: `<work.sets>/<set>/` (bundle, edits, `check.md`, `racheck.md`, `run.log`), its branch `<work.branch_prefix>set/<set>` (and `<work.branch_prefix>set/<set>-<repo>` for a second repo) in its worktree under `work.trees`. |

## What a set run does

`tools/port-set run <set>` takes one set through these steps, and records every model call's tokens and cost in `work.usage_log`:

1. **Trees.** One code-only worktree per repo the set writes, on its own branch at the repo's writing base (`framework.writing_base`, `app.writing_base`). The start commit goes to `<work.sets>/<set>/base-<repo>`. Trees have no target dir, and nothing in phase 5 runs cargo.
2. **Bundle.** One file with everything the writer needs: instructions, the `## Code` section of `rules/porting-rules.md`, the output format, the sheet (with line numbers at the stub head), its contract rows, its decisions, the text of its files (whole, or an outline plus the parts the sheet names), the framework definitions it names (from the SCIP index), and excerpts of other files the sheet cites. Budgets are in `[pipeline.bundle]`.
3. **Write.** One model call returns edit blocks; the script applies them once (a rerun skips blocks already applied). A writer that cannot proceed answers BLOCKED with the reason.
4. **Check.** Scripted checks (`check.md`): files in the Files table left untouched, leftover `todo!` stubs or `P3(<set>)` markers of the set's own items, missing tests, duplicate `mod` lines, lint patterns (`rules/lints.toml`), `// PLAN: assumed` guesses for items the framework already defines, decided items missing from the code.
5. **racheck.** rust-analyzer diagnostics for the files the set changed, from the warm daemon, in seconds (`racheck.md`). Unresolved names, type mismatches, wrong arity and missing fields show here; borrow-check errors and errors rustc reports inside macros show only at compile time.
6. **Repair.** When the checks fail, up to `pipeline.repairs` repair calls, each with the check output.
7. **Commit** on the set's branch.

A writer that needs an item another set is writing at the same time codes against the signature its sheet or contract row gives, and marks it `// PLAN: assumed <signature>`. The review checks each marker against the other set's sheet.

`tools/port-set agent <set>` writes a set with an autonomous agent instead: a short prompt, edit tools, the sheet and code read by the agent itself, up to `pipeline.agent_max_turns` turns; `--continue` finishes a set an earlier agent left incomplete. `tools/port-set.md` gives every flag, the bundle grammar and the exit states.

## Buckets: how each set is written

| Bucket | Which sets | Command |
|---|---|---|
| One-shot | Sets with at most `pipeline.agent_files_over` Files rows, except `models.write_shared` sets | `port-set run` |
| Agent mode | Sets with more Files rows; every `models.write_shared` set at any size (a one-shot Opus write runs out of turns far more often); one-shot sets that came back BLOCKED | `port-set agent`, in rounds of `pipeline.agent_round_turns` turns; `--continue` while `check.md` names a scripted error or the last round ran out of turns, at most `pipeline.agent_continue_rounds` rounds |

| Model | Which sets |
|---|---|
| `models.write` (Sonnet) | Every set its sheet fully specifies: the default |
| `models.write_shared` (Opus) | Sets that change a shared mechanism: the framework's runtime, contract pipeline, layout or behaviour crate, or anything many components call |
| `models.retry` (Opus) | A set a Sonnet writer failed twice (BLOCKED again after agent mode, or out of rounds) |

`tools/run-area` applies these rules to one area. It takes two list files: the shared-mechanism sets and the default sets.

## Batch lists

A list file holds one set id per line. Keep one pair per area and side, for example `<area>-fw-shared.txt` and `<area>-fw.txt`, under `<work.sets>/lists/`. `examples/photocraft/write-order.md` shows a real write order and its lists.

| Command | Use |
|---|---|
| `tools/run-area NAME SHARED-LIST DEFAULT-LIST [N]` | Write one area's sets, N at a time, each in its bucket. Log: `<work.sets>/area-NAME.log`. A killed run resumes: sets in the log are skipped, an agent-mode set with uncommitted work is committed and continued. |
| `tools/run-batch LIST [N] [MODEL]` | Write a flat list with one model and `port-set run --skip-plancheck`. |

Start every batch as a background task, so its end notifies you. Set `pipeline.quota_command` and `pipeline.quota_cap` so the runners hold new jobs near the quota limit, and pace launches over the quota window (`rules/lead-rules.md`, "Models and cost"). Before each batch, state its set count by model and its projected cost from `costs.md`.

Both runners start with the writer canary (`tools/racheck.py canary --sets <list>`): each repo's racheck daemon diagnoses one file no set has touched, and the runner refuses to start unless it has 0 errors. An error there means the daemon cannot resolve the writing base (a missing dependency or framework patch), so every set's racheck would report false errors; fix the daemon's tree, restart the daemon, and start the batch again. A daemon that is not running also stops the batch.

## Write order

1. **Pilot first.** Run one area end to end, framework side and app side, through phases 5 to 7 for its framework sets, before writing any other area. The pilot is the shell plus the section of the main surface with the most framework gaps (the top of the index's risk ranking, [02-inventory-and-map.md](02-inventory-and-map.md)): the riskiest design problems show first, while changes are cheap. It touches both repos. Judge its code on its own merits before anything compiles: a fresh Opus reviewer reads the written code against the sheets, decisions and rules ([07-review-combine-compile.md](07-review-combine-compile.md), step 1). A failing review goes back to the plan or the writers, never into a build. The pilot's cost per set, review findings by source and compile errors per 1,000 lines set the projection for the rest; record them in `log.md` and update the projection the developer has.
2. **All remaining framework sets as one build batch** (two batches when the plan has more than about 60 framework sets; split by area, the riskiest sets in the first). Write the batch, then review, fix, combine, compile, run the framework tests and fix ([07-review-combine-compile.md](07-review-combine-compile.md), [08-tests-and-red-rounds.md](08-tests-and-red-rounds.md)). The app batch setup starts when the framework batch is green.
3. **App sets, after the framework builds**, written against the real framework code instead of stubs, in one or two build batches. Set each batch up first ([07-review-combine-compile.md](07-review-combine-compile.md), "Setting up an app batch"). Every set still gets its review and fix round as it is written; the build steps (combine, compile, test run) run once per batch, since a warm incremental build costs about the same for 20 sets as for 60.

If the first app batch's compile shows plan-level errors (a wrong contract item, a missing API) rather than writer slips, split the next batch by area before it builds.

The number of cycles, not the number of sets, sets the wall time of phases 5 to 7 ([costs.md](costs.md), "The cycle model").

## Code-only trees for every writer

Set writers and review fixers in phases 5 to 7 work in a code-only tree: a git worktree with no target dir, where nothing runs cargo, `cl` or rust-analyzer. They write code that compiles by reading: every import path, signature and trait bound checked against the code. Compile and red-round fixers follow the fixer mode ([11-build-loop.md](11-build-loop.md)). `tools/cycle` builds everyone's work together.

One-off tasks with a build (a look fix in phase 8, a framework gap found late) use the same split: the agent plans and writes in a code-only tree while it waits, then takes a build tree only to compile, run its trials and capture, and hands the build tree back at once ([11-build-loop.md](11-build-loop.md), "Target dirs and trees"). Before switching a build tree to its branch, the agent detaches the branch in its code-only tree (git refuses a branch checked out twice) and checks that the switch succeeded before it rebases: a rebase after a failed switch rewrites the build tree's previous branch.

## Reading a set's result

`port-set` moves the set's task on the dashboard from its exit state:

| Exit | Task state | What you do |
|---|---|---|
| Written, scripted check clean | `done` | Nothing now. racheck errors in other sets' files wait for the combine. |
| Written, scripted errors or apply failures left | `review` | Read `check.md` and `apply.md`. A writer slip: continue the set (`agent --continue`) or leave it to the review fix. A sheet error: fix the sheet and rerun. |
| OPEN: the plan check left DECIDE items | `review` | The set skipped phase 4 or its sheet changed: decide the items ([05-plancheck-decide.md](05-plancheck-decide.md), step 4), then rerun. |
| BLOCKED | `blocked` on lead | Read `blocked.md`. Fix the cause in the sheet, decisions or stubs, then rerun in agent mode. |
| OUT OF TURNS | `blocked` on lead | `port-set agent <set> --continue`. |

After a batch ends, read the batch log and go through every set that is not `done`. Check `racheck.md` for each set: errors in the set's own files are 0 or explained (an item another set writes, a known racheck gap in `racheck.gap_patterns`). Errors listed under "not changed by the set" are readers in files that other sets change; they resolve at the combine.

A set that adds a framework component writes its gallery stories in the same set, as its sheet's `Stories` head line says ([rules/porting-rules.md](../rules/porting-rules.md), "UI gallery"). Check that the set's diff registers them before you hand the batch to review.

Record what you did to the batch: `tools/track event decision "<area>: <sets> moved to agent mode / retried on Opus"`. The batch runners and `port-set` post their own run events; never repeat them.

## Exit

- [ ] Every set of the batch has a commit on its branch and a `check.md` with no scripted error.
- [ ] racheck errors in each set's own files are 0, or explained in `log.md`.
- [ ] No set is `blocked`; every BLOCKED or OUT OF TURNS set was rerun or retried.
- [ ] Every component a set adds has its stories in the set's diff.
- [ ] For the pilot: the app compiles and runs with the pilot's parts, and their states are captured against production ([09-look-and-behaviour.md](09-look-and-behaviour.md)).
- [ ] For the pilot: the projection from its measured costs is in `log.md` and went to the developer.

Then review, combine and compile the batch: [07-review-combine-compile.md](07-review-combine-compile.md). Phases 5 to 7 repeat for each build batch; record `tools/track phase 6 "review, combine, compile"` when the batch moves on. `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

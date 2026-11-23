# p7-red-integrator

Integrator of a red round: merge every fixer branch, compile once, run the trials and one full run, write each fixer's packet. Fill the placeholders with `tools/render-prompt`.

You integrate round `{{ROUND}}` of the red tests. You own the framework integration tree {{FW_INT}} and the app integration tree {{APP_INT}} until you report. Do not start subagents or workflows. Never push. Stay under about 150 tool calls; stop at a clean point before that and report exactly what is left.

Read first, in full: {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md; the previous round's report in {{RUNS}} (the baseline for your comparison); {{KIT}}/process/08-tests-and-red-rounds.md; {{KIT}}/process/11-build-loop.md (the build tool, memory caps, disk rules).

## 1. Merge the round's branches, one at a time, into both trees

Your prompt lists each fixer's branches and heads (framework and app). They were written with no build, on the previous round's heads. Merge one branch at a time and resolve conflicts by keeping one mechanism: where two fixers added a mechanism for the same concept, keep the one already on the integration branch, drop the duplicate, and point the other fixer's caller and test at the kept one. Record each such choice for the report.

## 2. Compile, trials, full run

1. Compile both trees through the gates: `{{KIT}}/tools/compile-gate {{ROUND}}` (framework, then app). Fix compile errors yourself when they are mechanical (an import, a path, a renamed item). A cause that needs a design choice goes back to its fixer or into the report.
2. Run the framework trials of every crate a fixer changed: `{{KIT}}/tools/test-run` with the crate and filter.
3. Run the app's one full run: `{{KIT}}/tools/test-run` for the app, label `{{ROUND}}`. Logs go to {{RUNS}}/{{ROUND}}/. The tools record their own durations, counts and the round result on the dashboard.

## 3. Compare and attribute

1. `{{KIT}}/tools/compare-runs.py {{ROUND}} <previous run> --tracks <previous run>/groups.md` (both under {{RUNS}}) against the previous round: per track, tests fixed since, tests failing now, and new failures (with the fixer whose change most likely caused each).
2. `{{KIT}}/tools/split-failures.py` for the failure groups of the remaining failures. This is for information only: each fixer keeps its own list, and tracks are not re-formed in this round.
3. `{{KIT}}/tools/diag-cut.py {{ROUND}} --tracks <previous run>/groups.md` writes one return packet per fixer: the still-failing tests of its list, each with its panic line and its `DIAG <test_name>` lines.

## 4. Format, commit and report

Format as `{{RULES}}/agent-common.md` says ("Formatting"): `cargo fmt` on the changed crates only. Commit on both integration branches.

Write {{RUNS}}/{{ROUND}}/report.md (format: {{KIT}}/templates/run-report.md): the merges and conflict choices, compile fixes, pass and fail counts against the previous round, the per-track table, the new failures with their attribution, and the compile and run wall times. A new failure goes to the track that caused it, with the cause as far as you read it, marked confirmed or not confirmed by a run.

Final message: final heads of both trees, compile fixes, pass and fail counts, per-track results, new failures, and the path of every packet. The lead sends each packet to its fixer; you do not. Then `track event round-report "<one line>" --task {{TASK}}` and the report's path as a link.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `merge`, `compile`, `trials`, `full-run`, `compare`, `packets`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

# mp-test-fix

Follow-up packet for a minimal-port writer: the failing tests of one round in its files. Per call: TASK, ROUND. The lead appends each test with its panic lines and DIAG output. Fill the placeholders with `tools/render-prompt`.

Test round `{{ROUND}}` of the minimal port. The lead merged every writer's branch, built once and ran the app's tests once (`{{RUNS}}/{{ROUND}}/`: `summary.json`, `compare.md`, the logs). The tests below fail and are in the files you own or test the code you wrote. Merge the port branch's head into your branch first.

Do not start subagents or workflows. Stay under about {{FIXER_CALLS}} tool calls; before that, stop at a clean point and report what is left.

## Per test

Read the test body, the code it drives and production ({{PROD}}) until you know the cause. Then:

- **A port bug** (the app behaves differently from production): fix the code. Never weaken an assertion.
- **A harness without the runtime** (a bare context or a kittest harness that runs the app's UI): install it with `install_headless`.
- **A test of removed framework internals** (the old renderer's hit ids, divider geometry, its drags; old framework strings): delete it, and add it to your report's deleted-tests table with the reason.
- **A test whose premise the framework changed on purpose** (one press per pass, Escape routing, one-column floating windows, the font load drawing in the first frame): rewrite it to check the same user-visible behaviour under next's rule, keep its name, and list the difference in the report.
- **A framework fault** (the app does what next's docs say, and next does not): do not work around it. Write it in your report's findings table (craft-libs file:line, the evidence, the test), add `track event finding "<craft-libs file:line>: <fault>" --task {{TASK}}`, and leave the test failing. The lead decides whether it becomes a framework fix.
- **A test that already failed at the baseline**: leave it, and say so.

Where reading leaves the cause uncertain, write your best fix and prints that confirm or refute it in the next run: `eprintln!("DIAG <test_name>: ...")`, with exactly that prefix and the test's function name. Remove the prints of a test once it passes. No cargo: the lead's next run is the confirmation.

One line per test: `track event fix "<test_name>: cause, fix, confidence (sure | likely | guess), DIAG yes/no" --task {{TASK}}`. Commit per cause; messages say what behaviour changed. No attribution lines. Never push.

## Report

Append to your report file: per test the cause, the fix and the confidence; deleted and rewritten tests with reasons; framework findings; the commit hashes.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} fix "{{ROUND}}"` when you start, and `track step {{TASK}} report` before the report. If it exits 3, the port is paused: stop and report.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

## Failing tests

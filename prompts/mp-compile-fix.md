# mp-compile-fix

Follow-up packet for a minimal-port writer: the compile errors of one round in its files. Per call: TASK, ROUND. The lead appends the error lines. Fill the placeholders with `tools/render-prompt`.

Compile round `{{ROUND}}` of the minimal port. The lead merged every writer's branch onto the port branch and ran one compile check (`{{RUNS}}/{{ROUND}}/`). The errors below are in the files you own. Your tree is the one you wrote in; merge the port branch's head into your branch first, so you see the other writer's work.

Do not start subagents or workflows. Stay under about {{FIXER_CALLS}} tool calls; before that, stop at a clean point and report what is left.

## Job

1. Group the errors by cause: a framework signature you misread, a missing import, a moved item, a type that changed, an `#[non_exhaustive]` type built as a literal. One cause often gives many errors.
2. Read the definition in {{FW}} or in the app before each fix. Fix each cause once, then every site of it in your files.
3. Still code only: no cargo. The next round's compile checks your fixes.
4. A cause in a file you do not own: write it in your report (file:line, the change needed) and leave the file.
5. A cause in craft-libs (a signature that cannot be used as its docs say, a missing public item that the docs name): do not work around it. Write it in your report's findings table with the evidence, and add `track event finding "<craft-libs file:line>: <fault>" --task {{TASK}}`.
6. Commit per cause, with a message that says what changed. No attribution lines. Never push.

## Report

Append to your report file: per cause what it was, the fix (file:line) and the errors it should clear; the errors left and why; causes in other files or in craft-libs; the commit hashes.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} fix "{{ROUND}}"` when you start, and `track step {{TASK}} report` before the report. If it exits 3, the port is paused: stop and report.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

## Errors

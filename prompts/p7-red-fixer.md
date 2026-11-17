# p7-red-fixer

Fixer for one track of failing tests: fix by reading, write DIAG prints where unsure, hand back, stay resumable. Fill the placeholders with `tools/render-prompt`.

You own one track of failing tests: track `{{TRACK}}`, round `{{ROUND}}`. Your tree names and branches are in your prompt. Do not start subagents or workflows. Stay under about 150 tool calls; stop at a clean point before that and report what is left.

Read first, in full: {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md, {{RULES}}/testing-rule.md, and your track's section of {{RUNS}}/{{ROUND}}/groups.md (the tests, their triage rows and the class rows). Each test's triage row (file:lines, verdict, evidence, cause) is in the triage table named in your prompt. Current failure messages are in the logs in {{RUNS}}/{{ROUND}}/. If your tree already holds earlier edits (a work-in-progress commit or uncommitted), read them first and keep what is right.

## Rules

- **No cargo at all**: no build, no check, no test, no rust-analyzer. The lead's integrator compiles and runs once for every fixer. Write code that compiles: check imports, signatures and types by reading their definitions. Do not remove a trait import as unused.
- Never `git stash`. Never push. Edit only your own trees.
- Never weaken an assertion. Never add a `#[doc(hidden)]` back door. Never infer a fact from hover or side effects.
- Production ({{PROD}}) is the reference for behaviour. The test is evidence, not a specification.
- One mechanism per concept: a fix that adds a mechanism removes the one it replaces. A shared cause gets one fix for every test it affects.
- A fix that needs a design choice that the rules and production do not settle: stop that test, write the question with your recommendation in your report, and go on with the rest.
- A cause in a framework file that you may not edit (your prompt says which trees you own): write the cause (file:line, evidence) in your report and go on.

## Per test, by verdict

- `keep`: find the cause from the test body, the code it drives and production. A port bug: fix the code where the bug is (app or framework). A stale premise (the test reads a structure, label, helper or timing that the port replaced, while the user-visible behaviour matches production): update the test to drive and check the same behaviour through the port's own signals.
- `cut-fix`: fix the behaviour difference the triage names, then delete the test.
- `move`: write the behaviour as a framework trial in the crate that owns it (relations, never sizes), then delete the app test. Grep for an existing trial first; if one covers it, delete the app test.
- `cut`: delete it.

## How to work

1. For every test on your list: read the test body, the code it drives and production until you know the cause, and write the fix.
2. Where reading leaves the cause uncertain, write your best fix and targeted prints that confirm or refute it in the shared run: `eprintln!("DIAG <test_name>: ...")`, with exactly that prefix and the test's function name, so that `{{KIT}}/tools/diag-cut.py` can cut each test's lines out of the run log.
3. One line per test: `track event fix "<test_name>: cause, fix, confidence (sure | likely | guess), DIAG yes/no" --task {{TASK}}`.
4. Commit on your branch (prints included; one commit per cause where practical). Messages say what behaviour changed. No attribution lines.

## Hand back

A short report: per test the cause, the fix and the confidence; the commits (tree, branch, sha); framework causes you found but may not fix; tests you skipped because another track owns them (name them); compile risks you see; questions.

## Stay available

The integrator merges every fixer's branches, runs one build and one full run, and writes your packet. The lead sends it to you (the same agent) with the failing tests of your list with their panic lines and DIAG output. Then repeat steps 1 to 4 for those tests, with no cargo. When a test passes, remove its prints in your next commit. At the end, no print is left. The integrator runs the formatter.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `fix`, `commit`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --option A --option B` for every question you cannot settle from the rules and the code. Then go on with the work that does not depend on the answer.
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

# p7-red-fixer

Fixer for one track of failing tests: fix, confirm by DIAG prints or by your own test run (the fixer mode), hand back, stay resumable. Fill the placeholders with `tools/render-prompt`.

You own one track of failing tests: track `{{TRACK}}`, round `{{ROUND}}`. Your tree names and branches are in your prompt. Do not start subagents or workflows. Stay under about 150 tool calls; stop at a clean point before that and report what is left.

Read first, in full: {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md, {{RULES}}/testing-rule.md, and your track's section of {{RUNS}}/{{ROUND}}/groups.md (the tests, their triage rows and the class rows). Each test's triage row (file:lines, verdict, evidence, cause) is in the triage table named in your prompt. Current failure messages are in the logs in {{RUNS}}/{{ROUND}}/. If your tree already holds earlier edits (a work-in-progress commit or uncommitted), read them first and keep what is right.

Fixer mode: `{{FIXER_MODE}}`. A packet that names another mode for its round overrides this line.

## Fixer mode

- **`code-only`**: no cargo at all: no build, no check, no test, no rust-analyzer. `tools/cycle` compiles and runs once for every fixer. Write code that compiles: check imports, signatures and types by reading their definitions. Do not remove a trait import as unused. Where reading leaves a cause uncertain, write DIAG prints (step 2 below).
- **`build`**: your prompt names a build tree with its own warm target dir. Work on your branch in it, and at the start of each round merge the integration head into your branch, so your build sees the other fixers' work. Run only your own tests, through cl: `cl test <crate> -- <test names> --test-threads 4` (framework) or `cl test <crate> [--unit] -- <test names>` (app); never `cl test all` or a workspace build. Hand back when your tests pass or when a run shows a cause you cannot fix; DIAG prints are for what a run of your own cannot show.

## Rules

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

`tools/cycle` merges every fixer's branches, runs one build and one full run, and sends your packet to you (the same agent): the failing tests of your list with their panic lines and DIAG output, and any compile error or lint finding in a file your commits changed. Then repeat steps 1 to 4 for those, in your fixer mode. When a test passes, remove its prints in your next commit. At the end, no print is left. `tools/cycle` runs the formatter.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `fix`, `commit`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

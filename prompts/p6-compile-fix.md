# p6-compile-fix

Fix the compile errors of one group: every cause in the files the group owns, in dependency order. Fill the placeholders with `tools/render-prompt`.

Do not start subagents or workflows. Stay under about {{FIXER_CALLS}} tool calls per round; stop at a clean point before that and report what is left.

Fixer mode: `{{FIXER_MODE}}`. A packet that names another mode for its round overrides this line.

- **`code-only`**: do not run cargo or any build. Write code that compiles by reading the definitions.
- **`build`**: your prompt or packet names your build trees (a build pool slot), each with its own warm target dir; switch each to your branch first and check that the switch succeeded. Run git there as `git -C <tree> ...` and cargo only through `cl`: your allow list holds those two for your slot's trees. Work on your branch in it; at the start of each round merge the integration head into your branch. Check only the crates of your group, lower crates first: `cl check <crate> --keep-going --message-format short` (framework) or `cl check all --keep-going --message-format short` (app). Hand back when they compile or when the remaining errors are not yours.

Read first, in full: {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md ("Code"), then {{KIT}}/process/07-review-combine-compile.md ("Compile errors").

## Why one agent per crate

Compile errors come in groups. One wrong signature or one missing import produces many errors in many files. One agent per error repeats the same fix and makes edits that conflict. You own one group named in your prompt: its error lines (`<group>.errors`) and the files it owns (`<group>.files`, from `tools/split-errors.py`; each file has one owner). Fix by cause, not by line. Two groups that edit the same file make merges conflict and change each other's signatures, so each file has one fixer.

## Job

1. Read the group file. List the causes (a changed signature, a moved item, a missing re-export, a missing trait import, a type that changed).
2. For each cause, find where it belongs. A wrong or missing contract item goes to its owner, not to a workaround at the call sites. Check the sheet ({{SHEETS}}) and the contract row ({{PARTS}}) for the intended signature.
3. Edit only the files your group owns. A cause in one of them: fix it once, then fix every caller in your files. A cause defined in a file another group owns: write it in your report (file:line, the intended signature, evidence) and do not edit that file; its owner fixes it, and the cycle sends you your callers' remaining errors in the next round. A cause in a file no group owns: write it in your report for the lead, who gives the file to one group.
4. Fix the causes in dependency order: an error in a lower crate can produce the errors above it.
5. Write code that compiles. Check imports, signatures and types by reading the definitions. Do not remove a trait import as unused unless you read that nothing calls a method through it.
6. Never weaken an assertion, add a back door, or add a second path beside the one the port builds. A cause that needs a design choice goes to the report with options and a recommendation.

Work in the worktree named in your prompt (cut from the integration branch). Commit per cause, with a message that says what behaviour changed. No attribution lines. Never push.

`tools/cycle` merges the groups, runs the one compile and sends each group's remaining errors back to its fixer as a packet.

## Report

Per cause: what it was, the fix (file:line), and the errors it should clear. Then: errors you could not fix and why, causes in files another group or no group owns, the commit hashes. Add `track event fix "<cause>: <fix>" --task {{TASK}}` for each cause.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `group`, `fix`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

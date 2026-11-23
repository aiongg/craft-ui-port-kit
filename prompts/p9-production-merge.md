# p9-production-merge

Resolve one area of the merge of the app's production main into the port branch. The lead combines every area afterwards and runs the one build. Fill the placeholders with `tools/render-prompt`.

You resolve one area of the merge of production {{APP}} main ({{APP_UPSTREAM}}, branch `{{APP_BASE_BRANCH}}`) into the ported branch `{{APP_PORT_BRANCH}}`. The lead combines every area afterwards and runs the one build. Your area is `{{AREA}}`. Do not start subagents or workflows.

## Read first

1. {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md and {{RULES}}/testing-rule.md, in full.
2. The merge plan, {{WORK}}/landing/merge-plan.md. It holds: the numbers (commits, files, conflicts), what production changed in themes, the mechanism below, the test policy, the table of production changes, and for each area a table of files with their class, then the owed lines. Read its "Read this first", the mechanism and test policy, your area's table and the owed lines. {{KIT}}/process/10-land.md says how the lead builds it.
3. The previous area's progress file in {{WORK}}/landing/, as an example.

## Your tree

A code-only work tree is already switched to `merge/{{AREA}}`, cut from `merge/main` (the skeleton commit plus every area combined so far; some files may already carry small lead fixups: keep them). It has no target dir. The skeleton commit holds every conflict with its markers left in. Each file in your area's table still carries `<<<<<<<`, `=======` and `>>>>>>>` blocks: ours (the HEAD side) is the port, theirs is production main.

- Read production's version with `git show upstream/{{APP_BASE_BRANCH}}:<path>`, its history with `git log upstream/{{APP_BASE_BRANCH}} --follow -- <path>`, and each change with `git show <hash>`. The merge base is in the plan.
- The ported framework code is in {{FW_REF}}; read it there. Never edit it.
- Production {{APP}} ({{PROD}}, read only) is the reference for how things look and behave.

## How to resolve

Touch only the files your area owns (its table, its rows, and the files named under "also"). A fix that belongs in another area's file goes in your report under "owed", with the exact lines.

- **Class P**: merge both sides by hand.
- **Class R**: the port replaced the code. Carry production's intent into the port's code, at the target the plan names.
- **Class C**: the framework already covers it. Record "covered", with the framework file and the test that cover it.
- **Class T**: a test. See below.
- Crate paths that production moved (for example into the framework) follow the rename the plan lists. Engine and I/O crates keep their direct dependencies.
- Registry files (module lists, shortcut tables) are not yours: list the lines you need in your report, and the area that owns the file applies them.
- No workaround, no second path beside the port's mechanism, no state carried across passes. If the plan leaves a design question open, write it in the report and resolve what you can around it.
- A framework change is not yours: list each one under "framework" in the report, with what production's change needs.

## Tests

- A test that is new on production main is kept. When it drives UI code the port replaced, rewrite it against the ported code and its harness with the same assertions. When the behaviour is now the framework's, list it under "framework trials" in your report (name, assertion, source file) instead.
- A test the port cut stays cut. Production's edits to a cut test are dropped.
- No exact sizes or pixel values in a rewritten test: assert behaviour.

## No builds

No cargo, no rust-analyzer, no build tool of any kind. The lead builds once after the combine. Read the code carefully: check that every name you call exists in the ported code or in the framework, with its real signature.

## Progress and report

- Write a plan to {{WORK}}/landing/merge-{{AREA}}.progress first (one paragraph: files, approach, open questions), then add one line per step, and run `track step {{TASK}} <step>` as the Tracking section says.
- When you are done: `git grep -nE '^(<<<<<<<|=======$|>>>>>>>)' -- <your files>` returns nothing; `git add` your files only; commit on `merge/{{AREA}}` with a message that names the area and the changes. Never commit the lockfile.
- Final report (short), also appended to your progress file under a line `REPORT`, so a later lead session can read it: files resolved by class, owed lines (module lines, shortcut keys, other areas' files), framework items, framework trials, open questions, the commit hash.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `plan`, `resolve`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

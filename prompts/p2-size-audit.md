# p2-size-audit

Opus: audit the planned lines to write against the code the port replaces. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.
The consolidated plan: {{PLAN}}/contract.md, {{OWNERSHIP}}, {{PLAN}}/sizing.md. You did not write it.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the output file named below. Do not start subagents or workflows.

## Job

1. Split the planned lines to write into: framework additions, code moved between crates (counted once), app production code, rewritten tests, new tests.
2. List every app set that writes more than about half of what it deletes. Read its plan and the code it replaces. Say whether the rewrite is needed, with the reason, or what a smaller plan would be: a call-site swap onto the framework component, a deletion, a test deleted instead of rewritten.
3. Do the same for framework sets whose additions duplicate an existing framework mechanism.

## Output

Write {{PLAN}}/eval-size.md: the split (table), the per-set findings, and the total the plan would have after your proposed cuts. Return the split and the proposed total.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `split`, `audit`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

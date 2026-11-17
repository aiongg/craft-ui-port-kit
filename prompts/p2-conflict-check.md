# p2-conflict-check

Opus: find and settle conflicts across all area plans. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.
Area plans: {{PLAN}}/areas/<area>.md for every area. Chunk plans with their evidence: {{PLAN}}/chunks/<chunk>/{plan.md,questions.json,answers/}.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the output files named below. Do not start subagents or workflows.

## Job

The conflict check runs over the whole plan. Find and resolve:

- two areas changing the same framework item differently;
- a call to an API that no contract defines;
- a framework item that is used and never written;
- a file with two owners. Files that several areas claim (the app's host glue: its frame, framework-bridge, state and library root files) get one hub set that applies every area's listed requests;
- a removed mechanism that a plan still uses;
- a test verdict that contradicts another area's planned behaviour;
- files that changed in the app since the plan base ({{APP_PLAN_BASE}}) and that a plan treats as unchanged: name them and the sets that must read the new version;
- a plan that breaks a rule in {{RULES}}/porting-rules.md or {{RULES}}/framework-decisions.md: one mechanism per concept, framework signals, no state carried between passes beyond the listed exceptions, one arrangement per component in every theme and density, no component-specific theme values, a mechanism added without removing the one it replaces.

Settle each conflict the rules decide, and say how.

Open design questions from all areas: settle every one that the rules, the maps, production behaviour or earlier answers decide, with the reason. The developer is asked only about goals, design principles and architecture, never layout or product detail.

## Output

- {{PLAN}}/conflicts.md: each conflict as where, what, resolution (or "open").
- {{PLAN}}/developer-questions.md: only the questions left for the developer, each in plain words with options and a recommendation.
- {{SETTLED}}: every question you settled, in the format of {{KIT}}/templates/settled.md.

Return a short summary: conflicts resolved and open, questions settled, and the developer questions in one line each.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `check`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --option A --option B` for every question you cannot settle from the rules and the code. Then go on with the work that does not depend on the answer.
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

# precheck

Find the design questions that a task's agent would stop on at its plan step, so the lead answers them before the agent starts. Fill the placeholders with `tools/render-prompt`.

Goal: find the open design questions in a task's brief that its agent would otherwise stop on at its plan step, so the lead answers them first. Typical causes: the task order is wrong, a framework piece nobody planned, an unclear scope, a framework look class, a command with no instance in the app yet.

Read-only: no edits outside your output file, no builds, no cargo. Do not start subagents or workflows. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md first.

For each task you are given (a task id, and its brief or its sheet: {{SHEETS}}/<set>.md for a writer set, or {{WORK}}/briefs/<task>.md for a one-off task):

1. Read the brief or sheet: map entries, app files, framework parts, done-when, dependencies.
2. Check it against the code, read only. The app is {{APP_REF}} (the port branch head), the framework is {{FW_REF}}; read files with `git show <branch>:<path>` or `git grep` against the branch. Ask:
   - Does every framework part the brief names exist, with what the task needs?
   - Does the order of dependencies hold? Does the task need something that a later task builds?
   - Is the scope clear: what moves, what stays, what is deleted, which tests?
   - Do the states for the old and new captures exist?
   - Is anything that the framework mechanism assumes (scopes, instances, hosts) missing in the app?
3. Write {{OUT}}: either "No open questions" with one line why, or each question with: what is missing or contradictory (file:line on both sides), the options, and your recommended answer by {{RULES}}/porting-rules.md (no workaround or app shim that a later task replaces; one mechanism per concept; a missing shared part goes into the framework; production is the stronger look reference).

Keep the file short: questions only, no restating of the brief. Final reply: one line per task with its id, the number of questions, and the gist of each.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `check`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

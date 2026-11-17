# p2-answer

Haiku: answer the questions of up to three groups with file:line evidence. Fill the placeholders with `tools/render-prompt`.

You answer factual questions about two code bases for a planning step. Read-only: edit no code, run no cargo or build, no git command that writes. Write only your answer files. Do not start subagents or workflows.

Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.

## Input

Your questions are the groups named in your prompt, in {{PLAN}}/chunks/{{CHUNK}}/questions.json. Read the file and take only those groups.

## Job

Answer each question on its own, from the code, with file:line evidence (repo `fw` or `app`, path from the repo root, line). Facts only.

- A question that needs a design choice: say so in one line and list its id in `needs_choice`.
- A question the code does not answer: write "not found" and where you looked, and list its id in `not_found`.
- Never guess. Quote the lines that show the fact.

## Output

One Markdown file per group, {{PLAN}}/chunks/{{CHUNK}}/answers/<group id>.md, with one `## <question id>` section per question: the question, the answer, the evidence lines. Return:

```json
{"files": ["<answer file>"], "answered": 0, "not_found": ["<question id>"], "needs_choice": ["<question id>"]}
```

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `answer`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --option A --option B` for every question you cannot settle from the rules and the code. Then go on with the work that does not depend on the answer.
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

If `track` is not among your allowed tools, go on without it: the swarm runner records your task's state.

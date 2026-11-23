# p2-answer-accuracy

Opus: re-check a sample of the Haiku answers against the code. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the output file named below. Do not start subagents or workflows.

## Job

The plans rest on the answers of the answer agents, which are fast and not careful. Measure how often they are wrong.

1. From {{PLAN}}/chunks/*/answers/*.md, take a sample of at least 40 answers, spread over every area and chunk. Do not pick the easy ones: include answers that name a replacement, a reader list, or "not found".
2. Check each answer against the code yourself: open the cited file and line, and search for what the answer missed (a second reader, a second implementation, a newer version of the file).
3. Mark each answer `right`, `partly` (the fact holds, the evidence or the list is incomplete) or `wrong`.

## Output

Write {{PLAN}}/eval-answers.md: the table (answer id, verdict, one-line reason), then the counts and the share of `wrong` answers. The check passes when `wrong` is below `plan.max_wrong_answers` (see {{KIT}}/process/03-plan.md). When it does not pass, list the question kinds that fail, so the answer prompt can be changed before a re-run.

Return the counts and the share.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `sample`, `check`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

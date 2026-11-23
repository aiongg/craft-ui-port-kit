# p2-questions

Opus: split one chunk of the plan into small, checkable questions for the answer agents. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the output file named below. Do not start subagents or workflows.

## Input

Chunk `{{CHUNK}}`. {{PLAN}}/chunks.json names its area map, the line range of its whole sections and the lines of the map's preamble. Read those sections, the preamble, the rows for these sections in the map index ({{MAPS}}/README.md, section 1) and the index rows (shared gaps, hooks) they depend on. Lead answers already given are in {{PLAN}}/answers/.

## Job

Split the chunk into small questions that a Haiku agent can answer from the code alone, with file:line evidence. Kinds of question:

- Which framework call or component replaces the app's X?
- Does framework component C already have prop or behaviour P?
- Which app files call or read Z? Ask this for every reader of a mechanism the port replaces.
- What does production do on input Y?
- Which code does test T reach, and what does it exercise?
- What does a finished task's report leave open?

Cover everything an integrator needs to write the chunk's framework API contract, the per-file plan for every app file the sections touch, and a verdict for every test the sections list. No question may ask for a choice. Choices go in `choices` for the integrator.

Group the questions: 4 to 8 related questions per group, inside one section and one repo where possible. Each question says where to look (repo `fw` or `app`, paths, symbols). Ids: group `{{CHUNK}}-g<n>`, numbered from 1 with no gaps; question `<group id>-q<n>`.

Read enough code yourself to ask precise questions, and leave the answering to the swarm.

## Output

Write {{PLAN}}/chunks/{{CHUNK}}/questions.json (create the directory) and return the same JSON:

```json
{"groups": [{"id": "<chunk>-g1", "section": "<map section id>",
             "questions": [{"id": "<chunk>-g1-q1", "q": "<question>", "look_in": "<repo, paths, symbols>"}]}],
 "choices": [{"section": "<map section id>", "choice": "<design choice left to the integrator>"}]}
```

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `split`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

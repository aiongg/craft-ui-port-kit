# p2-chunk-plan

Opus: plan one chunk: contract, per-file plan, test verdicts, writer sets. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the plan file named below. Do not start subagents or workflows.

## Input

Chunk `{{CHUNK}}`: its map sections as {{PLAN}}/chunks.json lists them. Read:

- those sections and the map's preamble;
- {{PLAN}}/chunks/{{CHUNK}}/questions.json (its `choices` are left for you);
- every answer file in {{PLAN}}/chunks/{{CHUNK}}/answers/;
- {{RULES}}/testing-rule.md (the verdicts);
- {{RULES}}/framework-decisions.md.

The answer agents are fast, not careful. Check yourself every answer your plan rests on, and read further code where an answer is thin or "not found".

## Job

Write {{PLAN}}/chunks/{{CHUNK}}/plan.md with these sections.

1. **Framework API contract.** Every new, changed or removed type, function and prop: crate, file, full signature, one line of behaviour. Build on existing framework mechanisms: one mechanism per concept, framework signals, no per-theme arrangements, no component-specific theme values. An addition names what it replaces, and the removal belongs to the same change.
2. **App files.** Every file the chunk touches: new, rewrite, edit, delete or keep; what it becomes; which framework calls it uses; every reader of a replaced mechanism (from grep), each with its new path.
3. **Framework bodies.** For each new framework file and each changed function, the job of its body in a few lines.
4. **Tests.** Every app test in these sections and every framework test the change affects: keep, rewrite (say how) or delete, each with a one-line reason under the testing rule. App tests are evidence of intended behaviour, not a specification. A kept test that conflicts with the planned behaviour is rewritten to it. New tests only where the rule asks for one.
5. **Writer sets.** Group the files into sets that one writer completes in about 150 tool calls with no build. Each file is in exactly one set. Name each framework file that other chunks will probably change too as shared. Set ids are `{{CHUNK}}-w<n>`. Model per set: `opus` for framework or judgement work, `sonnet` for mechanical ports.
6. **Open design questions.** Only what the rules, the maps and earlier answers leave open. Give the options and your recommendation. Apply the rules yourself where they decide it. Ask no layout or look questions: the production look decides those.
7. **Size per set.** Files, estimated lines to write and to delete. "Write" counts lines added or changed, never kept lines; a file whose kept functions stay is `edit`, not `rewrite`.

## Return

```json
{"plan_file": "<path of plan.md>",
 "api": [{"crate": "", "item": "", "change": "new|changed|removed"}],
 "files": [{"repo": "fw|app", "path": "", "action": "new|rewrite|edit|delete|keep", "set": ""}],
 "sets": [{"id": "", "files": 0, "est_lines_write": 0, "est_lines_delete": 0, "model": "opus|sonnet"}],
 "shared_files": [""],
 "tests": {"keep": 0, "rewrite": 0, "delete": 0},
 "open_questions": [{"id": "", "question": "", "recommendation": ""}]}
```

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `verify`, `write-plan`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --option A --option B` for every question you cannot settle from the rules and the code. Then go on with the work that does not depend on the answer.
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

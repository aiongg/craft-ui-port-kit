# p2-area-merge

Opus: merge the chunk plans of one area into one area plan. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Your only output is the area plan file. Do not start subagents or workflows.

## Input

- The chunk plans of area `{{AREA}}`: {{PLAN}}/chunks/<chunk>/plan.md.
- Their questions and answers, under the same chunk directory, when you need evidence.
- {{RULES}}/testing-rule.md and {{RULES}}/framework-decisions.md.

## Job

Write {{PLAN}}/areas/{{AREA}}.md with these sections.

1. **One framework API contract for the area.**
   - Merge duplicates.
   - Where two chunks change the same item differently, pick one. The rules decide; otherwise choose the design that serves both. Say which chunk plans that changes.
   - Each item gives its crate, file, full signature, behaviour, what it replaces and its writer set.
2. **File ownership.**
   - Every file belongs to exactly one writer set. Merge or move sets that share a file.
   - A set stays within about 150 tool calls with no build. Split a bigger set; merge small ones that share code.
   - Set ids are `{{AREA}}-w<n>`. For each set give its files (repo, path, action), model (`opus` for framework or judgement work, `sonnet` for mechanical ports), lines to write and to delete, the map sections it covers, the contract items it implements and the sets it depends on through the contract.
3. **Test verdict totals**, and every verdict you changed, with the reason.
4. **Open design questions**, merged. Settle each one the rules or the maps settle, and record it. Keep open only what they do not settle, with options and a recommendation.
5. **Shared files.** The framework and app files this area shares with other areas, for the conflict check.
6. **Size.** Sets by model; lines to write and to delete.

## Return

A short summary: number of sets, files, contract items, open questions, and total lines.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `merge`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --option A --option B` for every question you cannot settle from the rules and the code. Then go on with the work that does not depend on the answer.
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

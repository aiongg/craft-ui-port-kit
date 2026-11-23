# p2-consolidate

Opus: write the consolidated contract, ownership and sizing from the area plans. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.
Area plans: {{PLAN}}/areas/<area>.md for every area. Read also {{PLAN}}/conflicts.md and {{SETTLED}} (apply their resolutions) and {{PLAN}}/developer-questions.md (leave those questions open; mark what depends on them).

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the output files named below. Do not start subagents or workflows.

## Job

Write the final plan files.

- {{PLAN}}/contract.md: the one contract, by crate and file, one table row per item in the columns and id format of {{KIT}}/templates/contract-part.md (no bullets: the tools read only table rows whose first cell is an id). It holds every framework item, then, under `### <crate> (app)` headings after the framework crates, every app item that more than one app set uses: constructors, shared view structs, a services or context parameter, the runtime install, the test harness. App ids take the Kind letter `A`. Phase 3 compiles all of these as stubs, so every set codes against its siblings' real signatures.
- {{OWNERSHIP}}: every file to write, in exactly one writer set. Per set: id, repo, files with action, model, estimated lines to write and to delete, the contract items and map sections it implements, the sets it waits on through the contract, and the base it starts from ({{PLAN_BASE}} for the framework, {{APP_PLAN_BASE}} for the app).
  Write it in the format `{{KIT}}/tools/coverage.py --from plan` parses, one block per set; other lines (prose, model, lines, waits on) may follow the `- Repo` line freely:

  ```
  #### panels-w3
  - Repo app
  - Map sections (panels): A1-A4, B2
  - Files:
    - `crates/ui-egui/src/panels/layers.rs` (rewrite)
    - `crates/ui-egui/src/panels/layers_row.rs` (delete)
  ```

  A set that implements another area's sections adds one `- Map sections (<area>): <ids>` line per area. Every file line is indented, the path in backticks, the action in parentheses: `new`, `edit`, `rewrite`, `delete` or `keep`.
- {{PLAN}}/sizing.md: totals (files; lines to write and to delete; crates touched; sets by model; tests kept, rewritten, deleted and new), the sets that depend on an open developer question, and a proposed pilot area for the later phases with the reason.

## Return

```json
{"sets": 0, "files": 0, "contract_items": 0, "write": 0, "delete": 0, "by_model": {"opus": 0, "sonnet": 0}}
```

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `contract`, `ownership`, `sizing`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

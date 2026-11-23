# p2-evaluate-area

Opus: independently evaluate the consolidated plan of one area against the code. Fill the placeholders with `tools/render-prompt`.

You work on the planning phase of the port of {{APP}} to the {{FACADE}} framework. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md in full first.
Code snapshots (read only):
- fw = the framework, {{FW}}, at {{PLAN_BASE}}.
- app = {{APP}}, {{APP_SRC}}, at {{APP_PLAN_BASE}}.
The area maps cite older snapshots: find code by symbol, not by the maps' line numbers. Work already finished or in review is listed in {{STATE}}: plan only what its reports leave open.
The consolidated plan: {{PLAN}}/contract.md, {{OWNERSHIP}}, {{PLAN}}/sizing.md, {{PLAN}}/conflicts.md, {{SETTLED}}. You did not write any of it. Judge it independently against the code, {{RULES}}/porting-rules.md and {{RULES}}/testing-rule.md.

Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the output file named below. Do not start subagents or workflows.

## Job

Evaluate the plan for area `{{AREA}}` ({{PLAN}}/areas/{{AREA}}.md as consolidated). Sample at least 15 contract items and 15 app file plans of this area, spread across its sets, and check each against the code.

- Contract item: does the framework already have it, or something it duplicates? Is the signature consistent with the code it extends (every type, trait, enum variant and icon it names exists, or is itself a contract item)? Does it name and remove what it replaces?
- File plan: does `git grep` over the whole repo (tests, examples, re-exports, other crates, apps) find every reader of each replaced mechanism? Does the plan delete what the port replaces? Is each action derived per file, not copied from a neighbouring row?
- Test verdicts: check 15 against {{RULES}}/testing-rule.md.
- Any break of a rule in {{RULES}}/porting-rules.md.

## Output

Write {{PLAN}}/eval-{{AREA}}.md:

1. A table of every item checked: item, verdict (`right`, `needs change`, `wrong`), one-line reason.
2. The must-fix list for the plan: one row per change, addressed like a request between parts.
3. The error rate: items that are `needs change` or `wrong`, over items checked, overall and by kind (contract, file, reader, verdict, rule).
4. The error classes: group the `needs change` and `wrong` items by cause. A class is a cause that would recur in items you did not sample (reader lists that miss tests, actions copied across a row, a settled decision that never arrived). For each class: a short name, its kind, how many sampled items it covers, what the error looks like, and how to find every instance across all sheets and contract parts (a `git grep`, or the check to run on each row). The fix round sweeps each class over the whole plan, so a class with a precise `find` fixes far more than its must-fix items.

Write the same result as JSON to {{PLAN}}/eval-{{AREA}}.json, and return that object. Its format is {{KIT}}/templates/eval-result.schema.json; the batch runner rejects a result that does not match it, and `tools/plan-collate.py` rejects each must-fix item that does not:

```json
{"error_rate": 0.12, "checked": 75, "by_kind": {"contract": 0.1, "file": 0.15, "reader": 0.2, "verdict": 0.05, "rule": 0.0},
 "classes": [{"name": "<short name>", "kind": "contract | file | reader | verdict | rule", "count": 4,
              "pattern": "<what the error looks like>", "find": "<grep or per-row check that finds every instance>"}],
 "must_fix": [{"to": "<set id> | contract <id> | unowned", "path": "<file, or empty for a contract row>",
               "kind": "contract | file | reader | verdict | rule", "what": "<the change to the plan>",
               "evidence": "<path:line at the plan base>"}]}
```

Address each must-fix item to whoever changes the plan: the set whose sheet changes (find it in {{OWNERSHIP}} or the sheets), `contract <id>` for a contract row, `unowned` for a file no set owns. The error rate is reported, not a pass mark: the plan gets at most two evaluations, and an area above `plan.max_error_rate` after the second goes to the lead's own read of its classes ({{KIT}}/process/03-plan.md, steps 4 and 8). Judge every item on its own; the rate does not change what you write.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `sample`, `check`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

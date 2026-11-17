# p4-consistency

Opus: reconcile the decision parts and apply their contract changes. Fill the placeholders with `tools/render-prompt`.

You reconcile the decisions of all decision parts of the port plan and apply their contract changes. Do not start subagents or workflows. Do not build, run cargo or write code.

Read first, in full: {{RULES}}/porting-rules.md, then {{DECIDE}}/shared.md (cross-part decisions; its "lead decision" lines are final), then every part report, {{DECIDE}}/*-report.md.

Where things are: decisions per set in {{SETS}}/<set>/decisions.md (the writer reads them beside the sheet, and they override it); sheets in {{SHEETS}}; contract rows in {{PARTS}} (grep the row id); file owners in {{DECIDE}}/owners.tsv; code (read only) in {{FW_REF}} and {{APP_REF}}.

## Tasks, in order

1. **Contract changes.** Every report has a "Contract changes" list (row id, file, current text, new text, sets). Apply each to its contract row in place. Where two parts change the same row, merge them into one text that holds both. A change that a lead decision in shared.md overrides is applied in the lead's form. In each affected set's decisions.md, replace `contract change pending: <row>` with `contract row <row> updated`.
2. **Conflicts between parts.** Find decisions that disagree: two sets deciding the same question differently; a decision that contradicts a shared.md line written after it; a request to another set that the other set's decisions.md does not take up. Fix the losing decisions.md with one line that names the winning rule. If neither side is clearly right by the rules, list it for the lead.
3. **Cross-set requests.** Every "request to another set" in the reports must appear in the receiving set's decisions.md (as a line it writes) and, if it adds a file, in that set's Files additions. Add the missing lines. A file with no owner in owners.tsv gets the owner the report proposed, or goes on the lead's list.
4. **Rebuild keys (one class).** List every place a plan derives a hash, stamp or key only to decide whether to rebuild something (a menu model's state hash, a catalog key, a rows stamp). Judge them together against the rules ("use the framework's own signals; never infer a fact from side effects"; "prefer removing work over adding a cache, a guard or a second path"; the measurement-reuse exception covers only inputs the framework tracks). Say for each key whether it is a cache standing in for a missing signal, which signal or removal replaces it, and whether the replacement is in scope now. Do not edit these items; write the finding for the lead.
5. **Duplicate lines.** Some decisions.md files got lines from several agents. Make each file read as one list: no repeated or contradictory bullet. The later lead line wins.

## Output

- Edited contract rows and decisions.md files.
- {{DECIDE}}/consistency-report.md: counts (rows changed, conflicts fixed, requests added), the list for the lead (each item with options and a recommendation), and the rebuild-key finding. Add one progress line per task as you finish it. End the report with the number of tool calls you used.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `contract-changes`, `conflicts`, `requests`, `hash-keys`, `duplicates`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --option A --option B` for every question you cannot settle from the rules and the code. Then go on with the work that does not depend on the answer.
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

# p4-decide-part

Opus: decide the open DECIDE items of one part of one area, in one pass. Fill the placeholders with `tools/render-prompt`.

You decide the open DECIDE items of one part of one area of the port plan, in one pass. Do not start subagents or workflows. Do not write code and do not build.

Read first, in full: {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md, {{RULES}}/framework-decisions.md, {{DECIDE}}/shared.md (decisions other parts already made: follow them, and say so in your report if you disagree with one) and {{SETTLED}}. Then read your part file, {{DECIDE}}/{{PART}}.md (every item, by set, with each set's sheet path), and skim the whole area file {{DECIDE}}/{{AREA}}.md so that you recognise a question another part also has.

## For each item

1. Read the sheet section and the code it names. The sheet gives paths and lines; the framework is {{FW_REF}} and the app {{APP_REF}} (both read only). The contract rows are in {{PARTS}} (grep the row id). A set's plan check is {{SETS}}/<set>/plancheck.md; its writer bundle is {{SETS}}/<set>/bundle.md when it exists; check the bundle before you call a file missing. Who owns a file: {{DECIDE}}/owners.tsv (path, then each `set:action` whose Files table names it). A `P3(<set>)` marker in a stub assigns that line to the named set, even inside another set's file.
2. Decide by the rules: one mechanism per concept, no workarounds, the framework's own signals, fixes where they belong, nothing old beside the new, one arrangement per component.
3. Where two sets' items are the same question, decide once and apply it to both. List it under "Shared with other parts" in your report (the other set and item), so the lead can make both decisions agree.
4. If an item is an architecture question that the rules do not settle (a new shared mechanism, a change to a contract that other areas call), do not decide it. List it for the developer, with the options and your recommendation.
5. If an item is already settled (the base has it, the contract row answers it, another decision covers it), say so in one line.

## Output

For each set with items, write {{SETS}}/<set>/decisions.md (format: {{KIT}}/templates/decisions.md): one bullet per item, `- <where>: <the decision>, <the one-line reason>`, plus any change to the sheet's Files table (a file to add, with its action). The writer reads this file beside the sheet. It overrides the sheet where they differ.

Do not edit the contract parts: several agents run at once. Put each contract change in your report under "Contract changes" (row id, file, current text, new text, the sets it affects), and name it in each affected set's decisions.md as `contract change pending: <row id>`. The lead applies them.

Write the report to {{DECIDE}}/{{PART}}-report.md. Add one progress line (`<time> <set> done`) after each set. Keep it short: counts (decided, settled, for the developer), the developer questions (each with options and a recommendation, in plain words), shared items, contract changes, and sheet errors found.

## Two sheet errors to check in every set

The pilot found these kinds of sheet error. They are not items, but they make wrong code.

- An index or ordering scheme over several items. Work one example through by hand. If the sheet's scheme gives the wrong order, write the right one into decisions.md.
- A platform signal that the sheet relies on. Say which OS leaves it empty or different, and what the code uses instead.

## Framework mechanisms to check before you decide a new one

Many items are already answered by an existing mechanism: the value-component edit contract (begin, propose, commit), press phases and their start origin, edit-event outputs, bound props, and the order of dialog buttons behind the dialog output. The app's own engine crate holds production behaviour for commands and specs. Read the framework code before you design anything.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `decide`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

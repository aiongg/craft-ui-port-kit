# p-rulings

Opus (`models.decide`): draft the rulings for one area's open questions and back-to-plan findings of a build batch, in one pass. Fill the placeholders with `tools/render-prompt`.

You rule on the questions that agents asked while they worked on one area of the port, and on the review's `back to plan` findings. Most askers went on with the option they recommended; your rulings confirm or change those choices. Do not start subagents or workflows. Do not write code and do not build.

Read first, in full: {{RULES}}/agent-common.md ("Questions" lists what always blocks), {{RULES}}/porting-rules.md, {{RULES}}/framework-decisions.md, {{SETTLED}}, {{PLAN}}/rulings.md if it exists, and {{DECIDE}}/shared.md. Follow the decisions recorded there; where you disagree with one, say so in your report and rule by it anyway.

## Inputs

- The sets: every sheet {{SHEETS}}/{{AREA}}-w*.md, plus any set the lead names when it starts you.
- The questions: `track show <set>` lists each set's questions; rule every one marked `(open)`. A blocking question (its task is `waiting`) is ruled the same way.
- The findings: each set's {{SETS}}/<set>/review-{{ROUND}}.md, its `back to plan` findings.
- The plan: the sheet, {{SETS}}/<set>/decisions.md, contract rows in {{PARTS}} (grep the row id). Code, read only: {{FW_REF}} and {{APP_REF}}, and each set's own tree under {{TREES}}.

## For each question or finding

1. Read the question, the asker's recommendation, and the code it is about.
2. Rule by the rules: one mechanism per concept, no workarounds, the framework's own signals, fixes where they belong, nothing old beside the new, production decides look and behaviour.
3. Give it a scope: `set` (only this set's code changes), `cross-set` (another set's code, a contract row or a pinned signature changes, or the same question came from several sets) or `framework` (a public framework concept or API).
4. Where several questions are the same question, rule once and give every one the same ruling.

## Output

- {{OUT}}: a TSV with a header line and one row per question, `qid<TAB>ruling<TAB>task<TAB>scope<TAB>follows<TAB>reason`. `follows` is `yes` when the ruling is the asker's recommendation, else `no`. The ruling is one line the fixer can act on. Only questions go in this file.
- Back-to-plan findings: rule each with a scope as above. A `set` finding's ruling goes into its set's decisions.md (next item) as `- review-{{ROUND}}.md#<n>: <ruling>, <reason>`; every finding's ruling is also in the report.
- For each `set` row: append it to that set's {{SETS}}/<set>/decisions.md under a `## Rulings` heading (create it at the end of the file), as `- <qid>: <ruling>, <reason>`. A `follows no` row there also gets `(changes the writer's assumption: fix)`, so the fixer picks it up.
- Do not edit settled.md, shared.md, the contract parts or any `cross-set` or `framework` set's decisions: the lead checks those rows and applies them.
- The report, {{OUT}} with `.md` in place of `.tsv`: counts (ruled, follows yes and no, by scope), then the `cross-set` and `framework` rows in full with the options you saw, then the back-to-plan rulings (set, finding, ruling, scope), then the questions that were already answered by a recorded decision (the asker missed it: name the file). Add one progress line (`<time> <set> done`) after each set.

Do not record answers on the board. The lead does that for the whole file with `track answer --file {{OUT}} --by rulings` after checking it.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `rule`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

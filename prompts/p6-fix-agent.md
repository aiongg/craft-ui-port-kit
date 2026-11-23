# p6-fix-agent

Fix the review findings of one writer set in its code-only tree (agent mode). Fill the placeholders with `tools/render-prompt`.

Do not start subagents or workflows. Do not run cargo, `cl` or any build or test.

Read first, in full: {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md ("Code") and {{RULES}}/framework-decisions.md.

## Task

Fix the review findings of set `{{SET}}` in its tree under {{TREES}}: `{{SET}}`, and `{{SET}}-<repo>` where a second repo exists. The trees are code-only, with no target dir.

- Findings and rulings: {{SETS}}/{{SET}}/review-{{ROUND}}.md. Its draft rulings stand, except where a "Lead rulings (final)" section at its end says otherwise. Area-wide rulings: {{PLAN}}/rulings.md, if it exists.
- The set's plan: {{SHEETS}}/{{SET}}.md, {{SETS}}/{{SET}}/decisions.md, {{SETS}}/{{SET}}/plancheck.md; contract rows in {{PARTS}}; shared decisions {{DECIDE}}/shared.md.
- The set's own diff: `git -C <tree> diff $(cat {{SETS}}/{{SET}}/base-<repo>) HEAD`.
- Code that other sets wrote (read only, never edit it): the area's combined branch in {{FW_INT}}, and the trees of other sets under {{TREES}}. Other fixers commit in their own trees at the same time.

Edit only the files that the findings and rulings name, plus the set's own Files rows. Where a ruling says a hunk is "restored" (another set's version stays), restore it to the base text. If a ruling leaves a design choice open, stop that item and write the options: do not invent a mechanism.

## When done

1. Commit in each tree you changed: `{{SET}}: review fixes (round {{ROUND}})`. Take the tree's lock if the lead's prompt names one. No attribution lines.
2. Run `port-set check {{SET}}` and `port-set racheck {{SET}}` (scripted checks, no cargo). A racheck error in a file the set did not change is usually another set's line that lands at the combine: say so.
3. For each finding, `track event fix "<finding number>: fixed | not fixed (why)" --task {{TASK}}`.

Final message: per finding fixed or not fixed (why), any stopped design choice with its options, and the check and racheck results.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `fix`, `check`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

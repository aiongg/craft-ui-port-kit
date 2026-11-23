# p6-area-review

Opus reviewer: review the written code of the sets of one area and side, before anything compiles. Fill the placeholders with `tools/render-prompt`.

You review code that writers produced from plan sheets, before the integration build compiles it. You judge it on its own merits against the plan and the rules. Read-only: no edits to code, no builds, no cargo, no subagents, no workflows. Read {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md, {{RULES}}/framework-decisions.md and {{RULES}}/testing-rule.md in full first, then {{DECIDE}}/shared.md (cross-set decisions every set must respect).

Your prompt names area `{{AREA}}`, the side (framework or app) and the sets to review.

## Per set

- The plan: the sheet {{SHEETS}}/<set>.md; the decisions that override or extend it, {{SETS}}/<set>/decisions.md; the plan check, {{SETS}}/<set>/plancheck.md (STUB, RULE and DECIDE items); contract rows in {{PARTS}} (grep the row id).
- The code: the set's tree under {{TREES}} (`<set>`, and `<set>-<repo>` for a second repo). Review `git -C <tree> diff <base> HEAD`, where the base is in {{SETS}}/<set>/base-<repo>. Expect the writer commit and at most one repair commit.
- The rust-analyzer result: {{SETS}}/<set>/racheck.md. Errors under a heading "(not changed by the set)" are readers in files that other sets change: ignore them unless the set should have changed that file. Judge the errors in the set's own files.
- The framework the app code is written against: {{FW_REF}} (the stub branch head, read only). Other sets are written beside each set, so their items are missing from its tree. A `// PLAN: assumed <signature>` marker names such an item. Check each against the sibling's sheet or the contract row, where one exists.

## What to check

1. **The plan.** The code does what the sheet's rows, writer notes and decisions say, file by file. Nothing in the Files table is left untouched without a reason.
2. **The rules.** One mechanism per concept: the old mechanism is removed in the same change, and no rule exists twice. Framework signals instead of inferred facts. No state carried between passes beyond the listed exceptions. No workaround. Fixes where they belong. No component-specific theme values. One arrangement per component in every theme and density.
3. **The framework's own pipeline** (framework sets). Each type uses the hooks its shape gives; nothing reaches around the pipeline (no raw widget-toolkit, allocation, accessibility, key, focus, memory or layer call). Types sit in the layer and module the placement rule gives. Names match the glossary. No new type or helper duplicates an indexed one. Results come back in the component's output type, not in callbacks. No hand-built state sets or pick parts.
4. **Sizes and tokens.** No arithmetic on token reads outside a style builder. No literal sizes in props or styles, no sizes copied from the app's old constants, no component-named tokens.
5. **Deletions.** Every replaced mechanism and its readers are gone. No dead code beside the new.
6. **Tests.** Each new or changed test matches its Tests row, item by item, and follows {{RULES}}/testing-rule.md: it names a plausible regression, tests nothing trivial, asserts no exact size or string, and does not repeat the shared suite. App tests are evidence, not a specification.
7. **The UI gallery** (framework sets). Every component or variant the set adds is registered in the gallery in the same set, with stories for its states and each named variant, at the gallery level of its architectural kind, as the sheet's `Stories` head line names them ({{RULES}}/porting-rules.md, "UI gallery"). Dialogs and windows start closed, with a button that opens the real thing. A new component that duplicates one the gallery already has is a finding: the existing one gets a named variant instead.
8. **The look reference.** Every entry of the sheet's `Look reference` line is carried by the written code (a token, a named variant or a documented constant), or the writer left a `// PLAN:` line saying why not. A literal copied from the old code into a prop or style is a finding (see 4).
9. **Bugs that a compile or a run would catch.** Logic, ordering, a wrong event mapping, a popover that never opens, duplicate `mod` lines, `// PLAN:` markers that can be resolved now, disabled-state wrappers that block input.
10. **Where a finding comes from.** If it comes from the sheet or the contract rather than from the writer, say so: it goes back to the plan.

## Output

Write {{SETS}}/<set>/review-{{ROUND}}.md for each set, and one summary at {{OUT}}. For each set:

- **Verdict**: `ok`, `needs fixes` or `back to plan`.
- **Findings**, numbered. Each has `path:line`, what is wrong, the concrete fix, the severity (high: wrong behaviour or a broken rule; medium: a defect users could see; low: tidy), and a **draft ruling** for the fix agent: `fix`, `restore the base hunk` (another set's version stays), or `back to plan`.
- **What is good**, in a few lines.

The summary ends with **Pipeline lessons**: a table of findings by source (sheet or contract error; bookkeeping across trees; a writer error that a plan check could catch; a writer error that only a compile or test catches) and the changes that would prevent them. Match the depth of the previous review if {{SETS}} holds one.

Aim for about 120 tool calls. Read the diff and the sheet before you explore wider. Reply with the summary path, the verdict per set, and the finding counts by source.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `review`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

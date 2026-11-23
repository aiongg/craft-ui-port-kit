# p3-contract-stubs-stage

Compile one stage of the contract (a group of framework crates, or the app) as stubs, so writers code against signatures that exist. Fill the placeholders with `tools/render-prompt`.

Do not start subagents or workflows.

You compile one stage of the contract as stubs, so the writers code against signatures that exist. Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md ("Code") first, then {{KIT}}/process/04-contract-stubs.md.

## Where

- Worktree: {{FW_INT}}, branch `{{FW_WRITING_BASE}}`. Earlier stages are already committed there. Work only on this branch. Do not push.
- Contract: {{PARTS}}/*.md. Items are grouped under `### <crate>` then `#### <file>`, with the columns of {{KIT}}/templates/contract-part.md. Stage {{STAGE}} covers only these crates: {{CRATES}}. A crate can appear in two part files: do both.
- Sheets (one per writer set): {{SHEETS}}/<set>.md. Ownership of every file: {{OWNERSHIP}}.
- Line numbers in the contract and sheets are at {{PLAN_BASE}}. The branch can differ by a few lines: find items by name.

## The app stage

When your stage is `app`, the app contract is yours, and these lines replace the matching ones above and under Checks:

- Worktree: {{APP_INT}}, branch `{{APP_WRITING_BASE}}`. Its manifest builds the app against the stubbed framework in {{FW_INT}}; leave the framework tree and the manifest's patch regions alone.
- Your rows are those under `### <crate> (app)` headings in {{PARTS}}/*.md; skip every other row. App line numbers in the contract and sheets are at {{APP_PLAN_BASE}}.
- Broken callers: anywhere in the app, including callers of framework items the earlier stages changed.
- Check: `cl check all` in {{APP_INT}} (the build tool's app mode), once after the stubs and again after the callers, until it passes with no new warning in the app.

## What to write

- **new** item: add it with the exact signature. Function and method bodies are `todo!("<id>")`. A new struct field, enum variant or trait method is added as specified. Where the crate builds that struct or matches that enum (a literal, `Default`, an exhaustive match), add the minimum that compiles (the field's `Default::default()`, a `todo!("<id>")` arm). Every new public item gets a doc comment: the contract's Behaviour text in one or two plain sentences (the crates warn on missing docs).
- **changed** item: change the signature or type exactly as written. Keep the existing body. If the body no longer compiles, make the smallest edit that compiles (bind a new parameter as `let _ = name;`, convert a changed type at the boundary) and mark it `// P3(<writer set>): <id>`. Never replace an existing body with `todo!()`, and never delete existing code.
- **removed** item: leave it in place. Its writer set removes it together with its readers in phase 5.
- Rows for files outside your crates (manifests, workflows, app rows of a framework stage): skip.

## Callers that your changes or earlier stages break

Inside your stage's crates only: make each broken caller compile with the smallest edit, marked `// P3(<set>): <id>`, where `<set>` owns that file ({{OWNERSHIP}}, or grep the sheets for the path). Then check whether a sheet lists the caller: grep the sheets' "Replaced mechanisms and their readers" tables for the path. Record every patched caller in your report with `listed: yes/no`. Do not touch crates of later stages.

## Plan errors

This phase exists to find them. Report them; do not redesign.

- A signature that cannot compile as written (a type that exists nowhere and no contract item creates, a lifetime or trait-bound conflict, an orphan rule). If the fix is obvious and mechanical (a missing import, an elided lifetime made explicit, a path to the right module), write the compiling version and report `plan error (fixed): <id>: what was wrong, what you wrote`. Otherwise leave the item out and report `plan error (open): <id>: why`.
- A broken caller that no sheet lists is a plan gap: report it (`listed: no`).
- Two contract rows that conflict: report them, and write neither.

## Checks

- After each crate of your stage, in the stage's order, run the framework's one-crate check through the build tool in {{KIT}}/process/11-build-loop.md (`cl check <crate>`), and show only the errors and warnings. It must pass with no new warning in your crates. It builds only the crate and its dependencies.
- No tests, no clippy, no doc build, no other cargo command, no workspace-wide build.
- `cargo fmt --all` once at the end (it needs no build).
- Commit once at the end: `Contract stubs: <crates>` (add new files first). No attribution lines.

## Notes

- A `const fn` cannot hold `todo!()`: give it the trivial real body the contract describes, and say so in the report.
- An item behind a non-default feature (outside the crate's feature set from `cl features <crate>`): check it once with that feature.
- Behaviour text that names something that does not exist (for example a method) is a plan error to report even when the signature compiles.
- An item whose signature spans crates: an earlier stage wrote only its own crate's part. {{PLAN}}/stage-carry.md lists the parts your stage owes; write them.
- New items that nothing calls yet may carry `#[allow(dead_code)] // P3(<set>): <id>`. Phase 5 writers remove it.

## Report

Write {{PLAN}}/stage-{{STAGE}}.md, adding one progress line per crate as you go. At the end it holds:

1. Items: counts per crate of written, adapted and left out, and the list of left-out ids.
2. Patched callers: a table `File:line | Item id | Owner set | Listed in a sheet (yes/no)`.
3. Plan errors: fixed and open, one line each.
4. Each `cl check` with its wall time.
5. The commit hash.

Your final message is the same five sections in short form.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `stubs`, `callers`, `check`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

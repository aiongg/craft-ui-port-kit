# p7-test-sweep

Read-only sweep: decide which framework tests stay under the test rule. Fill the placeholders with `tools/render-prompt`.

Snapshot: {{FW}} (read only). Edit nothing, run no cargo, no git command that writes. Do not start subagents or workflows. Use Read and Grep freely: every verdict needs evidence from the code, so expect to read the source of each module you judge.

Read first, in full: {{RULES}}/testing-rule.md (the rule, the list of what to test and not test, and the worked examples) and {{RULES}}/agent-common.md.

## Facts about the shared suite

Check these in the code; do not assume them. The framework builds trials for its components in a shared suite (see the testing module of the ui crate in {{FW}}). A type registered as a **component** gets the shared cases over its stories. A type registered as a **pattern** gets only the pattern trial. So a shared case covers a test only when the type under test, or the component that does the work, is a component. Before you cite a shared case, read its function and check that it checks the same thing the test does, not only the same area.

## Method: start from the code, not the tests

For each file:

1. Find the code the file tests (follow its imports and calls into the crate's src). Note for each type whether it is a component or a pattern.
2. List what in that code could plausibly break unnoticed: the non-obvious rules, with file:line. Skip what you can verify by reading.
3. Map each test to the item it guards. A test that maps to no item, or to an item that another test (in this file, another file, or a shared case that reaches the type) already guards, is `delete`. To claim that another test covers it, find that test (grep) and check that it goes through the same code path.
4. Of several tests that guard one item, keep the one at the user's level.

## Output

Write {{OUT}}, a tab-separated file with a header line:

`file:line	test_name	verdict	evidence`

`verdict` is `keep` or `delete`. Evidence is at most 30 words: for `keep`, the code (file:line) that could break and how; for `delete`, why, naming the covering test or shared case. Every `#[test]` and `#[trial]` in the files below gets one line (`grep -nE '^\s*#\[(test|trial)\]' <file>`). The last line is `# keep N delete M`.

Your files are named in your prompt. Return the TSV's content as your final message. Budget about 100 tool calls.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `judge`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

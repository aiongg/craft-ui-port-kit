# p7-failing-test-triage

Read-only triage of failing app tests: keep, cut, cut-fix or move, judged from the body, the code and production. Fill the placeholders with `tools/render-prompt`.

Do not start subagents or workflows. Read-only: edit nothing, run no cargo, no git command that writes. Use Read and Grep freely; every verdict needs evidence from the code.

Read first, in full: {{RULES}}/testing-rule.md and {{RULES}}/agent-common.md.

## Trees

- The port (the tests live here): {{APP_INT}}. The framework source it builds against: {{FW_INT}}.
- Production {{APP}}, the reference for behaviour: {{PROD}}. Use this checkout, never an older or stale one.
- Failure output of each test: the logs in {{RUNS}}/{{ROUND}}/ (grep the test name; the panic message follows `---- <name> stdout ----`).

## The rule

{{RULES}}/testing-rule.md holds it. Every test must name the regression it guards: a plausible change to the code that would break something without anyone noticing. A framework component's behaviour (a field's keys, a dialog's buttons, a list's selection) is the framework's to test. An app test of it is a repeat unless it checks the app's own logic on top.

## Verdicts (one per test)

- `keep`: guards a plausible, non-obvious regression in the app's own logic. Name the code (file:line) and how it could break.
- `cut`: the rule says the test goes, and the failure is about the test (its premise, a widget path, an exact label or value, a harness detail), not about a behaviour difference users would see.
- `cut-fix`: the rule says the test goes, but its failure shows a real behaviour difference from production that users would see. Say what differs (production file:line against the port). The behaviour gets fixed; the test still goes.
- `move`: guards framework behaviour that no framework trial covers yet. Grep the framework's tests for one first. Name the framework crate and component.

## Method (required for every test; no shortcuts)

1. Find it: `grep -rn "fn <last path segment>(" <app tree>/crates`. Wrap any command with globs in `bash -c '...'` if your shell expands them differently.
2. Read the whole test body, and the helpers it calls in the same file.
3. Read its failure message in the logs.
4. Read the port code the test drives (the function or handler the assertion depends on).
5. When the failing assertion is about behaviour a user would see, find the same behaviour in production and cite production file:line. That decides `cut` against `cut-fix`, and whether a `keep` failure is a port bug or a stale premise.

A verdict from a test's name, its module, a failure message alone, or another test's pattern is invalid. If you run out of budget, stop and mark the remaining tests `unjudged`. Never guess. Timing assertions (latency or frame-time budgets in milliseconds) break the "no exact values" rule: `cut`, unless the test counts work (runs, passes) instead of timing it.

## Output

Write {{OUT}}, tab-separated, with a header:

`test	file:line-range read	verdict	evidence	failure cause`

Evidence is at most 35 words: the port code (file:line) it guards, or why it goes, and the production file:line when you compared behaviour. Failure cause is at most 15 words: why it fails now (`port bug`, `stale premise` or `harness`). One line per test in your list. The last line is `# keep N cut M cut-fix K move J unjudged U`. Reply with that line and the three worst offenders (test name, one line each on why).

Budget: about 5 tool calls per test, and every row has its own file:line-range read.

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `judge`, `write`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

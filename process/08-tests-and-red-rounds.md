# Phase 7: tests and red rounds

Phase 7 makes the compiled batch pass its tests. Every failing test gets a verdict first (keep, cut, cut-fix or move), judged from its body, the code it drives and production. Then fixers work in **red rounds**: each fixer writes code-only fixes for its whole list, the lead builds every fix together once and runs the tests once, and each fixer gets back the tests of its list that still fail. One build per round serves every fixer, so a round costs the same wall time for one fix as for a hundred.

| | |
|---|---|
| Starts when | The batch compiles ([07-review-combine-compile.md](07-review-combine-compile.md)). |
| Ends when | The exit criteria below hold. |
| Agents | Triage agents on the calibrated model (`models.triage`); Sonnet fixers per track (`models.red_fixer`), Opus for tracks with a framework cause (`models.red_fixer_framework`); one integrator per round if the lead delegates the merge and run (`models.red_integrator`). |
| Builds | One compile and one full run per round, in the integration trees. Fixers never build. |
| Output | Run logs and failure lists under `work.runs`, the triage table, `groups.md` and a report per run, under `work.runs` (`templates/run-report.md`). |

Record the phase: `tools/track phase 7 "tests and red rounds"`.

## Step 1: first full run

Every full app run in this phase has a label, `<batch>-run-<n>` (written `run-<n>` below). The label names the run's directory under `work.runs`, where test-run writes its logs and failure list. test-run numbers the dashboard rounds itself, continuing across batches after the baseline's round 0.

1. Run the framework trials of every crate the batch changed, then the app's first full run, as background tasks: `tools/test-run run-1-fw --fw <crate> [--fw <crate>]...` and `tools/test-run run-1 --app`. The app run builds with `--no-run` first, then runs every test binary; the failing tests go to `<work.runs>/run-1/app.failed`. test-run records the round on the dashboard itself.
2. Compare it with the baseline (`work.baseline_failures`, from [01-setup.md](01-setup.md), step 7) with `tools/compare-runs.py`. A test that failed before the port is never charged to the port.
3. In a framework batch, separate the **expected** failures: tests that fail on a `todo!` stub or an owed line of a set not yet written. Name the owing set for each and leave them out of the rounds; they must pass once that set lands.

## Step 2: calibrate the triage model

Triage and test sweeps judge hundreds of tests. Before the first one, rate the candidate models against a reference, so the sweep runs on the cheapest model that judges well enough (`rules/testing-rule.md`, "Calibrating a model before a sweep"):

1. **Sample.** Pick about 60 tests across crates, areas, test kinds and likely verdicts: some that plainly guard real logic, some that plainly test wiring or exact values, and some hard cases.
2. **Reference.** The lead judges every test in the sample by the same method and output format the prompt asks for (`prompts/p7-failing-test-triage.md`, or `prompts/p7-test-sweep.md` for a framework sweep), with evidence per row.
3. **Candidates.** Run each candidate model (Haiku, Sonnet) on the same sample with the same rendered prompt, as separate jobs.
4. **Compare.** Count agreement with the reference, and read every disagreement. Its direction matters: a reference `cut` judged `keep` costs a fix round on a test that should go; a reference `keep` judged `cut` deletes a test that guards real logic, and nothing notices.
5. **Fix the prompt** where several disagreements share a reason (a rule the prompt states vaguely, a covering suite case the model did not check), and rerun the candidates on a fresh sample.
6. **Pick** the cheapest model with about 90 % agreement or more and no `keep` judged `cut`. Set `models.triage`, and record the result and the reason in `STATE.md` "Decisions".

Calibrate once per port and prompt, not per round. `lessons.md` has the results of one calibration.

## Step 3: triage the failing tests

1. Split the failing tests (expected ones left out) into lists of about 25 to 30 tests, keeping a module's tests together. Each test costs a triage agent about 5 tool calls.
2. Put each list on the board (`tools/track status triage-<n> todo "<k> tests"`), render `prompts/p7-failing-test-triage.md` with `{{ROUND}} = run-<n>`, `{{TASK}}` and `{{OUT}}`, and run the agents as one background batch.
3. Each agent writes a TSV: test, the lines it read, the verdict, evidence (the port code it guards, and production file:line where behaviour was compared), and the failure cause (port bug, stale premise, harness).
4. Merge the TSVs into one triage table, `<work.runs>/triage.tsv`. Rerun any `unjudged` rows.
5. Spot-check it yourself: a sample of each verdict, and every `move` and `cut-fix` row, against the code and production. A verdict taken from a test's name, module or failure message alone is invalid.

| Verdict | Meaning | What the fixer does |
|---|---|---|
| `keep` | Guards a plausible, non-obvious regression in the app's own logic | A port bug: fix the code. A stale premise: rewrite the test to drive the same behaviour through the port's own signals. |
| `cut` | The test rule says it goes, and the failure is about the test, not about behaviour users see | Delete it |
| `cut-fix` | The test goes, but its failure shows a real behaviour difference from production | Fix the behaviour, then delete the test |
| `move` | Guards framework behaviour no framework trial covers | Write it as a framework trial in the crate that owns it (relations, never sizes), then delete the app test |

## Step 4: form the tracks

A **track** is a group of failing tests with one likely cause, given to one fixer.

Tracks are formed from the latest run, `run-<n>`, and their fixers work from it: their prompts get `{{ROUND}} = run-<n>`, and its directory holds the logs, `groups.md` and the packets. The run the round ends with is `run-<n+1>`.

1. `tools/split-failures.py <dir> <N> <logs>` clusters the failures by module or integration-test file and balances whole clusters over N groups, with each failure's panic site and message.
2. Adjust the groups by cause, using the triage table's cause column: tests that share a cause belong to one track, even across modules. A track whose cause is in a framework crate gets the framework fixer model.
3. Write `<work.runs>/run-<n>/groups.md`: one section per track with its tests, their triage rows and the class rows (shared causes) it names.
4. Write a tracks file (one `TRACK_ID TITLE` per line) and put the tracks on the board: `tools/track import tracks <file>`.
5. Give each fixer its own code-only trees (a framework tree and an app tree whose patch points at it) under `work.trees`, on branches `red/<track>`, cut from the integration heads. Name in its prompt which trees it may edit: a fixer that may not edit the framework reports framework causes instead.

## Step 5: run a red round

Each round has four parts. Fixers never run cargo; the lead runs one build and one full run for all of them.

1. **Fixers write.** Start one fixer per track as background tasks (`prompts/p7-red-fixer.md` with `{{TRACK}}`, `{{ROUND}}`, `{{TASK}}`), paced over the quota window. Each fixer, for every test on its list: reads the test, the code it drives and production until it knows the cause, and writes the fix. Where reading leaves the cause uncertain, it writes its best fix and targeted prints, `eprintln!("DIAG <test_name>: ...")`, which the shared run will confirm or refute. It commits (prints included) and hands back with a cause, fix and confidence per test. It posts one `track event fix` line per test.
2. **One build and one run.** When every fixer of the round has handed back, merge their branches, one at a time, into both integration trees. Where two fixers added a mechanism for the same concept, keep the one already on the integration branch and point the other fixer's caller and test at it. Then:
   - `tools/compile-gate run-<n+1>`; fix mechanical compile errors (an import, a path) yourself;
   - `tools/test-run run-<n+1>-fw --fw <crate> [--fw <crate>]...` for the framework trials of every crate a fixer changed;
   - `tools/test-run run-<n+1> --app` for the one full app run;
   - `tools/compare-runs.py run-<n+1> run-<n> --tracks <run-n>/groups.md`: per track, tests fixed, still failing, and new failures with the fixer most likely to have caused each;
   - `tools/diag-cut.py run-<n+1> --tracks <run-n>/groups.md`: one return packet per fixer, holding the still-failing tests of its list, each with its panic line and its `DIAG <test_name>` lines.

   You may give this part to one integrator agent (`prompts/p7-red-integrator.md` with `{{ROUND}} = run-<n+1>`, task `run-<n+1>`), which owns both integration trees until it reports. The integrator also runs `cargo fmt` on the changed crates only, never on vendored code. The packets still go back through you.
3. **Report.** Write `<work.runs>/run-<n+1>/report.md` (`templates/run-report.md`): merges and conflict choices, compile fixes, counts against the previous round, the per-track table, new failures with their attribution, and the build and run times. test-run and compare-runs post the round's counts on the dashboard themselves, and diag-cut links each packet to its track's task. Record the merges: `tools/track event merge "run-<n+1>: <k> fixer branches"`.
4. **Send each packet to the same fixer.** Resume the agent that wrote the fixes, with its packet, never a fresh one: it already knows its tests and its causes ([12-running-agents.md](12-running-agents.md), "Resuming agents"). A new failure goes to the track whose change caused it. Start a fresh agent only when the old one's context is too large, with its report and packet as its brief.

Then the next round starts with part 1, from `run-<n+1>`, for the tests still failing. A fixer removes the prints of each test that passes in its next commit.

**When a track stalls.** If a track's failing count does not fall for two rounds, read its failures and DIAG lines yourself. Rebrief it with what you found, give it the Opus fixer model, or send the cause back to the plan when the failures show a contract error.

## Why fixers never build

The first full rounds of one port showed an app rebuild after a framework change of about 12 minutes, and a full run of 15 to 17 minutes (`costs.md`, phase 7). A fixer that builds and runs for each attempt spends most of its time waiting, and several fixers in one target dir queue behind each other. Writing every fix by reading, and confirming uncertain causes through DIAG prints in one shared run, keeps one build per round for everyone. `lessons.md` has the rounds that led here.

## Exit criteria

- [ ] Every `keep` test passes in the full run.
- [ ] Every `cut` test is deleted; every `cut-fix` behaviour difference is fixed and its test deleted; every `move` test is a framework trial that passes, and the app test is deleted.
- [ ] No new failure against the baseline; every remaining failure is in `work.baseline_failures` or is an expected failure owed by a named set of a later batch.
- [ ] The framework trials of every crate the batch changed pass, and so does the shared suite over every story the batch added.
- [ ] `git grep -n 'DIAG '` returns nothing in either integration tree.
- [ ] `cargo fmt` has run on the changed crates (not on vendored code), and both integration branches are committed.
- [ ] The last round's report is written and the dashboard shows its counts.

Then go to the next build batch: record `tools/track phase 5 "write" --batch <batch>` and follow [06-write.md](06-write.md), "Write order". After the last app batch, record `tools/track phase 8 "look and behaviour"` and go to [09-look-and-behaviour.md](09-look-and-behaviour.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

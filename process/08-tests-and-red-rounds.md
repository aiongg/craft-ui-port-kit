# Phase 7: tests and red rounds

Phase 7 makes the compiled batch pass its tests. Every test already has a verdict from the plan (keep, rewrite, move or delete, in its set's sheet); the **ledger** (`<work.runs>/ledger.tsv`, `tools/test-ledger.py`) holds each test of the baseline with that verdict and its status now. Fixers carry out the plan's verdicts; triage judges only the `keep` tests a fixer marks stale. Fixers work in **red rounds**: each fixer writes fixes for its whole list, one `tools/cycle` run builds every fix together and runs the tests once, and each fixer gets back the tests of its list that still fail. One build per round serves every fixer, so a round costs the same wall time for one fix as for a hundred.

| | |
|---|---|
| Starts when | The batch compiles ([07-review-combine-compile.md](07-review-combine-compile.md)). |
| Ends when | The exit criteria below hold. |
| Agents | Triage agents on the calibrated model (`models.triage`); fixers per track (`models.red_fixer`: Opus in the fixer mode `build`, Sonnet in `code-only`), Opus for tracks with a framework cause (`models.red_fixer_framework`). |
| Builds | One cycle per round in the integration trees (`tools/cycle`). Fixers build only in the fixer mode `build` ([11-build-loop.md](11-build-loop.md), rule 3). |
| Output | Run logs and failure lists, the ledger, the stale list and the triage table, `groups.md` and a report per run, under `work.runs` (`templates/run-report.md`). |

Record the phase: `tools/track phase 7 "tests and red rounds"`.

## Step 1: first full run

Every full app run in this phase has a label, `<batch>-run-<n>` (written `run-<n>` below). The label names the run's directory under `work.runs`, where test-run writes its logs and failure list. test-run numbers the dashboard rounds itself, continuing across batches after the baseline's round 0.

1. The cycle that compiled the batch ran the first full run ([07-review-combine-compile.md](07-review-combine-compile.md), step 6): the framework trials of every crate changed since `plan.base` (`test-run run-1-fw --fw`) and the app's first full run (`test-run run-1 --app`). The app run builds with `--no-run` first, then runs every test binary; the failing tests go to `<work.runs>/run-1/app.failed`. test-run records the round on the dashboard itself. Each run's `compare.md` lists, per test binary, whether it ran, crashed or went missing against the previous run and the baseline, and names every test that disappeared. test-run then rebuilds the ledger and names the tests that left the suite without a `delete` verdict or a passing `move` target: each is a plan gap to settle (a sheet row) or a test to restore, and the land gate refuses them ([10-land.md](10-land.md), "The exit gate"). Exit 2 is a tool failure, never a pass: fix the build loop and run again.
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

## Step 3: triage the tests fixers marked stale

Triage runs between rounds, only for `keep` tests a red fixer marked stale (`tools/test-ledger.py stale`, listed in `<work.runs>/stale.tsv`). A fixer never rewrites or deletes a `keep` test on its own. Tests the plan gave `rewrite`, `move` or `delete` are carried out as the sheet says, with no triage.

1. Split the stale tests not yet in the triage table into lists of about 25 to 30 tests, keeping a module's tests together. Each test costs a triage agent about 5 tool calls.
2. Put each list on the board (`tools/track status triage-<n> todo "<k> tests"`), render `prompts/p7-failing-test-triage.md` with `{{ROUND}} = run-<n>`, `{{TASK}}` and `{{OUT}}`, and run the agents as one background batch.
3. Each agent writes a TSV: test, the lines it read, the verdict, evidence (the port code it guards, and production file:line where behaviour was compared), and the failure cause (port bug, stale premise, harness).
4. Merge the TSVs into one triage table, `<work.runs>/triage.tsv`. Rerun any `unjudged` rows. The ledger reads it: a triage verdict replaces the plan's `keep` (`cut` and `cut-fix` count as `delete`). When a fixer has written a `move` row's framework trial, add its target as a 6th column, `<path> <test fn>`, so the ledger can check that it passes.
5. Spot-check it yourself: a sample of each verdict, and every `move` and `cut-fix` row, against the code and production. A verdict taken from a test's name, module or failure message alone is invalid.
6. The next cycle's packets carry the verdicts to the fixers (`diag-cut.py` reads the ledger).

| Verdict | Meaning | What the fixer does |
|---|---|---|
| `keep` | Guards a plausible, non-obvious regression in the app's own logic | A port bug: fix the code. A stale premise: rewrite the test to drive the same behaviour through the port's own signals. |
| `cut` | The test rule says it goes, and the failure is about the test, not about behaviour users see | Delete it |
| `cut-fix` | The test goes, but its failure shows a real behaviour difference from production | Fix the behaviour, then delete the test |
| `move` | Guards framework behaviour no framework trial covers | Write it as a framework trial in the crate that owns it (relations, never sizes), then delete the app test |

## Step 4: form the tracks

A **track** is a group of failing tests with one likely cause, given to one fixer.

Tracks are formed from the latest run, `run-<n>`, and their fixers work from it: their prompts get `{{ROUND}} = run-<n>`, and its directory holds the logs, `groups.md` and the packets. The run the round ends with is `run-<n+1>`.

1. `tools/split-failures.py <dir> <N> <logs>` clusters the failures by module or integration-test file and balances whole clusters over at least N groups, with each failure's panic site and message. No group holds more than 25 tests (`--max-per-track`): a longer list gives more tracks, not bigger ones, because a fixer works through about `pipeline.fixer_calls` tool calls per round and a larger track does not finish in one. swarm.py gives fixer jobs 1.3 times that many turns.
2. Adjust the groups by cause, using the panic sites and the plan's verdicts: tests that share a cause belong to one track, even across modules. A track whose cause is in a framework crate gets the framework fixer model.
3. Write `<work.runs>/run-<n>/groups.md`: one section per track with its tests, their ledger rows (set, verdict, target) and the class rows (shared causes) it names.
4. Write a tracks file (one `TRACK_ID TITLE` per line) and put the tracks on the board: `tools/track import tracks <file>`.
5. Give each fixer its own trees, on branches `<work.branch_prefix>red/<track>` cut from the integration heads: code-only trees under `work.trees` (a framework tree and an app tree whose patch points at it) in the fixer mode `code-only`, a build pool slot in the mode `build` (`tools/build-pool take <track>`, whose trees go in its prompt; [11-build-loop.md](11-build-loop.md), rule 3). From the first cycle on, the cycle takes and gives back the slots itself and names them in each packet. Name in its prompt which trees it may edit: a fixer that may not edit the framework reports framework causes instead.
6. Write the fixers file of the round: one line per track, `<track>` (its branches are then `<work.branch_prefix>red/<track>`), or `<track> fw:<branch> app:<branch>`.

## Step 5: run a red round

1. **Fixers write.** Start one fixer per track through `tools/swarm.py` (a job list with `"task": "<track>"`, `prompts/p7-red-fixer.md` with `{{TRACK}}`, `{{ROUND}}`, `{{TASK}}`), so later rounds can resume each one, paced over the quota window. Each fixer, for every test on its list: reads the test, the code it drives and production until it knows the cause, and writes the fix. In the fixer mode `code-only`, where reading leaves the cause uncertain, it writes its best fix and targeted prints, `eprintln!("DIAG <test_name>: ...")`, which the shared run confirms or refutes; in the mode `build` it runs its own failing tests in its build tree. It commits and hands back with a cause, fix and confidence per test, and posts one `track event fix` line per test.
2. **One cycle.** When every fixer of the round has handed back, run the round's cycle as a background task:

   ```sh
   tools/cycle <batch>-run-<n+1> --fixers <fixers file> --tracks <work.runs>/run-<n>/groups.md
   ```

   It merges each fixer's branches into both integration trees, compiles, formats the changed crates and commits the result, runs clippy and the doc build on them, runs the framework trials of each fixer's own crates (the crates its merged commits changed, plus any whose trials failed last cycle) and the one full app run, and when both are green the trials of every other crate changed since `plan.base`, compares the run with the last one per track (`compare-runs.py`, written to `tracks.md` in the run dir), cuts one packet per fixer (`diag-cut.py`: its still-failing tests with their panic lines and `DIAG <test_name>` lines, plus compile errors and lint findings in files its commits changed), and sends each packet to the same fixer, resumed through `swarm.py --follow-up` ([12-running-agents.md](12-running-agents.md), "Resuming agents"). It waits until every fixer has handed back or passed `pipeline.followup_timeout_min`, writes `report.md` in the run dir (`templates/run-report.md` has the sections you add by hand), and ends with one summary line. Later cycles take the fixers file and the tracks from the previous cycle, so `tools/cycle <batch>-run-<n+2>` is enough.
3. **Read the cycle's result.** Its summary line and `report.md`: merges, compile, lint, counts against the previous round, new failures with the track most likely to have caused them, stalled fixers and the errors no fixer owns. A merge conflict stops the cycle before the compile (exit 3): resolve it on the integration branch and run the cycle again. Where two fixers added a mechanism for the same concept, keep the one already on the integration branch and point the other fixer's caller and test at it. A new failure goes to the track whose change caused it. The cycle's merge guard has already acted on the clear cases: a fixer whose merges are the likely cause of more newly failing tests (tests that passed in the previous run) than its track fixed has its merges reverted on the integration branches before the cycle records, and its packet lists those tests. Its branch stays as it is; the next cycle skips it until it has new commits, then restores the reverted commits together with the new ones. A revert that conflicts stays merged and is in the report for you. The report's "Red round record" gives the round's models, pass delta and cost ([costs.md](costs.md), "Red rounds by fixer model").
4. **Next round.** The fixers are working on their packets by the time the cycle ends; when they hand back, run the next cycle. A fixer whose context reached `pipeline.follow_up_max_context` gets its packet in a fresh session, with its prompt and its last report (`swarm.py --follow-up` decides; [12-running-agents.md](12-running-agents.md), "Resuming agents"). A fixer removes the prints of each test that passes in its next commit.

**When a track stalls.** If a track's failing count does not fall for two rounds, read its failures and DIAG lines yourself. Rebrief it with what you found, give it the Opus fixer model, or send the cause back to the plan when the failures show a contract error.

## When fixers build

Whether red fixers build is the fixer mode (`pipeline.fixer_mode`), set from the build times phase 0 measured: [11-build-loop.md](11-build-loop.md), rule 3.

## Exit criteria

- [ ] Every `keep` test passes in the full run; every test a fixer marked stale has a triage row.
- [ ] Every test the plan gave `rewrite` passes; every `delete` test is gone; every `move` target passes and its old test is gone. `tools/test-ledger.py --check` passes.
- [ ] Every `cut` test is deleted; every `cut-fix` behaviour difference is fixed and its test deleted; every `move` test is a framework trial that passes, and the app test is deleted.
- [ ] No new failure against the baseline; every remaining failure is in `work.baseline_failures` or is an expected failure owed by a named set of a later batch.
- [ ] The framework trials of every crate the batch changed pass, and so does the shared suite over every story the batch added.
- [ ] `git grep -n 'DIAG '` returns nothing in either integration tree.
- [ ] The last cycle formatted the changed crates (not vendored code) and reports no clippy or doc finding in them; both integration branches are committed.
- [ ] The last round's report is written and the dashboard shows its counts.

Then go to the next build batch: record `tools/track phase 5 "write" --batch <batch>` and follow [06-write.md](06-write.md), "Write order". After the last app batch, record `tools/track phase 8 "look and behaviour"` and go to [09-look-and-behaviour.md](09-look-and-behaviour.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

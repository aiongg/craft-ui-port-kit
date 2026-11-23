# Phase 4: plan check and decisions

Phase 4 finds every choice a writer would otherwise make alone, and makes it before anyone writes. A cheap plan check per set lists what the sheet leaves open. Opus agents decide those items in parts, one consistency pass makes the decisions agree, the stubs gain every item the decisions add, and scripted audits confirm the plan and the stubs match. Writers then start from a base that does not move.

| | |
|---|---|
| Starts when | Every contract item is stubbed and the line references point at the stub head ([04-contract-stubs.md](04-contract-stubs.md)). |
| Ends when | No DECIDE item is open; every decision is in its set's `decisions.md`; the stubs hold every item the decisions name; `port-set audit` reports 0 on all four audits. |
| Agents | Sonnet plan check per set (`models.plancheck`); Opus per decision part of about 35 items (`models.decide`); Opus consistency pass (`models.consistency`); Sonnet for the stub refresh (`models.stubs`). |
| Builds | `cl check` per crate for the stub refresh only. |
| Output | `<work.sets>/<set>/plancheck.md` and `decisions.md`; `<work.decide>/<area>.md`, the part files and reports, `shared.md`, `owners.tsv`, `consistency-report.md`; the refreshed stub head. |

Every set already has a task on the dashboard (`tools/track import sheets`, phase 2 step 8). `port-set` moves a set's task itself: `running` while its plan check runs, `review` when DECIDE items are left, `todo` when none are. Record the phase first: `tools/track phase 4 "plan check and decisions"`.

## The plan check

`port-set plancheck <set>` builds the set's writer bundle (the sheet, its contract rows, the text of its files, the framework definitions it names) and makes one read-only model call against the stubbed code. The model lists only what would make a writer guess, and tags each item:

| Tag | Meaning | What happens to it |
|---|---|---|
| STUB | The base already has what the sheet row asks; the stubs wrote it. | Nothing. The writer uses what is there. |
| RULE | One option follows from the rules, the contract or the sheet itself, and any reader of the rules would pick it. | Nothing. The writer follows the named rule. |
| DECIDE | The options are all defensible, or picking one changes another set's files or the contract. | Decided in step 4 before the set is written. |

Every item must rest on a lookup (Read or grep), never on an unconfirmed guess. Some items are always DECIDE, whatever the model would pick:

- a fallback or second path beside an existing mechanism;
- a hash, cache, guard or flag standing in for a signal that does not exist;
- a visibility or API change made only so a test can reach an item;
- a choice that depends on the shape of another set's item beyond the signature the sheet or contract gives.

When unsure between RULE and DECIDE, the model uses DECIDE. The prompt lives in `tools/port-set` (`tools/port-set.md`, "plancheck"); change it there when the evaluation loop says so.

## Step 1: run an evaluation batch

Never plan-check every set on an untested prompt: a wrong label costs an Opus decision each (false DECIDE) or a writer's guess (a choice hidden as RULE).

1. Pick about 12 sets across every area and both sides, including the sets with the most contract rows and the sets the pilot found hard. Write them to a list file, one set id per line.
2. Run the batch as a background task: `tools/run-batch --plancheck <list>`. It runs `port-set plancheck --shared` for each set, `pipeline.parallel` at a time, and posts one event when it ends.
3. Read every item of every set in the batch yourself and judge the round by the criteria below.
4. Record the round in `<work.decide>/plancheck-eval.md`: counts by tag, DECIDE precision, failures found, cost, and the change made for the next round.

## Step 2: judge the round (the evaluation loop)

| Criterion | How to measure | Pass |
|---|---|---|
| DECIDE precision | For each DECIDE item: are all options defensible, or does one change another set or the contract? Count the real ones. | At least 80 % real |
| STUB and RULE correctness | Spot-check at least one STUB and one RULE item per set against the code in the racheck bases (`racheck.fw_base`, `racheck.app_base`). | No item misstates the code. One that would mislead a writer is a failure to fix before the full run. |
| Misses | Scan the RULE items for hidden choices: fallbacks, hashes and caches, visibility changes, dependence on other sets. Note anything the sheet obviously leaves open that the check did not list. | No hidden choice of the "always DECIDE" kinds |
| Cost | `port-set usage` per set (cost, turns); project the rest of the sets from the mean. | The projection fits the plan's budget |

If a criterion fails, change what caused it (the prompt in port-set, the bundle, the tag definitions), then run a new evaluation batch on fresh sets, plus a rerun of one set from the last round for a direct comparison. Repeat until the results are the best you can get. The lead decides this alone (`rules/lead-rules.md`, "The plan-check eval loop"): it is not a developer question.

Raising precision can lower recall. A rule that pushes items toward RULE can hide real choices inside RULE items, so the misses scan matters as much as the precision count. `lessons.md` shows how three rounds went on one port.

## Step 3: run the full plan check

When a round passes, run every remaining set as a background task: `tools/run-batch --plancheck <all-sets list>`. A set whose `plancheck.md` exists is skipped, so a killed run resumes. Sets checked under an earlier prompt are rerun: move their output aside first (`plancheck-old.md`).

Set `pipeline.quota_command` and `pipeline.quota_cap` before a large run, so the batch holds new jobs near the plan's quota limit instead of failing mid-call. A plan check cut off by a usage limit counts as failed and is rerun.

## Step 4: collect and decide

1. `tools/port-set collect` writes `<work.decide>/<area>.md`: every DECIDE item of every plan check (and every BLOCKED write), by set, with each item's option lines and the set's sheet path.
2. The same command writes `<work.decide>/owners.tsv` from the sheets' Files tables: one line per file, `path<TAB>set:action,...` for every set whose Files table names it. The decision agents, `cross-owner` and `gate-classify.py` read it. Never write it by hand; rerun `port-set collect` after a sheet's Files table changes. A `P3(<set>)` marker in a stub gives that line to the named set, even inside another set's file.
3. Split each area with more than about 35 items into parts, `<work.decide>/<area>-<n>.md`, keeping each set whole in one part.
4. Create `<work.decide>/shared.md`: decisions that apply across parts. It starts empty; you add a line whenever a part's decision should bind the others, marked "lead decision" when it is final.
5. Put one task per part on the board: `tools/track status decide-<part> todo "<n> items"`.
6. **Pilot two parts first.** Render `prompts/p4-decide-part.md` for each (`{{PART}}`, `{{AREA}}`, `{{TASK}}`), start them as background tasks, and read their decisions and reports. Fix the prompt or the inputs from what they got wrong (the part file missing option lines, a bundle path the agents could not find), then run the other parts, a few at a time. Never start every Opus part at once (`rules/lead-rules.md`, "No large Opus bursts").

Each part agent writes `<work.sets>/<set>/decisions.md` for every set with items (`templates/decisions.md`: one bullet per item, the decision and its one-line reason, plus any file to add to the Files table) and a report, `<work.decide>/<part>-report.md`, with counts, developer questions, items shared with other parts, contract changes and sheet errors found. Part agents never edit the contract parts, since several run at once; they list each change in the report and write `contract change pending: <row id>` in the affected `decisions.md`.

## Step 5: questions for the developer

Part agents decide everything the rules settle. An architecture question the rules leave open (a new shared mechanism, a change to a contract that other areas call) comes back in a report with options and a recommendation. Decide every one you can yourself, record it in `shared.md` as a lead decision, and record it on the board: `tools/track event decision "<part>: <decision>" --task decide-<part>`.

Only questions about goals, design principles or architecture go to the developer. Ask each on the board and in chat at once: `tools/track ask decide-<part> "<question>" --option "<A>" --option "<B>" --for developer`. Record the answer with `tools/track answer <qid> "<answer>"` and in `shared.md`. Never hold the other parts for an answer: only the sets that depend on it wait.

## Step 6: consistency pass

After every part has reported, one Opus agent reconciles them (`prompts/p4-consistency.md`, task `consistency`). It runs five tasks in order:

1. Applies every contract change from the reports to its contract row, merging two parts' changes to one row into one text.
2. Fixes decisions that disagree across parts, with one line naming the winning rule; lists the ones neither side clearly wins.
3. Writes every cross-set request into the receiving set's `decisions.md` (and its Files additions).
4. Judges, as one class, every hash, stamp or key a plan derives only to decide whether to rebuild something: a cache standing in for a missing signal, which signal or removal replaces it, and whether that is in scope now.
5. Makes each `decisions.md` read as one list.

Rule on its list for the lead and on the rebuild-key class yourself, write the rulings into the sets' `decisions.md`, and record them with `tools/track event decision`.

## Step 7: refresh the stubs

Every new or changed item that a decision names gets a stub with its full signature now, so no writer codes against an item that is missing from its base.

1. List the items from the consistency report's contract changes and from `decisions.md` lines that add a framework item.
2. Run one stage agent on them (`prompts/p3-contract-stubs-stage.md`, task `stub-refresh`), on the stub branch in the framework integration tree, exactly as a phase 3 stage: `cl check` per crate, one commit.
3. Move the line references to the new stub head: `tools/port-set remap`.
4. Move `racheck.fw_base` to the new head, restart the framework daemon, and rebuild `<work.scip>/fw.sqlite` ([04-contract-stubs.md](04-contract-stubs.md), steps 5 and 6).
5. Rerun the plan check of every set whose sheet a decision changed beyond a line or two (`tools/port-set plancheck <set>`), and decide what it lists.

## Step 8: audits

`tools/port-set audit` runs four scripted checks over every sheet. Each must report 0 before writing starts:

| Audit | What it checks | A finding means |
|---|---|---|
| Stub pins | Every cross-set signature a sheet or decision pins exists in the stubs, with that signature. | A writer would code against an item its base lacks. Stub it (step 7). |
| Story owners | Every component or variant a sheet adds to the framework names its gallery story and a story owner ([rules/porting-rules.md](../rules/porting-rules.md), "UI gallery"). | Add the `Stories` head line to the sheet of the set that adds the component. |
| Decision files | Every file a `decisions.md` adds is in that set's Files table. | Add the row. A file outside the Files table is a file the writer skips. |
| Readers | For every item a sheet changes or removes, every file that uses exactly that item (from the SCIP index) is in the sheet. | Add the file to the sheet's readers and Files table, or to its owner set's. |

`tools/port-set.md` describes each audit's report. Fix the findings in the sheets and contract (a Sonnet sheet fix per set, or by hand when small), then run the audit again. Record the clean run: `tools/track event decision "audits clean"`.

## Exit

- [ ] The evaluation rounds are recorded in `plancheck-eval.md`, and the last round met every criterion.
- [ ] Every set has `plancheck.md`; every DECIDE item is decided in its set's `decisions.md`, settled, or answered by the developer.
- [ ] The consistency report's lead list and the rebuild-key class are ruled on.
- [ ] Every item a decision names is stubbed; `port-set remap` ran on the new stub head; the racheck base and the framework index are on it.
- [ ] `port-set audit` reports 0 on stub pins, story owners, decision files and readers.
- [ ] `STATE.md` records the decisions and developer answers.

Then record `tools/track phase 5 "write"` and go to [06-write.md](06-write.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

# Costs

What each phase cost on the one app ported with this process so far (PhotoCraft), and how to project the cost of a new port from its size. Use these numbers to state a run's cost before launching it, as `rules/lead-rules.md` requires, and to give the developer a projection at the end of phase 2.

## How to read the numbers

- **App:** PhotoCraft, an image editor whose egui UI (one UI crate) made 86 inventory chunks of about 3,000 lines each, ported onto craft-libs `next`.
- **Dollars** are API-equivalent costs from the pipeline's usage log (`work.usage_log`: tokens per call priced at API rates). On a subscription plan they translate to quota, and that mapping was not measured, except where a row says so.
- **Times** are wall times on one Linux workstation with 64 GB of memory. Agent times are per call; batch times are at the parallelism given.
- Phases 1 and 2 ran before the usage log existed, so their cost is given in quota and agent counts.
- Each number is labelled with its phase (the numbering in [00-overview.md](00-overview.md)).

## Per phase

| # | Phase | PhotoCraft measured |
|---|---|---|
| 0 | Setup | First warm app build 12-15 min, target dir about 40 GB. Framework SCIP index about 6 min and 14 GB RAM; its sqlite table about 2 million rows, built in 10 s. |
| 1 | Inventory and map | 92 agents: 86 Haiku chunk readers, 5 Opus area maps, 1 Opus index. 944 inventory entries (661 user-visible, 283 infrastructure) in about 400 map sections; 67 shared framework gaps. The Opus mappers corrected 9 to 19 inventory entries per area. |
| 2 | Plan | 251 sheets (82 framework, 169 app) touching 2,170 files in 40 crates; about 405 contract items (297 changed, 102 new, 6 removed) plus 96 interfaces between app sets. 129,000 lines to write, 229,000 to delete. Plan error rate 21-52 % per area at the first evaluation, 9 % after the fix round (about 2 % outright wrong). Fact answers: 0 of 45 sampled wrong, 6.5-7 % partly right. 101 questions decided by the lead; none needed the developer. Phases 1 and 2 together used about 75 % of one subscription's weekly allowance. |
| 3 | Contract stubs | 8 stages, one Sonnet agent each, in sequence. |
| 4 | Plan check and decisions | Plan check: $0.65 mean per set (249 sets, $163 in all), about 30 s per call. First eval batch: DECIDE precision 81 %, $9.50 for 13 sets. |
| 5 | Write | See "Writing, per set" below. Pilot: 13 sets in 15 min at 6 in parallel. |
| 6 | Review, combine, compile | Pilot review: 72 findings over 18 sets (about 4 per set): 30 % sheet or contract errors, 35 % writer errors a plan check could catch, 25 % only a compile or test run catches, the rest bookkeeping between sets. Review fixes: $0.61 mean per set on Sonnet (181 sets), $3.95 on Opus (5 sets). Framework compile: 0.85 writer errors per 1,000 written lines, all small borrow or move slips. First app batch compile: about 150 errors. |
| 7 | Tests and red rounds | 275 failing of about 12,100 tests at the first full run. Triage of 420 tests: keep 196, cut 166, cut-fix 29, move 28. Failing count per round: 275, 215, 154, 121, 98, 68. Full run 900-1,050 s. App rebuild after a framework change about 12 min; after a UI-only change 40-70 s. |
| 8 | Look and behaviour | One warm old/new capture round about 20 s. |
| 9 | Land | Not measured. |

## Writing, per set (phases 4-6)

From the usage log over all 251 sets: $970 API-equivalent in all, for plan checks, writes, repairs and review fixes.

| Step | Model | Sets | Mean per set | Median per set | Mean wall time per set |
|---|---|---|---|---|---|
| Plan check | Sonnet | 249 | $0.65 | $0.58 | 33 s |
| One-shot write plus repair | Sonnet | 140 | $1.50 | $1.36 | 5 min |
| One-shot write plus repair | Opus | 13 | $3.12 | $2.28 | 5 min |
| Agent-mode write, all rounds | Sonnet | 88 | $2.60 | $2.42 | 10 min |
| Agent-mode write, all rounds | Opus | 23 | $8.59 | $8.16 | 10 min |
| Review fix | Sonnet | 181 | $0.61 | $0.56 | 45 s |
| Review fix | Opus | 5 | $3.95 | $4.01 | 7 min |

Some sets appear in two write rows: a one-shot set that ended BLOCKED was retried in agent mode.

Per call, from the same log: one-shot write $1.08 (Sonnet) and $2.12 (Opus); automatic repair $0.40 (Sonnet); first agent-mode round $2.40 (Sonnet, about 7.5 min) and $6.59 (Opus, about 13.5 min); a continue round $0.72 (Sonnet) and $2.51 (Opus).

## Pilot (phases 5-7, one area)

The panels area ran end to end first: 18 sets (13 framework, 5 app), 7,000 framework lines and 2,400 app lines planned.

| Step | Measured |
|---|---|
| Write | 17 sets with write records: $28.70, $1.69 mean per set including the repair call. |
| Review | Two Opus reviewers; no set needed a rewrite; 72 findings. |
| Fix rounds | Round 1 (review findings, 14 sets) and round 2 (test failures, 7 sets): about $0.85 per set, a few minutes per round. |
| Framework compile | 16 crates; 5 writer errors in 5,900 written lines, fixed by hand in minutes; 4 owed lines; no error pointed at the plan. |
| Tests | First run 1,967 passed, 221 failed: 209 expected (stubs and lines of unwritten sets), 9 writer bugs, 1 plan error, 1 stale test, 1 possibly older than the port. |

## Projecting a new port

1. **Phase 1.** Chunks = UI lines / `plan.chunk_lines`. Agents = chunks (Haiku) + 1 (areas) + one per area + 1 (index), all Opus except the readers. Expect about 11 entries per chunk and 2 to 3 entries per map section.
2. **Phase 2.** Sets scale with map sections: PhotoCraft had about 0.6 sets per map section and about 520 lines to write per set. Phase 2 is the most quota-heavy phase per line: budget most of a subscription week for an app of PhotoCraft's size, and expect one fix round and one re-evaluation.
3. **Phases 4-6, per set.** Plan check about $0.65; write about $1.70 for a Sonnet set (one-shot or agent mode); $3 to $9 for an Opus set; review fix about $0.85 including the test-failure round. Count the Opus sets from the sheets: framework sets that change a shared mechanism (pass, input routing, focus, layout, paint), plus retries.
4. **Wall time of writing.** Sets / `pipeline.parallel` x 5 to 10 min per set. At 6 in parallel, about 35 to 70 sets per hour; the pilot wrote 13 sets in 15 min.
5. **Build passes.** Wall time in phases 6 and 7 follows the number of build passes, not the number of sets: a warm incremental build costs about the same for 20 sets as for 60. Count one compile per batch plus one build and one full run per red round, and expect 5 or 6 red rounds per app batch. Price each pass from this app's own phase 0 timings (warm build, full run).
6. **Compare with the plan's size.** If the plan writes more than about half of what it deletes on the app side, the size audit in phase 2 should have cut it; a near one-to-one rewrite costs as much as the old code did to write.

Give the developer the projection as ranges, with the measured basis next to each number. Measure the pilot and re-project before writing the remaining areas.

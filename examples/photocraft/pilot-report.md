# Panels pilot: results and projection

Basis: the 18 panels sets written through the pipeline (13 framework-side, 5 PhotoCraft-side), their two Opus reviews, the framework compile and the test run on the integration branch `pilot/panels`.

## Results

| Step | Measured |
|---|---|
| Write (Sonnet, one Opus set) | 17 sets with write records: $28.70, mean $1.69 per set including the automatic repair call. 13 sets took 15 min at 6 in parallel. |
| Review (2 Opus reviewers) | No set needed a rewrite. 72 findings, about 4 per set: 30 % sheet or contract errors, 35 % writer errors a plan check could catch, 25 % only a compile or test run catches, the rest bookkeeping between sets. |
| Fix rounds (Sonnet) | Round 1 (review findings, 14 sets) and round 2 (test failures, 7 sets): about $0.85 per set, a few minutes per round. |
| Framework compile | 16 crates. 5 writer errors in 5,900 written lines (about 0.85 per 1,000), all small borrow or move slips that rustc alone reports; fixed by hand in minutes. 4 lines owed by sets not yet written, added as marked integration lines. No error pointed at the plan. |
| Tests | First run: 1,967 passed, 221 failed. Triage: 209 expected (stubs and lines of unwritten sets; 185 of them one duplicate command set that dialogs-w3 deletes), 9 pilot writer bugs, 1 plan error, 1 stale test, 1 possibly pre-existing. After fix round 2, 3 pilot items are left (fix round 3 running). |
| PhotoCraft side | Reviewed and checked by the language server only: it cannot compile until every framework set is written. |

## What changed in the pipeline from the pilot

- The post-write check now warns on the patterns behind real defects (a component output carrying the parent's response, row stamps on keyed rows, extra memory slots beside the gesture slot, modifiers read from the pointer frame), on `// PLAN:` guesses of items the framework already defines, and on decided items missing from the code; it refuses a plan check cut off by a usage limit.
- Edits apply once: a rerun skips blocks already applied.
- Files a decision adds go into the sheet's Files table before writing (the pilot lost edits to files outside it).

## Order of the full run

1. Audits: every pinned cross-set signature is in the stubs; every registered component has a story owner (the triage found 5 without one: `PathsPanel`, `ArrowheadsPopover`, `VectorModeSelect`, `StrokeCells`, `CropPresetList`).
2. Framework-side sets of every area (69): 27 that change shared mechanisms on Opus, 42 on Sonnet. One area at a time: write, one Opus review, fix, combine, compile, tests, fix.
3. PhotoCraft sets (164) once the framework builds, written against the real framework code, with the same steps per area.

## Projection

| Part | Cost | Agent time |
|---|---|---|
| Write 233 remaining sets | about $395 at the pilot's mean; the 27 Opus framework sets cost more per set (not yet measured) | about 4.5 h at 6 in parallel |
| Fix rounds | about $200 | about 1–1.5 h |
| Reviews (one Opus reviewer per area and side) | about 8–12 reviewers, roughly 10 min each | about 1 h if run in parallel |
| Framework compile and tests | small, if the other areas match the pilot (5 slips per 5,900 lines; test failures mostly expected) | measured per area |
| PhotoCraft compile and tests | not measured: the largest open cost | measured after the first PhotoCraft area |

Dollar figures are API-equivalent costs from the pipeline's usage log; the mapping to plan quota is not measured. The weekly usage of the subscription account moved about 2 points during the pilot's writes, two reviews and fix rounds.

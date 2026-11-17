# Phase 1 result and the pilot plan

Phase 1 (planning) of the no-build plan is finished. The pilot starts next.

## Summary

- The plan is 251 writer sheets plus one framework contract. Every map section, every PhotoCraft UI file and every PhotoCraft test has an owner or a verdict (coverage gaps: 0).
- Measured plan error rate: 21-52 % in the first evaluation, 9.0 % after the fix round (about 2 % outright wrong). The 47 must-fix items from that re-evaluation were then fixed, so the current rate is lower; it was not measured again.
- 101 open design questions were decided by the lead from the porting rules and production behaviour. None needed the owner.
- Size: 129 000 lines to write, 229 000 lines to delete.
- Phase 1 used about 75 % of one subscription account's weekly quota.

## Plan error rates

Errors per checked plan statement, from fresh Opus reviewers sampling each area against the code.

| Area | First evaluation | Re-evaluation |
|---|---|---|
| framework | 52 % | 10.6 % |
| panels | 29 % | 8.7 % |
| dialogs | 30 % | 9.8 % |
| top | 30 % | 14 % |
| canvas widgets | 30 % | 5.4 % |
| tools | 21 % | 5.9 % |
| **All** | | **9.0 %** |

The lead's spot check covered three sheets: panels-w1 (dock, framework), panels-w26 (Channels and Swatches, PhotoCraft) and the decision-heavy canvas-widgets-w29. All of their line references and replaced-mechanism readers matched the code, to within a doc comment's offset.

## What the plan is

- **Sheets:** one per writer set. Each lists its files with lines to write and delete, every reader of a mechanism it replaces (found by grep), a verdict for each test, and notes for the writer. Writers work from their sheet alone.
- **Contract:** about 405 framework items (297 changed, 102 new, 6 removed) in 26 crates, plus 96 interfaces between PhotoCraft sets.
- **Checks:** four scripts (contract, ownership, coverage, sizing) report 0 problems.

## Size

| Kind of line | Lines |
|---|---|
| Framework production code, stories, docs | 31 800 |
| Framework new and rewritten tests | 11 300 |
| PhotoCraft production code | 48 400 |
| PhotoCraft rewritten and new tests | 28 900 |
| Code moved between files | 8 700 |
| **Total to write** | **129 100** |
| Total to delete | 229 300 (PhotoCraft 223 600) |

The work is split into 251 sets: 82 framework and 169 PhotoCraft. They touch 2 170 files in 40 crates.

## Model split

- **PhotoCraft:** all 169 sets are written by Sonnet.
- **Framework:** Sonnet by default. Opus is used only for a set that changes a shared mechanism (pass, input routing, focus, layout, paint). 42 framework sets touch ui-contract, ui-canvas or behavior; the lead classifies each one when it launches. In the pilot, 1 of the 13 framework sets is Opus: panels-w4, the wheel and out-of-range signal in ui-contract.
- **Reviews:** one Opus review per area, and Opus retries a set a Sonnet writer failed.
- **Phase 2 stubs:** Sonnet.

## Pilot plan

**Phase 2: contract stubs**, on the framework branch head, in the warm integration worktree.

- 8 sequential stages in crate dependency order, one Sonnet agent each:
  1. base crates and behavior
  2. ui-contract
  3. widgets and panels
  4. canvas and shell
  5. patterns
  6. imaging, color, menu and update
  7. draw, automation, layers and the rest
  8. text and the facade
- Each stage adds the signatures for its crates with `todo!()` bodies and the contract line as the doc comment.
- Each stage also makes its crates compile where an earlier signature change broke a caller. It does this with a minimal edit marked `P3(<set>)`, which that caller's phase 3 writer replaces.
- **Plan check from phase 2:** every caller a stage had to patch is matched against the sheets' reader lists. A caller no sheet lists is a plan gap. A signature that does not compile as written is a plan error, reported rather than redesigned.

**Phase 3: the pilot sets.**

| Part | Sets | Lines to write | How it is checked |
|---|---|---|---|
| Framework | all 13 panels framework sets (w1-w13) | 7 000 | written, reviewed, then compiled against the stubs |
| PhotoCraft | panels-w26 (Channels, Swatches), w31 (swatch library), w37 (properties), w38 (Layer Comps, Styles), w45 (Timeline) | 2 400 | written and reviewed |

- **Why only five PhotoCraft sets:** the other panels PhotoCraft sets call PhotoCraft interfaces from other areas (mostly hub-w1, the app shell). Those cannot compile until those areas are written. The five chosen sets are reviewed on their merits, as the pilot rule says.
- **Review:** one Opus review of all pilot code against the sheets and the porting rules, before anything compiles. A failing review goes back to the plan or the writer.
- **Compile:** a bounded compile-fix of the framework sets. If errors point at the plan, the work stops and the plan is fixed first.

**What the pilot measures:**

- writer wall time and tokens per set and per 1 000 lines
- review findings per set
- plan-caused compile errors per 1 000 lines

Those numbers give the projection for the remaining 233 sets. No time estimate is given before then, because there is no measured writer data yet.

**Agents:** the pilot runs one or two agents at a time and paces its starts to the subscription's usage window.

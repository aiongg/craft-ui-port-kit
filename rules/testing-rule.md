# The testing rule

Which tests a port keeps, writes, moves or deletes, and how an agent decides. Planners apply it to every test a chunk touches (phase 2), writers to every test in their set (phase 5), reviewers to every test a set writes (phase 6), and triage to every failing test (phase 7).

## The rule

Every test names the regression it guards against: a plausible change to the code that would break something without anyone noticing. If no such change comes to mind, the test is not written.

Test:

- Shared mechanisms that many components rely on: the contract pipeline, measuring, focus and key routing, undo grouping, the suite's own checks. Test each once, at the mechanism.
- Logic with real room for mistakes: layout and room sharing, state machines, gesture sequences, geometry, parsing and saving the suite's own file formats.
- A bug that was hard to find, where the fix is not obvious from the code.
- A format or protocol boundary.

Don't test:

- Code you can verify by reading it: a few lines, a single branch, a swap, a clamp, a short loop with no state.
- Wiring: a button runs its command, a key calls a model function, a modifier picks copy instead of move.
- Defaults, getters, mappings.
- What the type system already guarantees.
- Library behaviour: egui, std, serde or any other dependency.
- Exact strings, values or sizes. Assert behaviour as relations (left of, inside, larger than, the same as before).
- Timing budgets in milliseconds. Count the work (runs, passes, rows) instead.
- One test per combination of cases.
- Per-component repeats of what the shared suite already checks on that type.

Keep tests small and fast. One behaviour test beats several per-function tests.

## Where a test goes

- A component gets its own trial only for behaviour that is unique to it and not trivial.
- Check behaviour at the level the user meets it: through the component, not in the helpers it calls. When a user-level test already goes through a helper's code path, the helper's own test goes.
- A framework component's behaviour (a field's keys, a dialog's buttons, a list's selection) is the framework's to test. An app test of it is a repeat, unless it checks the app's own logic on top.
- Framework behaviour that no framework trial covers yet moves into a framework trial, in the crate that owns the component.

## The shared suite

The framework runs shared cases over every registered component's stories: activation, focus, disabled and read-only states, right-to-left layout, pointer hit areas, values, themes, small room, elision and more. A shared case covers a test only when the type under test, or the component that does the work, is registered as a component. A type registered as a pattern gets only the pattern trial, so the component cases never run on it.

The list of cases and the component/pattern split live in the framework's testing kit (craft-libs `crates/ui-contract/src/testing/suite.rs` and its `suite/` modules). Before citing a case as cover, read its function and check that it checks the same thing the test does, not just the same area.

## Verdicts

Each phase uses its own set of verdicts.

**Plans and sheets (phases 2 to 6):**

| Verdict | Meaning | What happens |
|---|---|---|
| `keep` | Guards a plausible regression in code the port keeps | The test stays, updated to the new API where needed |
| `rewrite` | The behaviour must survive, but the test is written against a replaced mechanism or asserts a detail | The set rewrites it to the behaviour, under the same name in the same file, through the new mechanism. A kept test that conflicts with the planned behaviour is rewritten to the planned behaviour |
| `move` | The behaviour must survive in another test: another name or file, here or in another set (a framework trial, a merged table test) | The target set writes the target named in the Reason cell (`to <path> <test fn>`); the test goes |
| `delete` | No plausible regression, or another test or a shared case already guards it | The set deletes it |
| `new` | The rule asks for a test nothing covers yet | The set writes it |

App tests are evidence of intended behaviour, not a specification.

**Test sweeps** (read-only passes over existing tests): `keep` or `delete`, with the same meanings.

**Failing-test triage (phase 7):**

| Verdict | Meaning | What happens |
|---|---|---|
| `keep` | Guards a plausible, non-obvious regression in the app's own logic | The code is fixed until the test passes |
| `cut` | The rule says the test goes, and the failure is about the test (its premise, a widget path, an exact label or value, a harness detail), not a behaviour difference users would see | The test is deleted |
| `cut-fix` | The rule says the test goes, but its failure shows a real behaviour difference from production that users would see | The behaviour is fixed first; then the test is deleted |
| `move` | Guards framework behaviour that no framework trial covers yet | A framework trial is written in the owning crate; then the app test is deleted |

Triage judges only failing `keep` tests that a red fixer marked stale (`tools/test-ledger.py stale`); a test the plan gave another verdict is carried out as the plan says. The ledger (`<work.runs>/ledger.tsv`) holds every test of the baseline with its verdict and its status now.

A test whose verdict was not reached is `unjudged`, never guessed.

## How to judge a test

Start from the code, not the tests.

1. Find the code the test drives: follow its imports and calls into the source. For each type, note whether it is registered as a component or a pattern.
2. List what in that code could plausibly break unnoticed: the non-obvious rules, with file:line. Skip what you can verify by reading.
3. Map each test to the item it guards. A test that maps to no item, or to an item another test (in this file, another file, or a shared case that reaches the type) already guards, goes. To claim that another test covers it, find that test and check that it goes through the same code path.
4. Of several tests guarding one item, keep the one at the user's level.
5. For a failing test whose assertion is about behaviour a user would see, find the same behaviour in production and cite production's file:line. That decides `cut` against `cut-fix`, and whether a `keep` failure is a port bug or a stale premise.

A verdict from a test's name, its module, its failure message alone, or another test's pattern is invalid. Every verdict cites the code it rests on.

## When a correct fix breaks a test

First ask whether the test checks behaviour or an incidental detail (an exact string, a value, which items fit at one width). If it checks a detail, say so in the report and propose deleting it or loosening it to the behaviour; the lead decides. Never weaken an assertion only to make it pass.

## Worked examples

From an earlier calibration of the rule on framework tests:

| Test | Verdict | Why |
|---|---|---|
| `swap_exchanges_width_and_height` (crop bar) | delete | The code is a swap. |
| `a_style_pick_resets_the_numbers` | delete | On a pick the value becomes the style's start: one assignment. |
| `disabled_cells_take_no_input` (crop bar fields) | keep | The fields are a pattern, so the suite's disabled case never runs on them. Whether disabled reaches every cell is checked nowhere else. |
| `keys_move_delete_and_add_stops_one_set_each` (gradient bar) | delete | Keys mapped to model calls: wiring. |
| `a_moved_stop_passes_its_neighbours_and_keeps_its_tag_and_the_selection_index` (stop model) | delete | The editor's drag trial checks the reorder and the selection through the same move function, at the user's level. |
| `a_stop_keeps_its_place_among_stops_at_its_location_unless_it_crossed_them` | keep | Tie order at equal locations depends on the direction of travel: subtle, and nothing else checks it. |
| `wcag_contrast` | keep | Everything else uses the contrast function itself, so a wrong formula would be self-consistent and unnoticed. |
| `a_window_blur_cancels_a_captured_press_once` (pointer core) | delete | The suite's press-cancel case blurs mid-press on every component and checks that nothing acts. |

## Calibrating a model before a sweep

Before a sweep or triage over hundreds of tests, rate the model against a reference: the lead judges a sample of about 60 tests, the candidate model judges the same sample, and the sweep runs on the cheapest model whose verdicts match well enough. `process/08-tests-and-red-rounds.md` gives the steps.

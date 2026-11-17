# PhotoCraft examples

These files are real artifacts from one port: PhotoCraft (a large egui application) moved onto the craft-libs framework. Each is a trimmed copy with machine paths, names, tracker ids and local tool names removed. Read them to see what each process step produces. Do not copy their content into another port: the sets, line numbers and decisions belong to PhotoCraft.

Cross-references inside the files (for example `ownership.md`, `settled decision L-47`, links to other area maps) point to artifacts not shipped here. Line numbers refer to PhotoCraft and framework commits of the snapshot date.

Source kinds: **script output** was written by a kit script; **agent output** was written by an agent from a prompt in this kit; **lead text** was written by the lead session; **log** is a recorded run.

| File | Source kind | Snapshot | What a reader learns |
|---|---|---|---|
| `inventory-chunk-05.json` | agent output (Haiku, one chunk of the inventory) | 2026-11-12 | The inventory entry shape: name, kind, files, entry points, what the user sees, state read and written. Every entry later maps to one area-map section. |
| `port-map-index-excerpt.md` | agent output (Opus index agent) | 2026-11-12 | The head of the map index: the area table, the fit values (`direct`, `needs props`, `missing component`, `app-only`), the first rows of the parts table and the shared framework gaps (`SG-n`). |
| `map-section-panels-F1-G2.md` | agent output (Opus area map) | 2026-11-12 | Two map sections in full (Channels panel, Swatches panel): app code, framework replacement with file and line, gaps, app glue, test verdicts, look-comparison states, size and dependencies. These are the sections behind sheet `panels-w26`. |
| `sheets/panels-w1.md` | agent output (plan sheet, framework side) | 2026-11-15 | A framework set sheet: files with lines to write and delete, the reader of every replaced mechanism, test verdicts, notes for the writer. |
| `sheets/panels-w26.md` | agent output (plan sheet, app side) | 2026-11-14 | The same sheet for an app set that calls framework items by contract id. Follow it from the map sections above to see the end-to-end trace from map to sheet. |
| `sheets/canvas-widgets-w29.md` | agent output (plan sheet) | 2026-11-15 | A decision-heavy sheet: cross-set requests, reader tables for removed mechanisms, and decisions that the plan check settled. |
| `contract-part-excerpt.md` | agent output (contract part) | 2026-11-15 | A few rows of a contract part: id, kind (new, changed, removed), signature, behaviour, what it replaces, writer set, users, source and resolution. |
| `plancheck-and-decisions.md` | agent output (plan check, then decisions) | 2026-11-14 to 2026-11-15 | One set's plan check result (`[STUB]`, `[RULE]`, `[DECIDE]` items with options) next to the decisions file that answers each `DECIDE`, with rulings added from later reviews. |
| `review-excerpt.md` | agent output (Opus area review) | 2026-11-15 | The head of an area review and the section for one set: a verdict, numbered findings with file and line, and what is good. Findings mark the class (writer error, cross-set, back to plan) and severity. |
| `phase1-summary.md` | lead text | 2026-11-14 | The planning result for a large port: coverage, plan error rates per area, size in lines, model split, and the pilot plan. |
| `pilot-report.md` | lead text | 2026-11-14 | Pilot results (cost per set, review findings, compile errors per 1,000 lines, test triage), the pipeline changes it caused, the decided write order and the projection. |
| `write-order.md` | lead text with batch lists | 2026-11-15 | The write order and the batch-list file format: one file of set names per batch and model. It replaces a schedule file. |
| `triage-excerpt.tsv` | agent output (test triage, 20 of 419 rows) | 2026-11-16 | Test verdicts (`keep`, `cut`, `cut-fix`, `move`) with file and line, the evidence, and the cause of the red test. Causes separate harness faults, stale premises and port bugs. |
| `red-round-report.md` | lead text from a log | 2026-11-17 | One round of the red-test loop: merges and conflicts, one small fix, per-track counts against the previous round, newly failing tests and what is still failing. |
| `usage-summary.tsv` | script output (aggregate of the usage log) | 2026-11-15 | Calls, turns, API-equivalent cost and seconds per step and model for the plan check, write, repair, agent-mode writes and review fixes. |
| `look-driver/` | lead code (the phase 8 driver) | 2026-11-13 | A look driver for `tools/look`: PhotoCraft launched headless with its control channel, the startup dialogs it has to dismiss, how a states file's setup, reset, theme and steps reach the app; and the Layers panel's states file with its panel crop. |

Costs are API-equivalent figures from the pipeline's usage log, not billed amounts.

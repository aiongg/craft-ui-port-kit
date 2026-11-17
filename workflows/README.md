# Workflows

Each script here is one batch of agents: it splits the work into agent calls, runs them in parallel with a model per call, and returns a summary. The process documents say when to run each one. Every script reads its input from one JSON file of arguments (`args`) and reads no other file, so the same script runs under two runners.

| Script | Phase | What it does |
|---|---|---|
| `phase1-inventory-map.js` | 1 ([02](../process/02-inventory-and-map.md)) | Inventory chunks, propose areas, map each area, write the index |
| `phase2-part.js` | 2 ([03](../process/03-plan.md), step 2) | Per plan chunk: questions, fact answers, chunk plan |
| `phase2-final.js` | 2 (step 3 and 4) | Per area merge, conflict check, consolidation, independent evaluation |
| `phase2-fix.js` | 2 (step 5) | Fix round: contract parts, set sheets, coverage gaps |
| `phase2-reconcile.js` | 2 (step 6) | Apply requests between parts, rebuild plan files, evaluate again |

## Running a workflow

1. Build the arguments: `tools/render-prompt --workflow-args <name> [--stage S] [--only ID]... --out ARGS.json`. The builder fills the prompts from `port.toml` and the kit, and computes the lists each script needs (chunks, parts, sets). It names the missing input when there is one.
2. Run it as a background task, with `tools/swarm.py workflows/<name>.js --args ARGS.json` (`pipeline.batch_runner = "swarm"`, needs only the `claude` CLI and Node 18 or later), or with the Workflow tool (`"workflow"`). Under swarm, every agent call is a task on the dashboard and the run resumes: rerun the same command after a stop or an edit, and only new or failed calls run (`--fresh` ignores the stored results).
3. Read the returned summary. A failed call is `null` in it and listed under `failed` or `failedMerge`; the summary's `next` says how to rerun it (`--only`). Agents write their own output files. A script never writes files.

State the agent count by model and the projected cost before launching ([costs.md](../process/costs.md), phase 2).

Every agent call in these scripts reports under a board task. The task id is the call's `task` option, and the prompt's `track` calls use the same id, so the dashboard shows one task per call.

## Arguments

All five scripts get the common arguments from `render-prompt`: `workflow`, `stage`, `kit`, the workspace paths (`work`, `inventory`, `maps`, `plan`, `sheets`, `parts`, `sets`, `decide`, `runs`, `state`, `ownership`, `settled`), the snapshots (`fw`, `appSrc`), `planBase`, `appPlanBase`, `models` (the whole `[models]` table), `prompts` (the script's prompts, with the per-call placeholders left for the script to fill), `areas` (the `[[areas]]` tables with their map paths) and `only`. The phase 2 scripts also get `answerGroupsPerAgent`, `maxErrorRate` and `maxWrongAnswers` (the `plan.*` keys). Each script's header comment lists its own arguments; this table lists what the builder adds.

| Script | Added by the builder |
|---|---|
| `phase1-inventory-map.js` | Stage `inventory`: `chunks` (the chunk split) and `chunkSchema`. Stage `areas`: `chunks` and `inventoryList`. Stages `maps` and `index`: `areas` joined with the proposal, and `moves`. |
| `phase2-part.js` | `chunks`: each area map cut at section boundaries into plan chunks of about `plan.chunk_map_lines` lines (`id`, `area`, `map`, `preamble`, `lines`, `sections`, `index_rows`); also written to `<plan>/chunks.json`. A chunk of a framework-only area has `map: null`: its inputs are the lead's list in `<plan>/chunks/<id>/inputs.md`. |
| `phase2-final.js` | `stage`: `all` (default) or `evaluate` (the evaluations alone). |
| `phase2-fix.js` | `fixDir` (`<plan>/fix`); `contract`: one job per contract part; `sheets`: the sets of the ownership file, four to a job; `coverage`: one job per gap list of `eval-coverage.md`. When `<parts>/NN.md` do not exist yet, the builder cuts `<plan>/contract.md` at its `### <crate>` headings into parts of about 120 rows and writes them. |
| `phase2-reconcile.js` | `fixDir`; `partList` (the contract parts on disk); `round` (2 for the first re-evaluation, then the next unused number); stage `evaluate` runs the rebuild and the evaluations only. |

`--only ID` limits a run: chunk ids for `phase2-part`, area ids for `phase2-final` and `phase2-reconcile`, job ids for `phase2-fix`.

## Models and agent counts

Models come from `[models]` in `port.toml`.

| Script | Calls | Model keys |
|---|---|---|
| `phase2-part.js` | per chunk: 1 question split, ceil(groups / `plan.answer_groups_per_agent`) answerers, 1 chunk plan | `questions`, `answers`, `chunk_plan` |
| `phase2-final.js` | per area: 1 merge and 1 evaluation; once: 1 conflict check, 1 consolidation, 1 size audit, 1 answer-accuracy check, 1 coverage run | `area_merge`, `evaluate` (the coverage run uses a small model) |
| `phase2-fix.js` | one per contract part, per group of four sets and per gap list | contract parts `chunk_plan`; sheets and coverage `sheet_fix` |
| `phase2-reconcile.js` | 2 collations, one per contract part with requests, 2 routing jobs, one per group of four sets, 1 rebuild, one evaluation per area | `sheet_fix`, `chunk_plan`, `evaluate` |

## Judgement the scripts leave to the lead

- `phase2-final.js` returns each area's error rate and whether it is at most `plan.max_error_rate`, and the wrong-answer share against `plan.max_wrong_answers`. The lead decides what to fix, and whether to rerun the answers of the chunks concerned at one group per agent.
- `phase2-fix.js` and `phase2-reconcile.js` return open questions as counts. The questions themselves are in the requests and log files; the lead settles them (process/03-plan.md, step 7).

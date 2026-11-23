# Phase 2: plan

Phase 2 turns the port map into a plan that writers can follow with no build and no judgement calls: one framework contract, and one sheet per writer set that names every file, every line range, every reader of a replaced mechanism and every test verdict. The plan is checked against the code by fresh agents before any code is written, because a plan error found at compile time costs a rewrite.

| | |
|---|---|
| Starts when | The lead accepted the maps ([02-inventory-and-map.md](02-inventory-and-map.md)). |
| Ends when | Coverage reports 0 gaps; the re-evaluated plan error rate is at most `plan.max_error_rate`; at most `plan.max_wrong_answers` of the sampled fact answers are wrong; every open question is decided; the sizing report is written. |
| Agents | Opus splits questions, plans chunks, merges areas, checks conflicts and evaluates (`models.questions`, `chunk_plan`, `area_merge`, `evaluate`); Haiku answers facts (`models.answers`); Sonnet fixes sheets (`models.sheet_fix`). |
| Builds | None. Agents read the snapshots at the plan base; scripts check coverage and sizes. |
| Runs | `workflows/phase2-part.js`, `phase2-final.js`, `phase2-fix.js`, `phase2-reconcile.js` (`workflows/README.md` gives each one's args). |

Every run below is started as in phase 1: `tools/render-prompt --workflow-args <workflow> > <args file>`, then `tools/swarm.py workflows/<workflow>.js --args <args file>` (or the Workflow tool), as a background task. Under swarm, every job is a task on the dashboard. State each run's agent count by model and its projected cost before launching it (`costs.md`, phase 2).

## What the plan is

| Artifact | Holds | Read by |
|---|---|---|
| Contract parts (`work.parts/NN.md`) | Every new, changed or removed framework item, grouped by crate and file: Id, Kind, Signature, Behaviour, Replaces, Writer, Also, Used by, Source, Resolution (`templates/contract-part.md`). Ids are `<area code>.<Kind><n>`. | Phase 3 stubs them; writers get their rows |
| Sheets (`work.sheets/<area>-w<n>.md`) | One per writer set: header (repo, model, lines, contract items, waits on), Files table (path, action `new`/`edit`/`rewrite`/`delete`, lines to write and delete, what changes), Replaced mechanisms and their readers, Tests table (each test: `new`, `rewrite`, `keep` or `delete`, with the reason), writer notes with `path:line` evidence (`templates/sheet.md`, the format `port-set` parses) | Writers, reviewers, port-set |
| `ownership.md` | One row per set and the files it owns. Every file the port writes is in exactly one set. | Coverage, gates, the lead |
| `settled.md` | Every design question decided during planning, with the reason (`templates/settled.md`) | Writers, reviewers |
| `sizing.md` | Files, lines to write and delete, crates, sets by model, test verdict totals | The lead and the developer |

A **set** is what one writer completes in about 150 tool calls with no build. Sets are disjoint by file, so their branches combine without merges. Shared framework files get one owner set, which takes requests from the others through the contract.

## Step 1: plan chunks

A **plan chunk** is a run of whole sections of one area map, small enough that one Opus agent can plan it in full (typically 5 to 15 sections). `tools/render-prompt --workflow-args phase2-part` cuts each area map at section boundaries and adds each chunk's map preamble, its rows in the index, and the shared gaps and hooks it depends on.

Add one or more plan chunks for **framework work outside the map**: open framework follow-ups, framework changes the developer wants in the same port, fixes ported from the framework's main branch. Give them their own area (for example `framework-01`, with `repos = ["fw"]` in its `[[areas]]` table and no map file). Such an area becomes one plan chunk, `<area>-01`, with no map section: write its inputs, one item per line with its source, to `work.plan/chunks/<area>-01/inputs.md` before the run, and the planner reads them from there. Each such item is either planned or dropped with a one-line reason; a finding is not a task until it passes the new-task check in `rules/lead-rules.md`.

## Step 2: questions, answers and chunk plans

`phase2-part.js` runs three steps per plan chunk, as a pipeline (a chunk goes on to its next step as soon as it is ready):

1. **Questions** (Opus, `prompts/p2-questions.md`). The chunk is split into small questions a Haiku agent can answer from the code alone with `file:line` evidence: which framework call replaces X; does component C already have prop P; which files read Z (every reader of a mechanism the port replaces); what production does on input Y; what test T exercises. 4 to 8 related questions per group, one section and one repo per group where possible. Anything that needs a choice goes to a separate "choices" list for the planner. Output: `work.plan/chunks/<chunk>/questions.json`.
2. **Answers** (Haiku, `prompts/p2-answer.md`). Each agent takes `plan.answer_groups_per_agent` groups and answers each question on its own: facts only, the lines quoted, `not found` with where it looked, or `needs choice`. Output: one file per group under `chunks/<chunk>/answers/`.
3. **Chunk plan** (Opus, `prompts/p2-chunk-plan.md`). The planner checks every answer its plan rests on and reads more code where an answer is thin. It writes `chunks/<chunk>/plan.md`: the framework contract for the chunk (full signatures, each naming what it replaces); every app file it touches with its action and every reader of a replaced mechanism; the job of each new framework body; a verdict for every test under `rules/testing-rule.md`; writer sets; open questions with options and a recommendation; size per set.

Rules the planners apply: the app's tests are evidence of intended behaviour, not a specification; a test of the kind the testing rule removes (trivial, exact sizes, wiring, implementation detail) is deleted; a kept test that conflicts with the planned behaviour is rewritten to it. An addition names what it replaces, and the replaced thing is removed in the same set.

The UI gallery comes first ([rules/porting-rules.md](../rules/porting-rules.md), "UI gallery"): a planner checks it for a component that already does the job before it plans a new one, and an app variant is a named option on the existing component. A sheet that adds a framework component or variant names its stories in a head line, ``- Stories: `Type`: <story names> in `path/stories.rs` ``, and lists the stories file in its Files table. The set with that line is the type's story owner; the story-owner audit in phase 4 (`port-set audit`) refuses a new component without one.

## Step 3: area merge

One Opus agent per area (`prompts/p2-area-merge.md`) merges the area's chunk plans into `work.plan/areas/<area>.md`:

1. one contract for the area: duplicates merged; where two chunks change the same item differently, the rules decide, otherwise the design that serves both;
2. file ownership: every file in exactly one set; sets that share a file merged or moved; sets split at about 150 tool calls and small ones merged; ids `<area>-w<n>`; per set its files, model (Opus for framework work that needs judgement, Sonnet for mechanical ports), lines, map sections, contract items and the sets it waits on;
3. test verdict totals and any verdict changed, with the reason;
4. open questions, with the ones the rules or the maps settle already settled;
5. files this area shares with other areas, for the conflict check;
6. size by model.

## Step 4: conflict check, consolidation and evaluation

`phase2-final.js` runs three steps over all areas.

**Conflict check** (one Opus pass, `prompts/p2-conflict-check.md`). It finds and settles: two areas changing one item differently; a call to an API no contract defines; an item used but never written; a file with two owners (the app's host glue files usually are: give them one hub set that applies every area's requests); a removed mechanism still used; a test verdict that contradicts another area's behaviour; a plan that breaks a rule. Output: `conflicts.md`, `settled.md` (questions it decided, with the reason) and `developer-questions.md` (only goals, principles and architecture).

**Consolidation** (`prompts/p2-consolidate.md`): the contract, `ownership.md` and `sizing.md`, with the conflict resolutions applied.

**Evaluation**, by agents that wrote none of the plan:

- **Per area** (Opus, `prompts/p2-evaluate-area.md`): a random sample of at least 15 contract items, 15 file plans and 15 test verdicts, each checked against the code. A contract item: does the framework already have it or something it duplicates; does the signature fit the code it extends; does it remove what it replaces. A file plan: does `git grep` find every reader; is the action right. A verdict: is it right under the testing rule. Output: `eval-<area>.md` with every checked item, the must-fix list, and the **error rate** (wrong or needs-change items over items checked).
- **Answer accuracy** (Opus, `prompts/p2-answer-accuracy.md`): a random sample of Haiku answers, fixed before any answer is read, checked against the code. It reports the wrong rate for answers given one group per agent and for batched answers, and by position in the batch. Above `plan.max_wrong_answers`, the chunks concerned are answered again at one group per agent and their plans redone.
- **Size audit** (`prompts/p2-size-audit.md`): the lines to write split into framework additions, code moved between crates (counted once), app production code, rewritten tests and new tests. A port onto framework components should mostly delete: every app set that writes more than about half of what it deletes is checked, and either the rewrite is justified or a smaller plan is named (a call-site swap, a deletion, a test deleted instead of rewritten).
- **Coverage** (script, `tools/coverage.py`): every map section is covered by a set; every `.rs` file under `app.ui_dirs` has an action or a reason it is untouched; every `#[test]` function in those files has a verdict; no file is in two sets.

Expect the first evaluation to fail. Plans made from maps carry errors in a few repeating classes, and the fix round exists for them (`costs.md` has the measured rates).

## Step 5: fix round

`phase2-fix.js` writes the plan in its final form from the evaluation, in parallel jobs that each own their files:

- **Contract parts** (`work.parts/NN.md`, split by crate): every row checked, not a sample. When the parts do not exist yet, `render-prompt --workflow-args phase2-fix` cuts `contract.md` at its `### <crate>` headings into parts of about 120 rows and writes them.
- **Sheets**, one per set (`work.sheets/<set>.md`), in exactly the format `port-set` parses.
- **Coverage gaps**: each unowned file gets an owner set or a grep-backed "no edit" reason.

Each job fixes the **error class** in everything it owns, not only the sampled items (`prompts/p2-fix-round.md` gives the classes to every job):

1. **Row-level actions copied to every file.** A group row's single action (for example `delete`) applied to each file in it. Re-derive each file's action from the chunk plan and the code.
2. **Stale reads.** Plans that read the code at an older commit than the plan base. Re-read everything at the base.
3. **Incomplete reader lists.** Readers in tests, examples, re-exports (`pub(crate) use`), other crates and the app's other directories. Find every reader with `git grep` over the whole repo.
4. **Duplicate or unfounded framework items.** An item that duplicates an existing mechanism, or a signature written without reading the code it extends (types, variants or icons that do not exist).
5. **Decisions that never arrived.** Settled questions and conflict resolutions missing from the contract or the sheets.
6. **Rewrites sized as whole files.** Write counts are lines changed. A file whose kept functions stay is `edit`, so the writer edits in place and never retypes kept code.

Plus the coverage class: tests without a verdict and files without an owner.

Jobs never edit a file another job owns. What another part must change goes into the job's requests file, addressed to a set or a contract part.

## Step 6: reconcile

`phase2-reconcile.js` applies the requests between parts:

1. **Contract and routing:** each contract part applies the requests addressed to it, after checking each against the code (a request can be wrong); routing jobs give every "unowned" path an owner set.
2. **Inbox:** a script collects every request, routing decision and contract change log row per set.
3. **Sheets:** sheet groups apply their inbox, then check that every reader row of the set appears in its Files table, every `#[test]` function of each owned file has one verdict, and the header's line totals match the Files table.
4. **Rebuild and re-evaluate:** `ownership.md`, the joined contract, coverage and sizing are rebuilt from the sheets by script; fresh Opus evaluators sample each area again (at least 20 contract items, file rows, reader rows and test verdicts each) and report the error rate by kind.

If an area is still above `plan.max_error_rate`, fix its must-fix list (a Sonnet sheet fix per set) and re-evaluate that area.

## Step 7: decide the open questions

The lead decides every open question the rules, the code or production behaviour settle, and records each in `settled.md` with its reason (`L-1`, `L-2`, ...). Record a batch of decisions on the dashboard: `tools/track event decision "settled L-<from>..L-<to>"`.

The developer gets only questions about goals, design principles and architecture, never layout or product detail. Ask each one with `tools/track ask plan "<question>" --option "<A>" --option "<B>" --recommend "<A>" --blocking --for developer`, and in chat at the same time; record the answer with `tools/track answer <qid> "<answer>"` wherever it came from. A decision that changes the plan goes through the same contract and sheet fix as a request.

## Step 8: the lead's own check

Before phase 3, read the contract in full and a sample of sheets yourself: at least one framework sheet, one app sheet and the sheet with the most decisions. Check their line references and reader rows against the code. An agent's evaluation or a score is not a substitute.

Then put the sets on the board, so phases 4 to 7 have a task per set from the start: `tools/track import sheets`.

## Step 9: sizing and projection

`sizing.md` gives the developer the size of the port: sets by model, files, lines to write and delete by repo and area, crates touched, test verdict totals. Add a projection for phases 3 to 7 from `costs.md` (cost per set and per call, sets per hour at the batch runner's parallelism), and propose the **pilot**: the shell plus the main-surface section with the most framework gaps, taken from the index's risk ranking ([06-write.md](06-write.md), "Write order").

## Exit

- [ ] `tools/coverage.py` reports 0 gaps.
- [ ] Every area's re-evaluated error rate is at most `plan.max_error_rate`.
- [ ] The sampled wrong-answer rate is at most `plan.max_wrong_answers`.
- [ ] `developer-questions.md` has no open question; `settled.md` holds every decision.
- [ ] The lead's check is recorded in `STATE.md`; every set is on the board.
- [ ] `sizing.md` and the projection went to the developer.

Then record `tools/track phase 3 "contract stubs"` and go to [04-contract-stubs.md](04-contract-stubs.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

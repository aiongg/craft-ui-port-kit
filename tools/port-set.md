# port-set

`tools/port-set` writes one writer set from its sheet with few model calls, and runs the plan-level checks that come before writing. This file is its full spec. The phase docs say when each command runs: plan checks and audits in [process/05-plancheck-decide.md](../process/05-plancheck-decide.md), writing and the batch rules in [process/06-write.md](../process/06-write.md), review fixes in [process/07-review-combine-compile.md](../process/07-review-combine-compile.md).

## Contents

- [Terms](#terms)
- [Command summary](#command-summary)
- [Config](#config)
- [The sheet](#the-sheet)
- [The set dir](#the-set-dir)
- [Writing commands](#writing-commands): tree, bundle, apply, check, racheck, plancheck, run, agent, fix, usage
- [Plan-level commands](#plan-level-commands): validate, audit, remap, collect, status
- [Exit states and the dashboard](#exit-states-and-the-dashboard)
- [Who calls port-set](#who-calls-port-set)

## Terms

| Term | Meaning |
|---|---|
| set | One unit of writing: a sheet, its trees and its set dir. Its id is `<area>-w<n>` (an `[[areas]]` id from port.toml). |
| sheet | The set's plan, `<work.sheets>/<set>.md`, in the format of [templates/sheet.md](../templates/sheet.md). |
| repo | `fw` (the framework) or `app` (the app being ported). A sheet's own repo is its `Repo:` head key. |
| writing base | The branch every set tree starts from: `framework.writing_base` (the contract stubs) and `app.writing_base`. |
| set tree | A code-only git worktree of one repo for one set, on its own branch, with no target dir. |
| base checkout | The read-only checkout of a repo at its writing base (`racheck.fw_base`, `racheck.app_base`). The racheck daemons load it; app writers read the framework there. |
| bundle | One Markdown file holding everything a one-shot writer needs. |
| one-shot | A write in one model call that answers with edit blocks, which the script applies. |
| agent mode | A write by a `claude -p` agent that edits the files itself. |

## Command summary

Options before the command: `--config PATH` (a port.toml; default `PORT_KIT_CONFIG`, `./port.toml`, then the nearest one above) and `--set KEY=VALUE` (overrides one config key; repeatable).

| Command | What it does | Model calls | Writes |
|---|---|---|---|
| `tree SET` | Creates the set's trees, one per repo it writes | 0 | trees, `base-<repo>` |
| `bundle SET [--shared]` | Builds the writer bundle | 0 | `bundle.md` |
| `apply SET EDITS` | Applies an edits file to the set's trees | 0 | `apply.md` |
| `check SET` | Scripted self-check of the set's trees | 0 | `check.md` |
| `racheck SET` | rust-analyzer errors in the files the set committed | 0 | `racheck.md` |
| `plancheck SET [--shared]` | Lists what the sheet leaves open, tagged STUB, RULE or DECIDE | 1 | `plancheck.md` |
| `run SET [--skip-plancheck]` | Plan check, one write call, apply, check, repair calls | 2 to 2 + repairs | edits, `apply.md`, `check.md`, commits |
| `agent SET [--continue]` | Writes (or finishes) the set as an agent with edit tools | 1 | `check.md`, commits |
| `fix SET FINDINGS.md` | One call that fixes review findings on the written set | 1 | edits, `apply.md`, `check.md`, a commit |
| `usage [SET]` | Prints the usage log | 0 | - |
| `validate [--sheets DIR] [--parts DIR]` | Parses every sheet; reports what the writing commands cannot place | 0 | - |
| `audit [SET...] [--only CHECK,...]` | Token-free plan checks; four of them gate writing | 0 | `<work.dir>/audit/` |
| `remap [--dry-run]` | Moves framework line references in sheets and contract parts to the writing base | 0 | sheets, parts, `plan.linebase` |
| `collect` | Open DECIDE items by area, and `owners.tsv` | 0 | `<work.decide>/<area>.md`, `owners.tsv` |
| `status [SET...]` | Each set's stage from its set dir, beside its dashboard task | 0 | dashboard (with `--post`) |

Writing commands take `--model` and `--max-turns`; their defaults come from port.toml when the command runs (below).

Exit status: 0, or 2 for a config error. A command that fails (a model call, a git command) exits non-zero with the reason. `validate` and `audit` exit 1 when they report problems (`audit`: a gating check is not 0), so a script can gate on them. The writing commands exit 0 whatever state the set ends in: read the state from the output, `check.md` or the dashboard.

## Config

port-set reads these keys ([process/config.md](../process/config.md) has every key, its default and its environment variable).

| Key | Used for |
|---|---|
| `work.sheets`, `work.parts`, `work.settled` | Sheets, contract parts, settled questions |
| `work.sets` | Set dirs, `<work.sets>/<set>/` |
| `work.trees` | Set trees: `<trees>/<set>` in the set's own repo, `<trees>/<set>-<repo>` in the other |
| `work.decide` | `collect` output and `owners.tsv` |
| `work.scip` | SCIP indexes `fw.sqlite` and `app.sqlite` (built by `tools/scip/scipdb.py`) |
| `work.usage_log` | The usage log |
| `work.dir` | `audit` writes `<work.dir>/audit/` |
| `framework.integration`, `app.integration` | The repos set trees are added from |
| `framework.writing_base`, `app.writing_base` | The branch each set tree starts from |
| `racheck.fw_base`, `racheck.app_base` | Base checkouts (read only) |
| `framework.facade`, `framework.facade_manifest`, `app.facade_dirs` | The facade check |
| `framework.lints_file` and `[[lints]]` | The lints (`rules/lints.toml`, plus port.toml's own) |
| `plan.base`, `plan.linebase` | The framework commit the plan was made against; the commit line numbers refer to |
| `app.name` | Prompt text |
| `models.plancheck`, `models.write`, `models.fix` | Default models |
| `pipeline.run_max_turns`, `repairs`, `agent_max_turns`, `plancheck_max_turns`, `fix_max_turns`, `lookup_tools` | Turn limits, repair calls, the read tools of one-shot calls |
| `pipeline.bundle.*` | Bundle budgets (see [bundle](#bundle-set---shared)) |

Two kit files go into every writer prompt, and port-set stops if either section is missing: the `## Code` section of [rules/porting-rules.md](../rules/porting-rules.md) and the `## Notes` section of [rules/writer-notes.md](../rules/writer-notes.md).

## The sheet

The parser is `tools/portkit/portset/sheet.py`. [templates/sheet.md](../templates/sheet.md) is the format.

**Head keys** are lines `- Key: value` before the first table. port-set reads:

| Key | Read as |
|---|---|
| `Repo` | `fw` or `app`: the first word of the value. A sheet without it is rejected. |
| `Contract items it writes` | Contract ids (`<code>.<Kind><n>`, such as `pn.C12`); ranges such as `pn.C16-C24` count in `audit` and `validate`. |
| `Contract items and ...` | The ids the set calls; the wording after "and" is free. |
| `Map sections` | Area map section ids the set implements: bare ids are the set's own area's; `<area> <ids>` names another area's, until the next `;`. Read by `tools/coverage.py`. |
| `Waits on ...` | Set ids whose signatures the set codes against. Read by `audit` (waves). |
| `Stories` | The gallery stories of every component or variant the set adds to the framework: each type in backticks, its story names, and the stories file in backticks, such as ``- Stories: `ColorWell`: Default, Mixed, Compact variant in `crates/ui/src/controls/color_well/stories.rs`.`` The set that carries the line is the story owner. Required when the set adds a component or variant (`audit`, stories). |

**Tables**, each the first table under its `##` heading:

| Section | Columns | Read as |
|---|---|---|
| `## Files` | Path, Action, Write, Delete, What changes | The files the set owns. Actions: `new`, `edit`, `rewrite`, `delete`, `keep`. A path in backticks; one that exists in both repos carries `(fw)` or `(app)` after the backticks. A path may be a glob (deletes) or a `dir/` entry. |
| `## Replaced mechanisms ...` | Mechanism, Reader (path:line), Owner set, What the reader does instead | Old code the set removes and every place that reads it. |
| `## Tests` | File, Test, Verdict, Reason | Verdicts `keep`, `rewrite`, `delete`, `new`. |
| `## Requests to other sets` | To set, Path, What | Read by `audit` (readers) as files the sheet names. |

**Which repo a path is in:** its `(fw)` or `(app)` tag; else the set's own repo if the path exists there at the writing base; else the other repo if only that one has it; else (a new file) the set's own repo.

**What writers see:** the sheet without the Files table's Write and Delete columns (planning estimates a writer would read as targets).

## The set dir

`<work.sets>/<set>/` holds every file the set's commands write, plus the files the process adds:

| File | Written by | Holds |
|---|---|---|
| `base-fw`, `base-app` | `tree` | The commit each set tree started from |
| `bundle.md` | `bundle`, `run` | The writer bundle |
| `plancheck.md` | `plancheck` | The plan check's reply (`@@@ ITEMS` ... `@@@ END`, or `@@@ CLEAR`) |
| `decisions.md` | decision agents (phase 4) | Decisions that override the sheet ([templates/decisions.md](../templates/decisions.md)) |
| `moves.tsv` | the lead or a sheet fix | `from<TAB>to` per line: files `git mv` moves before edits apply |
| `open.md` | `run` | DECIDE items that stopped a write |
| `edits-1.md`, `edits-2.md`, ..., `edits-<label>.md` | `run`, `fix` | Each one-shot reply |
| `apply.md` | `apply`, `run`, `fix` | What applied and what failed |
| `check.md` | `check`, `run`, `agent`, `fix` | `## Errors` and `## Warnings`, one item per paragraph, `none` when empty |
| `racheck.md` | `racheck`, `run`, `fix` | rust-analyzer errors by file |
| `blocked.md` | `run`, `fix` | The writer's BLOCKED reason |
| `sheet.md`, `agent-prompt.md`, `agent-prompt-continue.md` | `agent` | The agent's input |
| `<findings>-prompt.md` | `fix` | The fix call's prompt |
| `<label>.json`, `<label>.err` | every model call | The raw reply; the output of a failed call |
| `review-<round>.md` | the area review (phase 6) | Findings for this set |
| `landed` | `combine-area` | The commit the combine took the set's net change at |
| `run.log`, `plancheck.log`, `agent*.log`, `fix-*.log` | the batch runners | Each command's output |

## Writing commands

### tree SET

Adds one worktree per repo the set writes, from that repo's integration tree, on branch `port/set/<set>` (own repo) or `port/set/<set>-<repo>` (other repo), at the writing base. Writes the start commit to `base-<repo>`. A tree that exists is left as it is. Every other writing command makes missing trees first.

### bundle SET [--shared]

Writes `bundle.md`, in this order:

1. **Instructions**: what every writer does (write every Files and Tests row, replace the set's `todo!("<id>")` and `P3(<set>)` markers, delete the old code, move the readers, `// PLAN:` notes for plan errors, never edit outside the Files table), the framework notes (`rules/writer-notes.md`), the moves, the code rules (`rules/porting-rules.md`, "Code") and the output format. A set that writes no framework code also gets the framework base checkout's path and the rule for coding against sibling sets: use the signatures the sheet and contract give, or write `// PLAN: assumed <signature>`.
2. **The sheet**, as writers see it.
3. **Settled before writing**: the STUB and RULE items of `plancheck.md` and the whole of `decisions.md`.
4. **Framework definitions your sheet names** (app-only sets with a framework SCIP index): the definition and public method signatures of each framework item the sheet and contract rows name.
5. **Contract rows** the set writes or calls.
6. **Files**: the current text of every file it edits, rewrites or keeps, and every `new` file the stubs already created.
7. **Excerpts** of the other places the sheet names (`path:N` references), the most-named files first.

`--shared` reads the base checkouts (`racheck.fw_base`, `racheck.app_base`) in place instead of the set's trees, and creates no worktree or branch. Use it to build a bundle without touching the integration repos. Without it, a missing set tree is created first.

Budgets (`pipeline.bundle.*`):

| Key | Default | Rule |
|---|---|---|
| `small` | 120 | A file up to this many lines goes in whole. |
| `small_edit` | 30 | A file up to `big` lines goes in whole when its row writes plus deletes at least this many lines. |
| `big` | 800 | Any other file goes in as its outline (item signature lines) plus the parts the sheet names, the markers left for the set and the lines naming items its row mentions. `rewrite` and `new` rows always go in whole. |
| `big_context`, `big_cap` | 30, 700 | Context lines around each part of a big file; most lines taken from one. |
| `context`, `snippet_cap` | 12, 260 | Context lines around each excerpt range; most lines of one excerpt. |
| `excerpt_budget` | 120000 | Characters of excerpts. Places past the budget are listed by location only. |

### apply SET EDITS

Applies an edits file in the one-shot format:

```
@@@ EDIT <path>
<<<<<<< SEARCH
<exact current lines, matching one place>
=======
<replacement>
>>>>>>> REPLACE

@@@ NEW <path>
<whole file>
@@@ END

@@@ DELETE <path>

@@@ BLOCKED
<reason>
@@@ END
```

Before the blocks: the moves in `moves.tsv` run as `git mv`, and the sheet's `delete` rows are removed. Then each block in order; a later SEARCH sees the text after earlier blocks. A block for a path outside the Files table fails and is skipped. A SEARCH that matches no place, or more than one, fails. Line-number prefixes copied from the bundle are stripped. A block that is already applied is reported as such, so rerunning an edits file is safe. `apply.md` lists what applied and what failed.

### check SET

The scripted self-check. Writes `check.md`; prints the counts.

Errors:

- `untouched: <path> (<action>)`: an `edit`, `rewrite` or `new` row whose file the set did not change (a warning instead when the contract stubs already edited a framework file).
- `not deleted: <path>`.
- `stub left for <id>`: a `todo!("<id>")` of an item the set writes is still in its trees.
- `P3 markers left`.
- `syntax: <path>`: rustfmt cannot parse a changed file (a warning when rustfmt is not on PATH).
- `duplicate mod declaration`.
- A lint of level `error` on a line the set added or changed.
- The facade rule: app code under `app.facade_dirs` names a framework crate by name instead of through the facade, and its package does not list that crate as a direct dependency.
- `plancheck.md was cut off by a usage limit`.
- `test missing` (a `new` test that is not there) and `test not deleted` (a `delete` test still in a file the set owns).

Warnings: lints of level `warn`; every `// PLAN:` note; PLAN notes naming items the framework index defines; names `decisions.md` gives that are in none of the set's trees; a `delete` test in another set's file; removed names still in the set's files.

Batch runners read `check.md`: an item starting `untouched:` or `test not deleted:` gets an agent round; items starting `compile error (rust-analyzer)` wait for the batch recheck.

### racheck SET

rust-analyzer diagnostics without a build. For each repo the set writes, it asks that repo's daemon (`tools/racheck.py serve fw|app`, one per repo, loaded on the base checkout) to overlay the set tree's changed `.rs` files (and the files its Replaced mechanisms table names) on the loaded checkout, and report diagnostics. Writes `racheck.md`; returns the errors as `compile error (rust-analyzer): <path>:<line> <code> <message>` items. Without a running daemon it prints how to start one and the command fails; inside `run` and `fix` the check goes on without it. rust-analyzer does not borrow-check and misses some macro and trait errors: the compile gate catches those later.

### plancheck SET [--shared]

One model call (`models.plancheck`, `pipeline.plancheck_max_turns` turns) on the write bundle plus a plan-check request. The model may look things up with the read tools (`pipeline.lookup_tools`) and lists only what would make it guess while writing:

| Tag | Means |
|---|---|
| `[STUB]` | The base already has what a row asks (the stubs wrote it). Nothing to decide. |
| `[RULE]` | One option follows from the code rules, the contract or the sheet; the item names the rule and the option. |
| `[DECIDE]` | The options are all defensible, or one changes another set's files or the contract. |

Always DECIDE, whatever the model would pick: a fallback or second path beside an existing mechanism; a hash, cache, guard or flag standing in for a missing signal; a visibility or API change made only for a test; a choice that depends on another set's item beyond the given signature.

The reply goes to `plancheck.md`. `--shared` reads the base checkouts instead of making set trees (a plan check only reads; `run-batch --plancheck` uses it). The session is kept, so `run` can resume it and reuse its prompt cache.

### run SET [--skip-plancheck] [--repairs N]

The one-shot pipeline:

1. Build the bundle (`bundle.md`).
2. Plan check (skipped with `--skip-plancheck`, which batch runs use once the decisions are in). DECIDE items stop the run: they go to `open.md` (state OPEN).
3. One write call (`models.write`, `pipeline.run_max_turns` turns), resuming the plan check's session. The reply goes to `edits-1.md`. A BLOCKED reply stops here (state BLOCKED, `blocked.md`).
4. Apply, commit (`<set>: written from its sheet`), check (scripted plus racheck when its daemons run).
5. Repair calls, up to `pipeline.repairs`: while apply failures or check errors remain, one call gets the remaining problems and the current text of the files they name, answers with blocks, and is applied, committed and checked again.

The set then ends done (check clean), in review (errors or apply failures left), blocked, or out of turns.

### agent SET [--continue]

The set written by one `claude -p` agent with edit tools (`models.write`, `pipeline.agent_max_turns` turns) in the set's tree. It reads the writer sheet (`sheet.md`), `decisions.md` and the contract rows itself. Its Bash is limited to read commands (git grep, show, log; grep; rg; ls; sed -n); it must not build. The sheet's `delete` rows are removed before it starts. When it stops, port-set runs the check and commits. An agent that runs out of turns leaves its work committed; `--continue` starts a new agent that reads the committed work, the Errors of `check.md` and `racheck.md`, and finishes only what is left. Batch runners use agent mode above `pipeline.agent_files_over` Files rows and for BLOCKED retries ([process/06-write.md](../process/06-write.md)).

### fix SET FINDINGS.md

One call (`models.fix`, `pipeline.fix_max_turns` turns) that fixes a review's findings on a written set: the bundle of the set's current text plus the findings, answered with blocks. Files outside the Files table that a finding names by full path may be edited. A finding that needs a design decision is answered BLOCKED. The reply goes to `edits-<findings stem>.md`; then apply, commit (`<set>: review fixes (<label>)`) and check. `tools/fix-batch` runs it over a list.

### usage [SET]

Prints the usage log (`work.usage_log`), tab-separated with a header: `time set step model turns input cache_write cache_read output cost_usd secs`, then the call count and total cost. `step` is the call's label: `plancheck`, `write`, `repair-<n>`, `agent`, `agent-cont`, `fix-<findings>`. Every model call also posts a `model-call` event on the set's dashboard task with the same numbers.

## Plan-level commands

### validate [--sheets DIR] [--parts DIR]

Parses every sheet as the writing commands do. Problems:

- the parser rejects the sheet (no `Repo: fw|app`);
- no Files rows, an unknown action, a path listed twice;
- an `edit`, `rewrite`, `keep` or `delete` row whose path is in neither repo at its writing base (globs and `dir/` entries are not checked);
- a contract id the sheet writes or calls with no row in the contract parts;
- a Tests verdict that is not `keep`, `rewrite`, `delete` or `new`;
- a set id whose area is not in `[[areas]]` (when areas are set);
- a stories file the `Stories` line names that is in neither the Files table nor the tree.

Warnings: a head key of the template (`Contract items it writes`, `Contract items and ...`, `Map sections`, `Waits on`) the sheet lacks.

`--sheets` and `--parts` check other directories, such as the kit's example sheets. When the repos cannot be read, the path checks are skipped and the output says so; without contract parts the id checks are skipped.

### audit [SET...] [--only CHECK,...]

Token-free plan checks over every sheet, the contract parts, the `decisions.md` files and both repos at their writing bases (read from the base checkouts when they exist, else from the integration repos with `git show`). No model call, no worktree. With SETs it audits only those sets; `markers` and `waves` always read every sheet. `--only` runs the named checks.

Each check writes `<work.dir>/audit/<check>.md`, which opens with how it decides; `README.md` is the summary. The four gating checks must report 0 before writing starts ([process/05-plancheck-decide.md](../process/05-plancheck-decide.md), step 8). Run it again before an app batch, after the framework writing base moves ([process/07-review-combine-compile.md](../process/07-review-combine-compile.md)).

| Check | Gates | Finding | Fix |
|---|---|---|---|
| `stubs` | yes | (1) A contract id a set writes, or another set calls (a pinned cross-set signature), whose framework row is `new` or `changed` and whose signature names a Rust item, but the stubs hold none of its items in the row's file, no `todo!("<id>")` and no `P3(` marker naming it. (2) A `fn` of the signature that is defined with a different parameter count (self forms left out). (3) A backticked type in a `decisions.md` bullet that neither tree has and that another set's sheet or decisions also names, where one of those sets writes framework code. Sets already written are skipped in (3). | Stub the item with the contract's signature ([process/05-plancheck-decide.md](../process/05-plancheck-decide.md), step 7), or correct the contract row. |
| `stories` | yes | (1) A sheet adds a component (a written contract row of kind `new` whose signature registers a type with the gallery: `#[derive(Component)]`, `#[derive(Pattern)]`, `#[pattern(...)]`) or a variant (the row's kind or behaviour says `variant of`, `named option`, `named variant` or `app variant`) with no `Stories` head line naming the type. (2) A stories file the line names that is in neither the Files table nor the tree. (3) A registered type in the framework tree with no `#[story(Type ...)]` and no story owner (a set whose Stories line names it, or that writes a stories file in the type's directory and names the type). | Add the `Stories` line and the stories file's Files row to the sheet of the set that adds the component ([rules/porting-rules.md](../rules/porting-rules.md), "UI gallery"). |
| `decision-files` | yes | A path on a `decisions.md` line that says add, edit, write, new file, moves to, goes in, owns or Files table, which is not in the set's Files table, and which no other set owns or which the line adds to the Files table. `apply` refuses such files, so the writer would skip them. | Add the Files row. |
| `readers` | yes | For each identifier in a sheet's Replaced mechanisms table (rows another set makes, or that say unchanged, gains, kept or adds, are skipped), a file that uses it which the sheet neither owns nor names (Files, Reader column, Requests table) and whose own set does not name the item. With both SCIP indexes the uses are exact references; without them, whole-word text hits filtered by qualifier, comments and local definitions (the report says which). Names with too many hit files are skipped or reported as one "wide" line: the sheet then needs a rule, not a list. | Add the reader to the sheet (Replaced mechanisms and Files, or a request to its owner set). |
| `line-refs` | no | A `path:N` reference whose backticked identifiers are not within 20 lines of N in the file at the writing base. Strong: the identifier is elsewhere in the file, or N is past the end (`remap` was likely not run). Weak: no named identifier in the file (often a new item). | Run `remap`, or correct the line. |
| `tests` | no | A Tests row with verdict keep, rewrite or delete whose test function is not in the named file. | Correct the file or name. |
| `markers` | no | A `P3(<set>)` marker in a file that set does not own, or a `todo!("<id>")` in a file the id's writer does not own. Also `markers.tsv`: every marker and the set that must clear it. | Move the marker or the Files row. |
| `waves` | no | Cycles, unknown ids and self-waits among the `Waits on` lines. The report also gives the waves: an order in which no set codes against an unwritten signature. | Correct the `Waits on` line. |
| `sizes` | no | A bundle over 150k tokens, a set whose Files rows write more than 1,500 lines, a sheet the bundle builder cannot read. Needs the base checkouts. | Split the set. |
| `names` | no | A `new` contract item whose (type, name) already has two or more definitions in its crate (the stub and an older one), not counting files the sheet deletes or names its row replaces. | Rename, or name the old item in the row's Replaces cell. |

### remap [--dry-run]

Moves every framework line reference in the sheets and the contract parts from the commit in `plan.linebase` to the current `framework.writing_base`, then writes that commit into `plan.linebase`. Run it after every move of the framework writing base: after the last stub stage, after the stub refresh, and from `tools/move-base` (which calls it).

- References: `path:N`, `path:N-M`, `path:N, :M`, a backticked `:N` after a full path in the same cell, and a bare `name.rs:N` that resolves to one framework file (the sheet's own Files rows first, then a unique file name).
- Only framework files that changed between the two commits are rewritten. A path in both repos counts as framework only in a framework sheet.
- A line inside a changed hunk goes to the hunk's new start; lines after a hunk move by its size.
- App references are never touched.
- Already at the writing base: nothing changes, exit 0.

`--dry-run` lists the files it would rewrite. Back up the sheets and parts before a remap that follows a large framework change: the rewrite is in place.

### collect

Writes what the decision pass needs ([process/05-plancheck-decide.md](../process/05-plancheck-decide.md), step 4):

- `<work.decide>/<area>.md`: every open DECIDE item, by set, with its option lines and the set's sheet path. Items come from `plancheck.md` and `open.md`, plus the reason in `blocked.md` as a `[BLOCKED]` item. A file counts unless it is older than the set's `decisions.md`, so a plan check rerun after the decisions brings its new items back. An area with no open items gets no file (an older file stays; the output names it).
- `<work.decide>/owners.tsv`: one line per path a Files table names, `path<TAB>set:action,set:action`, every set whose Files table names it, in sheet order, no header. `cross-owner`, `gate-classify.py` and the decision prompts read it. A `P3(<set>)` marker in a stub gives its line to the named set even inside another set's file: the readers apply that rule, not the file.

Split large areas into parts by hand after collecting ([process/05-plancheck-decide.md](../process/05-plancheck-decide.md), step 4).

### status [SET...] [--area A] [--stage S] [--json] [--post]

Each set's stage, read from its set dir (the latest that applies wins), beside its dashboard state:

| Stage | Read from | Means |
|---|---|---|
| `planned` | no `plancheck.md` | No plan check yet |
| `decide` | `plancheck.md` with DECIDE items and no newer `decisions.md` | Waiting for the decision pass |
| `ready` | `plancheck.md` clear, or `decisions.md` newer than it | Ready to write |
| `open` | `open.md` newer than `decisions.md` | `run` stopped on DECIDE items |
| `blocked` | `blocked.md` newer than `check.md` | The writer answered BLOCKED |
| `written` | `check.md` | Written; the detail gives the check and rust-analyzer error counts |
| `reviewed` | `review-*.md` | An area review covered it |
| `combined` | `landed` | The combine took its net change |

`--post` moves each set's dashboard task to the state its stage implies when they differ: planned and ready to `todo`; decide and open to `review`; blocked to `blocked` on lead; written to `done` with no check errors, else `review`; combined to `done`. Tasks that are `running`, and reviewed sets, are left alone. Use it after work that changes stages outside port-set, such as the decision pass writing `decisions.md`.

`--json` prints one list of `{set, stage, detail, board, board_note, updated}`.

## Exit states and the dashboard

Every command except `usage` and `status` posts one `port-set-<command>` event when it ends, with its duration, its result line, its log and key numbers (through `portkit.track.recorded`). Each model call posts a `model-call` event on the set's task.

The commands that own a set's state (`plancheck`, `run`, `agent`, `fix`) move its dashboard task:

| Moment | State | Note |
|---|---|---|
| The command starts | running | the step and model |
| The plan check leaves DECIDE items (OPEN) | review | the count; the items are in `open.md` (run) or `plancheck.md` |
| A standalone plan check leaves no DECIDE item | todo | ready to write |
| The writer answers BLOCKED | blocked, on lead | the reason's first line; `blocked.md` |
| The writer runs out of turns (OUT OF TURNS) | blocked, on lead | how to continue (`agent --continue`, or `fix` with more turns) |
| Written; check errors or apply failures left | review | the counts; `check.md`, `apply.md` |
| Written; check clean | done | rust-analyzer errors, if any, wait for the batch recheck |
| The command fails (a model call, git) | failed | the error |

The end event of `plancheck` is ok unless the command fails; that of `run`, `agent` and `fix` is ok only when the set ends done. `validate` and `audit` post ok only with no problems. `track import sheets` creates one task per sheet before writing starts, so the board is full from the start ([tools/track.md](track.md)).

## Who calls port-set

| Caller | Commands |
|---|---|
| `tools/run-batch` | `plancheck --shared` (with `--plancheck`), `run --skip-plancheck` |
| `tools/run-area` | `run`, `agent`, `agent --continue`, `check`, `racheck` (the bucket rules are in [process/06-write.md](../process/06-write.md)) |
| `tools/fix-batch` | `fix` |
| `tools/move-base` | `remap` |
| The lead | `validate`, `audit`, `collect`, `status`, `remap`, single-set commands |

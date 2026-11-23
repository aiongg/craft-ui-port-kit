# Phase 6: review, combine, compile

Phase 6 turns a written build batch into one branch that compiles. The code is reviewed before it compiles, because a review is cheaper than a compile round and catches what a compiler cannot (a second mechanism, a missing deletion, a wrong event mapping). Then the sets are combined on the integration branch, checked by rust-analyzer as a whole, and compiled: framework crates first, in dependency order, then the app.

| | |
|---|---|
| Starts when | A build batch is written ([06-write.md](06-write.md)). |
| Ends when | Every set has a review verdict and its findings are fixed or ruled; the combined branch compiles, framework crates first, then the app; every component the batch adds has a registered story that renders. |
| Agents | Opus reviewer per area and side (`models.review`); Sonnet fixers (`models.fix`, Opus `models.fix_retry` for a set that failed twice); Sonnet compile fixers per crate group (`models.compile_fix`). |
| Builds | One compile per cycle in the integration trees, through `tools/cycle`. |
| Output | `<work.sets>/<set>/review-<round>.md`, the review summaries, `<work.plan>/rulings.md`, the combined branch `<work.branch_prefix>area/<batch>` in each integration tree, compile logs under `work.runs`. |

Record the phase: `tools/track phase 6 "review, combine, compile"`.

## Step 1: review

One Opus reviewer per area and side (framework or app) reads the diffs of its sets against their sheets, decisions, plan checks and the rules (`prompts/p6-area-review.md`). It edits nothing and builds nothing.

1. Write each set's diff for its reviewer: `tools/port-set review-diff <set>...` for every set of the area (writes `review-diff.patch` in each set dir).
2. Put each review on the board: `tools/track status review-<area>-<side>-<round> todo "<n> sets"`.
3. Render the prompt with `{{AREA}}`, `{{ROUND}}`, `{{TASK}}` and `{{OUT}}` (the summary path), name the side and the sets in the prompt, and start the reviewers as background tasks. One reviewer handles about 15 to 20 sets in about 120 tool calls; split a larger area.
4. Each set gets `review-<round>.md`: a verdict (`ok`, `needs fixes`, `back to plan`), numbered findings with `path:line`, the fix, the severity and a draft ruling for the fixer (`fix`, `restore the base hunk`, `back to plan`). The summary ends with "Pipeline lessons": findings by source (sheet or contract, bookkeeping across trees, a writer error a plan check could catch, an error only a compile or test catches).

The reviewer checks the gallery rule for every component or variant the batch adds to the framework: its stories are registered in the same set, at the gallery level of its architectural kind, with a story owner, and its dialogs and windows start closed ([rules/porting-rules.md](../rules/porting-rules.md), "UI gallery"). A missing story is a `fix` finding on the set that adds the component.

## Step 2: rule on the findings

First rule the area's open questions and `back to plan` findings in one pass: put a task on the board (`tools/track status rulings-<area> todo`), render `prompts/p-rulings.md` with `{{AREA}}`, `{{ROUND}}`, `{{TASK}}` and `{{OUT}}` (`<work.runs>/rulings-<area>-<round>.tsv`), and run it as a background task. Check its `cross-set` and `framework` rows, apply them, and record every ruling with `tools/track answer --file <OUT> --by rulings` ([rules/lead-rules.md](../rules/lead-rules.md), "The dashboard").

Then read every review summary and every `back to plan` finding yourself.

- The reviewer's draft rulings stand unless you overrule them. Write overrides at the end of the set's review file under "Lead rulings (final)". Rulings that apply to a whole area go to `<work.plan>/rulings.md`.
- A `back to plan` finding means the sheet or contract is wrong. Fix the sheet, the contract row or `decisions.md` first (and the stubs, if a signature changes), then let the fixer apply it.
- Small things (a missed reader, a one-line mistake that crosses sets) you fix yourself at once, on the set's branch.
- Use the "Pipeline lessons" tables: a class of finding that a plan check or a lint could catch goes into the port-set prompt or `[[lints]]` before the next batch is written.

Record the round: `tools/track event decision "<area> review <round>: <n> findings, <k> back to plan"`.

## Step 3: fix batch

Fixers work in the sets' code-only trees, with no build.

- Write a list file with one line per set that has findings: `<set> <path to review-<round>.md>`.
- Run it as a background task: `tools/fix-batch <list>`. A line without an existing findings file stops the batch before it starts. Each line runs `port-set fix <set> <findings>`: one model call that applies the findings and rulings, then the scripted check and racheck. `port-set` moves each set's task (`running`, then `done` or `review`).
- A set with many findings or many files gets the agent-mode fixer instead: `prompts/p6-fix-agent.md`, one agent per set, task `<set>`.
- A set that fails its fix twice goes to `models.fix_retry`: `tools/fix-batch <list> <N> <models.fix_retry>`.

A fixer that meets a design choice the rulings leave open stops that item and writes the options; decide it, then rerun the set.

## Step 4: combine

Each repo's integration tree holds one warm target dir for the whole port. Combining puts every set of the batch onto the writing base there:

```sh
REPO=fw  tools/combine-area <batch> <set>...      # framework side, in framework.integration
REPO=app tools/combine-area <batch> <set>...      # app side, in app.integration
```

- Each set lands as **one net-change commit**: its whole diff from its base, not its separate commits. A set with a second repo lands from its `<set>-<repo>` tree.
- Where two sets edit the same lines, the later set wins (`-X theirs`). combine-area prints the files where that decided; read each and confirm both sets' intent survived.
- combine-area then runs `tools/combine-lost`: lines a set added that the combined tree lacks, and that no later set removed or changed. Each lost line is a combine error: combine-area exits 1, and you restore the line before the gate.
- combine-area also prints `UNLINKED <path>` for each new `.rs` file that no `mod` line reaches (cargo never builds it, so its code and tests are silently absent), and the cycle's compile step lists them in `unlinked.txt`. Add the `mod` line before the gate.
- **Owed lines.** A set not yet written may owe a line the batch needs to compile (a `mod` line, a re-export, a call it will add). Add it on the integration branch as a separate commit whose message starts `owed by <set>:`, so its writer finds and replaces it. Never edit another set's branch for it.
- `tools/cross-owner <set>...` lists files a set changed that `owners.tsv` gives to another set. Each is a bookkeeping error: move the change to its owner, or record why it stays.

Pause the dashboard around the combine, so no agent starts a step on a moving branch: `tools/track pause "combine <batch>"`, then `tools/track resume`. Record the result: `tools/track event merge "<batch>: <n> sets combined, <k> owed lines"`.

## Step 5: racheck gate

Before compiling, ask rust-analyzer about everything the combined trees changed:

```sh
tools/racheck-gate <batch>-ra
tools/gate-classify.py <work.runs>/<batch>-ra/racheck-gate.json <batch lists> --later <later lists> --tsv <work.runs>/<batch>-ra/classes.tsv
```

racheck-gate overlays the changed framework files on the framework daemon's tree and asks the app daemon for diagnostics, then lists every `mod x;` line whose module file is missing. gate-classify sorts the errors in this batch's own files:

| Class | Meaning | Action |
|---|---|---|
| `real` | An error in this batch's code | Fix before compiling: grouped as in "Compile errors" below, or by the set's fixer |
| `later:<sets>` | The name belongs to an item a later set writes | Expected; an owed line if the batch needs it to compile |
| `ra-gap` | A pattern rust-analyzer cannot resolve (`racheck.gap_patterns`) | Ignore; the compile decides |
| `mod-file` | A `mod` line with no module file | Fix: rust-analyzer reports nothing inside a missing module |
| `downstream`, `macro` | Follow-on errors of another error, or many errors on one macro line | Fix the cause, not these |

## Step 6: compile cycles

From here every build runs as a **cycle**: one `tools/cycle` command that merges the fixers' branches, compiles, formats and lints the changed crates, runs the tests once the batch compiles, cuts each fixer's packet, sends it to the same fixer and waits for them to hand back ([11-build-loop.md](11-build-loop.md), "The cycle"). Run it as a background task; its last line is the one notification of the cycle.

The first cycle of the batch has no fixers yet:

```sh
tools/cycle <batch>-run-1 --batch <batch> --area <area>
```

Its compile is `tools/compile-gate <batch>-run-1-compile`. The framework half runs `cl check <crate> --keep-going` for each framework crate the batch changed and every workspace crate that depends on one, in dependency order (`tools/crate-order.py`), and never stops at a failing crate, so every independent crate's errors come back in one run. Each error is counted once and charged to the crate that owns its file; a crate that fails only on another crate's errors shows as `failed-through` that crate. The app half runs `cl check all --keep-going` in the app integration tree once the framework is clean.

A cycle that exits 2 met a tool failure: cl exited nonzero and printed no `file:line:col: error` line (a manifest, resolution or setup fault), or an integration tree was dirty. Never count it as a pass or as "0 errors"; fix the setup and run the cycle again. Exit 3 is a merge conflict: resolve it on the integration branch, then run the cycle again.

When the batch compiles, the same cycle formats the changed crates, runs clippy and the doc build on them, runs the tests, and records `track phase 7` (the phase gate decides). The red rounds of [08-tests-and-red-rounds.md](08-tests-and-red-rounds.md) continue with the next cycles.

## Compile errors

Compile errors come in groups: one wrong signature or one missing import gives many errors in many files. Never give one error to one agent.

**Codemod first.** Before any compile fixer starts, run `tools/codemod` on the batch's first compile. It fixes four mechanical classes at rustc's own spans: a missing argument, cascaded into the callers' signatures round by round (E0061), a moved field (E0609), a field that became a method (E0615) and a borrow inside a call's arguments (E0502). Every other error it lists by code. Write the map file (`<work.plan>/codemod.toml`, format in `tools/codemod --help`) from the causes the errors show: the new context parameter, the field moves, the setters. Then:

```sh
tools/codemod <batch>-codemod --gate <batch>-run-1-compile --map <work.plan>/codemod.toml --apply --rounds 20
```

It commits its edits as one commit on the integration branch. Read its `codemod.diff` and `unhandled.md`, and revert what is wrong. To try new map rows without another compile, run it with `--json <work.runs>/<batch>-codemod/check-1.json --tree fw|app` and no `--apply`: that prints the diff only. The steps below start from its `remaining.errors`.

1. Group the errors by crate, then by cause (a changed signature, a moved item, a missing re-export or trait import, a type that changed). For a long list, `tools/split-errors.py <errors> <N> <prefix>` splits it into N groups of whole files, balanced by count, keeping directories together, and writes each group's owned files (`<prefix>-<i>.files`). Each file has one owner, so no two fixers edit one file. A fixer that finds a cause in a file no group owns reports it; add that file to one group's `.files`.
2. Small slips that rustc alone reports (a borrow, a move, a missing clone) in a framework batch: fix them yourself; they take minutes.
3. For the rest, one compile fixer per crate group, on a branch cut from the integration branch (`prompts/p6-compile-fix.md`, task `cfix-<group>`), started through `tools/swarm.py` so the cycles can resume it. Fixers work by cause, lower crates first, edit only the files their group owns (a cause in another group's file goes in their report, and that file's owner fixes it), and build only in the fixer mode `build` (`pipeline.fixer_mode`, [11-build-loop.md](11-build-loop.md), rule 3).
4. When the fixers have handed back, run the next cycle with them: `tools/cycle <batch>-run-<n> --fixers <file> --groups <dir>`, where the fixers file names each `cfix-<group>` task and its branches, and `<dir>` holds split-errors.py's `<group>.errors` and `<group>.files`. It merges every group's branch, compiles once, and sends each group the errors left in the files it owns (or, for a file no group owns, in files its commits changed). Errors no fixer owns are in the cycle's `report.md` for you. Repeat until the batch compiles.

**Stop rule.** If the errors point at the plan (a wrong contract item, a missing API, a signature that cannot work) rather than at writer slips, stop compile-fixing. Fix the plan (contract row, sheets, stubs) and send the affected sets back to their writers before any other area is written. A compile-fix agent never invents a mechanism to make wrong plan code compile.

## Step 7: the gallery gate

Once the framework half compiles, render the stories of every component or variant the batch added: `cl render <crate> <Component>` in the framework integration tree. Look at each yourself: every required story exists, renders, and dialogs and windows start closed with a button that opens them. Regenerate and commit the components index after adding or renaming a type, as craft-libs `docs/porting.md` ("Adding a component or story to the gallery") says. A missing or broken story goes back to the set that adds the component. The shared suite then runs over the stories in phase 7.

## Setting up an app batch

App sets are written against the combined, compiled and tested framework, not against the stubs. Before the first app batch is written:

1. **Freeze the framework.** When the framework batches pass their red rounds, tag the framework integration head. The app batch's framework stays at this tag for the whole batch; framework fixes found during the batch land in set trees and reach the app at the next batch.
2. **Move the framework writing base** to the tag: `tools/move-base <tag>`. It moves `framework.writing_base`, drops untouched set trees on the old base, runs `port-set remap`, moves `racheck.fw_base` and restarts the framework daemon. Back up `work.sheets` and `work.parts` first: the remap rewrites every sheet and contract part.
3. **Refresh the app writing base.** On `app.writing_base` (phase 3 made it from the port branch and committed the app contract stubs on it; cutting it again would drop them), run `tools/patch-framework` again. It writes path patches for every framework package the app's `Cargo.lock` takes from a framework URL (`framework.patch_urls`), not only the direct dependencies: an unpatched transitive crate builds a second time from git, with types that differ from the path copies. It takes the egui family from the framework's own patch section, so one egui builds, leaves the app's own patch lines in place, and reports pinned versions (`=x.y.z`) the framework crates do not satisfy.
4. Check that every facade feature the app uses exists in the framework's facade manifest.
5. Resolve once with no build: `cargo update -w --offline` (without `--offline` if a git source is missing from the cache). The lock must name no framework git source. Commit `Cargo.toml` and `Cargo.lock` on `app.writing_base`. Never push this branch: its patches hold local paths.
6. Move `racheck.app_base` to `app.writing_base` and restart the app daemon. A cold load takes minutes.
7. Rebuild both SCIP indexes on the new trees ([01-setup.md](01-setup.md), step 9). App bundles read framework definitions from `fw.sqlite`; a stale index hands writers stub-head signatures.
8. Spot-check the remap: open the framework lines that five app sheets cite. A reference inside a hunk the framework sets changed maps to the hunk start, and one to a function a set moved can be wrong; fix leftovers with a sheet fix.
9. List the stubs left in the framework: `git grep -n 'todo!("'` and `git grep -n 'P3('`. Each belongs to a set of this batch (an app set that writes framework bodies), to a later batch, or to a framework set that failed to land; send the last kind back to its set before the batch starts.
10. Run `tools/port-set audit` again. Any app sheet that names a framework item the tag lacks is a plan error: fix it before the set runs.

Then write the app batch ([06-write.md](06-write.md)) and come back to step 1 for it.

## Exit

- [ ] Every set of the batch has a review verdict; every finding is fixed, restored or ruled.
- [ ] The batch is combined in each integration tree; combine-lost reports nothing; owed lines are marked commits; cross-owner findings are resolved.
- [ ] The racheck gate has no `real` or `mod-file` error.
- [ ] The last cycle's compile (`tools/compile-gate`) exits 0: every changed framework crate and its dependents, then the app selection.
- [ ] Every component the batch adds has stories that render, checked by the lead.
- [ ] Plan errors found by the compile are fixed in the plan, and `STATE.md` records them.

The cycle that compiles the batch records `tools/track phase 7 "tests and red rounds"` itself; when the gate refuses, its summary names the items: fix them and record the phase. Then go to [08-tests-and-red-rounds.md](08-tests-and-red-rounds.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

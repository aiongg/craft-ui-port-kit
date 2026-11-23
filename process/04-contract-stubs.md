# Phase 3: contract stubs

Phase 3 writes every contract signature into the framework, and the app rows into the app, with `todo!()` bodies, and makes every crate compile. Writers then code against signatures that exist, so a signature mistake shows up here, in a cheap stub, instead of in hundreds of written lines. Phase 3 is also the plan's last check against the compiler: every signature that does not compile and every caller no sheet lists is a plan error, reported and fixed before anyone writes.

| | |
|---|---|
| Starts when | The plan passed ([03-plan.md](03-plan.md)). |
| Ends when | Every contract item is stubbed or has a recorded plan error that the plan fixed; every stage's `cl check` passes; every caller a stage patched is listed in a sheet; sheet line numbers point at the stub head. |
| Agents | Sonnet (`models.stubs`), one per stage, one stage after another. |
| Builds | `cl check` per crate in the framework integration tree; `cl check all` in the app integration tree for the app stage. No tests. |
| Output | The stub branches `framework.writing_base` and `app.writing_base`: the writers' bases. |

## Step 1: order the stages

1. List the crates the contract parts touch, and order them with `tools/crate-order.py`, which reads `cargo metadata` and prints dependency order with no build.
2. Group them into **stages** of related crates, lowest first: for example the base crates and the behaviour crate; the UI contract; widgets and panels; canvas and shell; patterns; the domain crates (imaging, colour, menus); the rest; text and the facade last. A crate can appear in two contract parts; its stage does both.
3. Create the stub branch in the framework integration tree, from `plan.base`: `git -C <framework.integration> switch -c <framework.writing_base> <plan.base>`. Its target dir stays warm for the whole phase.
4. Create the app writing base in the app integration tree, from the port branch: `git -C <app.integration> switch -c <app.writing_base> <app.port_branch>`. Run `tools/patch-framework`, so the app builds against the stub branch; resolve once with `cargo update -w --offline` and commit `Cargo.toml` and `Cargo.lock` there. Never push this branch: its patches hold local paths.
5. Put one task per stage on the board, the app stage last: `tools/track status stub-<n> todo "<crates>"`, `tools/track status stub-app todo "app contract"`.

## Step 2: run one stage at a time

Each stage builds on the commits of the stages before it, so stages run in sequence, never in parallel. For each stage:

1. Render its prompt: `prompts/p3-contract-stubs-stage.md` with `{{STAGE}}` and `{{CRATES}}` filled by `tools/render-prompt`.
2. Start the agent as a background task (a one-job list through `tools/swarm.py`, or one headless `claude -p`). Mark it on the board: `tools/track status stub-<n> running`.
3. When it hands back, read its report (`work.plan/stage-<n>.md`), record the plan errors (step 3), and start the next stage.

The **app stage** runs last, with `{{STAGE}}` set to `app` and `{{CRATES}}` to the crates of the `### <crate> (app)` headings. It works in the app integration tree on `app.writing_base`, against the stubbed framework: it stubs every app row as below, makes the app callers the framework stubs broke compile with the same marked smallest edits, and checks with `cl check all` in the app tree. Every app set starts from this branch when it is written, so the items it shares with other app sets already exist.

What a stage agent does, in its crates only:

- **New item:** added with the exact signature. Function bodies are `todo!("<id>")`. A new field, variant or trait method gets the minimum that compiles where the crate builds or matches it (`Default::default()`, a `todo!("<id>")` arm). Every new public item gets a doc comment from the contract's Behaviour text.
- **Changed item:** the signature changes exactly as written; the existing body stays. If the body no longer compiles, the smallest edit that compiles (bind a new parameter as `let _ = name;`, convert at the boundary), marked `// P3(<set>): <id>`. It never replaces a body with `todo!()` and never deletes code.
- **Removed item:** left in place. Its writer set removes it with its readers in phase 5.
- **Broken callers** inside the stage's crates (for the app stage, the whole app): the smallest edit that compiles, marked `// P3(<set>): <id>`, where `<set>` owns the file (`ownership.md`). The agent then checks whether a sheet lists the caller in its "Replaced mechanisms and their readers" table, and reports each patched caller with listed yes or no.
- **Checks:** `cl check <crate>` after each crate, in stage order (the app stage: `cl check all` in the app tree), with no new warnings; `cargo fmt --all` once at the end; one commit for the stage. No tests, no clippy, no workspace-wide builds.

A `P3(<set>)` marker is a promise: the named set's writer replaces the line, and `port-set check` flags a marker left in a written set's files.

## Step 3: feed plan errors back

Phase 3 exists to find plan errors. A stage reports them; it does not redesign. Collect every reported error in `work.plan/plan-errors.md`, one row each: Stage | Id | Owner set | Error | Fix. Fix each in the contract and the sheets **before the owner set is written** (a Sonnet sheet fix, or by hand when small).

The classes to expect, and their fixes:

| Class | Example | Fix |
|---|---|---|
| Signature that cannot compile | A type no item creates; a lifetime or trait-bound conflict; an orphan-rule break | Obvious mechanical fixes are written by the stage and reported as fixed; others are left out and the contract row is rewritten by the lead |
| Name collision | A new method with the name of an existing builder (`E0592`) | Rename in the contract and in every sheet that uses the item |
| Unlisted caller | A caller the stage had to patch that no sheet lists | Add it to the owner set's readers and Files table |
| Missing detail | An item with no signature, no field list or no value | The stage writes the plain choice and reports "chosen in stage N; writers confirm", or the lead gives the signature |
| Behaviour names something that does not exist | A method or type that is not in the code at the base | Rewrite the Behaviour text, even when the signature compiles |
| Item in the wrong crate | A row listed under one crate whose signature lives in another | Stubbed by the stage that owns the real crate |
| Old beside new | A stage kept an old body under a new name to compile | The owner set removes the old copy; `port-set check` greps for the names |

Rules the stages learned:

- A `const fn` cannot hold `todo!()`: give it the trivial real body the contract describes, and report it.
- An item behind a non-default feature: check it once with that feature through `cl cargo check -p <crate> --features <feature>`.
- An item whose signature spans crates: the earlier stage writes its own crate's part and records the rest in `work.plan/stage-carry.md` (Stage that does it | Item | Part); the later stage reads that file first.
- A new item nothing calls yet may carry `#[allow(dead_code)] // P3(<set>): <id>`; its writer removes the allow.
- A crate that denies `clippy::todo` fails clippy until phase 5 fills the bodies. That is expected; clippy runs after the bodies exist.

Record each stage on the board when its errors are filed: `tools/track status stub-<n> done "<k> plan errors, <m> unlisted callers"`.

## Step 4: move the line references

Sheets and contract rows cite line numbers at `plan.base`; writers work at the stub head. `plan.linebase` holds the commit the line numbers refer to (init-workspace wrote `plan.base` into it). After the last stage:

```sh
tools/port-set remap
```

It moves every line reference in the sheets and contract parts from `plan.linebase` to the stub head, then updates `plan.linebase`. Phase 4 runs it again after its stub refresh. App references are not moved: the app stage shifts app lines by its stubs and patches only, and writers find app items by name.

## Step 5: move the racheck bases

The racheck daemons must load the trees the writers write against:

1. Move the `racheck.fw_base` checkout to the stub head (`git -C <racheck.fw_base> switch --detach <framework.writing_base>`).
2. Move the `racheck.app_base` checkout to `app.writing_base` (step 1 made it; the app stage committed its stubs there), with its framework patch pointing at `racheck.fw_base`, so rust-analyzer resolves the app against the stubbed framework.
3. Restart the daemons when phase 5 starts (`tools/racheck.py serve fw`, `serve app`).

## Step 6: rebuild the framework index

The phase 4 audits and the writers' bundles look up items the stubs added. Rebuild the framework's SCIP index on the stub head, as in [01-setup.md](01-setup.md), step 9, with `racheck.fw_base` as the tree, and replace `<work.scip>/fw.sqlite`.

## Exit

- [ ] Every stage committed and its `cl check` passed with no new warnings, the app stage's `cl check all` included.
- [ ] Every contract item is stubbed, or its plan error is fixed in the contract and the sheets.
- [ ] Every patched caller is listed in its owner set's sheet.
- [ ] `plan-errors.md` has a fix for every row; `stage-carry.md` has no part left unwritten.
- [ ] `port-set remap` moved the line references to the stub head.
- [ ] The racheck bases and the framework index are on the stub head.

Then record `tools/track phase 4 "plan check and decisions"` and go to [05-plancheck-decide.md](05-plancheck-decide.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

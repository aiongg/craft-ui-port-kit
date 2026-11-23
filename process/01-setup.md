# Phase 0: setup

The lead runs this phase alone, with the developer answering a few questions. It ends with a workspace every later phase uses: one config file, a dashboard, a warm build of the app against one framework rev, a record of the tests that already fail, and the two indexes that stand in for the compiler while nothing builds.

| | |
|---|---|
| Starts when | The developer has picked the app and the framework rev to port onto (normally the head of `framework.branch`; step 2 says how to choose it). |
| Ends when | The checks under "Exit" all pass. |
| Agents | None. The lead runs every step. |
| Builds | One warm app build and one full test run; the SCIP indexes. |

Steps 7, 8 and 9 take minutes to tens of minutes each. Start each as a background task and go on with the next step; the tools post their own events to the dashboard when they end. On a machine with less than about 64 GB of memory, run them one after another (`costs.md` has the measured sizes).

## 1. Check the prerequisites

`tools/README.md` lists them: Python 3.11 or newer, git, a Rust toolchain, rust-analyzer, the claude CLI, Node 18 or newer (`swarm.py` runs the phase 1 and 2 workflow scripts under it), and gh and git-filter-repo for landing. The framework checkout must contain `tools/cl` (configured as `build.cl`). Both clones must be whole: `init-workspace` checks that `git rev-list -1 HEAD` and `git cat-file -e HEAD^{tree}` work in each and reports a damaged or shallow clone.

## 2. Create the workspace

```sh
tools/init-workspace <workspace-dir>
```

It creates the directory layout, copies `templates/port.toml.example` to `<workspace-dir>/port.toml`, writes `STATE.md` from `templates/STATE.md`, and reports any missing prerequisite.

Give the REQUIRED keys on the command line, so the copy of `port.toml` has them from the start:

```sh
tools/init-workspace <workspace-dir> --app-name "<App>" --framework <framework-clone> --app <app-clone> \
    --ui-dir <ui-source-dir> [--ui-dir <another>] --how-served "<answer from step 3>"
```

The flags apply only when `port.toml` does not exist yet. The second way is to edit `port.toml` by hand. The keys are:

| Key | Value |
|---|---|
| `framework.checkout` | The local craft-libs clone |
| `app.name` | The app's display name |
| `app.checkout` | The local app clone |
| `app.ui_dirs` | The app's UI source dirs, relative to the app tree (where its egui code lives) |

`--how-served` records the dashboard answer (step 3). For an unattended start, with no developer to ask, pass `--how-served "terminal only (track show, track alerts)"`; change it later in `port.toml`.

Two more keys decide where the port starts, and the defaults can be wrong:

- `framework.branch`: the framework branch the port targets. It is `next` on the framework's upstream. When `next` does not exist there yet, use the branch the framework team names (ask the developer). Check with `git -C <framework.checkout> ls-remote --heads origin`.
- `app.base_branch`: the branch the released app builds from, which is not always the default branch. Find the latest release tag (`git -C <app.checkout> tag --sort=-creatordate | head`), then the branch that contains it (`git -C <app.checkout> branch -r --contains <tag>`). When the default branch is far behind another one, ask the developer which one is production.

Leave every other key at its default unless this machine needs a different place for it. [config.md](config.md) documents every key. From here on, run the kit tools with `PORT_KIT_CONFIG=<workspace-dir>/port.toml`, or from inside the workspace.

Record the phase: `tools/track phase 0 "setup"`.

## 3. Set up the dashboard

The dashboard is the developer's view of the port ([00-overview.md](00-overview.md), "The progress dashboard"). Set it up before the long steps, so they report to it.

1. Check `[track]` in `port.toml`. The defaults work for most ports:
   - `track.dir`: the store (`events.jsonl`, `state.json`), default `<workspace>/track`;
   - `track.out_dir`: where `track publish` writes the static page and its data, default `<workspace>/track/site`;
   - `track.stale_min`: minutes without an update before a running task shows as stale, default 20.
2. **Ask the developer how they want to view the page.** The kit never chooses a host and never exposes anything itself. Offer the four ways:
   - their own static server or tunnel, pointed at `track.out_dir` (most developers already have one, for example a local web server or a private network tunnel);
   - opening `track.out_dir/index.html` directly in a browser;
   - `tools/track serve` as a plain fallback. It binds `track.serve_host` (default `127.0.0.1`) on `track.serve_port` (default 8765), and it also lets the developer answer questions from the page;
   - no page: `track show` and `track alerts` in a terminal.
3. Record the answer in `port.toml` as `track.how_served`, in the developer's words, with the URL if there is one. `track show` prints it, so a later session knows where the page is.
4. Publish once and give the developer the address: `tools/track publish`. If they chose `track serve`, start it as a background task.
5. Put the setup steps on the board, so the long ones are visible while they run:

   ```sh
   tools/track status setup-pin todo "pin the framework rev, port branch"
   tools/track status setup-build todo "selection, cl doctor, first warm build"
   tools/track status setup-baseline todo "baseline full test run"
   tools/track status setup-racheck todo "racheck daemons"
   tools/track status setup-scip todo "SCIP indexes"
   ```

   Move each one with `track status <task> running` when you start it and `done` when its check passes. A failure is `blocked` with `--on` naming what it waits for.

## 3a. Ask the landing questions

Ask the developer now, in chat, so landing never stops on a question at the end of the port ([10-land.md](10-land.md)). Record each answer in `STATE.md` under "Now" and in port.toml where a key exists:

1. **Targets.** The app repository URL and branch the port lands on (`land.push_target`, `land.push_branch`), and the framework branch (`framework.branch`, already set in step 2).
2. **How the framework changes arrive.** One PR per build batch, or a fast-forward push (`land.framework_via`).
3. **Commit identity on the build machine.** The name and email the port's commits carry: `git config user.name` and `git config user.email` in the app checkout (`init-workspace` reports a missing email).
4. **Early CI.** May the lead push scrubbed port branches to the developer's fork and open draft PRs there, so the wasm, macOS and Windows legs run early on small diffs? Set `land.early_ci_approved = true` only on a yes; the default is no, and kit tools never push or open anything without it. Fork pushes and draft PRs only: never the upstream repository.
5. **Tools.** `git-filter-repo` must be installed (`init-workspace` reports it missing; the landing tools stop without it).

## 4. Pin the framework and make the port branch

1. Note the framework commit: the head of `framework.branch` as it is now. Write it to `plan.base` in `port.toml`. Phases 1 and 2 read the framework at this commit, and the plan's line numbers refer to it. Set `framework.repo` to the remote that has this commit: the pin in step 3 names that URL, and a commit only a fork has does not resolve for anyone building from another URL. Then run `tools/init-workspace <workspace-dir>` again. The rerun writes `plan.base` into the `plan.linebase` file, which `port-set` reads, and refills the pins in `STATE.md` (plan bases, framework branch, port and writing branches) from `port.toml`; the rest of `STATE.md` stays as written.
2. In the app checkout, create `app.port_branch` from the head of `app.base_branch` (the production branch, chosen in step 2). Write that commit to `plan.app_base`.
3. On the port branch, pin the app's framework dependency to the `plan.base` commit by git rev, never to a branch name. `tools/land/pin-framework.py` rewrites the app's Cargo manifests for every URL in `framework.patch_urls`. Commit the pin.
4. Point the app's local builds at the framework integration tree with `tools/patch-framework`. It adds a marked `[patch]` section, so the app builds against local framework changes without a push. Do not commit it.
5. Write the commits to `STATE.md` and record `tools/track event pin "framework <rev>, app <rev>" --task setup-pin`.

## 5. Make the read-only checkouts

Phases 1 and 2 agents read code at fixed commits, never at a moving branch. `tools/make-snapshots` creates the detached worktrees from the config keys below. It prints each resolved path and commit, and refuses to overwrite a path that exists. `--release <tag>` adds the optional release reference at `app.release`.

| Checkout | Commit | Key | Read by |
|---|---|---|---|
| Framework snapshot | `plan.base` | `framework.snapshot` | phase 1 and 2 agents (`{{FW}}`) |
| App snapshot | `plan.app_base` | `app.snapshot` | phase 1 and 2 agents (`{{APP_SRC}}`) |
| Production reference | `plan.app_base`, and later the production commit the port last merged | `app.production` | triage, red rounds and look work (`{{PROD}}`) |
| Release reference (optional) | the latest app release tag | `app.release` | the same, when production and the release differ |

```sh
tools/make-snapshots
```

`git worktree add --detach <path> <commit>` in the matching checkout does the same by hand. Agents never edit these trees. When production moves during the port, move `app.production` to the merged commit as part of the production merge (`10-land.md`), never by hand in between.

## 6. Set up the build loop

Every cargo command goes through the framework's `cl` ([11-build-loop.md](11-build-loop.md) explains why). In an app workspace, cl reads the app's package selection from `[workspace.metadata.cl]` in the app's root `Cargo.toml`.

1. Derive the selection with no compile: `tools/feature-selection.py` runs `cargo tree` per workspace member, which resolves dependencies and may need the network (add `--offline` when they are already fetched). It prints every workspace package that contributes a feature to a crate the framework shares (egui, eframe, the facade, the I/O crates). Write the result into `[workspace.metadata.cl]` on the port branch.
2. Check the environment traps listed in 11-build-loop.md: build scripts that track environment variables (`rerun-if-env-changed`), the app's own build script environment against the test environment, and never `-p <one crate>`. Put what you find in `unset_env` or `set_env` of `[workspace.metadata.cl]`.
3. Run `cl doctor` in the app integration tree. It must report one feature resolution.
4. Make the first warm build in the app integration tree as a background task: `cl test all --no-run`. Set `build.launcher`, `build.runner` and `build.memory_cap` first if this machine shares its cores or memory with other work.
5. When it ends, run `cl doctor` again: the target dir must hold one build of each pinned crate. A second build of a framework crate means the selection misses a package; fix the selection and rebuild.

## 7. Record the baseline test run

Run the app's full test suite once, on the port branch with no port changes, as a background task:

```sh
tools/test-run baseline --app --round 0
```

It writes the run's logs under `<work.runs>/baseline/`, the failing tests to `<work.runs>/baseline/app.failed`, and posts the counts to the dashboard as round 0; later runs number their rounds from 1. When it ends, copy the failure list to `work.baseline_failures`:

```sh
cp <work.runs>/baseline/app.failed <work.baseline_failures>
```

In phase 7, `compare-runs.py` reads this file, so a test that already fails here is never charged to the port.

If the run does not finish, or most tests fail, the build loop is wrong (a missing environment variable, a scratch directory the tests expect). Fix it and run again before going on.

## 8. Start the racheck daemons

racheck answers "does this set's code resolve and type-check" in seconds, with no cargo build, from one warm rust-analyzer per repo ([06-write.md](06-write.md) uses it).

1. Create the base checkouts as detached worktrees at the plan base: `racheck.fw_base` from the framework at `plan.base`, `racheck.app_base` from the app at `plan.app_base`. Phase 3 moves them to the writing bases once those exist.
2. Start both daemons as background tasks: `tools/racheck.py serve fw` and `tools/racheck.py serve app`. Each runs under `build.memory_cap` with `racheck.memory_gb`, and its first load takes several minutes.
3. Check that each answers: `tools/racheck.py status fw` (and `app`) reports the server ready, and `tools/racheck.py check <racheck.fw_base> --repo fw --changed <one .rs file>` returns a diagnostic list (empty on a clean base).
4. Stop them until phase 5 (`tools/racheck.py stop fw`, `stop app`), unless memory is plentiful. They load again from their warm target dirs (`racheck.fw_target`, `racheck.app_target`).

## 9. Build the SCIP indexes

The plan's audits and the writers' bundles look up "which files use exactly this item" in a sqlite table built from rust-analyzer's SCIP index. Text search cannot tell two items with the same name apart; the index can. Build one per repo, as background tasks, under the memory cap:

```sh
rust-analyzer scip <framework.snapshot> --output <work.scip>/fw.scip
tools/scip/scipdb.py build <work.scip>/fw.scip <work.scip>/fw.sqlite
rust-analyzer scip <app.snapshot> --output <work.scip>/app.scip
tools/scip/scipdb.py build <work.scip>/app.scip <work.scip>/app.sqlite
```

Check each with one query, for example `tools/scip/scipdb.py refs <work.scip>/fw.sqlite <a framework type you know>`: it must list the files that use it. Phase 3 rebuilds the framework index on the stub head ([04-contract-stubs.md](04-contract-stubs.md), step 6).

## 10. Exit

Check each item, then record `tools/track phase 1 "inventory"` and go to [02-inventory-and-map.md](02-inventory-and-map.md).

- [ ] `port.toml` has every required key, `plan.base` and `plan.app_base`.
- [ ] The landing questions are answered and recorded ([step 3a](#3a-ask-the-landing-questions)).
- [ ] The dashboard is published, `track.how_served` is recorded, and the developer has the address.
- [ ] The port branch pins the framework at `plan.base` by rev; the local patch points at `framework.integration`.
- [ ] The snapshots and the production reference exist at their commits.
- [ ] `cl doctor` is clean after the warm build.
- [ ] `work.baseline_failures` exists and the baseline counts are on the dashboard.
- [ ] Both racheck daemons answered a check.
- [ ] Both sqlite indexes answer a query.
- [ ] `STATE.md` records the commits, the selection and the baseline counts; every setup task on the board is `done`.

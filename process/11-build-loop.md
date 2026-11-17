# The build loop

How a port builds and tests without waiting for builds. It applies to every phase that compiles: setup (phase 0), stubs (3), compile gates (6), red rounds (7), look work (8) and one-off tasks.

A cargo workspace in which every app crate links the framework rebuilds far more than a change touches whenever two commands disagree about features, environment or profile. Most lost time in a port is that kind of rebuild, not compiling the change itself. The rules below keep every build in a target dir on one resolution, so a change rebuilds only what depends on it.

## The rules

1. Every cargo command goes through the framework's `cl` (`build.cl`), in the framework tree and in the app tree alike.
2. Each build tree has its own target dir, kept warm. New target dirs are seeded from a warm one.
3. Agents write in code-only trees. Build trees are few, and are held only to compile, run trials and capture.
4. No workspace-wide build or test locally, and no `--all-features` or `--bins`. CI runs those.
5. A slow loop is diagnosed from `cl`'s build records, never by timing another long run.

## cl

`cl` lives in the framework (`tools/cl` in craft-libs; craft-libs `docs/development.md` is its reference). It finds its workspace with `git rev-parse --show-toplevel` from the current directory, so the framework checkout's `cl` run inside the app tree builds the app tree. Put it on your `PATH` or set `build.cl`.

In the framework workspace:

| To | Run |
|---|---|
| check a crate you changed but do not test | `cl check <crate>` |
| build a crate's tests | `cl test <crate> --no-run` |
| run some trials | `cl test <crate> -- <filter> --test-threads 4` |
| render one component's stories as images | `cl render <crate\|ui> <Component>` |
| see the features cl adds | `cl features <crate>` |
| check the manifests for drift | `cl doctor` |
| anything else, with nothing added | `cl cargo <args>` |

For a crate whose tests you build next, skip `cl check`: the test build reports the same errors, and the check is a second build of the same crates.

In an app workspace (app mode), `cl` builds the app's whole package selection in every command:

| To | Run |
|---|---|
| test one crate | `cl test <crate> [-- <filters>]`: builds the selection's libs and tests, runs only that crate's binaries |
| test a change in one crate's lib fast | `cl test <crate> --unit [-- <filters>]`: lib binaries only |
| the integration run | `cl test all [--no-run] [-- <filters>]`: builds everything, runs every binary of the selection, longest first |
| check | `cl check all --keep-going`, or `cl check <crate>` (the selection is fixed, so every package is checked) |
| the packages and builds | `cl doctor` |

`CL_DRY_RUN=1` prints the composed cargo command and its environment and runs nothing. The kit's gates (`compile-gate`, `test-run`) call these commands; agents with builds use them directly.

## One feature resolution

cargo compiles a crate once per distinct feature set, and every crate above it once more. It unifies features only over the packages one command selects. So a framework crate's tests, an app crate's tests and the app binary each pull in different features of egui, eframe and the framework's lower crates, and each would build its own copy of the framework.

`cl` gives every command the same selection:

- In the framework workspace, it selects the `feature-root` package beside the crate of every command. Its dependencies are the gallery's, so every local build resolves features as the gallery does, and only the targets the command names are built.
- In an app workspace, it selects the app's pinned package list, in test mode, without `--features` (test features come from dev-dependencies). Each package in the list brings features the others lack; a command that drops one builds a second copy of everything above them.

After every command, `cl` names any new build of a tracked crate with its feature set. One is expected after a manifest change. Any other is a trap from the list below: find it before the next build.

## The app's selection

`cl` reads the app's settings from `[workspace.metadata.cl]` in the app's root `Cargo.toml`, on the port branch:

| Key | What it holds |
|---|---|
| `selection` | The packages every command selects. |
| `tracked` | Crates whose new builds `cl` reports after every command (egui, eframe, the app's UI crate, crates with many features). Framework crates are always tracked. |
| `expected_features` | The feature set of each pinned crate's one build. `cl doctor` compares the target dir's builds with it. |
| `unset_env` | Environment variables `cl` removes for every command (variables a build script tracks, or that the app's own scripts set differently). |
| `set_env` | Environment variables `cl` sets for every command (for example a scratch directory the tests need on a disk with room). |
| `shard` | Per test binary (`"<package>/<test target>"`), how many shards it runs as when no filter is given: split the slowest binaries. |
| `default_seconds` | Run time per test binary, used to order the first `cl test all` (longest first) before `cl` has recorded times of its own. |
| `run_slots` | How many test binaries `cl test all` runs at once (default 1). |
| `test_threads` | `--test-threads` for each test binary, unless the command passes its own. This is the one source by default: `tools/test-run` passes `--test-threads` only when `build.test_threads` is set, and then that value wins. |

`cl` refuses a table with an unknown key or a value of the wrong type. craft-libs `docs/development.md`, "App workspaces", gives the exact syntax; the app's root `Cargo.toml` on the port branch is where the values live.

To make the selection for a new app, with no build:

1. Run `tools/feature-selection.py`. It reads `cargo metadata` and `cargo tree -e features -i <crate>` and prints every workspace package that contributes a feature to a crate the framework shares (egui, eframe, the facade, the I/O crates).
2. Write the result into `[workspace.metadata.cl]` as `selection`, and add the crates it names as `tracked`.
3. Work through the traps below and fill `unset_env`.
4. Make the first warm build (`cl test all --no-run`, as a background task), then run `cl doctor`. It must report one build of each tracked crate. Copy the reported feature sets into `expected_features`.

A second build of a framework crate after that means the selection misses a package. Add it and rebuild.

## Traps that force rebuilds

Each of these makes a second copy of a crate and everything above it, or rebuilds it on every switch between two kinds of command. Check each one in phase 0 and again whenever `cl` reports a new build.

| Trap | How to find it | Fix |
|---|---|---|
| A build script tracks an environment variable that differs between commands (a fonts directory, a data path) | `git grep -n 'rerun-if-env-changed' -- '*build.rs'` in the app and framework trees | One value in every command, or unset everywhere: add it to `unset_env` |
| The app's own build script sets environment the test commands do not (for example `CARGO_INCREMENTAL=0`, a different `RUSTFLAGS`) | Diff the app's build script environment against the test environment | Remove the override, or add the variable to `unset_env`; build snapshots and dev binaries through `cl` too |
| A command selects one package (`-p <crate>`) | It changes feature unification for everything below | Never pass `-p <one crate>`; `cl` refuses it in app mode |
| The app's dev build resolves features differently from its tests (optional features turned on only by the binary) | `cl doctor` after building the binary | Put the package that turns them on into `selection` |
| rust-analyzer checks in a build target dir | Its builds use other settings | rust-analyzer gets its own target dir (`racheck.fw_target`, `racheck.app_target`) |
| Profile settings change between builds in one target dir (incremental, codegen units, opt-level overrides) | Compare the command lines in `cl.log` | Use the same settings for every build in a target dir |
| Tests that keep a scratch reserve read a large `TMPDIR` | Test failures about free space | Set one `TMPDIR` for every command |

## Target dirs and trees

- **One target dir per build tree.** `cl` uses `<worktree>-target` when that directory exists beside the worktree, else `CARGO_TARGET_DIR`, else `target/`. Never share a target dir between worktrees: some tools bake the workspace root into their binaries, so a shared dir silently tests the wrong tree.
- **Seed new target dirs.** A new target dir rebuilds every dependency. Seed it from a warm target dir of the same repo instead: `tools/seed-target <new-target> <warm-target> [<worktree>]`. Dependencies are hardlinked and stay built; only the repo's own crates rebuild. Never seed with a plain `cp -al`: cargo rewrites shared fingerprint files in place.
- **A fixed pool of build trees.** One integration tree per repo (`framework.integration`, `app.integration`) and a small fixed set of build trees, each with its own warm target dir. A task takes a free build tree, switches it to its branch, builds incrementally, and gives it back when it hands back. Each target dir costs tens of GB, so a tree per task does not scale.
- **Switch branches inside a build tree** (`git switch`), never one new tree per task. A branch checked out in a code-only tree must be released first (`git -C <code-only tree> switch --detach`). Check that the switch succeeded before rebasing: a rebase after a failed switch rewrites the tree's previous branch.
- **Code-only trees** (`work.trees`) hold one worktree per set and repo, with no target dir. Writers, fixers and reviewers work there. No cargo runs in them; `rustfmt --edition 2024 <file>` on single files is fine.
- **Keep incremental caches.** Deleting a target dir's `debug/incremental` makes its next build compile the workspace's own crates from scratch.
- **Profiles that keep the loop short** (set in the app's manifest on the port branch, once, in phase 0): dependencies optimised once per target dir, so tests run at a usable speed; `lto = "off"` in dev builds, so an edit re-optimises only the changed units; the workspace's own crates at a low opt-level, where rustc shares generic code between crates and an edit rebuilds in seconds; line-table debug info only. Changing dependency settings later rebuilds every dependency in every target dir, the developer's included.

## Launcher, runner and memory cap

Plain cargo, with test binaries run directly, is right for a machine that runs one build at a time. Set these when several builds or agents share a machine:

| Key | Passed to cl as | Use |
|---|---|---|
| `build.launcher` | `CL_LAUNCHER` | A command prefix every cargo build runs under: a wrapper that gives every build on the machine one shared jobserver in `MAKEFLAGS`. A build alone then gets every core, and builds together share them. |
| `build.runner` | `CL_RUNNER` | A command prefix the built test binaries run under: a wrapper that limits how many run at once. |
| `build.memory_cap` | (applied by the kit tools) | A prefix that caps a heavy job's memory. `{gb}` is replaced with the job's size (`build.memory_gb`, `racheck.memory_gb`). On Linux with systemd, `{kit}/tools/capped {gb}` runs the job in its own memory-capped scope, so an out-of-memory kill takes the job and not the session that started it. |
| `build.test_threads` | `--test-threads` | Threads per test binary. Unset by default, so the app manifest's `test_threads` applies; set it to override that for `tools/test-run`. A test binary otherwise starts one thread per core, and screen tests start a software renderer's threads as well. |

There is one `CL_LAUNCHER` and `CL_RUNNER` pair, used the same way in the framework workspace and in app mode.

Keep the launcher and the runner apart. Test binaries take no jobserver tokens, so a limit held for a whole build only queues the builds behind it.

## Test runs

- `cl test` builds with `cargo test --no-run` through the launcher, then runs each test binary itself through the runner, from its package's directory, as cargo would.
- In app mode, `cl test all` runs the binaries `run_slots` at a time, longest first (from the last run's recorded times, else `default_seconds`), splits the slowest binary into shards, and ends with one summary line: passed, failed, binaries, overflowed stacks, wall time. Failures follow as `binary test_name`.
- `tools/test-run` wraps this for full runs and records each run as a round. When `build.target_dir` is set, it deletes the test executables that the build superseded (`tools/trash-stale-tests`): a framework change gives every test binary a new hash, and cargo keeps the old copies.
- Read only the failing lines of a run (`agent-common.md`, "Builds and runs").

## Reading a slow loop

Every build `cl` composes passes cargo's `--timings`: a report per build in `<target>/cargo-timings/`, with each unit's start, duration and freshness, and how many units waited for a jobserver token. Every `cl` command also appends one line to `<target>/cl.log`: start time, command, build wall time, test-run wall time, exit code and the build's report.

Read a slow loop from these:

- A build much longer than its report's units: a wait before cargo started (the launcher, a lock).
- A run much longer than the tests' own `finished in`: a wait for the runner.
- A unit rebuilt that the change does not reach: a trap from the table above.
- A long serial chain in the report: a crate structure problem (for example every app crate depending on the facade), for the developer to decide.

Fix the cause, then let the next real loop confirm the fix. Never run a long build only to time it.

## Loop targets

These are the targets every loop is held to. Every agent report and every lead update gives the measured times against them. A miss is a bug the lead fixes first.

| Loop | Target |
|---|---|
| Check of the crate you changed | under 30 s |
| The tests for what you changed | under 1 min |
| A whole crate's test binary | under 2 min |
| One fix to one component, from the request to its old/new comparison | under 1 min |
| The developer's rebuild of the app after a change | under 3 min |
| A frame-time round: build after a change plus old/new measurement | under 5 min |

`process/costs.md` has what the loops measured on the last port.

## Measuring frame time

- Measure only after a change meant to cut frame time. Build-time, look and behaviour changes get no frame-time round.
- Measure the build the developer runs (the framework's `gallery` profile, or the app's equivalent), in one tree kept for measuring only, so its profile stays warm.
- Build production and the port with the same profile settings, so a ratio compares the code and not the optimisation.
- Measure old and new at the same time, on two displays, in every round. Load on a shared machine moves both by more than one fix does, and the same load cancels in the comparison.
- What a frame runs (passes per frame, runs per interaction) is asserted by count trials, not counted in the measured build.

## Disk

- When no planned task needs a worktree any more, remove it and its target dir together.
- Build outputs, worktrees and captures never go on a RAM-backed `/tmp`.
- When space runs short while builds run, trim target dirs that are not building, in this order, taking only what the next build does not need:
  1. superseded test executables (`tools/trash-stale-tests`) and older copies of libraries;
  2. `debug/examples`, `doc`, wasm output dirs, `tmp`;
  3. incremental units no build has written for a day;
  4. still short: retire one whole free build tree's target dir, least recently built first, and seed it again before its next use.
- Never trim a whole `debug/incremental` of a tree that is in use.

## What CI covers

The framework's CI runs the workspace-wide checks (format, clippy, tests with and without `--all-features`) on pushes to its main and `next` branches and on pull requests. Locally, build the crates you changed and run their trials, run `cargo fmt --all` before each push (it needs no build), and let CI run the rest. A full local CI run happens only for a specific reason (a CI failure the log cannot explain, a check CI skips), stated in the report.

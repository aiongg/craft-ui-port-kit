# Kit tools

Every tool here reads the port's config, `port.toml`, and writes its logs into the port's workspace. Nothing in the kit's own tree is written to by a tool. `process/config.md` lists every key; the tool's header comment or `--help` lists the keys it reads.

## Requirements

- Python 3.11 or later, git, bash.
- `rust-analyzer` for the racheck tools.
- The `claude` CLI for `port-set` and `swarm.py`.
- `gh` and `git-filter-repo` for landing.
- Node 18 or later: `swarm.py` runs the workflow scripts of phases 1 and 2 under it. A plain job list needs no Node.
- The framework's `cl` build tool (`build.cl`). Every cargo command the kit runs goes through it, in the framework's tree and in the app's tree (cl's app mode).
- For `look` (phase 8): Pillow and numpy, or `uv` to fetch them; on Linux, `Xvfb` for headless app instances.
- `systemd-run` only when you set `build.memory_cap` to `{kit}/tools/capped {gb}`. Without a cap, the heavy jobs run uncapped.

## Config resolution

1. Defaults in `tools/portkit/config.py` (`KEYS`).
2. `port.toml`: the file named by `PORT_KIT_CONFIG`, else `./port.toml`, else the nearest one in a parent directory.
3. Environment variables `PORT_KIT_<SECTION>_<KEY>`.

Python tools load it with `from portkit import config; cfg = config.load()`. Shell tools source `tools/portkit/lib.sh`, which defines `cfg KEY`, `cfgr KEY` (stops when the key is unset), `with_cap GB CMD...` and `track_self`. `python3 tools/portkit/config.py show` prints the resolved config.

## Dashboard events

Every long-running tool posts one event to the progress dashboard when it ends, with its duration and key numbers. Python tools do this with `track.recorded(...)`, shell tools through `track run` (`track_self` in `lib.sh` re-runs the tool under it). Without a configured store the calls do nothing. `test-run` also posts the round's pass and fail counts. See `tools/track.md`.

## Tools

### Writing sets

| Tool | What it does | Main config keys |
|---|---|---|
| `port-set` | The writer pipeline: bundle, apply, check, run, agent, plan check, fix, racheck, audit, remap, collect, status. Spec in `port-set.md`. | `work.*`, `pipeline.*`, `models.*` |
| `run-area NAME SHARED-LIST DEFAULT-LIST [N]` | Writes one area's sets N at a time. Sets with more Files rows than `pipeline.agent_files_over` use agent mode in rounds with continue rounds; smaller sets use the one-shot pipeline. Resumes a killed run. Starts only after the writer canary passes. | `pipeline.agent_*`, `pipeline.run_max_turns`, `models.write`, `models.write_shared` |
| `run-batch [--plancheck] LIST [N] [MODEL]` | Writes every set in a list with the plan check already done, or with `--plancheck` plan-checks every set. Waits while `pipeline.quota_command` reports a use at or above `pipeline.quota_cap`. | `pipeline.parallel`, `pipeline.quota_*`, `models.write`, `models.plancheck` |
| `fix-batch LIST [N] [MODEL] [TURNS]` | Applies review findings: one `port-set fix` per `<set> <findings-file>` line. A line without an existing findings file stops it before any set runs (exit 2). | `models.fix`, `pipeline.fix_max_turns` |
| `racheck.py serve\|stop\|status fw\|app`, `racheck.py check TREE --repo fw\|app --changed PATH...`, `racheck.py canary [fw\|app...] [--sets LIST...]` | rust-analyzer daemon on a read-only checkout. A check overlays a tree's changed files and returns diagnostics without a cargo build. The canary diagnoses one untouched file per repo; exit 0 with 0 errors, 1 with errors, 2 when a daemon is not running. | `racheck.*`, `framework.*`, `app.*`, `build.memory_cap` |
| `racheck-tree WORKTREE [FILE...]` | Errors of a code-only app worktree, checked against the combined framework. | `racheck.*`, `app.writing_base`, `framework.integration` |

### Combining and gating

| Tool | What it does |
|---|---|
| `combine-area NAME SET[@REV]...` | Lands each set as one net-change commit on branch `area/NAME` in the integration worktree (`REPO=fw` or `REPO=app`), prints the files where a later set overrode an earlier one, and the touched crates. |
| `combine-lost SET[@REV]...` | Lists lines a set added that the combined tree lacks; exit 1 when there is one. Run by `combine-area`, which then exits 1 too. |
| `racheck-gate LABEL` | rust-analyzer errors over every app file the combined trees changed, plus missing `mod` files. Writes `racheck-gate.json`. |
| `gate-classify.py GATE.json BATCH-LISTS --later LATER-LISTS` | Sorts a gate's errors into `later:<set>`, `ra-gap`, `mod-file`, `downstream`, `macro` and `real`. |
| `compile-gate LABEL [--fw-only\|--app-only] [CRATE...]` | `cl check --keep-going` of every touched framework crate and its workspace dependents in dependency order, never stopping at a failure, then of the app's whole selection. Exit 0 clean, 1 compile errors, 2 tool failure. Writes `summary.json`, `fw.errors`, `app.errors`. |
| `test-run LABEL [--fw [CRATE[:FILTER]]...] [--fw-all] [--app] [--baseline]` | Builds and runs test binaries through cl, counts each binary from its own result line, lists each binary's tests, compares binaries and tests with the previous run and the baseline (`compare.md`), removes superseded test executables, writes `app.failed` and `summary.json`, posts the round. Exit 0, 1 or 2 (tool failure). |
| `split-errors.py ERRORS N PREFIX` | Splits a compile's error list into N balanced groups of whole files. |
| `split-failures.py OUT-DIR N LOG...` | Splits failing tests into N groups of whole clusters. |
| `mod-lines.py` | Reads `.rs` paths on stdin and prints every `mod x;` line whose file is missing. |
| `cross-owner SET...` | Lists files a set changed that the ownership table gives to another set. |
| `move-base COMMIT` | Moves the framework writing base, drops unchanged set trees, remaps sheet line numbers, restarts the framework daemon. Prints the push command; never pushes. |
| `patch-framework [--dry-run]` | Writes the framework path patches into the app's `Cargo.toml` for local builds, from the committed lock, as marked overrides beside the app's own patch lines; a rerun changes nothing. Exit 1 when the lock takes no framework package. |
| `trash-stale-tests --dir DEPS --since EPOCH` | Removes test executables a build superseded (to the trash when a `trash` command exists, else deleted). |

### Build helpers

| Tool | What it does |
|---|---|
| `seed-target NEW-TARGET WARM-TARGET [WORKTREE]` | Seeds a cargo target dir from a warm one, so a new worktree reuses the built dependencies. Use the same toolchain. |
| `capped GB CMD...` | Runs a heavy job in its own systemd scope with a memory cap (Linux). Optional launcher through `build.memory_cap`. |
| `scip/scipdb.py` | Turns a rust-analyzer SCIP index into sqlite and answers reference queries. `scip_pb2.py` is its generated protobuf module (needs the `protobuf` Python package). |

### Other tools

`coverage.py`, `compare-runs.py`, `diag-cut.py`, `feature-selection.py`, `crate-order.py`, `swarm.py` (also `--follow-up TASK PROMPT-FILE`), `render-prompt`, `init-workspace`, `land/*`, `track`, `look`, `collect-logs` (packs a run's logs for review; README "Sending your run's logs"), `lead-context` (the plugin's SessionStart hook, `hooks/hooks.json`: prints the lead's context in a port workspace), `kit-check` and `check-workflow` (parses the workflow scripts as `swarm.py` loads them) are described in their own headers and in the process docs that use them; `track` and `look` also in `track.md` and `look.md`.

## Interfaces between tools

- `compile-gate` calls `crate-order.py WORKSPACE-DIR [--with-dependents] [--skip-outside] CRATE...`, expecting the crates one per line, dependencies first, and `skipped: <name> (not a workspace member)` lines on stderr; when it fails, the gate exits 2. `test-run` calls it with `--skip-outside`.
- Machine-readable results, for tools that chain the gates (each tool's `--help` has the full format):
  - `compile-gate`: `<work.runs>/LABEL/summary.json` (`{"tool", "label", "exit", "framework": {"crates": [{"crate", "status", "exit", "errors", "through", "seconds"}], "skipped", "errors", "errors_by_package"} | null, "app": {"status", "exit", "errors", "crates_failed", "seconds"} | null}`; status `ok`, `failed`, `failed-through`, `tool-failure`), and the last stdout line `compile-gate LABEL: exit N; framework: ...; app: ...`.
  - `test-run`: `<work.runs>/LABEL/summary.json` (`{"tool", "label", "exit", "parts": [{"part", "filter", "status", "exit", "passed", "failed", "failing", "binaries": {key: {"status", "passed", "failed", "tests"}}, "previous", "baseline", "missing", "gone", "gone_vs_baseline"}]}`; part `app` or `fw:<crate>`; binary status `ok`, `failed`, `crashed`, `not run`), `<part>.tests.tsv`, `compare.md`, the index `<work.runs>/test-runs.tsv` and `<work.runs>/baseline.json`, and the last stdout line `test-run LABEL: exit N; <part>: ...`.
  - `swarm.py --follow-up TASK PROMPT-FILE`: one JSON object on stdout, `{"task", "ok", "value", "error", "session_id", "cost_usd", "job_dir"}`; exit 0 ok, 1 failed call, 2 no such task or session.
- `swarm.py` job roles: `ROLE_TOOLS` in `swarm.py` maps a `[models]` role to the commands its jobs may run; a job list names it as `role`, a workflow as `opts.role`. A job's `inputs` files are part of its resume key.
- `compile-gate` and `test-run` call `cl check all` and `cl test all` in the app tree: cl's app mode with the selection from `[workspace.metadata.cl]`.
- `run-area`, `run-batch`, `fix-batch` and `move-base` call `port-set` with the subcommands and flags in `port-set.md`.
- Set output lives in `<work.sets>/<set>/`: `plancheck.md`, `run.log`, `agent.log`, `check.md`, `base-fw`, `base-app`, `landed`. Set trees are `<work.trees>/<set>` and `<work.trees>/<set>-<repo>`.

## Selftest

`tools/selftest/run [-v] [CASE...]` runs every fixture case in `tools/selftest/cases/`, each in a fresh scratch workspace with its own `port.toml`, and prints `selftest: <n> passed, <n> failed` (exit 1 on a failure). It needs no build and no network. Run it after changing a tool it covers, and add a case with every tool fault you fix.

Stubs in `tools/selftest/stubs/`, for cases of any tool:

- `cl`: prints `<STUB_CL_LOGS>/<key>.log` and exits with `<key>.rc` (0 when missing). The key is the command word and its first argument, plus `-no-run` with `--no-run` (`check-craft-ui`, `check-all`, `test-all-no-run`, `test-all`); `<key>.<n>.log` and `<key>.<n>.rc`, when present, answer the n-th call of that key. Every call is appended to `<STUB_CL_LOGS>/calls.jsonl`. `lib.Scratch` points `build.cl` at it; `Scratch.cl_log(key, text, rc)` writes a canned answer, and canned logs live in `tools/selftest/fixtures/`.
- `cargo`: answers `cargo metadata` with the tree's `.stub-metadata.json` (`lib.cargo_metadata()` writes one).
- `claude`: records each call (`<STUB_CLAUDE_DIR>/calls.jsonl`) and answers like `claude -p --output-format json`, keeping the `--resume` session id.

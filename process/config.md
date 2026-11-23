# port.toml reference

Every kit tool reads one config file per port: `port.toml` at the root of the port's workspace. This page lists every key, its default, and the tools that read it. `templates/port.toml.example` is a filled-in starting point; `tools/init-workspace` copies it into a new workspace.

`tools/portkit/config.py` is the loader every tool uses, and its `KEYS` list is the source of the tables below. After changing a key, regenerate the tables with `python3 tools/portkit/config.py doc` and paste them over the section "Keys".

## Where the config comes from

Lowest precedence first:

1. The defaults in the tables below.
2. `port.toml`. The tools look for it in this order:
   1. the file named by `PORT_KIT_CONFIG`;
   2. `./port.toml`;
   3. the nearest `port.toml` in a parent of the current directory.

   With none found, the tools run on defaults and environment only, and any tool that needs a required key stops and names it.
3. Environment variables `PORT_KIT_<SECTION>_<KEY>`: the key path in upper case with dots as underscores. For example, `PORT_KIT_BUILD_LAUNCHER` sets `build.launcher` and `PORT_KIT_PIPELINE_BUNDLE_SMALL` sets `pipeline.bundle.small`. `land.private_patterns` also reads `PORT_KIT_PRIVATE_PATTERNS`. A `PORT_KIT_` variable that names no key prints a warning.
4. Overrides a tool passes on its command line (`config.py --set KEY=VALUE`).

`python3 tools/portkit/config.py env` lists every variable name.

### Value syntax

- **Lists** in the environment are a JSON array (`'["a","b"]'`) or comma-separated (`a,b`).
- **Booleans** in the environment are `1`/`0`, `true`/`false`, `yes`/`no` or `on`/`off`.
- **References.** A string can name another key as `{section.key}`, and `{kit}` is the kit's root directory. A value that is exactly one reference takes that key's value and type, so `facade_dirs = "{app.ui_dirs}"` is a list. A value built on an unset key is unset too.
- **Paths** expand `~` and environment variables. Relative paths resolve against the directory of `port.toml`, or against the current directory when there is no file.
- **Literal braces.** `{gb}` in `build.memory_cap` is not a reference. The tool that applies the cap replaces it with the job's memory size.

### Unknown keys

A key in `port.toml` that the tables don't list prints a warning and is ignored. `[[areas]]` and `[[lints]]` entries with unknown fields are errors.

## Path roles

The tools never hard-code a machine path. Each tree the port uses has a role:

| Role | Key | What it is |
|---|---|---|
| Workspace | `work.dir` | Plans, maps, per-set output, logs, `STATE.md`. Not a git repo of either project. |
| Set trees | `work.trees` | One git worktree per set and repo (`<set>`, or `<set>-<repo>` for a set's second repo), plus the read-only base checkouts. Code only: no target dirs. |
| Framework clone | `framework.checkout` | Your craft-libs clone. Worktrees and branches are made from it. |
| Framework integration tree | `framework.integration` | Where combines and compile gates run. One warm target dir. |
| App clone | `app.checkout` | Your clone of the app. |
| App integration tree | `app.integration` | Where app combines, compile gates and full test runs run. One warm target dir. |
| Planning snapshots | `framework.snapshot`, `app.snapshot` | Read-only checkouts at `plan.base` and `plan.app_base`. Phase 1 and 2 agents read these, so their answers stay valid while the branches move. |
| racheck bases | `racheck.fw_base`, `racheck.app_base` | Read-only checkouts at the writing bases. The rust-analyzer daemons load them; app writers read the framework through `racheck.fw_base`. |
| Production reference | `app.production` | Read-only checkout of the app's production main at the commit the port last merged. It is the behaviour reference for triage, red rounds and look work. |
| Release reference | `app.release` | Optional read-only checkout of the latest release. |

Two roles may share one directory, for example `app.integration = "{app.checkout}"` (the default) on a machine with room for one app target dir only.

## How cargo runs

Every cargo command goes through the framework's `cl` (`build.cl`). cl selects one feature resolution for every command, so builds never make a second copy of the framework. In an app workspace, cl reads the app's package selection from `[workspace.metadata.cl]` in the app's root `Cargo.toml`. `tools/feature-selection.py` derives that selection for a new app without a build. process/11-build-loop.md covers cl, the selection and the rebuild traps.

The kit tools pass `build.launcher` to cl as `CL_LAUNCHER` and `build.runner` as `CL_RUNNER`. Both default to empty, which means plain cargo and test binaries run directly. That is the right setting for a machine that runs one build at a time. Set them when several builds share a machine: the launcher for a jobserver wrapper, the runner for a wrapper that limits how many test binaries run at once. `build.memory_cap` wraps heavy jobs the kit starts itself (rust-analyzer daemons, swarm batches, gates). On Linux with systemd, `{kit}/tools/capped {gb}` runs each job in its own memory-capped scope.

## Agent batches

`pipeline.batch_runner` chooses how a batch of agents runs. With `swarm` (the default), `tools/swarm.py` runs `claude -p` over a job list and needs only the claude CLI. With `workflow`, the scripts in `workflows/` run through Claude Code's Workflow tool, for those who have it. Both read the same args. Not every developer uses Claude Code, so the scripts are written to be read and adapted by any agent.

## Landing

`land.framework_via = "pr"` sends framework changes to `framework.branch` as one PR per build batch, which a framework maintainer fast-forwards. `framework.branch` holds the framework until every app has ported; it merges to the framework's main branch only after that, because an earlier merge would strand the apps that still build against main. The app's landed branch goes straight to `land.push_target` / `land.push_branch`. The scrub always runs first. `land.early_ci_approved` records the developer's standing approval, asked in phase 0, for pushing scrubbed branches to their fork (`land.early_ci_fork`) and opening draft PRs there; it is false until they say yes. The landing tools work in scratch clones under `work.landing` and print the push commands; `land/early-ci.sh` is the one tool that pushes, to the fork only and only with that approval. `land.sync_after_commits` (100) is a placeholder, not a measured value: replace it when the logs of a port show how far upstream moves in a day.

`land.private_patterns` names a file outside every repo with the scrub patterns that identify you and your machine: names, handles, emails, hostnames, local tree names. Its format: one Python regular expression per line, matched case-insensitively; blank lines and lines starting with `#` are ignored. CONTRIBUTING.md describes how the kit repo itself uses the same file.

## Areas and lints

`[[areas]]` lists the port's areas. Phase 1 chooses them from the inventory. Set ids are `<area>-w<n>` and contract ids `<code>.<Kind><n>`, so tools find a set's area and code from this table. PhotoCraft's areas: `top` (tp), `panels` (pn), `dialogs` (dl), `canvas-widgets` (cw), `tools` (tl), `framework-01` (fx, framework only) and `hub` (cx).

`framework.lints_file` holds the framework lints port-set checks every written file against. Each lint is labelled with the framework revision it was written for. `[[lints]]` entries in `port.toml` add lints for one port.

## Prompt placeholders

`tools/render-prompt` fills `{{NAME}}` placeholders in `prompts/` and `templates/` from the resolved config. Per-call values (`{{AREA}}`, `{{SET}}`, …) are given as `NAME=VALUE` arguments (`tools/render-prompt p7-red-fixer TRACK=g3 ROUND=run-4 TASK=red-g3`). `python3 tools/portkit/config.py placeholders` prints every config placeholder with its resolved value. A placeholder with no value stays in the text as `{{NAME}}`, and render-prompt names it on stderr with the key that fills it (`--strict` makes that an error).

## Keys

### [work]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `dir` | path | port.toml's directory | all | Workspace root: plans, maps, per-set output, logs, STATE.md. Default: the directory holding port.toml. Placeholder `{{WORK}}`. Env: `PORT_KIT_WORK_DIR`. |
| `trees` | path | `{work.dir}/trees` | port-set, run-area, combine-area, combine-lost, cross-owner, move-base, racheck.py, init-workspace | Per-set git worktrees (`<set>` and `<set>-<repo>`) and the read-only base checkouts. Placeholder `{{TREES}}`. Env: `PORT_KIT_WORK_TREES`. |
| `inventory` | path | `{work.dir}/inventory` | workflows/phase1-inventory-map.js, render-prompt | Phase 1 chunk inventory (`chunk-NN.json`). Placeholder `{{INVENTORY}}`. Env: `PORT_KIT_WORK_INVENTORY`. |
| `maps` | path | `{work.dir}/port-map` | coverage.py, render-prompt | Phase 1 area maps (`<area>.md`) and their index (`README.md`). Placeholder `{{MAPS}}`. Env: `PORT_KIT_WORK_MAPS`. |
| `plan` | path | `{work.dir}/plan` | init-workspace, render-prompt | Phase 2 output root. Placeholder `{{PLAN}}`. Env: `PORT_KIT_WORK_PLAN`. |
| `sheets` | path | `{work.plan}/sheets` | port-set, run-area, coverage.py, render-prompt | Writer sheets, one per set (`<area>-w<n>.md`). Placeholder `{{SHEETS}}`. Env: `PORT_KIT_WORK_SHEETS`. |
| `parts` | path | `{work.plan}/contract-parts` | port-set, render-prompt | Contract parts (`NN.md`), the stub target. Placeholder `{{PARTS}}`. Env: `PORT_KIT_WORK_PARTS`. |
| `ownership` | path | `{work.plan}/ownership.md` | coverage.py, gate-classify.py, render-prompt | File ownership: every file the port writes, in exactly one set. Placeholder `{{OWNERSHIP}}`. Env: `PORT_KIT_WORK_OWNERSHIP`. |
| `settled` | path | `{work.plan}/settled.md` | port-set, render-prompt | Design questions settled during planning. Placeholder `{{SETTLED}}`. Env: `PORT_KIT_WORK_SETTLED`. |
| `sets` | path | `{work.dir}/sets` | port-set, run-area, run-batch, fix-batch, combine-area, combine-lost, cross-owner, move-base, gate-classify.py, render-prompt | Per-set output dirs (bundle, edits, check.md, plancheck.md, decisions.md, review findings, base-<repo>). Placeholder `{{SETS}}`. Env: `PORT_KIT_WORK_SETS`. |
| `decide` | path | `{work.dir}/decide` | port-set, cross-owner, gate-classify.py, render-prompt | DECIDE collection per area (`<area>.md`) and `owners.tsv`. Placeholder `{{DECIDE}}`. Env: `PORT_KIT_WORK_DECIDE`. |
| `runs` | path | `{work.dir}/runs` | compile-gate, test-run, racheck-gate, compare-runs.py, diag-cut.py, split-failures.py | Compile and test run logs, one dir per run label. Placeholder `{{RUNS}}`. Env: `PORT_KIT_WORK_RUNS`. |
| `scip` | path | `{work.dir}/scip` | port-set, scip/scipdb.py, init-workspace | SCIP sqlite indexes (`fw.sqlite`, `app.sqlite`). Env: `PORT_KIT_WORK_SCIP`. |
| `swarm` | path | `{work.dir}/swarm` | swarm.py, init-workspace | swarm.py's run dirs, one per workflow or job list: each job's prompt, reply and checked result (the resume cache), the run log and the script's return value. Env: `PORT_KIT_WORK_SWARM`. |
| `usage_log` | path | `{work.dir}/usage.tsv` | port-set, swarm.py | Token and cost log of every model call. Env: `PORT_KIT_WORK_USAGE_LOG`. |
| `state` | path | `{work.dir}/STATE.md` | init-workspace, port-set | The lead's phase state file. Placeholder `{{STATE}}`. Env: `PORT_KIT_WORK_STATE`. |
| `baseline_failures` | path | `{work.dir}/baseline-failures.txt` | test-run, compare-runs.py | Tests that fail on the unported app at the pinned framework rev (phase 0). Env: `PORT_KIT_WORK_BASELINE_FAILURES`. |
| `landing` | path | `{work.dir}/landing` | land/land-framework.sh, land/land-app.sh | Scratch clones and scan reports of landing runs. Env: `PORT_KIT_WORK_LANDING`. |

### [framework]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `repo` | str | `https://github.com/storytold/craft-libs` | land/land-framework.sh, land/early-ci.sh, land/pin-framework.py, patch-framework, sync, cycle, prompts | Framework repository URL. It must be the remote that holds plan.base: the pin names this URL and a rev only that remote has does not resolve for anyone else. Placeholder `{{FW_REPO}}`. Env: `PORT_KIT_FRAMEWORK_REPO`. |
| `branch` | str | `next` | land/land-framework.sh, land/early-ci.sh, sync, cycle, init-workspace, prompts | Framework branch the port targets: `next` on the framework's upstream; when it does not exist there yet, the branch the framework team names. Pins and landing use it. Placeholder `{{FW_BRANCH}}`. Env: `PORT_KIT_FRAMEWORK_BRANCH`. |
| `checkout` | path | required | move-base, patch-framework, init-workspace | Local framework clone. Branches and worktrees are made from it. Placeholder `{{FW_CHECKOUT}}`. Env: `PORT_KIT_FRAMEWORK_CHECKOUT`. |
| `integration` | path | `{framework.checkout}` | combine-area, combine-lost, compile-gate, test-run, patch-framework, racheck-tree, racheck-gate, look, portkit/gates.py | Framework integration worktree: combines and compile gates run here. Placeholder `{{FW_INT}}`. Env: `PORT_KIT_FRAMEWORK_INTEGRATION`. |
| `snapshot` | path | `{work.trees}/snap-fw` | init-workspace, make-snapshots, workflows, prompts | Read-only framework checkout at plan.base, read by phase 1 and 2 agents. Placeholder `{{FW}}`. Env: `PORT_KIT_FRAMEWORK_SNAPSHOT`. |
| `writing_base` | str | `port/stubs` | port-set, combine-area, move-base, racheck.py, compile-gate, racheck-tree, racheck-gate | Framework branch the writers start from: the contract stubs (phase 3). Placeholder `{{FW_WRITING_BASE}}`. Env: `PORT_KIT_FRAMEWORK_WRITING_BASE`. |
| `facade` | str | `craft` | port-set, prompts, feature-selection.py, racheck.py | Facade crate. App code reaches every member crate through it. Placeholder `{{FACADE}}`. Env: `PORT_KIT_FRAMEWORK_FACADE`. |
| `facade_manifest` | str | `crates/craft/Cargo.toml` | port-set, racheck.py | Facade manifest, relative to the framework tree; its dependencies give the member crates. Env: `PORT_KIT_FRAMEWORK_FACADE_MANIFEST`. |
| `lints_file` | path | `{kit}/rules/lints.toml` | port-set | Framework lints, labelled by the framework revision they were written for. `[[lints]]` tables in port.toml add to them. Env: `PORT_KIT_FRAMEWORK_LINTS_FILE`. |
| `patch_urls` | list | `["{framework.repo}"]` | patch-framework, land/pin-framework.py, test-run | Framework URLs the app's Cargo manifests may name (upstream and forks); patch-framework and pin-framework rewrite each. Env: `PORT_KIT_FRAMEWORK_PATCH_URLS`. |

### [app]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `name` | str | required | port-set, prompts | Display name of the app. Placeholder `{{APP}}`. Env: `PORT_KIT_APP_NAME`. |
| `id` | str | from app.name | init-workspace, prompts | Short lowercase id for file and branch names. Default: app.name lowercased, spaces to dashes. Placeholder `{{APP_ID}}`. Env: `PORT_KIT_APP_ID`. |
| `checkout` | path | required | init-workspace, patch-framework, land/land-app.sh | Local app clone. Branches and worktrees are made from it. Placeholder `{{APP_CHECKOUT}}`. Env: `PORT_KIT_APP_CHECKOUT`. |
| `integration` | path | `{app.checkout}` | combine-area, combine-lost, compile-gate, test-run, patch-framework, racheck-tree, racheck-gate, gate-classify.py, feature-selection.py, look, portkit/gates.py | App integration worktree: combines, compile gates and full test runs run here. Placeholder `{{APP_INT}}`. Env: `PORT_KIT_APP_INTEGRATION`. |
| `snapshot` | path | `{work.trees}/snap-app` | init-workspace, make-snapshots, coverage.py, workflows, prompts, render-prompt | Read-only app checkout at plan.app_base, read by phase 1 and 2 agents. Placeholder `{{APP_SRC}}`. Env: `PORT_KIT_APP_SNAPSHOT`. |
| `production` | path | `{work.trees}/prod` | prompts, compare-runs.py, make-snapshots | Read-only checkout of the app's production main at the commit the port last merged: the behaviour reference for triage, red rounds and look work. Placeholder `{{PROD}}`. Env: `PORT_KIT_APP_PRODUCTION`. |
| `release` | path | unset | prompts | Optional read-only checkout of the latest app release. Placeholder `{{RELEASE}}`. Env: `PORT_KIT_APP_RELEASE`. |
| `upstream` | str | unset | land/land-app.sh, sync, cycle, prompts | App repository URL (production). Placeholder `{{APP_UPSTREAM}}`. Env: `PORT_KIT_APP_UPSTREAM`. |
| `base_branch` | str | `main` | land/land-app.sh, sync, cycle, prompts | Branch the released app builds from: the branch of the latest release tag (`git branch -r --contains <tag>`), which can differ from the default branch. Placeholder `{{APP_BASE_BRANCH}}`. Env: `PORT_KIT_APP_BASE_BRANCH`. |
| `port_branch` | str | `port/framework` | init-workspace, land/land-app.sh, prompts | App branch that carries the port. Placeholder `{{APP_PORT_BRANCH}}`. Env: `PORT_KIT_APP_PORT_BRANCH`. |
| `writing_base` | str | `port/app-base` | port-set, combine-area, racheck.py, racheck-tree, racheck-gate | App branch the writers start from. Placeholder `{{APP_WRITING_BASE}}`. Env: `PORT_KIT_APP_WRITING_BASE`. |
| `ui_dirs` | list | required | coverage.py, gate-classify.py, workflows/phase1-inventory-map.js, prompts, render-prompt, racheck.py | UI source dirs, relative to the app tree: what phase 1 inventories and coverage checks. Placeholder `{{UI_DIRS}}`. Env: `PORT_KIT_APP_UI_DIRS`. |
| `facade_dirs` | list | `{app.ui_dirs}` | port-set | App dirs whose code must reach framework crates through the facade, relative to the app tree. Env: `PORT_KIT_APP_FACADE_DIRS`. |

### [plan]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `base` | str | unset | port-set, coverage.py, workflows, prompts, test-run | Framework commit the plan was made against; phase 3 stubs are diffed from it. Placeholder `{{PLAN_BASE}}`. Env: `PORT_KIT_PLAN_BASE`. |
| `app_base` | str | unset | coverage.py, workflows, prompts | App commit the plan was made against. Placeholder `{{APP_PLAN_BASE}}`. Env: `PORT_KIT_PLAN_APP_BASE`. |
| `linebase` | path | `{work.plan}/LINEBASE` | port-set, move-base | State file holding the framework commit that sheet and contract line numbers refer to. init-workspace writes plan.base into it; `port-set remap` moves it. Env: `PORT_KIT_PLAN_LINEBASE`. |
| `chunk_lines` | int | `3000` | workflows/phase1-inventory-map.js, render-prompt | Target size of one inventory chunk, in lines. Env: `PORT_KIT_PLAN_CHUNK_LINES`. |
| `chunk_map_lines` | int | `250` | render-prompt | Target size of one plan chunk, in area-map lines. Plan chunks hold whole map sections. Env: `PORT_KIT_PLAN_CHUNK_MAP_LINES`. |
| `answer_groups_per_agent` | int | `3` | workflows/phase2-part.js | Question groups one answering agent takes. Env: `PORT_KIT_PLAN_ANSWER_GROUPS_PER_AGENT`. |
| `max_error_rate` | float | `0.1` | workflows/phase2-final.js, prompts | Highest sampled plan error rate that passes the evaluation. Env: `PORT_KIT_PLAN_MAX_ERROR_RATE`. |
| `max_wrong_answers` | float | `0.1` | workflows/phase2-final.js, prompts | Highest share of wrong fact answers that passes the accuracy check. Env: `PORT_KIT_PLAN_MAX_WRONG_ANSWERS`. |
| `build_batches` | int | unset | track | How many build batches the write order has (pilot included), set when the order is fixed (process/06-write.md). `track eta` counts the batches still to come from it. Unset: the projection counts the current batch only. Env: `PORT_KIT_PLAN_BUILD_BATCHES`. |

### [racheck]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `fw_base` | path | `{work.trees}/racheck-fw` | racheck.py, racheck-tree, racheck-gate, move-base, port-set | Read-only framework checkout at framework.writing_base, the framework daemon's root; app writers read it. Placeholder `{{FW_REF}}`. Env: `PORT_KIT_RACHECK_FW_BASE`. |
| `app_base` | path | `{work.trees}/racheck-app` | racheck.py, racheck-tree, racheck-gate, port-set | Read-only app checkout at app.writing_base, the app daemon's root. Placeholder `{{APP_REF}}`. Env: `PORT_KIT_RACHECK_APP_BASE`. |
| `fw_target` | path | `{work.trees}/racheck-fw-target` | racheck.py | rust-analyzer target dir for the framework daemon. Env: `PORT_KIT_RACHECK_FW_TARGET`. |
| `app_target` | path | `{work.trees}/racheck-app-target` | racheck.py | rust-analyzer target dir for the app daemon. Env: `PORT_KIT_RACHECK_APP_TARGET`. |
| `sockets` | path | `{work.trees}` | racheck.py, racheck-gate, move-base | Directory of the daemons' sockets and logs. Env: `PORT_KIT_RACHECK_SOCKETS`. |
| `memory_gb` | int | `16` | racheck.py | Memory cap per daemon in GB, applied through build.memory_cap. Env: `PORT_KIT_RACHECK_MEMORY_GB`. |
| `gap_patterns` | list | `["Harness", "kittest", "`ctx` on type `&?(mut )?Ui`", "`input` on type `&?(mut )?Ui`", "run_ui", "__register_", "egui_kittest"]` | gate-classify.py | Regexes for diagnostics rust-analyzer reports wrongly (test harness and macro gaps); gates class them `ra-gap`. Env: `PORT_KIT_RACHECK_GAP_PATTERNS`. |

### [build]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `cl` | path | `{framework.checkout}/tools/cl` | compile-gate, test-run | The framework's cl. Every cargo command goes through it. Env: `PORT_KIT_BUILD_CL`. |
| `launcher` | str | `""` | compile-gate, test-run | Command prefix every cargo build runs under (for example a shared jobserver). Passed to cl as CL_LAUNCHER. Empty: plain cargo. Env: `PORT_KIT_BUILD_LAUNCHER`. |
| `runner` | str | `""` | compile-gate, test-run | Command prefix the built test binaries run under. Passed to cl as CL_RUNNER. Empty: run directly. Env: `PORT_KIT_BUILD_RUNNER`. |
| `memory_cap` | str | `""` | racheck.py, swarm.py, compile-gate, test-run | Command prefix that caps a heavy job's memory; `{gb}` is replaced with the job's GB (example: `{kit}/tools/capped {gb}`). Empty: no cap. Env: `PORT_KIT_BUILD_MEMORY_CAP`. |
| `memory_gb` | int | `28` | compile-gate, test-run | Memory cap in GB for builds and test runs under build.memory_cap. Env: `PORT_KIT_BUILD_MEMORY_GB`. |
| `test_threads` | int | unset | test-run | --test-threads for test binaries. Unset: test-run passes none, and cl uses the app manifest's `[workspace.metadata.cl] test_threads`. Env: `PORT_KIT_BUILD_TEST_THREADS`. |
| `target_dir` | path | `""` | compile-gate, test-run | CARGO_TARGET_DIR for the integration trees. Empty: cl's default (`<worktree>-target` when it exists). Env: `PORT_KIT_BUILD_TARGET_DIR`. |
| `warm_check_s` | int | unset | cycle, render-prompt | Seconds of a warm `compile-gate` of the app after a one-file change, measured in phase 0. With build.full_run_s it sets the fixer mode when pipeline.fixer_mode is `auto`. Unset: not measured. Env: `PORT_KIT_BUILD_WARM_CHECK_S`. |
| `full_run_s` | int | unset | cycle, render-prompt | Seconds of one full `test-run --app` (build already warm), measured in phase 0. Unset: not measured. Env: `PORT_KIT_BUILD_FULL_RUN_S`. |

### [pipeline]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `batch_runner` | str | `swarm` | workflows/README | How agent batches run: `swarm` (tools/swarm.py, claude CLI only) or `workflow` (the Workflow tool). Env: `PORT_KIT_PIPELINE_BATCH_RUNNER`. |
| `parallel` | int | `6` | run-area, run-batch, fix-batch, swarm.py | Sets or jobs run at once. Env: `PORT_KIT_PIPELINE_PARALLEL`. |
| `agent_files_over` | int | `15` | run-area | A sheet with more Files rows than this goes to agent mode; smaller ones to the one-shot pipeline. Env: `PORT_KIT_PIPELINE_AGENT_FILES_OVER`. |
| `run_max_turns` | int | `25` | port-set | Turn limit of a one-shot write call (`port-set run`). Env: `PORT_KIT_PIPELINE_RUN_MAX_TURNS`. |
| `repairs` | int | `1` | port-set | Repair calls after a one-shot write whose check fails. Env: `PORT_KIT_PIPELINE_REPAIRS`. |
| `agent_max_turns` | int | `200` | port-set | Turn limit of `port-set agent` run on its own. Env: `PORT_KIT_PIPELINE_AGENT_MAX_TURNS`. |
| `agent_round_turns` | int | `100` | run-area | Turn limit of one agent-mode round in run-area. Env: `PORT_KIT_PIPELINE_AGENT_ROUND_TURNS`. |
| `agent_continue_rounds` | int | `3` | run-area | Continue rounds for an agent-mode set while its check names an error or it ran out of turns. Env: `PORT_KIT_PIPELINE_AGENT_CONTINUE_ROUNDS`. |
| `plancheck_max_turns` | int | `14` | port-set | Turn limit of a plan check. Env: `PORT_KIT_PIPELINE_PLANCHECK_MAX_TURNS`. |
| `fix_max_turns` | int | `40` | port-set, fix-batch | Turn limit of a review-fix call. Env: `PORT_KIT_PIPELINE_FIX_MAX_TURNS`. |
| `lookup_tools` | str | `Read,Grep,Glob,Bash(git grep:*),Bash(git show:*),Bash(git ls-files:*),Bash(track:*)` | port-set, swarm.py | Tools a one-shot writer or plan check may use to look things up. Env: `PORT_KIT_PIPELINE_LOOKUP_TOOLS`. |
| `job_max_turns` | int | `300` | swarm.py | Turn limit of one swarm.py job. Env: `PORT_KIT_PIPELINE_JOB_MAX_TURNS`. |
| `quota_command` | str | `""` | run-batch, swarm.py | Command printing the plan's current 5-hour window use as a percent. Empty: never wait on quota. Env: `PORT_KIT_PIPELINE_QUOTA_COMMAND`. |
| `quota_cap` | int | `90` | run-batch, swarm.py | Start no new job while quota_command reports at or above this. Env: `PORT_KIT_PIPELINE_QUOTA_CAP`. |
| `weekly_quota_command` | str | `""` | cycle, track | Command printing the plan's weekly use as a percent. cycle records it with each cycle, and `track eta` projects it to the finish. Empty: no weekly line in the projection. Env: `PORT_KIT_PIPELINE_WEEKLY_QUOTA_COMMAND`. |
| `fixer_mode` | str | `code-only` | cycle, render-prompt | How compile and red fixers work: `code-only` (no cargo; DIAG prints where unsure), `build` (each fixer takes a build tree and runs `cl check` or its own failing tests), or `auto` (`build` when build.warm_check_s plus build.full_run_s is at most pipeline.fixer_build_max_s, else `code-only`). Writers are code-only in every mode (process/11-build-loop.md, rule 3). Env: `PORT_KIT_PIPELINE_FIXER_MODE`. |
| `fixer_build_max_s` | int | `600` | cycle, render-prompt | The `auto` threshold in seconds on build.warm_check_s plus build.full_run_s. The default is a placeholder until measured ports set it. Env: `PORT_KIT_PIPELINE_FIXER_BUILD_MAX_S`. |
| `followup_timeout_min` | int | `120` | cycle | Minutes cycle waits for one fixer's follow-up. A fixer past it is named as stalled in the cycle's summary and report, and the cycle ends without it. Env: `PORT_KIT_PIPELINE_FOLLOWUP_TIMEOUT_MIN`. |

### [pipeline.bundle]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `context` | int | `12` | port-set | Lines of context around each line range a sheet names. Env: `PORT_KIT_PIPELINE_BUNDLE_CONTEXT`. |
| `snippet_cap` | int | `260` | port-set | Most lines of one excerpt. Env: `PORT_KIT_PIPELINE_BUNDLE_SNIPPET_CAP`. |
| `big` | int | `800` | port-set | An edited file longer than this goes in as an outline plus the parts the sheet names. Env: `PORT_KIT_PIPELINE_BUNDLE_BIG`. |
| `big_context` | int | `30` | port-set | Context lines around named parts of a big file. Env: `PORT_KIT_PIPELINE_BUNDLE_BIG_CONTEXT`. |
| `big_cap` | int | `700` | port-set | Most lines taken from one big file. Env: `PORT_KIT_PIPELINE_BUNDLE_BIG_CAP`. |
| `small` | int | `120` | port-set | Files up to this many lines always go in whole. Env: `PORT_KIT_PIPELINE_BUNDLE_SMALL`. |
| `small_edit` | int | `30` | port-set | A file up to `big` lines goes in whole when its row writes plus deletes at least this many lines. Env: `PORT_KIT_PIPELINE_BUNDLE_SMALL_EDIT`. |
| `excerpt_budget` | int | `120000` | port-set | Characters of excerpts from files outside the Files table; the rest is listed by location. Env: `PORT_KIT_PIPELINE_BUNDLE_EXCERPT_BUDGET`. |

### [models]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `default` | str | `sonnet` | swarm.py | Model for a job that names no role. Env: `PORT_KIT_MODELS_DEFAULT`. |
| `inventory` | str | `haiku` | workflows/phase1-inventory-map.js | Phase 1 chunk inventory. Env: `PORT_KIT_MODELS_INVENTORY`. |
| `area_map` | str | `opus` | workflows/phase1-inventory-map.js | Phase 1 area maps. Env: `PORT_KIT_MODELS_AREA_MAP`. |
| `index` | str | `opus` | workflows/phase1-inventory-map.js | Phase 1 map index. Env: `PORT_KIT_MODELS_INDEX`. |
| `questions` | str | `opus` | workflows/phase2-part.js | Phase 2 question split. Env: `PORT_KIT_MODELS_QUESTIONS`. |
| `answers` | str | `haiku` | workflows/phase2-part.js | Phase 2 fact answers. Env: `PORT_KIT_MODELS_ANSWERS`. |
| `chunk_plan` | str | `opus` | workflows/phase2-part.js | Phase 2 chunk plans. Env: `PORT_KIT_MODELS_CHUNK_PLAN`. |
| `area_merge` | str | `opus` | workflows/phase2-final.js | Phase 2 area merge, conflict check, consolidation. Env: `PORT_KIT_MODELS_AREA_MERGE`. |
| `evaluate` | str | `opus` | workflows/phase2-final.js | Phase 2 evaluation. Env: `PORT_KIT_MODELS_EVALUATE`. |
| `sheet_fix` | str | `sonnet` | workflows/phase2-fix.js, workflows/phase2-reconcile.js | Phase 2 sheet fixes. Env: `PORT_KIT_MODELS_SHEET_FIX`. |
| `stubs` | str | `sonnet` | swarm.py | Phase 3 contract-stub stages. Env: `PORT_KIT_MODELS_STUBS`. |
| `plancheck` | str | `sonnet` | port-set, run-batch | Phase 4 plan check per set. Env: `PORT_KIT_MODELS_PLANCHECK`. |
| `decide` | str | `opus` | swarm.py | Phase 4 decision parts. Env: `PORT_KIT_MODELS_DECIDE`. |
| `consistency` | str | `opus` | swarm.py | Phase 4 consistency pass. Env: `PORT_KIT_MODELS_CONSISTENCY`. |
| `write` | str | `sonnet` | port-set, run-area, run-batch | Phase 5 writer, default. Env: `PORT_KIT_MODELS_WRITE`. |
| `write_shared` | str | `opus` | run-area | Phase 5 writer for sets that change a shared mechanism. Env: `PORT_KIT_MODELS_WRITE_SHARED`. |
| `retry` | str | `opus` | run-area, run-batch | Retry of a set a Sonnet writer failed. Env: `PORT_KIT_MODELS_RETRY`. |
| `review` | str | `opus` | swarm.py | Phase 6 area review. Env: `PORT_KIT_MODELS_REVIEW`. |
| `fix` | str | `sonnet` | port-set, fix-batch | Phase 6 review fixes. Env: `PORT_KIT_MODELS_FIX`. |
| `fix_retry` | str | `opus` | fix-batch | Fix of a set that failed twice. Env: `PORT_KIT_MODELS_FIX_RETRY`. |
| `compile_fix` | str | `sonnet` | swarm.py | Phase 6 compile-fix groups. Env: `PORT_KIT_MODELS_COMPILE_FIX`. |
| `triage` | str | `sonnet` | swarm.py | Phase 7 test triage; confirm by calibration before a sweep. Env: `PORT_KIT_MODELS_TRIAGE`. |
| `red_fixer` | str | `sonnet` | swarm.py | Phase 7 red-round fixer. Env: `PORT_KIT_MODELS_RED_FIXER`. |
| `red_fixer_framework` | str | `opus` | swarm.py | Phase 7 fixer whose failures have a framework cause. Env: `PORT_KIT_MODELS_RED_FIXER_FRAMEWORK`. |

### [track]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `dir` | path | `{work.dir}/track` | track, portkit/track.py | The dashboard store: `events.jsonl` (append-only), `state.json` (derived from the events) and the lock file. Kit tools post events only when a port.toml is found or this key is set in the environment. Env: `PORT_KIT_TRACK_DIR`. |
| `out_dir` | path | `{track.dir}/site` | track, portkit/track.py | Where `track publish` writes the page (index.html, app.js, app.css) and its data (`state.json`, `state.js`). Point a static server or tunnel here. Env: `PORT_KIT_TRACK_OUT_DIR`. |
| `stale_min` | int | `20` | track, portkit/track.py | A running or review task with no event for this many minutes is stale: red on the page, a line in `track alerts`. Env: `PORT_KIT_TRACK_STALE_MIN`. |
| `serve_host` | str | `127.0.0.1` | track | Address `track serve` binds. Env: `PORT_KIT_TRACK_SERVE_HOST`. |
| `serve_port` | int | `8765` | track | Port `track serve` listens on. Env: `PORT_KIT_TRACK_SERVE_PORT`. |
| `how_served` | str | unset | track, init-workspace | Free text the setup records: how the developer opens the page (their own server or tunnel on out_dir and its URL, the file itself, or `track serve`). `track show` prints it. Env: `PORT_KIT_TRACK_HOW_SERVED`. |
| `heads` | list | `["app={app.integration}:{app.port_branch}", "framework={framework.integration}:HEAD"]` | portkit/track.py | Branch heads `track publish` watches, as `LABEL=REPO_PATH:REF`. A head that moved since the last publish becomes a `head` event. Entries built on unset keys are dropped. Env: `PORT_KIT_TRACK_HEADS`. |

### [look]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `driver` | path | unset | look, portkit/gates.py | The app's look driver: a Python file with `start`, `shoot` and `stop` (tools/look.md, "Driver interface"). Env: `PORT_KIT_LOOK_DRIVER`. |
| `states_dir` | path | `{work.dir}/look/states` | look, portkit/gates.py | States files, one per panel or dialog (`<Panel>.json`). Env: `PORT_KIT_LOOK_STATES_DIR`. |
| `run_dir` | path | `{work.dir}/look/run` | look | Scratch space of `look pair`: each app instance's work dir and the full-window shots of the last run. Env: `PORT_KIT_LOOK_RUN_DIR`. |
| `production_binary` | path | unset | look, portkit/gates.py | Production build with the control hooks (process/01-setup.md, step 6a); side `up`. Env: `PORT_KIT_LOOK_PRODUCTION_BINARY`. |
| `port_binary` | path | unset | look | The port's binary as the build loop builds it in the app integration tree; side `port`. Env: `PORT_KIT_LOOK_PORT_BINARY`. |
| `window` | str | `1440x900` | look | Window size `<width>x<height>` for states files that name none. Env: `PORT_KIT_LOOK_WINDOW`. |
| `installed_version` | str | unset | look, portkit/gates.py | The production release the developer runs and compares with by eye: a tag, a version such as `0.18.1`, a commit, or `none`. `look calibrate` compares the production build's revision with it. Env: `PORT_KIT_LOOK_INSTALLED_VERSION`. |
| `reader_max_px` | int | `1568` | look, prompts | The longest edge, in pixels, that the agents' image reader keeps without shrinking. Region crops are cut to fit it, and `look brief` marks larger images as page-only, never for acceptance. Placeholder `{{READER_MAX_PX}}`. Env: `PORT_KIT_LOOK_READER_MAX_PX`. |
| `port_build` | str | unset | cycle | cl arguments that build look.port_binary in app.integration (for example `build <example>`). cycle runs them before `look pair`. Unset: cycle skips the look step and says so. Env: `PORT_KIT_LOOK_PORT_BUILD`. |
| `threshold` | int | `16` | look | A pixel differs visibly when one colour channel differs by more than this (of 255). Smaller differences show in the difference image but make no crop. Env: `PORT_KIT_LOOK_THRESHOLD`. |
| `differences` | path | `{work.dir}/look/differences.md` | look, portkit/gates.py | The differences file: one row per look difference with its judgement, class and outcome (tools/look.md, "The differences file"). `look brief` and the phase 8 gate read it. Env: `PORT_KIT_LOOK_DIFFERENCES`. |

### [land]

| Key | Type | Default | Read by | Meaning |
|---|---|---|---|---|
| `framework_via` | str | `pr` | land/land-framework.sh | How framework changes reach framework.branch: `pr` (one PR per build batch) or `fast-forward`. Env: `PORT_KIT_LAND_FRAMEWORK_VIA`. |
| `early_ci_approved` | bool | `False` | land/early-ci.sh | The developer's standing approval for the lead to push scrubbed port branches to the developer's fork and open draft PRs there, so CI runs early on small diffs. False: kit tools never push and nothing is opened. Set it only after the developer says yes in phase 0. Env: `PORT_KIT_LAND_EARLY_CI_APPROVED`. |
| `early_ci_fork` | str | unset | land/early-ci.sh, cycle | The developer's fork of the framework repository (URL), where land/early-ci.sh pushes scrubbed port branches and opens draft PRs for early CI. It must differ from framework.repo, app.upstream and land.push_target. Env: `PORT_KIT_LAND_EARLY_CI_FORK`. |
| `sync_after_commits` | int | `100` | cycle, sync | cycle reports a sync as due when framework.branch or app.base_branch is more than this many commits ahead of the port's integration branch (or a day has passed since the last sync). A placeholder value, not measured. Env: `PORT_KIT_LAND_SYNC_AFTER_COMMITS`. |
| `push_target` | str | unset | land/land-app.sh | App repository URL the landed branch goes to; land-app.sh prints the push command. Env: `PORT_KIT_LAND_PUSH_TARGET`. |
| `push_branch` | str | `next` | land/land-app.sh | App branch the landed port goes to. Env: `PORT_KIT_LAND_PUSH_BRANCH`. |
| `sibling_framework` | str | `../craft-libs` | land/land-app.sh | Replacement for local framework paths in the scrubbed app history. Env: `PORT_KIT_LAND_SIBLING_FRAMEWORK`. |
| `rewrite_rules` | path | `{kit}/tools/land/rewrite-rules.txt` | land/land-framework.sh, land/land-app.sh | Generic `git filter-repo --replace-text` rules. Env: `PORT_KIT_LAND_REWRITE_RULES`. |
| `private_patterns` | path | `~/.config/craft-ui-port-kit/private-patterns.txt` | kit-check, land/scan-range.py, land/land-framework.sh, land/land-app.sh | Private scrub patterns (names, handles, hosts, local tree names), one regex per line. Never committed. Env: `PORT_KIT_LAND_PRIVATE_PATTERNS` or `PORT_KIT_PRIVATE_PATTERNS`. |
| `replace_message` | path | unset | land/land-framework.sh, land/land-app.sh | Optional private file of replacements applied to commit messages and file contents of the landed range, one `git filter-repo` rule per line (`old==>new` or `regex:PATTERN==>new`). Rules run in file order, after the local framework paths are replaced and before land.rewrite_rules. Env: `PORT_KIT_LAND_REPLACE_MESSAGE`. |
| `known_idents` | path | unset | land/scan-range.py | Optional file of commit identities (`Name <email>`) the scan accepts. Env: `PORT_KIT_LAND_KNOWN_IDENTS`. |

### [[areas]]

| Field | Meaning |
|---|---|
| `id` | Area id; set ids are `<id>-w<n>` |
| `code` | Two lowercase letters; contract ids are `<code>.<Kind><n>` |
| `description` | What the area covers |
| `map` | Its map file (default `{work.maps}/<id>.md`) |
| `repos` | Repos its sets write: `fw`, `app` or both (default both) |

### [[lints]]

| Field | Meaning |
|---|---|
| `pattern` | Regex matched against added lines |
| `why` | Message shown with a hit |
| `level` | `error` (legacy call the framework replaces) or `warn` |
| `framework_rev` | Framework revision the lint was written for |

### Placeholders

| Placeholder | Filled from |
|---|---|
| `{{KIT}}` | Kit root directory |
| `{{RULES}}` | The kit's rules/ directory |
| `{{FIXER_MODE}}` | `build` or `code-only`: pipeline.fixer_mode, with `auto` decided by the measured build times |
| `{{WORK}}` | `work.dir` |
| `{{TREES}}` | `work.trees` |
| `{{INVENTORY}}` | `work.inventory` |
| `{{MAPS}}` | `work.maps` |
| `{{PLAN}}` | `work.plan` |
| `{{SHEETS}}` | `work.sheets` |
| `{{PARTS}}` | `work.parts` |
| `{{OWNERSHIP}}` | `work.ownership` |
| `{{SETTLED}}` | `work.settled` |
| `{{SETS}}` | `work.sets` |
| `{{DECIDE}}` | `work.decide` |
| `{{RUNS}}` | `work.runs` |
| `{{STATE}}` | `work.state` |
| `{{FW_REPO}}` | `framework.repo` |
| `{{FW_BRANCH}}` | `framework.branch` |
| `{{FW_CHECKOUT}}` | `framework.checkout` |
| `{{FW_INT}}` | `framework.integration` |
| `{{FW}}` | `framework.snapshot` |
| `{{FW_WRITING_BASE}}` | `framework.writing_base` |
| `{{FACADE}}` | `framework.facade` |
| `{{APP}}` | `app.name` |
| `{{APP_ID}}` | `app.id` |
| `{{APP_CHECKOUT}}` | `app.checkout` |
| `{{APP_INT}}` | `app.integration` |
| `{{APP_SRC}}` | `app.snapshot` |
| `{{PROD}}` | `app.production` |
| `{{RELEASE}}` | `app.release` |
| `{{APP_UPSTREAM}}` | `app.upstream` |
| `{{APP_BASE_BRANCH}}` | `app.base_branch` |
| `{{APP_PORT_BRANCH}}` | `app.port_branch` |
| `{{APP_WRITING_BASE}}` | `app.writing_base` |
| `{{UI_DIRS}}` | `app.ui_dirs` |
| `{{PLAN_BASE}}` | `plan.base` |
| `{{APP_PLAN_BASE}}` | `plan.app_base` |
| `{{FW_REF}}` | `racheck.fw_base` |
| `{{APP_REF}}` | `racheck.app_base` |
| `{{READER_MAX_PX}}` | `look.reader_max_px` |
| `{{AREA}}` | Area id (an `[[areas]]` id) (per call) |
| `{{AREA_CODE}}` | The area's two-letter contract code (per call) |
| `{{SET}}` | Set id, `<area>-w<n>` (per call) |
| `{{CHUNK}}` | Inventory chunk id (per call) |
| `{{TRACK}}` | Red-round track id (a split-failures group) (per call) |
| `{{ROUND}}` | Round label (per call) |
| `{{OUT}}` | The job's output file or directory (per call) |
| `{{TASK}}` | The board task id the agent reports under (`track step <TASK> ...`) (per call) |
| `{{PART}}` | Decision part id (`<area>-<n>`) (per call) |
| `{{STAGE}}` | Contract stub stage number (per call) |
| `{{CRATES}}` | Framework crates of one contract stub stage, in build order (per call) |
| `{{LOOK}}` | The look evidence of one fix class, filled by `look brief` (per call) |

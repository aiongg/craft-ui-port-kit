#!/usr/bin/env python3
"""Shared config loader for the port kit tools.

Every kit tool reads the port's workspace config, port.toml, through this module. KEYS below is the one list of
config keys: their defaults, types, which tools read them, and which prompt placeholder each one fills.
process/config.md documents the same list; `config.py doc` prints its tables from KEYS.

Resolution, lowest precedence first:
  1. defaults in KEYS
  2. port.toml: the file named by PORT_KIT_CONFIG, else ./port.toml, else the nearest port.toml in a parent directory
  3. environment: PORT_KIT_<SECTION>_<KEY> (for example PORT_KIT_BUILD_LAUNCHER), plus the aliases KEYS names
  4. overrides a tool passes (the CLI's --set KEY=VALUE)

String values may name other keys as {section.key}; a value that is exactly one reference takes that key's value
and type. {kit} is the kit's root directory. Paths expand ~ and resolve relative to the directory of port.toml
(the current directory when there is none).

CLI:
  config.py show [--json]      the resolved config
  config.py get KEY            one value (lists one item per line)
  config.py placeholders       the {{PLACEHOLDER}} table with resolved values
  config.py env                every environment variable name and its key
  config.py check              required keys that are unset and configured paths that do not exist
  config.py doc                the key tables of process/config.md, as Markdown
Options before the command: --config PATH, --set KEY=VALUE (repeatable).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_NAME = "port.toml"
ENV_CONFIG = "PORT_KIT_CONFIG"
ENV_PREFIX = "PORT_KIT_"
# Set in every agent the kit starts headless: the plugin's SessionStart hook (tools/lead-context) stays silent there.
ENV_AGENT = "PORT_KIT_AGENT"
# Commands the tools take from the environment instead of PATH (swarm.py: claude; land/early-ci.sh: gh).
ENV_COMMANDS = ("PORT_KIT_CLAUDE_BIN", "PORT_KIT_GH_BIN")


FIXER_MODES = ("code-only", "build", "auto")


@dataclass(frozen=True)
class Key:
    path: str                    # "section.key"
    default: object              # None: unset (required keys, optional values)
    type: str                    # str | path | int | float | bool | list | paths
    readers: tuple[str, ...]     # kit tools that read the key
    doc: str
    required: bool = False
    placeholder: str | None = None
    env_alias: str | None = None
    default_doc: str | None = None   # how a computed default is shown in the docs


def K(path, default, type, readers, doc, **kw):
    return Key(path, default, type, tuple(readers.split()), doc, **kw)


# Tool names in `readers` are paths under tools/ without the prefix; "prompts" means render-prompt fills the key
# into prompts through its placeholder.
KEYS: list[Key] = [
    # ---- work: the workspace layout (everything the port writes outside the two repos)
    K("work.dir", None, "path", "all", "Workspace root: plans, maps, per-set output, logs, STATE.md. Default: the directory "
      "holding port.toml.", placeholder="WORK", default_doc="port.toml's directory"),
    K("work.trees", "{work.dir}/trees", "path", "port-set run-area combine-area combine-lost cross-owner move-base racheck.py init-workspace",
      "Per-set git worktrees (`<set>` and `<set>-<repo>`) and the read-only base checkouts.", placeholder="TREES"),
    K("work.inventory", "{work.dir}/inventory", "path", "workflows/phase1-inventory-map.js render-prompt",
      "Phase 1 chunk inventory (`chunk-NN.json`).", placeholder="INVENTORY"),
    K("work.maps", "{work.dir}/port-map", "path", "coverage.py render-prompt",
      "Phase 1 area maps (`<area>.md`) and their index (`README.md`).", placeholder="MAPS"),
    K("work.plan", "{work.dir}/plan", "path", "init-workspace render-prompt", "Phase 2 output root.", placeholder="PLAN"),
    K("work.sheets", "{work.plan}/sheets", "path", "port-set run-area coverage.py render-prompt",
      "Writer sheets, one per set (`<area>-w<n>.md`).", placeholder="SHEETS"),
    K("work.parts", "{work.plan}/contract-parts", "path", "port-set render-prompt",
      "Contract parts (`NN.md`), the stub target.", placeholder="PARTS"),
    K("work.ownership", "{work.plan}/ownership.md", "path", "coverage.py gate-classify.py render-prompt",
      "File ownership: every file the port writes, in exactly one set.", placeholder="OWNERSHIP"),
    K("work.settled", "{work.plan}/settled.md", "path", "port-set render-prompt",
      "Design questions settled during planning.", placeholder="SETTLED"),
    K("work.sets", "{work.dir}/sets", "path", "port-set run-area run-batch fix-batch combine-area combine-lost cross-owner move-base gate-classify.py render-prompt",
      "Per-set output dirs (bundle, edits, check.md, plancheck.md, decisions.md, review findings, base-<repo>).",
      placeholder="SETS"),
    K("work.decide", "{work.dir}/decide", "path", "port-set cross-owner gate-classify.py render-prompt",
      "DECIDE collection per area (`<area>.md`) and `owners.tsv`.", placeholder="DECIDE"),
    K("work.runs", "{work.dir}/runs", "path", "compile-gate test-run racheck-gate compare-runs.py diag-cut.py split-failures.py",
      "Compile and test run logs, one dir per run label.", placeholder="RUNS"),
    K("work.scip", "{work.dir}/scip", "path", "port-set scip/scipdb.py init-workspace",
      "SCIP sqlite indexes (`fw.sqlite`, `app.sqlite`)."),
    K("work.swarm", "{work.dir}/swarm", "path", "swarm.py init-workspace",
      "swarm.py's run dirs, one per workflow or job list: each job's prompt, reply and checked result (the resume "
      "cache), the run log and the script's return value."),
    K("work.usage_log", "{work.dir}/usage.tsv", "path", "port-set swarm.py track",
      "Token and cost log of every model call."),
    K("work.state", "{work.dir}/STATE.md", "path", "init-workspace port-set", "The lead's phase state file.",
      placeholder="STATE"),
    K("work.baseline_failures", "{work.dir}/baseline-failures.txt", "path", "test-run compare-runs.py",
      "Tests that fail on the unported app at the pinned framework rev (phase 0)."),
    K("work.landing", "{work.dir}/landing", "path", "land/land-framework.sh land/land-app.sh",
      "Scratch clones and scan reports of landing runs."),

    # ---- framework: craft-libs
    K("framework.repo", "https://github.com/storytold/craft-libs", "str",
      "land/land-framework.sh land/early-ci.sh land/pin-framework.py patch-framework sync cycle prompts", "Framework repository URL. It must be the remote that holds plan.base: "
      "the pin names this URL and a rev only that remote has does not resolve for anyone else.",
      placeholder="FW_REPO"),
    K("framework.branch", "next", "str", "land/land-framework.sh land/early-ci.sh sync cycle init-workspace prompts",
      "Framework branch the port targets: `next` on the framework's upstream; when it does not exist there yet, "
      "the branch the framework team names. Pins and landing use it.", placeholder="FW_BRANCH"),
    K("framework.checkout", None, "path", "move-base patch-framework init-workspace",
      "Local framework clone. Branches and worktrees are made from it.", required=True, placeholder="FW_CHECKOUT"),
    K("framework.integration", "{framework.checkout}", "path", "combine-area combine-lost compile-gate test-run patch-framework racheck-tree racheck-gate look portkit/gates.py",
      "Framework integration worktree: combines and compile gates run here.", placeholder="FW_INT"),
    K("framework.snapshot", "{work.trees}/snap-fw", "path", "init-workspace make-snapshots workflows prompts",
      "Read-only framework checkout at plan.base, read by phase 1 and 2 agents.", placeholder="FW"),
    K("framework.writing_base", "port/stubs", "str", "port-set combine-area move-base racheck.py compile-gate racheck-tree racheck-gate",
      "Framework branch the writers start from: the contract stubs (phase 3).", placeholder="FW_WRITING_BASE"),
    K("framework.facade", "craft", "str", "port-set prompts feature-selection.py racheck.py",
      "Facade crate. App code reaches every member crate through it.", placeholder="FACADE"),
    K("framework.facade_manifest", "crates/craft/Cargo.toml", "str", "port-set racheck.py",
      "Facade manifest, relative to the framework tree; its dependencies give the member crates."),
    K("framework.lints_file", "{kit}/rules/lints.toml", "path", "port-set",
      "Framework lints, labelled by the framework revision they were written for. `[[lints]]` tables in port.toml "
      "add to them."),
    K("framework.patch_urls", ["{framework.repo}"], "list", "patch-framework land/pin-framework.py test-run",
      "Framework URLs the app's Cargo manifests may name (upstream and forks); patch-framework and pin-framework "
      "rewrite each."),

    # ---- app: the app being ported
    K("app.name", None, "str", "port-set prompts", "Display name of the app.", required=True, placeholder="APP"),
    K("app.id", None, "str", "init-workspace prompts",
      "Short lowercase id for file and branch names. Default: app.name lowercased, spaces to dashes.",
      placeholder="APP_ID", default_doc="from app.name"),
    K("app.checkout", None, "path", "init-workspace patch-framework land/land-app.sh",
      "Local app clone. Branches and worktrees are made from it.", required=True, placeholder="APP_CHECKOUT"),
    K("app.integration", "{app.checkout}", "path", "combine-area combine-lost compile-gate test-run patch-framework racheck-tree racheck-gate gate-classify.py feature-selection.py look portkit/gates.py",
      "App integration worktree: combines, compile gates and full test runs run here.", placeholder="APP_INT"),
    K("app.snapshot", "{work.trees}/snap-app", "path", "init-workspace make-snapshots coverage.py workflows prompts render-prompt",
      "Read-only app checkout at plan.app_base, read by phase 1 and 2 agents.", placeholder="APP_SRC"),
    K("app.production", "{work.trees}/prod", "path", "prompts compare-runs.py make-snapshots",
      "Read-only checkout of the app's production main at the commit the port last merged: the behaviour "
      "reference for triage, red rounds and look work.", placeholder="PROD"),
    K("app.release", None, "path", "prompts", "Optional read-only checkout of the latest app release.",
      placeholder="RELEASE"),
    K("app.upstream", None, "str", "land/land-app.sh sync cycle prompts", "App repository URL (production).",
      placeholder="APP_UPSTREAM"),
    K("app.base_branch", "main", "str", "land/land-app.sh sync cycle prompts", "Branch the released app builds from: the branch of the latest release tag "
      "(`git branch -r --contains <tag>`), which can differ from the default branch.",
      placeholder="APP_BASE_BRANCH"),
    K("app.port_branch", "port/framework", "str", "init-workspace land/land-app.sh prompts",
      "App branch that carries the port.", placeholder="APP_PORT_BRANCH"),
    K("app.writing_base", "port/app-base", "str", "port-set combine-area racheck.py racheck-tree racheck-gate",
      "App branch the writers start from.", placeholder="APP_WRITING_BASE"),
    K("app.ui_dirs", None, "list", "coverage.py gate-classify.py workflows/phase1-inventory-map.js prompts render-prompt racheck.py",
      "UI source dirs, relative to the app tree: what phase 1 inventories and coverage checks.", required=True,
      placeholder="UI_DIRS"),
    K("app.facade_dirs", "{app.ui_dirs}", "list", "port-set",
      "App dirs whose code must reach framework crates through the facade, relative to the app tree."),

    # ---- plan
    K("plan.base", None, "str", "port-set coverage.py workflows prompts test-run",
      "Framework commit the plan was made against; phase 3 stubs are diffed from it.", placeholder="PLAN_BASE"),
    K("plan.app_base", None, "str", "coverage.py workflows prompts", "App commit the plan was made against.",
      placeholder="APP_PLAN_BASE"),
    K("plan.linebase", "{work.plan}/LINEBASE", "path", "port-set move-base",
      "State file holding the framework commit that sheet and contract line numbers refer to. init-workspace "
      "writes plan.base into it; `port-set remap` moves it."),
    K("plan.chunk_lines", 3000, "int", "workflows/phase1-inventory-map.js render-prompt", "Target size of one inventory chunk, in lines."),
    K("plan.chunk_map_lines", 250, "int", "render-prompt",
      "Target size of one plan chunk, in area-map lines. Plan chunks hold whole map sections."),
    K("plan.answer_groups_per_agent", 3, "int", "workflows/phase2-part.js", "Question groups one answering agent takes."),
    K("plan.max_error_rate", 0.10, "float", "workflows/phase2-final.js prompts",
      "Highest sampled plan error rate that passes the evaluation."),
    K("plan.max_wrong_answers", 0.10, "float", "workflows/phase2-final.js prompts",
      "Highest share of wrong fact answers that passes the accuracy check."),
    K("plan.build_batches", None, "int", "track",
      "How many build batches the write order has (pilot included), set when the order is fixed (process/06-write.md). "
      "`track eta` counts the batches still to come from it. Unset: the projection counts the current batch only."),

    # ---- racheck: rust-analyzer daemons on read-only base checkouts
    K("racheck.fw_base", "{work.trees}/racheck-fw", "path", "racheck.py racheck-tree racheck-gate move-base port-set",
      "Read-only framework checkout at framework.writing_base, the framework daemon's root; app writers read it.",
      placeholder="FW_REF"),
    K("racheck.app_base", "{work.trees}/racheck-app", "path", "racheck.py racheck-tree racheck-gate port-set",
      "Read-only app checkout at app.writing_base, the app daemon's root.", placeholder="APP_REF"),
    K("racheck.fw_target", "{work.trees}/racheck-fw-target", "path", "racheck.py", "rust-analyzer target dir for the framework daemon."),
    K("racheck.app_target", "{work.trees}/racheck-app-target", "path", "racheck.py", "rust-analyzer target dir for the app daemon."),
    K("racheck.sockets", "{work.trees}", "path", "racheck.py racheck-gate move-base", "Directory of the daemons' sockets and logs."),
    K("racheck.memory_gb", 16, "int", "racheck.py", "Memory cap per daemon in GB, applied through build.memory_cap."),
    K("racheck.gap_patterns", ["Harness", "kittest", r"`ctx` on type `&?(mut )?Ui`", r"`input` on type `&?(mut )?Ui`",
                               "run_ui", "__register_", "egui_kittest"], "list", "gate-classify.py",
      "Regexes for diagnostics rust-analyzer reports wrongly (test harness and macro gaps); gates class them `ra-gap`."),

    # ---- build: how cargo runs
    K("build.cl", "{framework.checkout}/tools/cl", "path", "compile-gate test-run",
      "The framework's cl. Every cargo command goes through it."),
    K("build.launcher", "", "str", "compile-gate test-run",
      "Command prefix every cargo build runs under (for example a shared jobserver). Passed to cl as CL_LAUNCHER. "
      "Empty: plain cargo."),
    K("build.runner", "", "str", "compile-gate test-run",
      "Command prefix the built test binaries run under. Passed to cl as CL_RUNNER. Empty: run directly."),
    K("build.memory_cap", "", "str", "racheck.py swarm.py compile-gate test-run",
      "Command prefix that caps a heavy job's memory; `{gb}` is replaced with the job's GB (example: "
      "`{kit}/tools/capped {gb}`). Empty: no cap."),
    K("build.memory_gb", 28, "int", "compile-gate test-run", "Memory cap in GB for builds and test runs under build.memory_cap."),
    K("build.test_threads", None, "int", "test-run",
      "--test-threads for test binaries. Unset: test-run passes none, and cl uses the app manifest's "
      "`[workspace.metadata.cl] test_threads`."),
    K("build.target_dir", "", "path", "compile-gate test-run",
      "CARGO_TARGET_DIR for the integration trees. Empty: cl's default (`<worktree>-target` when it exists)."),
    K("build.warm_check_s", None, "int", "cycle render-prompt",
      "Seconds of a warm `compile-gate` of the app after a one-file change, measured in phase 0. With "
      "build.full_run_s it sets the fixer mode when pipeline.fixer_mode is `auto`. Unset: not measured."),
    K("build.full_run_s", None, "int", "cycle render-prompt",
      "Seconds of one full `test-run --app` (build already warm), measured in phase 0. Unset: not measured."),
    K("build.fw_trial_s", None, "int", "cycle render-prompt",
      "Seconds of the slowest warm `cl test` of a framework crate the port changes, measured from the phase 0 "
      "framework baseline (process/11-build-loop.md, \"Measuring the fixer mode's inputs\"). Unset: counts as 0."),

    # ---- pipeline: the writer buckets and batch runners
    K("pipeline.batch_runner", "swarm", "str", "workflows/README",
      "How agent batches run: `swarm` (tools/swarm.py, claude CLI only) or `workflow` (the Workflow tool)."),
    K("pipeline.parallel", 6, "int", "run-area run-batch fix-batch swarm.py", "Sets or jobs run at once."),
    K("pipeline.agent_files_over", 15, "int", "run-area",
      "A sheet with more Files rows than this goes to agent mode; smaller ones to the one-shot pipeline."),
    K("pipeline.run_max_turns", 25, "int", "port-set", "Turn limit of a one-shot write call (`port-set run`)."),
    K("pipeline.repairs", 1, "int", "port-set", "Repair calls after a one-shot write whose check fails."),
    K("pipeline.agent_max_turns", 200, "int", "port-set", "Turn limit of `port-set agent` run on its own."),
    K("pipeline.agent_round_turns", 100, "int", "run-area", "Turn limit of one agent-mode round in run-area."),
    K("pipeline.agent_continue_rounds", 3, "int", "run-area",
      "Continue rounds for an agent-mode set while its check names an error or it ran out of turns."),
    K("pipeline.plancheck_max_turns", 14, "int", "port-set", "Turn limit of a plan check."),
    K("pipeline.fix_max_turns", 40, "int", "port-set fix-batch", "Turn limit of a review-fix call."),
    K("pipeline.lookup_tools", "Read,Grep,Glob,Bash(git grep:*),Bash(git show:*),Bash(git ls-files:*),Bash(track:*)", "str",
      "port-set swarm.py", "Tools a one-shot writer or plan check may use to look things up."),
    K("pipeline.job_max_turns", 300, "int", "swarm.py", "Turn limit of one swarm.py job."),
    K("pipeline.quota_command", "", "str", "run-batch swarm.py",
      "Command printing the plan's current 5-hour window use as a percent. Empty: never wait on quota."),
    K("pipeline.quota_cap", 90, "int", "run-batch swarm.py", "Start no new job while quota_command reports at or above this."),
    K("pipeline.weekly_quota_command", "", "str", "cycle track",
      "Command printing the plan's weekly use as a percent. cycle records it with each cycle, and `track eta` "
      "projects it to the finish. Empty: no weekly line in the projection."),
    K("pipeline.fixer_mode", "code-only", "str", "cycle render-prompt",
      "How compile and red fixers work: `code-only` (no cargo; DIAG prints where unsure), `build` (each fixer "
      "takes a build tree and runs `cl check` or its own failing tests), or `auto` (`build` when build.warm_check_s "
      "plus the larger of build.full_run_s and build.fw_trial_s is at most pipeline.fixer_build_max_s, else "
      "`code-only`). Writers are code-only in every mode (process/11-build-loop.md, rule 3)."),
    K("pipeline.fixer_build_max_s", 600, "int", "cycle render-prompt",
      "The `auto` threshold in seconds on build.warm_check_s plus the larger of build.full_run_s and "
      "build.fw_trial_s. The default is a placeholder backed by one measured app, whose builds stayed well under it."),
    K("pipeline.follow_up_max_context", 150_000, "int", "swarm.py",
      "Tokens of context. `swarm.py --follow-up` resumes a job's session while its last context is under this; at "
      "or over it, it starts a fresh session with the job's prompt, its last report and the follow-up."),
    K("pipeline.followup_timeout_min", 120, "int", "cycle",
      "Minutes cycle waits for one fixer's follow-up. A fixer past it is named as stalled in the cycle's summary "
      "and report, and the cycle ends without it."),
    K("pipeline.bundle.context", 12, "int", "port-set", "Lines of context around each line range a sheet names."),
    K("pipeline.bundle.snippet_cap", 260, "int", "port-set", "Most lines of one excerpt."),
    K("pipeline.bundle.big", 800, "int", "port-set",
      "An edited file longer than this goes in as an outline plus the parts the sheet names."),
    K("pipeline.bundle.big_context", 30, "int", "port-set", "Context lines around named parts of a big file."),
    K("pipeline.bundle.big_cap", 700, "int", "port-set", "Most lines taken from one big file."),
    K("pipeline.bundle.small", 120, "int", "port-set", "Files up to this many lines always go in whole."),
    K("pipeline.bundle.small_edit", 30, "int", "port-set",
      "A file up to `big` lines goes in whole when its row writes plus deletes at least this many lines."),
    K("pipeline.bundle.excerpt_budget", 120_000, "int", "port-set",
      "Characters of excerpts from files outside the Files table; the rest is listed by location."),

    # ---- models: model per role
    K("models.default", "sonnet", "str", "swarm.py", "Model for a job that names no role."),
    K("models.inventory", "haiku", "str", "workflows/phase1-inventory-map.js", "Phase 1 chunk inventory."),
    K("models.area_map", "opus", "str", "workflows/phase1-inventory-map.js", "Phase 1 area maps."),
    K("models.index", "opus", "str", "workflows/phase1-inventory-map.js", "Phase 1 map index."),
    K("models.questions", "opus", "str", "workflows/phase2-part.js", "Phase 2 question split."),
    K("models.answers", "haiku", "str", "workflows/phase2-part.js", "Phase 2 fact answers."),
    K("models.chunk_plan", "opus", "str", "workflows/phase2-part.js", "Phase 2 chunk plans."),
    K("models.area_merge", "opus", "str", "workflows/phase2-final.js", "Phase 2 area merge, conflict check, consolidation."),
    K("models.evaluate", "opus", "str", "workflows/phase2-final.js", "Phase 2 evaluation."),
    K("models.sheet_fix", "sonnet", "str", "workflows/phase2-fix.js workflows/phase2-reconcile.js", "Phase 2 sheet fixes."),
    K("models.stubs", "sonnet", "str", "swarm.py", "Phase 3 contract-stub stages."),
    K("models.plancheck", "sonnet", "str", "port-set run-batch", "Phase 4 plan check per set."),
    K("models.decide", "opus", "str", "swarm.py", "Phase 4 decision parts."),
    K("models.consistency", "opus", "str", "swarm.py", "Phase 4 consistency pass."),
    K("models.write", "sonnet", "str", "port-set run-area run-batch", "Phase 5 writer, default."),
    K("models.write_shared", "opus", "str", "run-area", "Phase 5 writer for sets that change a shared mechanism."),
    K("models.retry", "opus", "str", "run-area run-batch", "Retry of a set a Sonnet writer failed."),
    K("models.review", "opus", "str", "swarm.py", "Phase 6 area review."),
    K("models.fix", "sonnet", "str", "port-set fix-batch", "Phase 6 review fixes."),
    K("models.fix_retry", "opus", "str", "fix-batch", "Fix of a set that failed twice."),
    K("models.compile_fix", "sonnet", "str", "swarm.py", "Phase 6 compile-fix groups."),
    K("models.triage", "sonnet", "str", "swarm.py", "Phase 7 test triage; confirm by calibration before a sweep."),
    K("models.red_fixer", "sonnet", "str", "swarm.py", "Phase 7 red-round fixer."),
    K("models.red_fixer_framework", "opus", "str", "swarm.py", "Phase 7 fixer whose failures have a framework cause."),


    # ---- track: the progress dashboard (tools/track.md)
    K("track.dir", "{work.dir}/track", "path", "track portkit/track.py",
      "The dashboard store: `events.jsonl` (append-only), `state.json` (derived from the events) and the lock file. "
      "Kit tools post events only when a port.toml is found or this key is set in the environment."),
    K("track.out_dir", "{track.dir}/site", "path", "track portkit/track.py",
      "Where `track publish` writes the page (index.html, app.js, app.css) and its data (`state.json`, `state.js`). "
      "Point a static server or tunnel here."),
    K("track.stale_min", 20, "int", "track portkit/track.py",
      "A running or review task with no event for this many minutes is stale: red on the page, a line in `track alerts`."),
    K("track.serve_host", "127.0.0.1", "str", "track", "Address `track serve` binds."),
    K("track.serve_port", 8765, "int", "track", "Port `track serve` listens on."),
    K("track.how_served", None, "str", "track init-workspace",
      "Free text the setup records: how the developer opens the page (their own server or tunnel on out_dir and its "
      "URL, the file itself, or `track serve`). `track show` prints it."),
    K("track.heads", ["app={app.integration}:{app.port_branch}", "framework={framework.integration}:HEAD"], "list",
      "portkit/track.py",
      "Branch heads `track publish` watches, as `LABEL=REPO_PATH:REF`. A head that moved since the last publish "
      "becomes a `head` event. Entries built on unset keys are dropped."),

    # ---- look: production against port captures (tools/look.md)
    K("look.driver", None, "path", "look portkit/gates.py",
      "The app's look driver: a Python file with `start`, `shoot` and `stop` (tools/look.md, \"Driver interface\")."),
    K("look.states_dir", "{work.dir}/look/states", "path", "look portkit/gates.py",
      "States files, one per panel or dialog (`<Panel>.json`)."),
    K("look.run_dir", "{work.dir}/look/run", "path", "look",
      "Scratch space of `look pair`: each app instance's work dir and the full-window shots of the last run."),
    K("look.production_binary", None, "path", "look portkit/gates.py",
      "Production build with the control hooks (process/01-setup.md, step 6a); side `up`."),
    K("look.port_binary", None, "path", "look",
      "The port's binary as the build loop builds it in the app integration tree; side `port`."),
    K("look.window", "1440x900", "str", "look",
      "Window size `<width>x<height>` for states files that name none."),
    K("look.installed_version", None, "str", "look portkit/gates.py",
      "The production release the developer runs and compares with by eye: a tag, a version such as `0.18.1`, a "
      "commit, or `none`. `look calibrate` compares the production build's revision with it."),
    K("look.reader_max_px", 1568, "int", "look prompts",
      "The longest edge, in pixels, that the agents' image reader keeps without shrinking. Region crops are cut to "
      "fit it, and `look brief` marks larger images as page-only, never for acceptance.", placeholder="READER_MAX_PX"),
    K("look.port_build", None, "str", "cycle",
      "cl arguments that build look.port_binary in app.integration (for example `build <example>`). cycle runs "
      "them before `look pair`. Unset: cycle skips the look step and says so."),
    K("look.threshold", 16, "int", "look",
      "A pixel differs visibly when one colour channel differs by more than this (of 255). Smaller differences "
      "show in the difference image but make no crop."),
    K("look.differences", "{work.dir}/look/differences.md", "path", "look portkit/gates.py",
      "The differences file: one row per look difference with its judgement, class and outcome (tools/look.md, "
      "\"The differences file\"). `look brief` and the phase 8 gate read it."),

    # ---- land: scrub and landing (the tools print push commands and never push)
    K("land.framework_via", "pr", "str", "land/land-framework.sh",
      "How framework changes reach framework.branch: `pr` (one PR per build batch) or `fast-forward`."),
    K("land.early_ci_approved", False, "bool", "land/early-ci.sh",
      "The developer's standing approval for the lead to push scrubbed port branches to the developer's fork and open "
      "draft PRs there, so CI runs early on small diffs. False: kit tools never push and nothing is opened. Set it "
      "only after the developer says yes in phase 0."),
    K("land.early_ci_fork", None, "str", "land/early-ci.sh cycle",
      "The developer's fork of the framework repository (URL), where land/early-ci.sh pushes scrubbed port branches "
      "and opens draft PRs for early CI. It must differ from framework.repo, app.upstream and land.push_target."),
    K("land.sync_after_commits", 100, "int", "cycle sync",
      "cycle reports a sync as due when framework.branch or app.base_branch is more than this many commits ahead of "
      "the port's integration branch (or a day has passed since the last sync). A placeholder value, not measured."),
    K("land.push_target", None, "str", "land/land-app.sh",
      "App repository URL the landed branch goes to; land-app.sh prints the push command."),
    K("land.push_branch", "next", "str", "land/land-app.sh", "App branch the landed port goes to."),
    K("land.sibling_framework", "../craft-libs", "str", "land/land-app.sh",
      "Replacement for local framework paths in the scrubbed app history."),
    K("land.rewrite_rules", "{kit}/tools/land/rewrite-rules.txt", "path", "land/land-framework.sh land/land-app.sh",
      "Generic `git filter-repo --replace-text` rules."),
    K("land.private_patterns", "~/.config/craft-ui-port-kit/private-patterns.txt", "path",
      "kit-check land/scan-range.py land/land-framework.sh land/land-app.sh",
      "Private scrub patterns (names, handles, hosts, local tree names), one regex per line. Never committed.",
      env_alias="PORT_KIT_PRIVATE_PATTERNS"),
    K("land.replace_message", None, "path", "land/land-framework.sh land/land-app.sh",
      "Optional private file of replacements applied to commit messages and file contents of the landed range, one `git filter-repo` rule per line (`old==>new` or `regex:PATTERN==>new`). Rules run in file order, after the local framework paths are replaced and before land.rewrite_rules."),
    K("land.known_idents", None, "path", "land/scan-range.py",
      "Optional file of commit identities (`Name <email>`) the scan accepts."),
]

# Placeholders a caller fills per call (render-prompt flags), not from port.toml.
CALL_PLACEHOLDERS = {
    "AREA": "Area id (an `[[areas]]` id)",
    "AREA_CODE": "The area's two-letter contract code",
    "SET": "Set id, `<area>-w<n>`",
    "CHUNK": "Inventory chunk id",
    "TRACK": "Red-round track id (a split-failures group)",
    "ROUND": "Round label",
    "OUT": "The job's output file or directory",
    "TASK": "The board task id the agent reports under (`track step <TASK> ...`)",
    "PART": "Decision part id (`<area>-<n>`)",
    "STAGE": "Contract stub stage number",
    "CRATES": "Framework crates of one contract stub stage, in build order",
    "LOOK": "The look evidence of one fix class, filled by `look brief`",
}
# Placeholders derived from the kit itself.
KIT_PLACEHOLDERS = {"KIT": "Kit root directory", "RULES": "The kit's rules/ directory",
                    "FIXER_MODE": "`build` or `code-only`: pipeline.fixer_mode, with `auto` decided by the measured build times"}

AREA_FIELDS = {"id": "Area id; set ids are `<id>-w<n>`", "code": "Two lowercase letters; contract ids are `<code>.<Kind><n>`",
               "description": "What the area covers", "map": "Its map file (default `{work.maps}/<id>.md`)",
               "repos": "Repos its sets write: `fw`, `app` or both (default both)"}
LINT_FIELDS = {"pattern": "Regex matched against added lines", "why": "Message shown with a hit",
               "level": "`error` (legacy call the framework replaces) or `warn`",
               "framework_rev": "Framework revision the lint was written for"}

BY_PATH = {k.path: k for k in KEYS}
SECTIONS = sorted({k.path.split(".")[0] for k in KEYS})
REF = re.compile(r"\{([a-z_]+(?:\.[a-z_]+)+|kit)\}")


def env_name(path: str) -> str:
    return ENV_PREFIX + path.replace(".", "_").upper()


ENV_NAMES: dict[str, str] = {}
for _k in KEYS:
    for _n in filter(None, (env_name(_k.path), _k.env_alias)):
        assert _n not in ENV_NAMES, f"env name {_n} names two keys"
        ENV_NAMES[_n] = _k.path


class ConfigError(Exception):
    pass


class _Unset(Exception):
    pass


def find_config(explicit: str | None = None) -> Path | None:
    """PORT_KIT_CONFIG, else ./port.toml, else the nearest port.toml in a parent directory."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            raise ConfigError(f"config file not found: {p}")
        return p.resolve()
    if os.environ.get(ENV_CONFIG):
        p = Path(os.environ[ENV_CONFIG]).expanduser()
        if not p.is_file():
            raise ConfigError(f"{ENV_CONFIG} names a missing file: {p}")
        return p.resolve()
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / CONFIG_NAME).is_file():
            return d / CONFIG_NAME
    return None


def _flatten(table: dict, prefix: str = "") -> dict[str, object]:
    out = {}
    for name, v in table.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(v, dict) and path not in BY_PATH:
            out.update(_flatten(v, path))
        else:
            out[path] = v
    return out


def _from_text(key: Key, text: str):
    t = key.type
    if t in ("str", "path"):
        return text
    if t == "int":
        return int(text)
    if t == "float":
        return float(text)
    if t == "bool":
        low = text.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off", ""):
            return False
        raise ConfigError(f"{key.path}: not a boolean: {text!r}")
    if t in ("list", "paths"):
        s = text.strip()
        if s.startswith("["):
            v = json.loads(s)
            if not isinstance(v, list):
                raise ConfigError(f"{key.path}: not a list: {text!r}")
            return [str(x) for x in v]
        return [x.strip() for x in s.split(",") if x.strip()]
    raise AssertionError(t)


def _check_type(key: Key, v):
    t = key.type
    ok = {"str": isinstance(v, str), "path": isinstance(v, str), "int": isinstance(v, int) and not isinstance(v, bool),
          "float": isinstance(v, (int, float)) and not isinstance(v, bool), "bool": isinstance(v, bool),
          "list": isinstance(v, list) and all(isinstance(x, str) for x in v),
          "paths": isinstance(v, list) and all(isinstance(x, str) for x in v)}[t]
    # A value that is exactly one reference is typed after interpolation.
    if not ok and not (isinstance(v, str) and REF.fullmatch(v)):
        raise ConfigError(f"{key.path}: expected {t}, got {type(v).__name__}: {v!r}")


@dataclass
class Config:
    file: Path | None
    values: dict[str, object]
    areas: list[dict] = field(default_factory=list)
    lints: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def base_dir(self) -> Path:
        return self.file.parent if self.file else Path.cwd()

    def get(self, path: str, default=None):
        if path not in BY_PATH:
            raise ConfigError(f"unknown config key: {path}")
        v = self.values.get(path)
        return default if v is None else v

    def require(self, path: str):
        v = self.values.get(path)
        if v is None or v == "" or v == []:
            k = BY_PATH[path]
            raise ConfigError(f"{path} is not set: {k.doc} Set it in port.toml or {env_name(path)}.")
        return v

    def path(self, path: str) -> Path:
        return Path(self.require(path))

    def __getitem__(self, path: str):
        return self.require(path)

    # ---- areas
    def area(self, area_id: str) -> dict:
        for a in self.areas:
            if a["id"] == area_id:
                return a
        raise ConfigError(f"no [[areas]] entry with id {area_id!r}")

    def area_of(self, set_id: str) -> str:
        """Area id of a set id `<area>-w<n>[a-z]`."""
        aid = re.sub(r"-w\d+[a-z]?$", "", set_id)
        if self.areas and aid not in {a["id"] for a in self.areas}:
            raise ConfigError(f"set {set_id}: area {aid!r} is not in [[areas]]")
        return aid

    def code_of(self, area_id: str) -> str:
        return self.area(area_id)["code"]

    # ---- fixer mode
    def fixer_mode(self) -> str:
        """`build` or `code-only`: pipeline.fixer_mode, with `auto` decided by the measured build times."""
        mode = self.get("pipeline.fixer_mode")
        if mode not in FIXER_MODES:
            raise ConfigError(f"pipeline.fixer_mode = {mode!r}: one of {', '.join(FIXER_MODES)}")
        if mode != "auto":
            return mode
        check, run = self.get("build.warm_check_s"), self.get("build.full_run_s")
        if check is None or run is None:
            return "code-only"
        trial = self.get("build.fw_trial_s") or 0
        return "build" if check + max(run, trial) <= self.get("pipeline.fixer_build_max_s") else "code-only"

    # ---- placeholders
    def placeholders(self) -> dict[str, str]:
        out = {"KIT": str(KIT_ROOT), "RULES": str(KIT_ROOT / "rules"), "FIXER_MODE": self.fixer_mode()}
        for k in KEYS:
            if k.placeholder:
                v = self.values.get(k.path)
                out[k.placeholder] = "" if v is None else (", ".join(v) if isinstance(v, list) else str(v))
        return out


def load(config_file: str | None = None, overrides: dict[str, str] | None = None, env: dict | None = None) -> Config:
    env = os.environ if env is None else env
    file = find_config(config_file)
    raw: dict = {}
    if file:
        with open(file, "rb") as f:
            raw = tomllib.load(f)
    warnings = []
    areas = raw.pop("areas", [])
    lints = raw.pop("lints", [])
    values: dict[str, object] = {k.path: k.default for k in KEYS}
    for path, v in _flatten(raw).items():
        if path not in BY_PATH:
            warnings.append(f"{file}: unknown key {path} (ignored)")
            continue
        _check_type(BY_PATH[path], v)
        values[path] = v
    for name, path in ENV_NAMES.items():
        if name in env:
            values[path] = _from_text(BY_PATH[path], env[name])
    for name in env:
        if name.startswith(ENV_PREFIX) and name not in ENV_NAMES and name not in (ENV_CONFIG, ENV_AGENT, *ENV_COMMANDS):
            warnings.append(f"environment: {name} names no config key (ignored)")
    for path, text in (overrides or {}).items():
        if path not in BY_PATH:
            raise ConfigError(f"--set: unknown key {path}")
        values[path] = _from_text(BY_PATH[path], text)

    base = file.parent if file else Path.cwd()
    if values["work.dir"] is None:
        values["work.dir"] = str(base)
    if values["app.id"] is None and isinstance(values["app.name"], str):
        values["app.id"] = re.sub(r"\s+", "-", values["app.name"].strip().lower())

    resolved: dict[str, object] = {}

    def resolve(path: str, stack: tuple[str, ...] = ()):
        if path in resolved:
            return resolved[path]
        if path in stack:
            raise ConfigError("config references form a cycle: " + " -> ".join((*stack, path)))
        v = values[path]
        st = (*stack, path)

        def sub(s: str):
            m = REF.fullmatch(s)
            if m:
                name = m.group(1)
                return str(KIT_ROOT) if name == "kit" else ref(name, st, path)

            def one(mm):
                name = mm.group(1)
                if name == "kit":
                    return str(KIT_ROOT)
                r = ref(name, st, path)
                if r is None:
                    raise _Unset
                if isinstance(r, list):
                    raise ConfigError(f"{path}: {{{name}}} is a list; it cannot be part of a string")
                return str(r)
            try:
                return REF.sub(one, s)
            except _Unset:   # a value built on an unset key is unset too; require() names it when a tool needs it
                return None

        if isinstance(v, str):
            v = sub(v)
        elif isinstance(v, list):
            items = []
            for x in v:
                r = sub(x)
                if r is not None:
                    items.extend(r if isinstance(r, list) else [r])
            v = items
        key = BY_PATH[path]
        if key.type == "path" and isinstance(v, str) and v:
            v = _abspath(v, base)
        elif key.type == "paths" and isinstance(v, list):
            v = [_abspath(x, base) for x in v]
        resolved[path] = v
        return v

    def ref(name, stack, owner):
        if name not in BY_PATH:
            raise ConfigError(f"{owner}: {{{name}}} names no config key")
        return resolve(name, stack)

    for k in KEYS:
        resolve(k.path)

    cfg = Config(file, resolved, warnings=warnings)
    cfg.areas = _areas(areas, cfg)
    cfg.lints = _lints(lints)
    return cfg


def _abspath(v: str, base: Path) -> str:
    p = Path(os.path.expandvars(v)).expanduser()
    return str(p if p.is_absolute() else (base / p).resolve())


def _areas(areas, cfg: Config) -> list[dict]:
    out, ids, codes = [], set(), set()
    for a in areas:
        if not isinstance(a, dict) or "id" not in a or "code" not in a:
            raise ConfigError(f"[[areas]] entry needs id and code: {a!r}")
        extra = set(a) - set(AREA_FIELDS)
        if extra:
            raise ConfigError(f"[[areas]] {a['id']}: unknown fields {sorted(extra)}")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", a["id"]) or re.search(r"-w\d+[a-z]?$", a["id"]):
            raise ConfigError(f"[[areas]] id {a['id']!r}: lowercase letters, digits and dashes, not ending in -w<n>")
        if not re.fullmatch(r"[a-z]{2}", a["code"]):
            raise ConfigError(f"[[areas]] {a['id']}: code must be two lowercase letters, got {a['code']!r}")
        if a["id"] in ids or a["code"] in codes:
            raise ConfigError(f"[[areas]] {a['id']}: id or code {a['code']!r} used twice")
        ids.add(a["id"]); codes.add(a["code"])
        repos = a.get("repos", ["fw", "app"])
        if isinstance(repos, str):
            repos = [repos]
        if not repos or set(repos) - {"fw", "app"}:
            raise ConfigError(f"[[areas]] {a['id']}: repos must be fw, app or both")
        maps = cfg.get("work.maps")
        out.append({"id": a["id"], "code": a["code"], "description": a.get("description", ""),
                    "map": _abspath(a["map"], cfg.base_dir) if "map" in a else f"{maps}/{a['id']}.md", "repos": repos})
    return out


def _lints(lints) -> list[dict]:
    out = []
    for l in lints:
        if not isinstance(l, dict) or not {"pattern", "why"} <= set(l):
            raise ConfigError(f"[[lints]] entry needs pattern and why: {l!r}")
        extra = set(l) - set(LINT_FIELDS)
        if extra:
            raise ConfigError(f"[[lints]] {l['pattern']!r}: unknown fields {sorted(extra)}")
        level = l.get("level", "warn")
        if level not in ("error", "warn"):
            raise ConfigError(f"[[lints]] {l['pattern']!r}: level must be error or warn")
        re.compile(l["pattern"])
        out.append({"pattern": l["pattern"], "why": l["why"], "level": level, "framework_rev": l.get("framework_rev", "")})
    return out


# ---------------------------------------------------------------- CLI

def _fmt_default(k: Key) -> str:
    if k.default_doc:
        return k.default_doc
    if k.default is None:
        return "required" if k.required else "unset"
    if isinstance(k.default, str):
        return f"`{k.default}`" if k.default else '`""`'
    if isinstance(k.default, list):
        return "`" + json.dumps(k.default) + "`"
    return f"`{k.default}`"


def doc_tables() -> str:
    """The key tables of process/config.md."""
    out = []
    groups: dict[str, list[Key]] = {}
    for k in KEYS:
        sec = k.path.rsplit(".", 1)[0] if k.path.startswith("pipeline.bundle.") else k.path.split(".")[0]
        groups.setdefault(sec, []).append(k)
    for sec, keys in groups.items():
        out += [f"### [{sec}]", "", "| Key | Type | Default | Read by | Meaning |", "|---|---|---|---|---|"]
        for k in keys:
            name = k.path.rsplit(".", 1)[1]
            env = f" Env: `{env_name(k.path)}`" + (f" or `{k.env_alias}`." if k.env_alias else ".")
            ph = f" Placeholder `{{{{{k.placeholder}}}}}`." if k.placeholder else ""
            out.append(f"| `{name}` | {k.type} | {_fmt_default(k).replace('|', '&#124;')} | {', '.join(k.readers)} | "
                       f"{k.doc.replace('|', '&#124;')}{ph}{env} |")
        out.append("")
    out += ["### [[areas]]", "", "| Field | Meaning |", "|---|---|"]
    out += [f"| `{n}` | {d} |" for n, d in AREA_FIELDS.items()]
    out += ["", "### [[lints]]", "", "| Field | Meaning |", "|---|---|"]
    out += [f"| `{n}` | {d} |" for n, d in LINT_FIELDS.items()]
    out += ["", "### Placeholders", "", "| Placeholder | Filled from |", "|---|---|"]
    out += [f"| `{{{{{n}}}}}` | {d} |" for n, d in KIT_PLACEHOLDERS.items()]
    out += [f"| `{{{{{k.placeholder}}}}}` | `{k.path}` |" for k in KEYS if k.placeholder]
    out += [f"| `{{{{{n}}}}}` | {d} (per call) |" for n, d in CALL_PLACEHOLDERS.items()]
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("get"); s.add_argument("key")
    for name in ("placeholders", "env", "check", "doc"):
        sub.add_parser(name)
    a = p.parse_args(argv)
    if a.cmd == "doc":
        sys.stdout.write(doc_tables()); return 0
    if a.cmd == "env":
        for n, path in sorted(ENV_NAMES.items()):
            print(f"{n}\t{path}")
        print(f"{ENV_CONFIG}\t(path of port.toml)")
        return 0
    overrides = {}
    for kv in a.set:
        if "=" not in kv:
            p.error(f"--set needs KEY=VALUE: {kv}")
        k, v = kv.split("=", 1); overrides[k] = v
    try:
        cfg = load(a.config, overrides)
    except (ConfigError, tomllib.TOMLDecodeError, ValueError) as e:
        print(f"config: {e}", file=sys.stderr); return 2
    for w in cfg.warnings:
        print(f"config: warning: {w}", file=sys.stderr)
    if a.cmd == "show":
        if a.json:
            print(json.dumps({"file": str(cfg.file) if cfg.file else None, "values": cfg.values, "areas": cfg.areas,
                              "lints": cfg.lints}, indent=2))
        else:
            print(f"# config file: {cfg.file or '(none: defaults and environment only)'}")
            for k in KEYS:
                print(f"{k.path} = {json.dumps(cfg.values[k.path])}")
            for ar in cfg.areas:
                print(f"area {ar['id']} ({ar['code']}): {ar['map']}")
        return 0
    if a.cmd == "get":
        try:
            v = cfg.get(a.key)
        except ConfigError as e:
            print(f"config: {e}", file=sys.stderr); return 2
        if isinstance(v, list):
            print("\n".join(v))
        elif v is not None:
            print(v)
        return 0
    if a.cmd == "placeholders":
        for n, v in cfg.placeholders().items():
            print(f"{{{{{n}}}}}\t{v}")
        return 0
    if a.cmd == "check":
        bad = 0
        for k in KEYS:
            v = cfg.values[k.path]
            if k.required and (v is None or v == "" or v == []):
                print(f"missing: {k.path}: {k.doc}"); bad += 1
            elif k.path == "land.private_patterns" and not Path(v).exists():
                print(f"warning: no private patterns file at {v}: the scrub runs with the generic patterns only")
            elif (k.type == "path" and v and not Path(v).is_relative_to(cfg.values["work.dir"])
                  and not Path(v).exists()):   # paths inside the workspace are the kit's to create
                print(f"no such path: {k.path} = {v}"); bad += 1
        if not cfg.areas:
            print("note: no [[areas]] yet (phase 1 chooses them)")
        print(f"check: {bad} problem(s)")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

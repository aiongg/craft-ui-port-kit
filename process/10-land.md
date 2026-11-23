# Phase 9: land

Phase 9 puts the port where others can build it: the framework changes on the framework's port branch (`framework.branch`), and the app on its landing branch, pinned to the framework revision that landed. Before anything leaves the machine, production's newest changes are merged into the port, and every commit to be pushed is scanned and scrubbed of anything that names the developer, their machine or their local tools. The landing tools prepare all of this in scratch clones and print the push commands; they never push. The one exception is early CI on the developer's fork during the port ([Early CI on the fork](#early-ci-on-the-fork)).

| | |
|---|---|
| Starts when | The lead accepted the look and behaviour ([09-look-and-behaviour.md](09-look-and-behaviour.md)). Framework changes may also land earlier, after any build batch passes its red rounds. |
| Ends when | The framework changes are on `framework.branch` (merged PR or fast-forward); the app's landing branch is scrubbed, pinned to that framework revision and pushed by the developer; its CI result is recorded. |
| Agents | Production merge: one agent per merge area (`prompts/p9-production-merge.md`). Landing: the lead. |
| Builds | One build and full run after the production merge; CI after the push. |
| Output | `<work.landing>/merge-plan.md` and the merge's area reports; scan reports and landing clones under `work.landing`. |

Record the phase: `tools/track phase 9 "land"`, and put the landing tasks on the board: `tools/track status land-framework todo`, `tools/track status land-app todo`.

## Why the framework lands on its port branch

The framework's changes go to `framework.branch`, never to the framework's main branch, until every app has ported. Apps that have not ported still build against main's old UI code; merging the port's framework into main earlier would break them all at once. `framework.branch` merges to main through a reviewed PR after the last app ports ([rules/framework-decisions.md](../rules/framework-decisions.md)). Each app pins a framework revision by git rev, so an app keeps building while the branch moves.

## Step 1: sync with upstream

Merge upstream's new work into the port before landing, and once a day during the port (`rules/lead-rules.md`, "Sync once a day"), at the heads as they are when the sync starts. Never chase commits that land during a sync.

`cycle` says when a sync is due: its report and summary line carry `sync due` when an integration tree is more than `land.sync_after_commits` commits behind its upstream branch, or behind with its last sync more than a day ago. Then run:

```sh
tools/sync                 # --fw or --app for one repo; --dry-run measures only
```

It refuses a tree with uncommitted changes, fetches the upstream branch (into `refs/portkit/upstream/`, moving none of your branches), counts the commits and the files that would conflict, and merges with one merge commit when nothing conflicts. It never rebases and never pushes. Each run is a row in `<work.runs>/syncs.tsv` with its seconds. When files would conflict it changes nothing, lists them and exits 3: merge by hand by the rules below (for the app, the production merge), then run `tools/sync` again, which records the merge. The next `cycle` compiles and tests the merged trees.

**Framework.** Merge the new commits of `framework.branch` into the port's framework integration branch, as a merge commit.

- Keep every upstream code change: fixes, new APIs, new crates.
- The port's framework changes stay. Where an upstream fix lands in code the port rewrote, carry the fix's intent into the port's version. If that needs a design call (the fix collides with a framework mechanism), stop and decide it as a lead question.
- Tests upstream adds or changes stay as upstream wrote them. Where one tests code the port replaced, carry it to the port's code with the same assertions.
- `Cargo.toml`: the union of the crate lists, with the port's pins and patch section kept. `Cargo.lock`: take the port's side while resolving, then let one resolve add upstream's new packages. CI workflow files: upstream's version.
- Check `cl check` for each crate with a conflict and each new crate, then compare `git diff <upstream head> <synced head> --stat` with `git diff <old upstream head> <old port head> --stat`: only the port's changes, and nothing of upstream's code lost.

Once a branch has been pushed, sync it with merges only. Rebasing or force-pushing a branch that others have pulled breaks their history.

**App: the production merge.** Production keeps changing during the port. Merge production's main branch (`app.base_branch`) into the port branch, area by area, with one build at the end:

1. **Measure** without writing: the merge base, upstream's commits since it, and the conflicted files from `git merge-tree --write-tree <port branch> <production head>`. Count the files that conflict, the files production modified that the port deleted (modify/delete), and production's new files that call UI code the port replaced.
2. **Write the merge plan**, `<work.landing>/merge-plan.md`, which every area agent reads:
   - "Read this first": the numbers and how they were measured, the merge base;
   - what production changed, in themes, with its PRs or commits;
   - the mechanism (below) and the test policy;
   - every conflicted file in exactly one area, with its conflict hunks and its class: **P** merge both sides by hand, **R** the port replaced this code (carry production's intent to the target the plan names), **C** the framework already covers it (record which file and test), **T** a test;
   - the modify/delete files and what happens to each (the port's deletion is kept; production's intent goes to the port's replacement);
   - framework items production's changes need, for one framework agent;
   - areas with their model, call estimate and dependencies; the combine order; the owed lines (registry files such as module lists and shortcut tables get their lines from the areas' reports, applied by the lead);
   - risks and questions for the developer (architecture only).
3. **Skeleton.** In a scratch clone, check out the port branch and run `git merge --no-commit <production head>`. Stage everything with the conflict markers left in, keep the port's deletion for every modify/delete file, and commit this as the skeleton on `merge/main`. It gives the final file list.
4. **Areas.** Each area branches from `merge/main` in its own code-only tree and resolves only its own files (`prompts/p9-production-merge.md` with `{{AREA}}` and `{{TASK}}`; task `prod-merge-<area>`). No builds. Production's tests: new ones are kept (rewritten against the port's harness when they drive replaced UI code, or listed as framework trials); tests the port cut stay cut.
5. **Combine** the area branches into `merge/main` in the plan's order, add the owed lines, and check that `git grep -nE '^(<<<<<<<|=======$|>>>>>>>)'` returns nothing.
6. **Build and test once**: `tools/compile-gate prod-merge` and `tools/test-run prod-merge --app`. Failures go back to the area that owns the file, as a small red round ([08-tests-and-red-rounds.md](08-tests-and-red-rounds.md)).
7. **Fold into one merge commit** with both parents: `git commit-tree <final tree> -p <port branch head> -p <production head>`, then fast-forward the port branch to it. No rebase.
8. Move `app.production` to the merged production commit, and record the merge: `tools/track event merge "production <sha> merged into the port"`.
9. **Compare again.** Merge production's commits into the production hooks branch ([01-setup.md](01-setup.md), step 6a), rebuild production, build the port at the merged head, and run `tools/look pair --all`. Judge what changed as in phase 8 ([09-look-and-behaviour.md](09-look-and-behaviour.md), step 2). The landing tools want every pair from the head they land (next section).

## Early CI on the fork

The repositories' CI builds legs that no local build runs: wasm, macOS, Windows. Run them on small diffs during the port, not all at once at landing. After the pilot's framework sets go green, and after each green framework batch, `cycle` notes the command when `land.early_ci_fork` is set:

```sh
tools/land/early-ci.sh fw <framework tree> <ref> <label>
```

It clones `<ref>` under `work.landing`, scans and scrubs the range since its merge base with `framework.branch` (step 2), and stops before any push when hits remain. Then it pushes upstream's `framework.branch` head to the fork's `framework.branch` without force, so the PR's diff is the port's alone (a fork branch that has diverged stops it), pushes the scrubbed head to the fork's `port-ci/<label>` with force (the kit owns those branches), and opens one draft PR there into `framework.branch` with `gh`, or leaves the open one, which the push updated. It never targets `framework.repo`, `app.upstream` or `land.push_target`, and every PR is a draft.

It pushes only when `land.early_ci_approved` is true, the developer's standing approval from phase 0 ([01-setup.md](01-setup.md), step 3a). Otherwise it prints the commands for the developer. Each run is a row in `<work.landing>/early-ci.tsv`. A red leg is fixed on the port branch like any failure: a small red round for a test, a direct fix for a lint or a platform gap. Early CI covers the framework; the app's CI runs at landing (step 5).

## The exit gate

Both landing tools run two groups of phase 8 exit items before they scan anything (`tools/land/exit-gate.py`):

- **Look:** every map section has a states file, every state has a pair captured from the commit being landed (and the other integration tree's head), every difference is fixed or has a `kept: <reason>` row in the differences file, and every panel is accepted ([tools/look.md](../tools/look.md), "The phase gate").
- **Tests:** every test of the baseline that left the suite has a `delete` verdict or a `move` target that passes (`tools/test-ledger.py --check`; the ledger is `<work.runs>/ledger.tsv`, rebuilt by each full test run).

When one fails, the tool prints it and stops with exit 1.

The one override is the decision recorded with `tools/track phase 9 --force "reason"`. The landing tools pass when the latest `track phase 9` record forced every item that fails at landing time, and print that decision. An item that fails later and the decision did not cover needs a new one: `tools/track phase 9 --force "reason"` again, which checks the phase 8 items once more and records them.

`land-framework.sh` runs the exit gate only from phase 8 on. Before that, an early framework landing after a build batch prints that the gate does not apply yet.

## Step 2: the pre-push scrub

Nothing that names the developer, their machine or their local tools may reach a public repository: absolute home paths, local tree names, host names, private domains, user names, emails, private tracker ids. This holds for files and for history (commit messages, authors, every added line).

- **Patterns.** Generic shapes ship with the kit (`tools/portkit/scrub.py`: home, cache and scratch paths, emails other than noreply, IPv4 addresses other than 127.0.0.1, private host name suffixes). Names that identify you live only in your private patterns file, `land.private_patterns`, never in any repository: a scrub list that names you is itself the leak.
- **Scan.** `tools/land/scan-range.py <clone> <range>` checks authors, committers, messages and added lines of every commit in the range, with both pattern sets. Commit identities you accept go in `land.known_idents`.
- **Rewrite.** The landing tools rewrite only the range being landed, with `git filter-repo`. The generic `land.rewrite_rules` change only the local home prefix, never ordinary text (emails, host names, cache directories stay and the scan reports them), and no rule touches a trailer line (`Co-authored-by:`, `Signed-off-by:`): identities are reported, never rewritten. The rules are local framework paths replaced by `land.sibling_framework`, and your private message replacements (`land.replace_message`). Then they scan again; the second scan must be clean.
- **First push of a branch:** the range is its whole history from the upstream commit it started at.

The kit repository itself uses the same idea through `tools/kit-check` and its pre-push hook (CONTRIBUTING.md).

## Step 3: land the framework

```sh
tools/land/land-framework.sh <framework tree> <ref>
```

It fetches only `<ref>` and its history into a fresh repository under `work.landing` (never touching your trees; no other branch or tag comes along), runs the exit gate from phase 8 on ([The exit gate](#the-exit-gate)), fetches `framework.branch` from `framework.repo`, and checks that `<ref>` is a fast-forward of it. If not, it stops and lists upstream's missing commits: sync first (step 1). Then it scans and scrubs the range `framework.branch..<ref>` (step 2), runs `cl check all` in the landed clone ([step 3a](#build-the-landed-clone-before-any-push)), and prints the landing commands. With `land.framework_via = "pr"` (the default), it prints the commands to push a branch and open one PR per build batch, which a framework maintainer fast-forwards onto `framework.branch`. With `fast-forward`, it prints the push to `framework.branch`.

You read the scan report, then push from the clone yourself (the push uses your accounts). Record it: `tools/track event landing "framework <sha> to <framework.branch>" --task land-framework`. The landing tools post their own run events.

After the push, move the framework integration branch to the landed head before the next combine, so the next landing is again a fast-forward. The scrub changed commit ids, not code: `git diff <local head> <landed head>` shows only scrubbed lines.

### Build the landed clone before any push

Both landing tools run the framework's `cl check all` (`build.cl`) in the scrubbed clone after the second scan and before they print a push command. The scrub and the pin change files the port never built, so only this build shows that what leaves the machine compiles. A failure, or a missing `build.cl` or `framework.checkout`, stops the tool with "Do not push" and exit 1. The only way past is `--skip-check "reason"` (for example, no network for the pinned git dependency): the tool prints the reason and records it on the dashboard as a landing event. The check log is `<clone>.check.log`. The check may update `Cargo.lock` in the clone; commit that change as step 4 says.

## Step 4: land the app

```sh
tools/land/land-app.sh <app tree> <ref> <landed framework rev>
```

It fetches only `<ref>` into a fresh repository under `work.landing`, runs the exit gate ([The exit gate](#the-exit-gate)), finds the merge base with production's `app.base_branch`, and scans and scrubs that range, replacing local framework paths with `land.sibling_framework`. Its last commit pins every framework dependency to the landed framework revision by git rev (`tools/land/pin-framework.py`, for every URL in `framework.patch_urls`) and drops the local framework patch block. It then runs `cl check all` in the landed clone and prints the push command to `land.push_target`, branch `land.push_branch`.

1. Pin only a framework revision that is already on `framework.branch` upstream (step 3 first). An app pinned to an unpushed or scrubbed-away commit does not build for anyone else.
2. Regenerate `Cargo.lock` in the landing clone against the pinned revision with one resolve, and commit it. The lock must name no local path and no framework URL other than `framework.repo`.
3. Read the scan report and the pin's changed files, then push from the clone yourself.
4. Record it: `tools/track event landing "app <sha> to <land.push_branch>" --task land-app`.

**Who lands what (recommended; not yet confirmed by the framework maintainers).** Framework changes reach `framework.branch` as one PR per build batch, which a framework maintainer fast-forwards. The porter pushes the app to the app repository's landing branch directly. The scrub always runs first.

## Step 5: CI

The push starts the repositories' CI. Upstream CI may refuse things a local build accepts, for example a git dependency from outside the project's organisation, or a path dependency: the pin step exists for that.

- Record the result for each repository: `tools/track event landing "CI <passed|failed> at <sha>" --task land-app`.
- A failure is fixed on the port branch (a small red round when it is a test, a direct fix when it is a pin or a lint), then landed again through steps 2 to 4. An agent that fixes it gets its brief from `prompts/p10-followup-fix.md` ([After landing: follow-up fixes](#after-landing-follow-up-fixes)).

## Before the merge: run the app on each platform

The developer runs the landed app once on each platform it ships on (a window opens, the main surface draws, one edit works) before the PRs merge. CI builds the legs; only a run shows a window that opens blank. Record each platform and the result in `STATE.md`.

## After landing: follow-up fixes

Work after landing (issues on the landed port, red CI legs, conflicts on the landing PRs) runs as one-off tasks, one fix per agent. Render every brief from `prompts/p10-followup-fix.md`, never write one freehand: it carries `rules/agent-common.md` and gives the agent one warm build tree from the pool or a seeded target dir, cargo in the background with a notice, no sleep loops, the call budget and when to stop. Answer its plan, look at its result yourself, and land the fix through steps 2 to 4.

## Exit

- [ ] Production's main, as of the last sync, is merged into the port with one merge commit; the build and full run after it pass; `app.production` is at the merged commit.
- [ ] Every pushed range was scanned with the generic and private patterns, and the second scan was clean.
- [ ] The framework changes are on `framework.branch`, and the framework integration branch is at the landed head.
- [ ] The app's landing branch pins the landed framework revision by git rev, with no local path left, and is pushed.
- [ ] `cl check all` passed in both landed clones, or each `--skip-check` reason is in `STATE.md`.
- [ ] The exit gate passed for both landed commits, or the `track phase 9 --force` decision covers what it reported.
- [ ] The developer ran the app once on each platform it ships on, and the results are in `STATE.md`.
- [ ] CI results for both repositories are recorded on the dashboard and in `STATE.md`.
- [ ] `tools/track md` has written `STATUS.md` in the workspace.

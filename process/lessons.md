# Lessons

What went wrong in earlier ports, and what the process changed because of it. Each section gives the measurement, then the change and where the kit holds it. Numbers are labelled with the port and the phase (this kit's phase numbering) they come from.

## Per-task waves were replaced: 30 of 249 tasks in 21 hours, 68 % idle

The first PhotoCraft port ran as waves of per-task agents: each agent planned, wrote, built and gated one task, and merged it. After about 21 hours, 30 of 249 tasks were done. At that pace the whole port would have taken about a week.

Where the time went (PhotoCraft, per-task waves, 14 tasks over 122 hours of wall time):

| Category | Hours | Share |
|---|---|---|
| Idle: quota stops, a scheduled wake that never fired, tasks paused before start, tasks queued after an answer | 83.6 | 68 % |
| Implementing | 10.9 | 9 % |
| Fix rounds (27 rounds, about 0.5 h each) | 9.8 | 8 % |
| Waiting for the one shared check directory | 5.6 | 5 % |
| Waiting for a lead answer or a merge | 5.5 | 4 % |
| Runs in the check directory | 4.0 | 3 % |
| Gates | 2.9 | 2 % |

- Without idle time, a task took 2.8 hours on average. Each task paid the same overhead again: a cold compile of the app at its own framework pin (8.5 to 15.5 minutes), a queue for the one check directory (about 1.9 hours per task with tests), and gate rounds.
- One missed wake left 7 tasks idle for 7.1 hours each. A merge loop never ran for half an hour because its process check matched its own command line.
- In the first 35 minutes of wave 1, 5 of 20 tasks stopped at their plan on design questions, and 4 of them waited 25 to 30 minutes for an answer. The Workflow run dropped 4 tasks, which needed reruns.
- Five fix rounds went to a fresh agent because the old one had passed about 300k tokens of context.
- 137 must-fix items from gates and reviews fell into a few classes: missed production paths (about 27), design questions the brief left open (about 27), look mismatches (about 25), a second mechanism beside an existing one (about 17), facts taken from side effects or per-frame work (about 10), missing states, literal values, uncompiled tests, rebase slips, missing trials. About half could have been caught by the implementer before hand-back.

What changed:

- The batch model ([00-overview.md](00-overview.md)): plan everything with read-only agents, write with no builds, build once per batch. The overhead is paid once per build batch instead of once per task.
- Design questions are found and decided in the plan (phase 2) and the plan check (phase 4), before writers start.
- Every batch starts as a background task whose exit notifies the lead; no hand-written polls ([12-running-agents.md](12-running-agents.md)).
- The dashboard shows a question the moment it is asked, and stale tasks in red (`tools/track.md`).
- Tasks are sized to about 150 tool calls (`rules/lead-rules.md`).

## The gallery port passed every check and was still worse than the old one

Before PhotoCraft, the framework's own component gallery was moved onto the new framework. It passed every check, and the developer still found it far worse than the old gallery:

1. It was rebuilt, not ported: agents built a minimal shell (no dock, no overview, module paths as names, flat surfaces), and nobody held it against the old gallery.
2. Every check was about behaviour. About 1,500 component trials ran in CI; none looked at the screen.
3. No trial ran the app itself. The native gallery panicked on its first frame in debug builds; the release build skipped the assert.
4. Framework defaults were never compared on every target: on the web, every label drew in the toolkit's fallback font.
5. Two event forms carried one meaning (a chevron click and the Right key reported "open" differently), and a domain crate had worked around it instead of fixing the framework.

What changed: the old app is the spec, written down as the map in phase 1; a side-by-side gate for every changed state; driving the app like a user; an app smoke trial; framework defaults compared on every target; a framework gap gets a framework fix ([rules/porting-rules.md](../rules/porting-rules.md), "Look" and "Tests and builds"; [09-look-and-behaviour.md](09-look-and-behaviour.md)).

## Plans are wrong more often than they look

- **Phase 1** (PhotoCraft): the Opus area maps corrected 9 to 19 inventory entries per area. The lead's spot checks against the code are part of the exit.
- **Phase 2** (PhotoCraft): the first evaluation found plan error rates of 21 to 52 % per area; after one fix round, 9 %. The fact answers were good (0 of 45 sampled wrong, 6.5 to 7 % partly wrong), so the errors came from the planning, not the facts.
- **Phase 3** (PhotoCraft): the eight stub stages found 56 plan errors: signatures that could not compile, name collisions, callers no sheet listed, items with no signature, behaviour text naming things that did not exist, items listed under the wrong crate, old bodies kept beside new ones. Each was fixed in the plan before its set was written.

What changed: phase 3 compiles every contract signature before anyone writes, and its errors go back to the plan ([04-contract-stubs.md](04-contract-stubs.md)); phase 4's audits check the plan against the stubs and the SCIP index ([05-plancheck-decide.md](05-plancheck-decide.md)).

## The plan check needed three rounds to label well

PhotoCraft, phase 4, evaluation batches of 13 sets each:

| Round | Prompt change | DECIDE per set | DECIDE precision | Cost |
|---|---|---|---|---|
| 1 | "Not DECIDE" rule added | 1.6 | 81 % | $9.50 |
| 2 | Every item must rest on a lookup; an item the rules already pick is RULE | 0.23 | about 2.5 of 3 | $5.40 |
| 3 | "Always DECIDE" triggers; unsure means DECIDE | 1.8 | 91 % | $7.30 |

Round 2 looked better by precision, but its RULE items hid real choices: a hash of inputs standing in for a counter the sheet asked for, a fallback arm beside a mechanism (a second path, against the rules), an item made public only for a trial. Round 3 brought those back as DECIDE without losing precision. The full run then checked 236 sets and found 485 DECIDE items.

What changed: the "always DECIDE" list is part of the plan-check prompt, and the evaluation loop scans RULE items for hidden choices as well as counting precision ([05-plancheck-decide.md](05-plancheck-decide.md), step 2).

## The pilot showed where review findings come from

PhotoCraft, phases 5 and 6, one area of 18 sets written, reviewed, compiled and tested before the rest:

- 72 review findings, about 4 per set: 30 % sheet or contract errors, 35 % writer errors a plan check could catch, 25 % errors only a compile or test run catches, the rest bookkeeping between sets. No set needed a rewrite.
- Framework compile: 5 writer errors in 5,900 lines, all small borrow or move slips that only rustc reports. No error pointed at the plan.
- First test run: 221 failures, of which 209 were expected (stubs and lines of sets not yet written), 9 were pilot writer bugs, 1 a plan error, 1 a stale test.
- Five components had no story owner.

What changed:

- Each sheet carries worked examples for index and ordering schemes, names the mechanism a decision relies on, and lists every event variant it maps; the decision agents check index schemes and platform signals in every sheet.
- The base stays still while writing: stubs are refreshed and audited before writing, and files a decision adds go into the sheet's Files table first. Stub items added after a set was written, and files outside the Files table, cost the most bookkeeping.
- Edits apply once (a rerun skips applied blocks), and the post-write check warns on the patterns behind the pilot's defects.
- The story-owner audit ([05-plancheck-decide.md](05-plancheck-decide.md), step 8).
- Budget one compile pass and one or two test rounds per area: some errors only rustc or a run finds (borrows, focus, key routing).

## Red rounds: from one cause per agent to one build for every fixer

**Fix loop, one cause per agent** (craft-libs framework migration, its test phase): 19 full runs found 315 distinct failures; 220 were fixed and 65 stayed red through the last 7 runs. Agents had 2 or 3 remote runs each (5 minutes median) and spent 74 % of their tool calls searching and reading, then reported "not diagnosed". Letting them build and run locally, with diagnostic prints, made causes visible.

**Fixers with their own builds** (PhotoCraft, phase 7): each fixer owned an area, built and ran its own tests. An app rebuild after a framework change took about 12 minutes, so fixers spent most of their time waiting, and fixers sharing a target dir queued behind each other.

**Code-only fixers, one shared build** (PhotoCraft, phase 7): every fixer writes fixes for its whole list by reading, adds `DIAG` prints where unsure, and hands back; the lead merges every branch, builds once, runs once and sends each fixer its still-failing tests with their panic lines and DIAG output.

- Failing tests per round: 275, 215, 154, 121, 98, 68 (of about 12,100).
- One such round: 5 fixer branches merged, one duplicate mechanism resolved to one, an app compile of 723 seconds with no errors, a full run of 1,030 seconds; failing tests went from 98 to 68, with 1 new failure, attributed to the fixer whose change caused it.
- Triage of 420 failing tests: keep 196, cut 166, cut-fix 29, move 28. Two in five failing tests were tests to delete, not code to fix.

What changed: the code-only fixer model is the default ([08-tests-and-red-rounds.md](08-tests-and-red-rounds.md)); triage comes before fixing; a fixer is resumed with its packet, never replaced.

## Calibrating the triage model

Framework test sweep (craft-libs framework migration), the lead's reference on a sample against two models:

| Sample | Haiku agreement | Sonnet agreement | Haiku: reference delete judged keep | Sonnet: reference delete judged keep |
|---|---|---|---|---|
| First prompt, 60 tests | 47 (78 %) | 51 (85 %) | 12 | 6 |
| Revised prompt, 55 tests | 37 (67 %) | 52 (95 %) | 17 | 3 |

Haiku leaned toward keeping tests that the reference deleted, more so with the revised prompt; Sonnet improved with it. On these numbers Sonnet is the triage default (`models.triage`). The sweep then judged 4,412 framework tests: 2,652 kept, 1,760 deleted.

What changed: every sweep and triage starts with a calibration ([08-tests-and-red-rounds.md](08-tests-and-red-rounds.md), step 2).

## Build loops: where the waiting came from

craft-libs framework migration, a read-only review of the build setup and existing timings:

- **Feature-set churn.** The same crate existed in 2 to 5 feature variants in every target dir, so commands rebuilt the framework and its dependencies again and again; one full workspace test build took 43 minutes.
- **Fixed job slots.** Each build was capped at 4 jobs on a 16-thread machine, so codegen-heavy steps took 3 to 4 times longer.
- **Optimised workspace crates in dev.** opt-level 1 on the framework crates turned a one-line rebuild from 28.7 seconds into 215 seconds.
- **Every look change went through the whole gallery binary** (17 app crates and a 1.1 GB link) instead of rendering one story.
- **Per-agent target dirs started cold** for workspace crates.

What changed: `cl` with one feature resolution per workspace and the app selection, a shared jobserver as the optional launcher, opt-level 0 for workspace crates in dev, per-story rendering, and warm shared trees instead of reseeded ones ([11-build-loop.md](11-build-loop.md)). Slowness is found by reading the setup and existing timings, never by another long timing run ([rules/porting-rules.md](../rules/porting-rules.md), "Tests and builds").

## Landing and app batches

- **Patch every framework package.** The first PhotoCraft app batch (phase 6) patched only the app's direct framework dependencies. The lock file held 57 packages from framework URLs; the 37 transitive ones would have built a second time from git, with types that differ from the path copies. `tools/patch-framework` patches every framework package in the lock ([07-review-combine-compile.md](07-review-combine-compile.md), "Setting up an app batch").
- **First app compile.** The first PhotoCraft app batch compiled with about 150 errors, against 0.85 per 1,000 lines on the framework side: app code written against stubs meets real framework code for the first time there. App sets are written after the framework builds, against the real code.
- **Production moves.** By landing time, production had 1,090 new commits and 181 conflicted files against the port (PhotoCraft, phase 9). The merge runs by areas from one skeleton commit, with one build ([10-land.md](10-land.md), step 1).
- **Scrub lists leak.** The first scrub scripts listed personal names and host names inside their own pattern lists. The patterns that name anyone live in a private file outside every repository ([10-land.md](10-land.md), step 2).

## Write a codemod for a class

When one mechanical change hits many sites, a script beats a batch of agents. In the PhotoCraft port, tests that held the app built a fresh UI context instead of the app's own. A script found each site, rewrote the cases where the app binding was plainly in scope, and listed every other site for a person to judge. Agents doing the same edit site by site would have cost a fix round each and drifted in style.

Use this whenever a review, a compile or a triage shows one cause at many sites: write the codemod, apply it to the clear cases, and give the rest to one fixer.

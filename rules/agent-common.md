# Rules for every agent

Every agent prompt and brief in a port includes this file. Your prompt gives your job, its inputs and outputs, and the reference values. This file gives the rules every job shares.

## Source precedence

When two sources disagree, the first one in this list wins:

1. The rules: `porting-rules.md`, `framework-decisions.md`, `testing-rule.md`.
2. This file.
3. Decisions the lead recorded for this port: lead rulings in your prompt, the set's `decisions.md`, the plan's `settled.md` and `rulings.md`, `STATE.md` "Decisions".
4. Your prompt, brief or sheet.

If your prompt contradicts a source above it, stop and report the contradiction. Do not pick one.

For facts, these hold:

- **The code decides what the code does.** When a sheet, a map or a brief describes code differently from what is at the named commit, the code is right. Report the difference.
- **Production decides how the app looks and behaves** (`app.production`, the production checkout the port last merged). App tests are evidence of intended behaviour, not a specification.
- **The framework's own docs and the gallery decide what the framework offers.** Read them (craft-libs `docs/`, the UI gallery's stories) before searching the code, and never restate the framework from memory.

## Plan first

When your brief asks for a plan (one-off tasks, briefs from `prompts/p8-task-brief.md`):

1. Before your first edit, append `## Plan` to your report file: the mechanism you will build on (file:line), the files you expect to change, and how you will check the goal (trials, captures, the commands your brief allows).
2. End your turn with the plan as your reply. The lead answers "go" or corrects it. Do not edit before that answer.

Writers in a batch (`port-set`, a batch job) start from their sheet and the set's decisions, which the plan check already reviewed. They do not stop for a plan unless their prompt says so.

## Tracking

The port has one progress dashboard (`tools/track.md`). Your prompt gives your task id. These calls are rules, not suggestions:

- At the start of every step: `track step TASK STEP` (`plan`, `write`, `compile`, `test`, `fix`, `merge`, or the steps your prompt names). If it exits 3, the port is paused: stop and report.
- On every state change: `track status TASK STATE "what happened"`. When blocked or waiting, name what on with `--on` (a task id, `developer`, `lead`, `review`, `check`).
- Every question: `track ask TASK "question" --recommend A --option A --option B`, as "Questions" below says. Never wait silently.
- On hand-back: `track status TASK review "summary" --calls N --link report=PATH`, where N is your tool-call count.

Kit tools record their own results (gate outcomes, test counts, set states). Do not repeat them with `track`; report only your judgement.

If your prompt names a report file, also append one line per step under its `## Progress` heading: UTC time, what is done, what is next.

## Scope and signals

- Your brief's files are where the work starts, not a fence. Make the clean fix where it belongs, in any file, framework and public API included, when your goal and mechanism decide what the fix is.
- When you edit a file that your brief says other running tasks also edit, keep that hunk minimal and list it in your report. The lead resolves overlaps when combining.
- Use the framework's own signals: what a story opens, which key was pressed, which kind of component it is, what has focus. Never infer such a fact from side effects (focus movement, sizes, text, draw order). If the framework has no signal for it, adding the signal at its mechanism is part of the fix.
- Do not start subagents or workflows. If you need to find something your brief does not give, search for it yourself with one narrow, batched search (several patterns in one command), or ask the lead.

## Questions

Most questions have an answer already, and most of the rest do not need to wait for one.

1. **Look first:** the plan's `settled.md` and `rulings.md`, the set's `decisions.md`, and the cross-set decisions (`shared.md` in the decide directory). A question one of them answers is not a question.
2. **Recommend.** Every question carries the option you recommend: `track ask TASK "question" --recommend A --option A --option B`.
3. **Proceed** on your recommendation, unless the question is on the always-DECIDE list below. List it in your report under "Assumptions": the question id, the option you took, and the file:line it shaped. The lead rules on the batch's assumptions together; a ruling that differs from yours comes back as a fix.
4. **Always DECIDE.** A question on this list blocks the work that depends on it. Ask it with `--blocking`, stop that work, carry on with the rest, and report with the options:
   - your prompt, brief or sheet contradicts a source above it ("Source precedence");
   - a new public concept in the framework, or a change to a contract row or pinned signature that other sets build on;
   - a behaviour change from production that no rule or decision settles, or production and a rule in `porting-rules.md` disagree;
   - a change to saved data: file formats, settings, document contents;
   - deleting a test that the plan or the triage table marks `keep`;
   - anything that only the developer decides: goals, design principles, architecture.

A brief or sheet that describes code differently from the code is not a question: the code is right ("Source precedence"); follow it and report the difference.

## Stop and hand back

Stop, commit what is done, and hand back with what is left when your work turns out much bigger than your brief expected (past about 150 tool calls, or a second distinct piece of work appears). The lead decides, and starts a fresh agent with a corrected brief when the brief was wrong.

## Shared code

Before changing what a shared function, helper or rule does (anything with callers outside the code you are fixing), find every caller and every trial that uses it: grep, or the SCIP index when your prompt names one. Check each against the new behaviour before writing the change, and list the callers you checked in your report.

## Code, tests and the UI gallery

- Code follows `porting-rules.md`, "Code". Tests follow `testing-rule.md`.
- Before you plan or write a new component, check the framework's UI gallery for one that already does the job. Every component or variant you add to the framework is registered in the gallery in the same change: stories for its states and each named variant, at the gallery level of its architectural kind, with a story owner (`porting-rules.md`, "UI gallery").

## Builds and runs

Only when your prompt gives you builds:

- Every cargo command goes through `cl` (`process/11-build-loop.md`), in the tree and target dir your prompt names. A cargo command without them builds a second copy of everything from scratch.
- One cargo command at a time. No workspace-wide build or test, and no full CI command locally.
- Read only the failing lines of a run: grep the log for `^test .* FAILED$`, `^---- `, `error\[` and `panicked at`. Never read a whole log.
- To debug, print values at the suspected path with lines that start with `DIAG `, run the one trial, read, repeat. Remove every `DIAG ` line before you commit the final change.
- Bound every wait with a timeout. No polling loops on a process.

Without builds, you write code that compiles by reading carefully: check every import path, signature and trait bound against the code. **Formatting:** an agent that runs no builds formats each file it changed with `rustfmt --edition 2024 <file>`, which needs no build. `tools/cycle` runs `cargo fmt` on the changed crates only, never on vendored code (`process/11-build-loop.md`, "The cycle").

## Git

- Work only in your own worktree and branch. Commit there, in steps, with plain messages that say what changed.
- Never `git stash`: stashes are shared by every worktree of a repo. Commit a work-in-progress commit instead.
- Delete tracked files with `git rm`, so the deletion is part of the commit.
- Push only when your prompt says so, only your own branch, and never force-push a shared branch.
- Before your work merges, rebase it on the shared branch your prompt names. Fixes after a merge go on the shared branch.
- Do not regenerate generated docs (component indexes, API listings) unless your prompt says so. The lead does that once.
- Commit messages and code carry no attribution lines and nothing that names your machine, your accounts or personal data.

## Report

Write your report where your prompt says (its template is `templates/task-report.md` unless your prompt gives another), and give the same content as your final reply:

- the commit sha, the goal, and whether it is met;
- the cause or causes with file:line, and the fix;
- framework edits, and the callers you checked;
- edits in files that other running tasks also edit;
- tests added, rewritten or deleted, each with its reason under the testing rule;
- the checks you ran, with their actual results (counts, failures); never a check you did not run;
- what still differs from production, with the states compared;
- findings outside your goal, one line each with file:line;
- "Assumptions": each question you proceeded on, with its id, the option you took and the file:line it shaped;
- blocking questions you stopped on, with options and your recommendation.

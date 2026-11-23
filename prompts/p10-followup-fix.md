# p10-followup-fix

Brief for one fix after landing: an issue on the landed port, a red CI leg, or a conflict on a landing PR. The lead fills every field. Fill the placeholders with `tools/render-prompt`.

## How the lead uses this file

Copy the block under "The brief" into {{WORK}}/briefs/{{TASK}}.md and fill every field marked `<...>`. One brief per fix: a second issue or a second red leg is its own task. Before you write it, take a build tree for the agent: a free tree of the pool with its warm target dir, or a new target dir seeded from a warm one with `{{KIT}}/tools/seed-target <new-target> <warm-target> <worktree>` ({{KIT}}/process/11-build-loop.md, "Target dirs and trees"). Never hand an agent a cold target dir: it rebuilds every dependency before its first test. Put the task on the board before you launch it: `track status {{TASK}} todo --title "<one line>"`. When the agent hands back, give the build tree back to the pool and record the fix (`track event merge "{{TASK}}"`, or `track event landing` for a push).

## The brief

```
# Task {{TASK}} (round <R>)

Kind: <issue fix | CI fix | PR conflict>. Source: <the issue, PR or CI run, with its link or id>.
Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md first, in full.
Model: <sonnet for a well-specified fix; opus for framework work or anything that needs judgement>.
Do not start subagents or workflows.

## Goal
<What works when this is done, in a few sentences: the behaviour the issue asks for, the CI leg that passes, or
the PR that merges cleanly. Copied word for word into every later round.>

## What failed
<The failing lines only: the CI log lines (`error[`, `^---- `, `panicked at`, the failing step's name), the issue's
steps and expected result, or the conflicted files with their hunks.>

## Tree and branch
- Build tree: <path>, target dir <path> (warm). Branch <branch>, from <base sha>.
  Switch to the branch inside the tree with `git switch`; check that the switch succeeded before anything else.
- Shared branch to rebase on before your work merges: <branch>.
- Push: <"no push: the lead pushes" | "push only <branch> to <remote>">. Never force-push a shared branch.
- PR conflict: merge the target branch into the PR branch (one merge commit), never a rebase of a pushed branch.
  Keep both sides' intent; where the port replaced the code, carry the target's change to the code that replaced
  it ({{KIT}}/process/10-land.md, "Step 1: sync with upstream").

## Mechanism and start
<The framework signal or declaration to build on, and the files and lines where the work starts, with the callers
you found. If the fix needs a design choice that is not made yet: "Stop and report the options".>

## Builds and waits
- Every cargo command goes through `cl` in the build tree above: `cl check <crate>`, `cl test <crate> -- <tests>
  --test-threads 4`. One cargo command at a time; never `cl test all` or a workspace build.
- Run each cargo command through `cl` in the foreground with the Bash tool's timeout (up to 10 minutes). A command
  you move to the background gets one bounded wait per call, `timeout 170 ... until <done marker>`, and you wait
  again in the next call if it is not done. No bare `sleep`, no unbounded loops, and no agent whose only job is
  to wait.
- Read only the failing lines of a run (agent-common.md, "Builds and runs").

## Done when
- <The check that shows the goal is met: the named tests pass, the CI leg's command passes locally through cl, the
  merge has no conflict and `cl check` of each conflicted crate passes.>
- The change is committed on your branch with a plain message.

## When to stop
Stop, commit what is done and hand back when:
- you reach about <N, at most {{FIXER_CALLS}}> tool calls;
- a second distinct problem appears (another failing leg, another issue): report it, do not fix it;
- the cause lies outside the goal or needs a design choice the brief does not make;
- the build tree is missing, busy or cold.

## Tracking
You report under the board task `{{TASK}}`. These calls are rules:
- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Steps: `plan`, `fix`, `build`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change (`running`, `review`, `waiting`, `blocked`, `done`); name the blocker with `--on`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as the last action, where N is your tool-call count.

## Report
Write the plan first and stop for the lead's "go" (agent-common.md, "Plan first"). Then append "## Update <R>" to {{WORK}}/reports/{{TASK}}.md (format: {{KIT}}/templates/task-report.md) and reply with it: the commit sha, the cause with file:line, the fix, the checks you ran with their results, and what is left.
```

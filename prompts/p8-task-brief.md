# p8-task-brief

Single-task brief for one-off work (a look fix, a framework gap found late): Goal, Reference, Mechanism, Start here, Done when, Report. The lead fills every field. Fill the placeholders with `tools/render-prompt`.

## How the lead uses this file

For a look fix, `{{KIT}}/tools/look brief <class>` writes the block under "The brief" to {{WORK}}/briefs/look-fix-<class>.md with its Look evidence filled from the differences file ({{KIT}}/tools/look.md, "look brief"); fill every field marked `<...>`. For any other task, copy the block into {{WORK}}/briefs/{{TASK}}.md, delete its Look evidence section and fill every field marked `<...>`. The agent reads {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md and this brief. Whatever else it needs, the brief names with its section. What you already looked up (files, lines, values, callers) goes into the brief, so the agent does not search for it again. A brief is complete and correct before the agent starts. Before you launch the agent, create its task: `track status {{TASK}} todo`. A task that builds gets a build slot: `{{KIT}}/tools/build-pool take {{TASK}}` prints the worktree and target dir for the brief; give it back with `{{KIT}}/tools/build-pool give {{TASK}}` when the agent hands back.

A follow-up brief copies the Goal of round 1 word for word, and updates the Reference table with the values as they now are. Each item in "This round" says which part of the goal it serves, and why. Write the item yourself from the review or gate verdict. A finding outside the goal is not an item: it becomes a new task. If the goal itself was wrong, stop: rewrite the brief from the base and start a fresh agent. A task that has grown past its goal is split: finish the goal, and open new tasks for the rest.

## The brief

```
# Task {{TASK}} (round <R>)

Worktree <path>, branch <branch> (from <base sha>, or tip <sha> for round 2 and later), target dir <path>.
Read {{RULES}}/agent-common.md and {{RULES}}/porting-rules.md first, in full.
Model: <opus for framework work or anything that needs judgement; sonnet only for a well-specified, mechanical change>.
Do not start subagents or workflows.

## Goal
<What the user sees and does when this is done, in a few sentences: which components, which views, which states. Copied word for word into every later round.>

## Reference
| Part | Production ({{PROD}} file:line, value) | New now (file:line, value) | Target |
|---|---|---|---|
| <part> | <path:NN, value> | <path:NN, value> | <the production value, the unified rule, or the behaviour> |

Relations that must hold for these parts: <for example "the title sits inside the band", "the chevron is smaller than the text">.

## Look evidence
{{LOOK}}

## Mechanism
<The framework signal or declaration to build on, with file:line. If none exists and adding it follows from the goal, say where it belongs. If it needs a design choice that is not made yet: "Stop and report the options".>

## Start here
<Files and lines where the work starts, with the callers you found.> Other running tasks also edit: <file> (<task>). These lists are not a fence: agent-common.md says how to treat a fix that belongs elsewhere.

## This round (round 2 and later)
1. <Item> serves the goal by <reason>. <file:line>.
Not in this task (outside the goal): <one line each, or "none">.

## Done when
- Trials: <behaviour trials by name, or "none: <reason>">.
- Pairs: <for a look fix: every state under Look evidence, through the `look pair` calls listed there; otherwise element, view, mode on the compare page `<track.out_dir>/look/<Panel>/`, made with `{{KIT}}/tools/look pair <Panel> --only <ids>`>. Judge them one image at a time: one crop per region at native scale, and the shots that fit in {{READER_MAX_PX}} px; never a montage, a contact sheet or a downscaled page. Sizes are image pixels at the scale <the capture scale, from Look evidence or the page> ({{KIT}}/tools/look.md, "Judging at full size").
- Verify by driving: <user actions and the expected result, if any>.
- Crate tests: <packages, with the base counts>.

## Tracking
You report under the board task `{{TASK}}`. These calls are rules:
- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Steps: `plan`, `write`, `compare`, `tests`, `report`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change (`running`, `review`, `waiting`, `blocked`, `done`); name the blocker with `--on`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as the last action, where N is your tool-call count.

## Report
Write the plan first and stop for the lead's "go" (agent-common.md, "Plan first"). Then append "## Update <R>" to {{WORK}}/reports/{{TASK}}.md (format: {{KIT}}/templates/task-report.md) and reply with it. Budget about <N> tool calls.
```


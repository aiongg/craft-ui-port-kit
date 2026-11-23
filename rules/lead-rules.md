# Rules for the lead

The lead is the agent session that runs the port (`process/00-overview.md`, "Roles"). These rules are in addition to `porting-rules.md` and `agent-common.md`, which bind the lead too. The phase runbooks in `process/` say what to run when; these rules say how the lead decides and organises.

## Deciding

- **Never wait on a decision these rules let you make.** Decide, record the decision and its reason in `STATE.md` "Decisions", and keep agents running. An idle port costs more than a decision the developer later changes.
- **Ask the developer only about goals, design principles and architecture.** Never ask layout or design questions: the old app answers those (`porting-rules.md`, "Look").
- **You own how the work is organised**, the tooling and the build setup. Decide, and tell the developer what changed.
- **Record every developer correction or preference** as one line in `STATE.md` "Decisions", in the same turn: merged with the line it refines, in plain words, no duplicates, no history. A rule that would bind every port is a change to the kit's `rules/`: propose it to the kit's maintainers.

## Models and cost

- **Pick each agent's model by need.**
  - Haiku: finding things, reading code for facts, builds, runs and logs.
  - Sonnet: writing, by default. Every set its sheet fully specifies, review fixes, compile fixes, red-round fixers.
  - Opus: judgement. Contract design, plans, evaluations, decisions, reviews, sets that change a shared mechanism, and a retry of a set or task a Sonnet agent failed.
  The `[models]` table in `port.toml` holds these defaults per step.
- **No large Opus bursts.** Spread Opus work over the quota window instead of starting many Opus agents at once. A burst spends the reserve the rest of the week needs.
- **State the cost before every batch:** the agent count by model, and the measured cost of similar runs (`process/costs.md`). Then launch.
- **Pace launches to the quota window.** Spread the agents that are left evenly until the window resets (the budget per hour is what is left divided by the hours to the reset), and keep agents running at that rate the whole time. Never a burst and then a pause. `pipeline.quota_command` and `pipeline.quota_cap` let the batch runners hold new jobs near the limit.

## Tasks and briefs

- **The schedule owns the work.** Every file the port writes belongs to one set (`ownership.md`), and every set has a sheet.
- **A new task starts only after three checks**, written at the top of its brief:
  1. No scheduled set or task owns its component, test or file: grep the sheets and `ownership.md`.
  2. Its cause is not transitional: old app code that a later set replaces belongs to that set.
  3. It blocks the current batch. Otherwise it is one line in `STATE.md` "Open".
  Agents' questions, findings outside a goal, production look differences and failing app tests are findings, not tasks, until they pass these checks. Reason: findings launched as tasks produce code that a later set deletes.
- **Every app test a task inherits** is assigned to the task that ports what the test exercises. A test of code that a later task replaces moves to that task before work starts.
- **One task fits in about 150 tool calls.** Split anything bigger before launch: one fix or one feature per agent. Every call re-reads the whole context, so an agent's cost grows with the square of its length: two half-size agents cost about half as much as one.
- **A brief is complete and correct before the agent starts:** the goal, the reference values, the mechanism to build on, and the testing instructions. One short brief per task; agents do not read a batch file holding every other task.
- **Briefs give places, not concepts:** the files and line numbers the task changes, the signatures it touches, and their callers. Whatever you already looked up goes into the brief. Send Haiku lookup agents to collect places, signatures and callers, and spend your own calls on decisions.
- **Every brief forbids the agent to start subagents or workflows.** A writer that starts its own agents spends Opus quota nobody planned.
- **Every brief includes the agent's `track` calls** (`agent-common.md`, "Tracking") and its task id.
- **Plan checkpoints for one-off tasks.** A one-off task's agent writes its plan and stops (`agent-common.md`, "Plan first"). Answer each plan as it arrives, with "go" or a correction. Never let an agent edit before you answer. A one-component look fix skips the checkpoint; you review it after.
- **A plan that only adds a mechanism goes back to its agent.** A fix that adds a mechanism removes the one it replaces in the same change.
- **Code-only trees while builds wait.** Agents plan and write in code-only worktrees with no target dir. A build tree is taken only to compile, run trials and capture, and is handed back at once (`process/11-build-loop.md`).

## Running the work

- **Batch everything known.** All fixes known now go into one batch with one build (`porting-rules.md`, "Efficiency").
- **Write order.** The pilot first, then all remaining framework-side sets as one build batch (two above about 60), with its review, compile and tests before the app sets ([06-write.md](../process/06-write.md), "Write order"). App sets are written after the framework builds, against the real code, in one or two batches. The number of build passes, not the number of sets, sets the wall time.
- **Before writing:** a stub audit (every pinned cross-set signature is in the stubs) and a story-owner audit (every new component has a story owner). `port-set audit` runs both (`process/05-plancheck-decide.md`).
- **The plan-check eval loop.** After each evaluation batch of plan checks, decide alone whether the checks are good enough for the full run. If not, change what is needed and run another evaluation batch. Repeat until the results are the best you can get, then run the full batch. The criteria are in `process/05-plancheck-decide.md`.
- **Integration.** One shared branch per repo, in one warm integration tree. In the batch phases, combine and build per batch (`process/07-review-combine-compile.md`). For one-off tasks, merge a change onto the shared branch as soon as it passes its own checks, then check the changed crates and run their trials there. A failure goes back to the agent that wrote the change.
- **One owner per bug or task, start to finish.** Follow-ups go back to the same agent, resumed. Start a fresh agent only when the old one's context is too large (`process/12-running-agents.md`).
- **Never redirect a running agent.** Stop it, and start a fresh one with a corrected brief. Resuming an agent after it handed back is not a redirect.
- **Sync once a day.** Merge the framework branch's new commits and the app's production main into the port once a day, at the heads as they are when the sync starts. Commits that land during or after it wait for the next sync. Never chase each upstream commit: the port would spend its time rebasing.

## Review and results

- **Merge rounds take up to about 10 finished branches.** The developer gets one update per merge round: what merged, what started, decisions taken. Anything that needs the developer goes to them at once.
- **The developer never waits on your checks.** Their run command goes out as soon as the shared branch moves, while local checks run in parallel. A failure there goes to them at once with a new head.
- **No upstream issue, PR or comment about the port** until the developer says so. Prepare the texts for them to read first.

- **One review per piece of work**, when its owner says the goal is met. Not a review per round.
- **Look at results yourself** (the captures, the pairs, the page, the test counts) before telling the developer anything is done or how it looks. An agent's summary or a score is not a check.
- **A component the developer flags** is looked at by you, old and new side by side at full size, before its fix is briefed.
- **Fix small things at once**, yourself or through the task's agent: what a review, a merge or a tool turns up. Anything bigger becomes a tracked task with an owner. Small things parked in a list are never done.

## The dashboard

The dashboard (`tools/track.md`) is the developer's view of the port. These duties are rules, not suggestions:

- **Before launching an agent, put its task on the board:** `track import sheets`, `track import tracks FILE`, or `track status TASK todo --title "..."`. Give the agent its task id.
- **At each phase change:** `track phase N "note"`.
- **Keep `track watch` running as a background task** while agents run. When it exits, act on every line of its digest, then start it again:
  - stale: read the agent's output; resume it, or stop it and start a fresh one with a corrected brief;
  - blocked or failed: remove the blocker or reassign, then set the task running again;
  - question: a blocking question; answer it, or pass it to the developer.
- **Rule on questions per batch, not one by one.** Agents proceed on their recommendation unless a question is on the always-DECIDE list (`agent-common.md`, "Questions"). Before the review findings of a batch are ruled, run `prompts/p-rulings.md` per area: it drafts a ruling for every open question and back-to-plan finding and applies the set-scope ones to the sets' `decisions.md`. Check its `cross-set` and `framework` rows yourself, write the ones that bind other sets into `shared.md` or `settled.md`, then record every ruling with one `track answer --file <rulings.tsv> --by rulings`. A ruling that changes an asker's assumption is a fix for that set's fixer.
- **Every question to the developer goes on the board and in chat:** `track ask TASK "..." --for developer --blocking --option ... --recommend ...`, and the same question in chat, in full, with the options and your recommendation. An answer in either place counts. Record it with `track answer QID "..."` and in `STATE.md` "Developer answers", in the same step. Closing or moving a task does not answer its question: the answer is recorded on the question itself, and a question left open after it was answered is a bug.
- **Record merges, landings and decisions:** `track event merge|landing|decision "..." --task ID`.
- **Pause around shared-branch moves:** `track pause` before a move that agents must not start steps across, `track resume` after it.
- **Blocking questions reach you at once.** `track watch` exits on the next poll after one is asked; never rely on the stale timer to notice a question.

## Background work and the machine

- **Run everything that takes more than a few seconds as a background task** (builds, gates, batches, waits), and start it so that its exit notifies you. Never wait in the foreground, and never poll a job with a hand-written loop that can miss its end.
- **Cap the memory of heavy jobs** (rust-analyzer daemons, builds, writer batches) with `build.memory_cap`, so an out-of-memory kill takes the job, not your session.
- **Headless agents run with the rust-analyzer LSP plugin off** (`templates/claude-settings.json`). Writers get diagnostics from the shared racheck daemons. Stop rust-analyzer servers nothing uses.
- **Keep build trees few and warm.** One integration tree per repo and a small fixed pool of build trees, each with its own target dir; agents switch branches inside them (`process/11-build-loop.md`).
- **Watch disk while builds run.** Trim target dirs by what the next build loses, never a whole incremental cache (`process/11-build-loop.md`, "Disk").

## Records and hand-offs

- **`STATE.md` holds the current state and the decisions**: phase, step, next action, pins, decisions, developer answers, open items. Update it at every phase change and every round.
- **Before a long break**, stop new launches, record the running agents and their task ids in `STATE.md`, and run `track md`.
- **Hand off at a stopping point** once your context is large: write the current state and pointers (not copies of earlier hand-offs) into `STATE.md`, run `track md`, and stop your monitors. A session that starts without context reads `STATE.md` and `track show` before anything else (`process/12-running-agents.md`).

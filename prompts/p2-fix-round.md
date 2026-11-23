# p2-fix-round

Opus: one job of the plan fix round: re-check a contract part, write verified set sheets, or assign unowned files. Fill the placeholders with `tools/render-prompt`.

You work on the fix round of the planning phase of the port of {{APP}} to the {{FACADE}} framework. The consolidated plan had its independent evaluation ({{PLAN}}/eval-*.md). Sampled items are only evidence: the plan gets one more evaluation, so this round must remove each error class from everything it owns, not fix the sampled items one by one. Read {{RULES}}/agent-common.md, {{RULES}}/porting-rules.md and {{RULES}}/testing-rule.md in full first.

## Error classes

A fix-round job runs one sweep per class over every file it owns: the six standing classes below, which appear in every area, and each class the evaluators named, listed after your job section with what it looks like and how to find it. (A reconcile job applies its inbox instead, and checks each row it applies against the same classes.) For each class, check every sheet, row or contract item you own, not only the sampled ones, and fix every instance. Log one line per class in {{OUT}}/logs/<your job id>.md: `class <name>: <n> found, <n> fixed`, then the ids or paths you changed.

The six standing classes:

1. **File actions copied across a row.** One action written for an area-plan row (for example "delete") was applied to every file in the row. Derive each file's action again from the chunk plans and the code: `delete` only when every function goes and its readers move; `edit` when kept functions stay; `rewrite` only when most of the file changes.
2. **Old snapshots.** The plans read the code at older revisions. Re-read everything at the current bases: framework {{FW}} and app {{APP_SRC}} (read only), at the revisions {{STATE}} names.
3. **Incomplete reader lists.** Readers missed tests, examples, re-exports (`pub(crate) use`), other crates and the app's binaries. Find every reader of a removed or changed mechanism with `git grep` over the whole repo.
4. **Duplicates and invented signatures.** Framework items that duplicate an existing mechanism (a second link text, a second point-to-value mapping, state kept across passes), and signatures written without reading the code they extend (types, icons or methods that do not exist).
5. **Decisions that never arrived.** Settled decisions ({{SETTLED}}, {{PLAN}}/conflicts.md, developer answers in {{STATE}}) that never reached the contract or the file sets. {{PLAN}}/eval-coverage.md, sections 5 and 6, lists the settled rows a set does not cite by id and the open-question markers left in set texts: carry each decision with its id, and decide or remove each marker.
6. **Rewrite sized as the whole file.** "Write" counts lines changed. A file whose kept functions stay is `edit`: the writer edits it in place and never retypes kept code.

## Rules

- Read-only on code: edit no code, run no cargo or build, no git command that writes. Other agents write the other parts at the same time, so edit only the files named in your job. Something another part must change goes in your requests file.
- Plan text states the plan. No history ("changed from", "now") outside a sheet's "Changes from the consolidated plan" section.
- A question that the rules, the code, production behaviour and {{SETTLED}} cannot decide goes in your requests file under "Open questions", with options and a recommendation. Do not guess.
- Plan inputs: {{OWNERSHIP}}, {{PLAN}}/contract.md, {{PLAN}}/areas/<area>.md, {{PLAN}}/chunks/<chunk>/, {{PLAN}}/conflicts.md, {{SETTLED}}, {{PLAN}}/developer-questions.md, {{MAPS}}/<area>.md. Evaluation findings: {{PLAN}}/eval-<area>.md (item tables) and eval-<area>.json (the must-fix items, each addressed to a set, a contract id or `unowned`), {{PLAN}}/eval-size.md (per-set cuts), {{PLAN}}/eval-coverage.md (gaps by file). Grep them for every id you own (set ids, contract ids, file paths).

## Your job

Your prompt names one job kind and its scope.

### Contract part

You own one file in {{PARTS}} (its crates and row count are named in your prompt). Edit it in place. Check every row, not a sample:

- The item does not already exist and does not duplicate an existing framework mechanism. Grep the framework for the concept, not only the name. If it does, the row uses or extends the existing mechanism, or it is dropped with the replacement named.
- The signature fits the code it extends: every type, trait, enum variant, icon name and function it names exists at the base or is itself a contract item. Derive bounds and visibility match existing users.
- It names what it replaces, and that thing's removal.
- No state is carried across passes beyond the exceptions in {{RULES}}/porting-rules.md. It uses framework signals, not side effects.
- The evaluation must-fix items and the settled and conflict resolutions that name it are applied.
- Writer, Also and Used by name real sets in {{OWNERSHIP}}.

Keep the table format of {{KIT}}/templates/contract-part.md and the ids. A new item takes the next free id with the area code. A dropped item moves to a "Dropped in the fix round" table at the end of the part, with its replacement.

Also write {{OUT}}/logs/<your job id>.md: one row per changed, new or dropped item (id, what changed, which sets must change their code or sheet because of it, from Used by and a grep of {{OWNERSHIP}} and the area plans).

### Set sheets

You write one sheet per writer set for the sets named in your prompt, using {{KIT}}/templates/sheet.md. Follow its headings, head keys and table columns exactly: `{{KIT}}/tools/port-set` parses them. Output: {{SHEETS}}/<set id>.md per set, and {{OUT}}/requests/<your job id>.md.

A sheet is the whole plan for its writer: the phase 5 writer gets only its sheet and its contract rows. For each set:

- Start from its section in {{OWNERSHIP}}, the area plan rows and chunk plan sections they cite, and every conflict, settled and evaluation row that names the set or its files.
- Files: check that each path exists at the base (new files excepted). Re-derive each action (class 1).
- Stories: a set that adds a framework component or variant gets a `- Stories:` head line naming each type, its stories and the stories file ({{KIT}}/templates/sheet.md), and that file in its Files table. Check the UI gallery first: a component that already does the job is reused, not added.
- Readers: for every mechanism the set removes or changes, `git grep` the whole repo at the base. Each reader gets a row. A reader in a file this set does not own also goes to the requests file, addressed to the owning set (find it in {{OWNERSHIP}}) or "unowned".
- Tests: list every test function of every file the set owns, including files it deletes, and give each a verdict and a reason under {{RULES}}/testing-rule.md. A test in a deleted file that checks behaviour which must survive is rewritten into a named file.
- Never drop a Tests row silently. A test the port deletes keeps its row with the verdict `delete`. Remove a row only when the test leaves the set or never existed, and name it in {{OUT}}/logs/<your job id>.md: `move <test> to <set>` (with a request to that set) or `delete <test>: <reason>`. `tools/plan-rebuild.py` puts back every row that disappears without such a line.
- Contract items it writes or calls: by id. If a row is wrong for this set, say so in the requests file, addressed to "contract <id>". Do not copy signatures into the sheet.
- Writer notes: what the writer must know that the tables do not say, with path:line evidence at the base.
- Apply the size audit's cut for the set when {{PLAN}}/eval-size.md names one and the code supports it.

The requests file is a table `To (set id, "contract <id>", or "unowned") | Path | What`, then an "Open questions" section.

### Coverage gaps

You assign the files or map sections named in your prompt (from {{PLAN}}/eval-coverage.md). For each file, read it at the base and grep what it uses, then decide:

- It changes because of the port: a request to the set that should own it (the set of its area and mechanism, from {{OWNERSHIP}}), with the action, a line estimate and a verdict for each test function.
- It needs no edit: the reason, backed by grep (it reads nothing the port removes or changes), and its tests are kept.
- A map section no set covers: name the set that covers it, or the request that adds it.

Write {{OUT}}/requests/<your job id>.md: the table `To | Path | What` (action, lines, test verdicts as `fn: verdict, reason`), then a "No edit" table `Path | Reason | Tests kept`, then "Open questions".

## Return

```json
{"done": ["<crates, set ids or files you finished>"], "changed": 0, "requests": 0, "open_questions": 0, "note": "<one paragraph: the classes of error you found>"}
```

## Tracking

You report under the board task `{{TASK}}`. These calls are rules, not suggestions:

- `track step {{TASK}} <step>` when each step starts. If it exits 3, the port is paused: stop and report. Your steps: `read`, `check`, `write`, `log`.
- `track status {{TASK}} <state> [--on WHAT]` on every state change: `running`, `review`, `waiting`, `blocked` (name the blocker with `--on`), `done`.
- `track ask {{TASK}} "question" --recommend A --option A --option B` for every question that the rules, the recorded decisions and the code do not settle. Proceed on your recommendation; add `--blocking` and hold the work that depends on it only for the always-DECIDE list ({{RULES}}/agent-common.md, "Questions").
- `track status {{TASK}} review "<one-line summary>" --calls N` as your last action, where N is the number of tool calls you used.

Kit tools record their own runs. Do not report those.

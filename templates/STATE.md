# {{APP}} port: state

The lead's phase state file. The lead keeps it current at every phase change and every round. Every prompt that says "work already finished or in review" reads it. The progress dashboard (`track show`) holds the task-level detail; this file holds the decisions and the pins.

## Now

- Phase: <number and name> (`track phase <N>`).
- Step: <current step>. Next: <the next command or action>.
- Dashboard: <how the developer views it: own server or tunnel pointed at the output directory | the file opened directly | `track serve`>. Recorded in port.toml.

## Pins

| What | Value |
|---|---|
| Framework plan base | {{PLAN_BASE}} |
| App plan base | {{APP_PLAN_BASE}} |
| Framework branch | {{FW_BRANCH}} |
| Contract stubs branch | {{FW_WRITING_BASE}} |
| App port branch | {{APP_PORT_BRANCH}} |
| App writing base | {{APP_WRITING_BASE}} |
| Production checkout revision | <revision> |

## Phases

| Phase | Entry check | Exit check | State |
|---|---|---|---|
| 0 setup | workspace, pins, baseline test run | baseline failures recorded | <todo / running / done> |
| 1 inventory and map | app UI dirs split into chunks | maps and index; coverage check passes | |
| 2 plan | maps and index | evaluation under `plan.max_error_rate`; sheets and contract parts; answer accuracy under `plan.max_wrong_answers` | |
| 3 contract stubs | contract parts | every stage compiles; plan errors fed back | |
| 4 plan check and decisions | sheets, stubs | decisions written; consistency pass done; audits pass | |
| 5 write | decisions, stubs | every set written, checked, racheck clean | |
| 6 review, combine, compile | written sets | reviews fixed; combine; compile gate green | |
| 7 tests and red rounds | compiled port | exit criteria in process/08-tests-and-red-rounds.md | |
| 8 look and behaviour | tests at exit | pairs reviewed by the lead | |
| 9 land | green port | framework on its branch; app pinned; CI green | |

## Done or in review

Work already finished, or in review, that plans must not repeat. One line each: what, where (branch or report), state.

- <item>: <branch or report>, <done | in review>.

## Decisions

Decisions that bind later steps. Each: the decision and its reason. No names, no dates.

- <decision>: <reason>.

## Developer answers

Every answer, with the question it answered (`track answer`). The answer is recorded here and on the dashboard.

- <question id>: <question>. Answer: <answer>.

## Rounds

| Round | Run label | Pass | Fail | New failures | Report |
|---|---|---|---|---|---|

## Open

- <question or follow-up>, owner: <lead | developer>.

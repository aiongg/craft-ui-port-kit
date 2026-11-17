# craft-ui-port-kit

A process, rules, prompts and tools for porting a craft app's legacy egui UI onto the craft framework ([craft-libs](https://github.com/storytold/craft-libs)), run by one developer with one Claude Code lead session.

The lead plans the whole port with many small read-only agents, has every set of files written with no build, then builds once per batch and fixes failures in rounds. A progress dashboard shows every task, question and test round on one local page. The process was worked out on PhotoCraft's port, and the measured costs below come from it.

## What it does

| Phase | What happens | Runbook |
|---|---|---|
| 0 Setup | Workspace and config, framework pin, one warm app build, baseline test run, rust-analyzer daemons and SCIP indexes, the dashboard | [01-setup.md](process/01-setup.md) |
| 1 Inventory and map | Haiku agents inventory the app's UI code in chunks; Opus agents map each area onto framework components | [02-inventory-and-map.md](process/02-inventory-and-map.md) |
| 2 Plan | Questions, fact answers and chunk plans, merged into one framework contract and one sheet per writer set; independent evaluation and a fix round | [03-plan.md](process/03-plan.md) |
| 3 Contract stubs | Every planned framework signature compiled as a stub, so writers code against real types | [04-contract-stubs.md](process/04-contract-stubs.md) |
| 4 Plan check and decisions | Each sheet read against the stubbed code; open choices decided; audits | [05-plancheck-decide.md](process/05-plancheck-decide.md) |
| 5 Write | Each set written from its sheet by a headless agent, with rust-analyzer instead of a build | [06-write.md](process/06-write.md) |
| 6 Review, combine, compile | Area reviews and fixes, then each batch combined and compiled once | [07-review-combine-compile.md](process/07-review-combine-compile.md) |
| 7 Tests and red rounds | Failing tests triaged and fixed in rounds of one build and one full run | [08-tests-and-red-rounds.md](process/08-tests-and-red-rounds.md) |
| 8 Look and behaviour | Production and port captured state by state and compared side by side | [09-look-and-behaviour.md](process/09-look-and-behaviour.md) |
| 9 Land | Framework changes and the app pushed, after a scrub; the tools never push themselves | [10-land.md](process/10-land.md) |

[process/00-overview.md](process/00-overview.md) gives the entry and exit of each phase.

## Prerequisites

- A craft app whose UI is egui code in its own directories, pinning craft-libs by git revision.
- Local clones of the app and of craft-libs at the framework branch you port onto (normally `next`). craft-libs provides `tools/cl`, the build wrapper every build goes through.
- Claude Code, logged in, with access to Haiku, Sonnet and Opus.
- Python 3.11 or later, git, bash, a Rust toolchain, rust-analyzer, Node 18 or later, and gh. Linux or macOS; `tools/README.md` lists the optional extras.
- A machine with about 64 GB of memory for an app of PhotoCraft's size (less works with the heavy steps run one at a time), and disk for a few warm target dirs of tens of GB each (PhotoCraft's app target was about 40 GB).

## How to start

Install the skill as a Claude Code plugin:

```text
/plugin marketplace add aiongg/craft-ui-port-kit
/plugin install craft-ui-port@craft-ui-port-kit
```

From a local clone, add the clone instead: `/plugin marketplace add <path-to-clone>`. Then, in a Claude Code session opened where the port's workspace should live, say:

> Port `<app>` to the craft framework using the craft-ui-port-kit. The app is at `<path>`, craft-libs at `<path>`.

The session loads the skill ([skills/craft-ui-port/SKILL.md](skills/craft-ui-port/SKILL.md)), becomes the port's lead, creates the workspace (`tools/init-workspace`), and asks you how you want to view the dashboard. From then on it asks you only about goals, design principles and architecture.

## How long and what it costs

Measured on PhotoCraft (86 inventory chunks of about 3,000 lines, 251 writer sets, about 129,000 lines written and 229,000 deleted); [process/costs.md](process/costs.md) has the details and how to project a new port from its size.

| Part | Measured |
|---|---|
| Setup | First warm app build 12-15 min; framework SCIP index about 6 min |
| Phases 1 and 2 (inventory, map, plan) | 92 mapping agents, then the plan; together about 75 % of one subscription's weekly allowance |
| Phases 4 to 6 (plan check, write, review fixes) | About $970 API-equivalent over 251 sets; per Sonnet set about $0.65 plan check, $1.70 write, $0.85 fixes; Opus sets $3 to $9 |
| Writing wall time | About 35 to 70 sets per hour at 6 in parallel |
| Phase 7 (red rounds) | 5 to 6 rounds per app batch; a full test run 15 to 18 min, an app rebuild after a framework change about 12 min |

Wall time in phases 6 and 7 follows the number of build passes, not the number of sets. The lead states the projected cost of every batch before it starts it.

## Where to look next

| To | Read |
|---|---|
| Understand the process | [process/00-overview.md](process/00-overview.md), then [process/lessons.md](process/lessons.md) |
| See what binds every agent | [rules/](rules/) |
| Configure a port | [process/config.md](process/config.md), [templates/port.toml.example](templates/port.toml.example) |
| Find a tool | [tools/README.md](tools/README.md) |
| See real artifacts | [examples/photocraft/](examples/photocraft/README.md) |
| Change the kit | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Licence

MIT OR Apache-2.0, at your option ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE)).

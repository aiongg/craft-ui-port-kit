# Phase 1: inventory and map

Phase 1 finds every user-visible part of the app's UI and decides what each part becomes on the framework. Its output, the port map, is the only input phase 2 plans from, so a part missing here is missing from the whole port.

| | |
|---|---|
| Starts when | Setup is done ([01-setup.md](01-setup.md)). |
| Ends when | Every UI file is in a chunk; every inventory entry is in an area map; the index reports no unmapped entry; the lead has spot-checked each area map against the code; every map section's states are in a states file and production reaches each one. |
| Agents | Haiku, one per chunk (`models.inventory`); Opus for the area proposal and one per area map (`models.area_map`); Opus for the index (`models.index`). |
| Builds | None for the agents, which read the snapshots and write only their own output file. Production is rebuilt once with the hooks the maps add (step 7). |
| Runs | `workflows/phase1-inventory-map.js`, twice: stage `inventory`, then stage `maps`. |

## What the map holds

The framework's porting guide defines the map: `docs/porting.md` in craft-libs, sections "Inventory" and "Map". This kit uses its fields as they are:

- **Inventory**, per part: the app files and lines that build it, the tests that cover it, what the user does with it, and how a script reaches its states.
- **Map**, per part: the framework replacement, the fit (`direct`, `needs props`, `missing component`, `app-only`), the framework gaps, the app glue that stays, a verdict per test (`delete`, `table`, `keep`, `new`), the states to compare old against new, dependencies and size.
- **Reuse before adding**: before a part is marked `missing component`, the mapper walks porting.md's reuse ladder (existing component, new story, builder option, tokens, family component, new library component, app component as the last resort) and stops at the first step that works.

The kit adds two things around them: the chunk inventory is a fixed JSON format (`templates/inventory-chunk.schema.json`), and an index merges the areas' gaps and hooks so each shared framework change is planned once.

## Step 1: build the chunk list

An inventory agent reads one **chunk**: about `plan.chunk_lines` lines of UI code (3,000 by default; a Haiku agent reads that in full and stays accurate). `tools/render-prompt` makes the split when it builds the workflow's input:

```sh
tools/render-prompt --workflow-args phase1-inventory-map --stage inventory > <work.inventory>/args-inventory.json
```

The split:

1. List the Rust files under `app.ui_dirs` in the app snapshot (`git ls-files`), in path order.
2. Set test files aside (`tests.rs`, `*_tests.rs`, files under a `tests/` directory). Each goes with the chunk that holds the code it tests, as a test file the reader counts tests in but does not inventory.
3. Fill chunks in path order, keeping a directory's files together, and start a new chunk when the next file would pass `plan.chunk_lines`.
4. A file longer than `plan.chunk_lines` is split into line ranges at item boundaries (`fn`, `impl`, `mod`), one range per chunk.
5. Number the chunks from `00`.

The same command fills the rendered prompts, the models and the chunk schema into the args file. It also writes the chunk statistics (count, total lines, largest chunk, the files split into line ranges) to `<work.inventory>/chunks.md`. Read that file before launching.

## Step 2: run the inventory

State the run's size and cost before launching, as `rules/lead-rules.md` requires: one Haiku agent per chunk plus one Opus agent for the areas (`costs.md`, phase 1).

Run stage `inventory` as a background task, with the runner `pipeline.batch_runner` names:

- `swarm` (the default): `tools/swarm.py workflows/phase1-inventory-map.js --args <work.inventory>/args-inventory.json`. It runs each agent as a headless `claude -p` with the read-only settings in `templates/claude-settings.json`, creates one dashboard task per job (`inv-NN`, `areas`) and moves it through its states.
- `workflow`: the Workflow tool, with the script and the args file's content as `args`. Put one task on the board first: `tools/track status p1-inventory running "<n> chunks"`, and move it to `done` when the run returns.

Each inventory agent writes `<work.inventory>/chunk-NN.json` and returns the same object, which the runner checks against the schema. When every chunk has succeeded, the run goes on to the areas proposal (step 3) by itself.

The run returns:

- `failed`: chunks whose agent returned nothing. Rerun them with `"only": ["07", ...]` in the args, then run stage `areas` (`--stage areas` builds its args from the chunk files).
- `gaps`: chunks with a file that no entry names and that is not listed as skipped. Open the chunk file; rerun the chunk if the reader missed a part, or accept a file with nothing to inventory.
- the entry count.

Readers need read access without permission prompts: a headless agent that stops at a prompt returns nothing. `templates/claude-settings.json` allows reads, `grep` and read-only git, and `tools/track` for reporting a blocked chunk.

## Step 3: choose the areas

The areas agent proposes how to divide the inventory into **areas**, the unit of the rest of the port: one agent maps an area, one plan merge and one evaluation cover it, and its writer sets are named after it. It writes `<work.inventory>/areas.json` (each area's chunks, plus single entries moved to another area) and `areas.md` (the reasons).

Review the proposal yourself:

- each area at or under about 20 chunks or 200 entries, so one agent can map it;
- areas follow what the user sees (panels and chrome, dialogs, tools, canvas and shared widgets, the top-level shell);
- shared infrastructure sits in one area, usually the top-level shell;
- ids are short and lowercase; codes are two lowercase letters and unique.

Edit `areas.json` where you disagree. Then write each area into `port.toml` as an `[[areas]]` table with its `id`, `code` and `description`, and record the decision: `tools/track event decision "areas: <ids>"`. Framework work outside the map gets its own area in phase 2.

## Step 4: check the framework listing

The area-map agents learn what the framework has from the framework snapshot: `docs/components-index.md` (every component with its shape and purpose), `docs/porting.md` and `docs/craft-framework.md`. Check that `components-index.md` at `plan.base` is current: it is generated from the registered components (`cargo run -p craft-ui-gallery --bin components-index`), and the framework commits it with each change. If it is behind, regenerate it in the framework integration tree through cl and tell the mappers where the fresh copy is.

## Step 5: run the maps

```sh
tools/render-prompt --workflow-args phase1-inventory-map --stage maps > <work.maps>/args-maps.json
```

This joins `[[areas]]` from `port.toml` with the chunk lists and moves in `areas.json`. Run it as in step 2. Under swarm, the board gets one task per area (`map-<area>`) and one for the index (`map-index`); under the Workflow tool, put one task `p1-maps` on the board.

Each area agent writes `<work.maps>/<area>.md` (format: `templates/area-map.md`, one section per part as in `templates/map-section.md`). Before mapping, it spot-checks at least 10 entry points and every test count of its area against the code, and lists its corrections at the top of the map. When every area map exists, the index agent writes `<work.maps>/README.md` (format: `templates/map-index.md`):

1. every part, one row per map section;
2. the shared framework gaps (`SG-n`), merged and deduplicated across areas, each marked `before` (blocks a family of parts) or `beside`;
3. the app-side changes several sections need (`AC-n`);
4. the dependency order, the critical path and the areas ranked by risk (missing components and shared gaps per area, the riskiest sections first);
5. the missing control hooks (`H-n`): states a script cannot reach yet;
6. coverage: per-area counts, every inventory entry checked by id, and the parts mapped in more than one area.

A failed area comes back in `failed`, and the index waits. Rerun the area with `"only": ["<area>"]` in the args, then run stage `index` (`--stage index`), which writes the index from the maps on disk.

## Step 6: spot-check the maps

The agents' maps are the plan's foundation, so the lead reads a sample itself before phase 2:

- **Per area, at least five sections** spread over the map: open the app code at the cited lines, then the framework component at its cited path. Is the component real, does it do what the section says, and is the fit right?
- **Gaps:** for each sampled gap, grep the framework for the concept, not only the name. A gap that duplicates an existing mechanism is the most common map error.
- **Citations:** `tools/coverage.py` checks every `` `Symbol` (path:line) `` citation of the maps (check 7 of its report): the file exists, the line is inside it, and the line names the symbol. Fix each drifted citation before phase 2; spot-check only what the script cannot read (a bare `:236`, a symbol after the path).
- **Tests:** compare two test counts per area with `grep -c '#\[test\]'`.
- **The index:** its coverage table lists no unmapped entry, and every `SG-n` names real sections.

Fix what you find in the map directly when it is small; rerun the area with a note in its prompt when a pattern repeats. Record each finding class in `log.md`.

## Step 7: write the states files

As you accept each area map in step 6, write its states, so the look comparison runs from the port's first compile ([tools/look.md](../tools/look.md)):

1. For each section of the map, run `tools/look states <area> <section>`. It writes the section's **States** field into the panel's states file (`<look.states_dir>/<Panel>.json`), records the section on each state (`map`), and puts the panel's task `look-<Panel>` on the board. Sections on one panel share its file. A part with nothing to show has `none` in its States field, with the reason.
2. Read each file against its map section: every state the section lists, every named variant, the empty, mixed and long-text cases the map names. A state that leaves a dialog open ends by closing it, or the file's `reset` closes it.
3. Fill in what the map could not give: the panel's `crop`, the steps of each named setup, and the steps of every state marked `needs: "steps"`.
4. Add the hooks the index lists as missing (`H-n`, marked `needs: "CH-n"` on the states) to the production branch from phase 0 ([01-setup.md](01-setup.md), step 6a), with the method names and parameters the port will answer. Remove each `needs` field once its hook exists.
5. When every map is accepted, rebuild production once, then run `tools/look pair --all --side up` as a background task. Every state must show production on its page; fix a driver error or a wrong step now, while nothing waits on it. The port's side comes from the build loop once the port compiles.

## Exit

- [ ] Every file under `app.ui_dirs` is in a chunk, and every chunk file parses.
- [ ] `[[areas]]` in `port.toml` matches `areas.json`.
- [ ] Every area has its map; the index exists and its coverage section lists no unmapped entry.
- [ ] The lead's spot-check is recorded in `STATE.md`.
- [ ] Every map section has a states file (`none` in its States field for a part with nothing to show).
- [ ] Production reaches every state: no state has `needs`, and `look pair --all --side up` shows each one.

Then record `tools/track phase 2 "plan"` and go to [03-plan.md](03-plan.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate").

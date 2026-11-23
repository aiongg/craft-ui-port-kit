# Map one area of {{APP}} onto the framework

Do not start subagents or workflows.

You write the map of area `{{AREA}}`: for every inventoried part of {{APP}} in this area, what framework component replaces it, how well it fits, which framework changes it needs, what stays app code, what happens to its tests, and which states show that the port matches the old app. Phase 2 plans the port from your map, so every claim needs a line reference that a planner can open. Background: `{{KIT}}/process/02-inventory-and-map.md`.

Read only. Edit no code, run no build, run no git command that writes. Your only output is the map file.

## Input

- Code, read only:
  - app = `{{APP_SRC}}` ({{APP}} at the plan's app commit; UI under {{UI_DIRS}});
  - fw = `{{FW}}` (the framework at the plan's framework commit).
- Your area's inventory: the chunks and entry moves listed under "Your area" at the end of this prompt, from `{{INVENTORY}}/chunk-*.json`. Entry ids are `<chunk>.<index>` (index from 0).
- What the framework has:
  - `{{FW}}/docs/components-index.md`: every component, with its shape and purpose;
  - `{{FW}}/docs/porting.md`, sections "Map" and "Reuse before adding": the map fields and the reuse ladder;
  - `{{FW}}/docs/craft-framework.md` sections 1-4, and the component's own source and stories when you cite it.
- The rules every port follows: `{{RULES}}/porting-rules.md` and `{{RULES}}/framework-decisions.md`. The testing rule: `{{RULES}}/testing-rule.md`.
- Formats: `{{KIT}}/templates/area-map.md` (the file) and `{{KIT}}/templates/map-section.md` (one section).

## Steps

1. Run `track step {{TASK}} read`. Read every inventory entry of your area.
2. **Spot-check the inventory.** Open at least 10 entry points spread over the area, and check every test count the entries give against the code (`grep -c '#\[test\]'`, and the gating `cfg` of the test module). Fix what is wrong in your map, and list each correction in the section "Inventory corrections" with the evidence.
3. Run `track step {{TASK}} write`. Group the entries into **sections**: one section per part, or a few small parts that share a host. A section is one future planning unit. Section ids: a letter per group of related sections and a number (`A1`, `A2`, `B1`).
4. For each section, fill these fields (the map-section template shows the layout):
   - **Kind** and the inventory entries it covers, by id.
   - **App code**: files and line ranges, with the functions that matter.
   - **Framework**: the component or components that replace it, each with fw path:line. Walk the reuse ladder in porting.md and stop at the first step that works.
   - **Fit**: `direct` (use as is), `needs props` (list them), `missing component` (describe it), `app-only` (stays app code, built from framework components).
   - **Gaps**: framework changes the section needs. Give each an area-local id (`FG-n`) and list them all again at the end of the map. Before naming a gap, grep the framework for the concept, not only the name: a gap that duplicates an existing mechanism is wrong.
   - **App glue**: what the app still does (commands it sends, state it owns, settings it saves), and what app code is deleted.
   - **Tests**: per test file, `(n)` its `#[test]` count, then verdicts: `delete` (the framework now owns the behaviour, or the code goes), `table` (event-to-command mapping, folded into a few table-driven tests per event family), `keep` (the app's own decisions: command ids, engine effects, saved settings), `new`. One-line reason each, under the testing rule.
   - **States**: the states that show old and new match (default, empty, filled, open, disabled, error, long text), each with the control-channel steps that reach it. Where no control call reaches a state, name the missing hook (`CH-n`) and list it at the end. Every section has this field: write `none` and the reason only for a part with nothing to show (infrastructure, a model with no surface).
   - **Look reference**: the literal sizes, paddings, alignments and icon sizes of the old part and the framework variant that matches, each with `app path:line`. Read them from the old code (constants, layout calls, icon sizes), never from screenshots; a part with no visible surface says `none`. Where no framework variant carries a value, name it as a gap.
   - **Size**: S (under about 40 agent tool calls), M (up to about 100) or L (up to about 150; split anything larger).
   - **Depends on**: other sections, gaps and hooks that must land first.
5. Infrastructure entries that no section covers go in a table "Infrastructure" at the end: entry, what happens to it, the section that carries the change.
6. End the map with: "Framework gaps" (every `FG-n`: the change, the sections that need it, size), "Missing control hooks" (every `CH-n`), and "Open questions" (only what the rules, the code and production behaviour leave open; options and a recommendation each; no layout or look questions, since the old app decides those).

## Rules

- Every user-visible entry of your area lands in a section; every infra entry in a section or the infrastructure table. List any entry you could not place, with the reason.
- Facts carry `app path:line` or `fw path:line`. Find code by symbol; line numbers in the inventory can be off.
- Apply the porting rules while you choose components: one mechanism per concept, the framework's own signals, one arrangement per component in every theme and density, no component-specific theme values.

## Output

Write `{{OUT}}`. Return the structured summary: area, section count, entries mapped and not mapped (ids), fit counts, gap count, hook count, inventory corrections, open questions.

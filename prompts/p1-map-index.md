# Write the index of {{APP}}'s port map

Do not start subagents or workflows.

You write the index over all area maps of {{APP}}'s port: one table of every part, the framework gaps merged across areas, the app-side changes, the dependency order, the missing control hooks, and the coverage check. Phase 2 splits its work from this index, and the lead checks coverage with it. Background: `{{KIT}}/process/02-inventory-and-map.md`.

Read only. Edit no code. Your only output is the index file.

## Input

- The area maps: `{{MAPS}}/<area>.md` for the areas listed under "The areas" at the end of this prompt.
- The inventory: `{{INVENTORY}}/chunk-*.json` and `{{INVENTORY}}/areas.json` (which chunks and entry moves make each area).
- Code, read only: app = `{{APP_SRC}}`, fw = `{{FW}}`. Open code only to settle a conflict between two maps.
- Format: `{{KIT}}/templates/map-index.md`.

## Steps

1. Run `track step {{TASK}} read`. Read every area map in full.
2. Run `track step {{TASK}} write`. Write the index with these sections:
   1. **Every user-visible part.** One table per area, one row per map section: Section (linked to the map heading) | Part | Kind | Framework replacement | Fit | Size | Depends on. Depends on uses section ids, `SG-n` and `AC-n` from the next two sections, and `H-n` from section 4.
   2. **Shared framework gaps.** Merge the areas' `FG-n` gaps: one row per framework change, deduplicated across areas (same component and same missing behaviour = one gap). Columns: Id (`SG-n`) | Gap | Framework change | Sections that need it | Size | When (`before`: it blocks a whole family of parts; `beside`: it lands with the part that needs it) | Area ids (each map's own id). Where two maps describe the same gap differently, open the framework code and write the version that fits it, with the reason.
   3. **App-side changes.** Changes on the app's side that several sections need (a shared model type, a view adapter), one row each: Id (`AC-n`) | Change | Sections | Size.
   4. **Dependency order.** The order the dependencies force: gaps marked `before` and what they unblock, then the longest chain of `Depends on` (the critical path), then the rest by area. This order feeds the plan's write order, not a schedule.
   5. **Missing control hooks.** Merge the areas' `CH-n`: one row per hook the app's control channel lacks: Id (`H-n`) | What is missing | Sections that wait | Area ids. Name the states that cannot be reached by design (outside the window, hardware-only).
   6. **Coverage.** Per area: chunks, inventory entries (user-visible / infra), map sections, rows in section 1, fit counts (direct / needs props / missing / app-only), entries not mapped. Then check by entry id that every inventory entry appears in exactly one area map (as a section entry or an infrastructure row) and list every entry that does not, with its chunk. Then a table "Parts mapped in more than one area": the part, its sections; the first section listed owns the code, the others carry wiring, tests or the caller.
3. Contradictions between maps that the code does not settle go in a last section, "Open questions", with options and a recommendation.

## Output

Write `{{OUT}}`. Return the structured summary: parts (rows in section 1), shared gaps, app-side changes, hooks, entries not mapped (ids), parts in more than one area, open questions.

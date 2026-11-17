# Propose the port's areas from the inventory

Do not start subagents or workflows.

You divide {{APP}}'s UI inventory into areas. An area is the unit of the rest of the port: one Opus agent writes its map, its plan is merged and evaluated as one piece, and its writer sets are named `<area>-w<n>`. This is the step between the inventory and the area maps in phase 1 (`{{KIT}}/process/02-inventory-and-map.md`).

Read only. Edit no code. Your only outputs are the two files named below.

## Input

- The inventory: `{{INVENTORY}}/chunk-*.json` (schema `{{KIT}}/templates/inventory-chunk.schema.json`). A compact list of every entry (id, name, kind, files, lines) is under "The inventory" at the end of this prompt; open a chunk file when the list does not tell you enough.
- App code, read only: `{{APP_SRC}}` (UI under {{UI_DIRS}}).

## How to divide

- Follow what the user sees, not the directory tree alone: for example panels and window chrome, dialogs, tools and their options, canvas and shared widgets, the top-level shell (menus, preferences, shortcuts, notices). Use the app's own structure where it already groups parts this way.
- Size: one agent maps a whole area, so keep each area at or under about 20 chunks or 200 entries. Split a larger area in two.
- Keep a part with its infrastructure: an entry of kind `infra` goes to the area whose parts use it most.
- A part that clearly belongs to another area than its chunk's goes there as an entry move. Prefer whole chunks; move single entries only where the chunk mixes areas.
- Shared infrastructure every area uses (the app shell, the frame loop, global state) goes to one area, usually the top-level shell; the other areas list what they need from it.
- Ids: short lowercase words (`panels`, `canvas-widgets`). Codes: two lowercase letters, unique (`pn`, `cw`); contract ids become `<code>.<Kind><n>`.
- Framework work outside the inventory gets its own area later, in phase 2. Do not add it here.

## Output

1. `{{OUT}}`: JSON, `{"areas": [{"id", "code", "description", "chunks": ["00", ...], "entries": <count>, "lines": <count>}], "moves": [{"entry": "<chunk>.<index>", "area": "<id>", "why": "..."}]}`. Every chunk appears in exactly one area. Return the same object as your structured result.
2. Beside it, `areas.md`: one short paragraph per area (what it covers and why these chunks), then the moves with their reasons, then any entry you could not place, with the options.

The lead reviews the proposal, copies the areas into `port.toml` as `[[areas]]` tables (id, code, description), and keeps the chunk lists in your JSON file for the area maps.

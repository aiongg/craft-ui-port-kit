# Inventory one chunk of {{APP}}'s UI code

Do not start subagents or workflows.

You list every user-visible part, and every piece of UI infrastructure, in one chunk of {{APP}}'s UI code. This is step 1 of phase 1 of a port of {{APP}} onto the craft framework. Mappers read your output to decide what each part becomes, so they need facts with line references, not opinions.

Read only. Edit no code, run no build, run no git command that writes. Your only output is the chunk file.

## Input

- App code, read only: `{{APP_SRC}}`. Paths below are relative to it. The UI code lives under {{UI_DIRS}}.
- Your chunk is `{{CHUNK}}`. Its files (with line ranges where a large file was split) and the test files beside them are listed under "Your chunk" at the end of this prompt.
- Read every file of the chunk in full. Open other files only to resolve a call you need to describe (where a command id is defined, which control call reaches a panel). Use `grep -rn` or `git -C {{APP_SRC}} grep -n` for that.

## What an entry is

- One entry per part a user can see or use: a panel, a dialog, a popup, a menu, an options bar, a canvas overlay, a reusable widget. A part that spans several files is one entry. Several tiny parts in one file that always show together are one entry.
- One entry per piece of infrastructure the UI depends on, with no pixels of its own: dispatch, UI state, persistence, registries, glue to the engine. Kind `infra`.
- Every file of the chunk belongs to at least one entry, or goes in `skipped` with the reason (a module root holding only `mod` lines, generated code).
- A part that continues in another chunk: describe the part of it in your files, and say in `notes` which file continues it.

## The keys

The schema is `{{KIT}}/templates/inventory-chunk.schema.json`; each key's description there says what it holds. Rules for all keys:

- Every fact carries its evidence as `path:line` or `path:from-to`. A line number is right when it points at the code it names.
- `files[].lines` counts the lines of that file that belong to the entry; `lines` is their sum.
- `tests`: for each test file that covers the entry, count its `#[test]` functions that concern the entry (grep `#\[test\]` and read the function names) and give up to five names. Include inline `mod tests` blocks.
- `control_reach`: look for the app's control or automation channel (a JSON-RPC style handler, `ui.set`, `ui.inspect`, a test harness that opens the part). Give the method and params that bring the part into view, or `none found` and where you looked.
- `interactions`: what pointer, key, wheel, drag and focus input does, as the code does it today.
- Facts only. If something cannot be found, say `not found` and where you looked. Never guess.

## Output

Write the chunk as JSON to `{{OUT}}` (create the directory if needed): `{"chunk": "{{CHUNK}}", "entries": [...], "skipped": [...]}`. Return exactly the same object as your structured result.

If you cannot finish (a file is missing, the chunk is too large to read), run `track status {{TASK}} blocked "<what is missing>"`, write what you have, and return it.

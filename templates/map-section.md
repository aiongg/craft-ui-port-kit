### <ID> <Part name>

- **Kind**: panel | dialog | popup | menu | options bar | widget | infra | canvas overlay.
- **App code**: <path:lines, one entry per file or function that the part is made of>
- **Framework**: <the components, types and props that replace it, each with path:line>
- **Fit**: `direct` (use as is) | `needs props` (list them) | `missing component` (what it would be) | `app-only` (stays app code, built from framework widgets).
- **Gaps**: <framework changes the part needs, by gap id; or "none">
- **App glue**: <what stays in the app: commands it sends, models it owns, what is deleted as the part ports>
- **Tests**: <file (count): how many keep, how many fold into table tests, how many delete, each group with its reason>
- **States**: <the app states to capture for the old and new comparison, in the form the control channel can reach; hooks that are missing go to the area map's hook list>
- **Depends on**: <section ids of the same area, shared gap ids, app-side change ids>
- **Size**: S (under about 40 tool calls) | M (up to about 100) | L (about 150 or more; split before briefing).
- **Done when**: <what the user sees and does, what code and tests are gone, which tests are rewritten>

Example:

```markdown
### A4 Brush Settings panel

- **Kind**: panel
- **App code**: panels/brush_panel.rs (all), panels/brush_preview.rs:1-240
- **Framework**: `Section`, `ListRow`, `Slider`, `CheckRow`; preview through `RasterDisplay`
- **Fit**: needs props: `ListRow` label column (gap G-12)
- **Gaps**: G-12 ListRow label column
- **App glue**: sends `brush.set` commands; owns the brush settings model and its saved presets
- **Tests**: brush_panel/tests.rs (42): 30 table (event family "slider edits"), 8 keep (preset save and load), 4 delete (preview cache: the framework owns previews)
- **States**: default; tip-shape section open; dual-brush on; long preset name
- **Depends on**: G-12
- **Size**: M
- **Done when**: the four states match the old panel; the preview cache code and its tests are gone; kept tests are rewritten
```

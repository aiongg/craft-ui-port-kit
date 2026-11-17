# PhotoCraft port map: index

Index of the five area maps that say what each user-visible part of PhotoCraft's egui UI (`crates/ui-egui/src`, at the map's base commit) becomes on the craft-libs framework (at the framework integration commit). Each area map has the full brief material per part: PhotoCraft code, framework components with file:line, gaps, app glue, test verdicts, look-comparison states.

| Area map | Covers | Inventory chunks |
|---|---|---|
| [panels.md](panels.md) | Dock and window chrome, options bar, tool palette, status bar, every dock panel | 00–11 |
| [dialogs.md](dialogs.md) | Dialog host, prompts, parameter and adjustment dialogs, Layer Style, colour, full-window workspaces, RAW Develop, file dialogs | 12–30 |
| [tools.md](tools.md) | Tool options bars, tool canvas parts, type, transform, pen and shapes, crop, analysis, retouch, brush picker, artboards | 31–47 |
| [canvas-widgets.md](canvas-widgets.md) | Canvas view and navigation, overlays, cursors, canvas menus, document area, shared `widgets/**` | 48–63 |
| [top.md](top.md) | Menus, macOS menu, workspaces, shell dialogs, Preferences, shortcuts, notices, jobs, and the wiring and tests in `panels.rs` | 64–85 |

Contents: [1. Every user-visible part](#1-every-user-visible-part) · [2. Shared framework gaps](#2-shared-framework-gaps) · [3. Suggested port order](#3-suggested-port-order) · [4. Missing control hooks](#4-missing-control-hooks) · [5. Coverage](#5-coverage)

**Fit**: `direct` (a framework component replaces the part), `needs props` (the component lacks props listed in the area map), `missing component`, `app-only` (stays PhotoCraft code, built from framework widgets).

## 1. Every user-visible part

One row per section of an area map (a port task). **Depends on** uses section ids of the same area (`A1`, `31.10`, `top 34`), `SG-n` for the shared framework gaps in section 2 and `PC-n` for the PhotoCraft-side changes. **Size** is the app port on each area map’s scale: S under about 40–50 agent tool calls, M up to about 100–150, L at or past one agent’s 150 calls (split before briefing). `fw` is the framework work when a section sizes it separately.

### 1.1 Panels (67)

| Section | Part | Kind | Framework replacement | Fit | Size | Depends on |
|---|---|---|---|---|---|---|
| [A1](panels.md#a1-dock-columns-groups-floating-windows-widths-saved-workspace) | Dock (columns, groups, floating windows, widths, saved workspace) | panel + infra | `DockArea`, `Workspace<P>`, `Action` | needs props | M | SG-40; every panel section (bodies) |
| [A2](panels.md#a2-panel-group-menu) | Panel group menu | popup | `DockGroup`, `PanelMenu`, `DockConfig::close_menu_items` | direct | S | A1; PC-4 |
| [A3](panels.md#a3-icon-rail-dock-rail-and-railmenu-bar-visibility) | Icon rail (dock rail) and rail/menu-bar visibility | widget | `PanelRail`, `CanvasPanel` | direct | S | A1 |
| [A4](panels.md#a4-floating-preset-and-type-windows-styles-shapes-tool-presets-clone-source-type-styles-glyphs-timeline-and-their-window-menu-wiring) | Floating preset and type windows (Styles, Shapes, Tool Presets, Clone Source, Type Styles, Glyphs, Timeline) and their Window-menu wiring | widget + infra | `FloatingGroup`, `WindowMenuRows` | direct | S | A1 |
| [A5](panels.md#a5-title-bar-and-window-title) | Title bar and window title | panel | `TitleBar`, `AppShell`, `MenuBar` | direct | S | A6, A1 (workspace switcher) |
| [A6](panels.md#a6-caption-buttons-and-their-style-model) | Caption buttons and their style model | widget + infra | `CaptionButton`, `Captions` | direct | S | A5 |

## 2. Shared framework gaps

The area maps list about 100 framework gaps under their own ids. Merged and deduplicated they are the 67 below, plus 5 changes on PhotoCraft's side. Each becomes a framework task.

- **When**: `before` means the gap blocks the sample (section 3) or a whole family of parts, so it lands first; `beside` means it lands with, or just before, the part that needs it.
- **Size**: from the area maps where they size the framework work; `~` marks an estimate made for this index.
- **Area ids**: the gap's id in each area map (panels `FG-n`, dialogs and canvas-widgets `Gn`, top "shared n" or a section's own gap list, tools by name).

| Id | Gap | Framework change | Entries that need it | Size | When | Area ids |
|---|---|---|---|---|---|---|
| SG-1 | Dialog automation surface | Read a `StackDialog`'s values as JSON, set one by key, set a prompt's choice, so `ui.dialog.set/confirm/cancel` work on typed dialogs without one adapter per type | dialogs A1, and every dialog state that sets a value (B1 `gaussian-blur-40`, E1 `color-picker-web-only`) | ~M | before (sample) | dialogs G3 |
| SG-2 | Hosted dialog forms | `StackDialog` forms for `LayerStyleDialog`, `ExportAsDialog`, `FormatOptionsDialog`, `CanvasSize`, `AboutDialog`, `Alert` and an adjustment-editor dialog | dialogs A1, A2, A7, C1, D1, H2, H3, H6, H7 | ~M | before (dialog host) | dialogs G2 |
| SG-3 | Canvas input under a modal dialog | Done (F-7): `runtime::sampler` and the `Sampler` trait (ui-contract `contract/sampler.rs`): `keep_view_open(canvas)` passes the wheel, the middle-press pan and Space+primary; `pass_canvas_gesture(canvas, CanvasGesture)` passes the named press (button and required modifiers) and its drag. Left: the Hand tool's primary-drag pan under a dialog, with the tool host adoption (P-15): `ToolHost::run` calls `runtime::sampler::pass_tool_gesture(ctx, canvas, gesture)` for the running tool's gestures, which take effect only while a modal body keeps the same canvas (`keep_view_open` or `pass_canvas_gesture`), for that modal | dialogs A1, B1, C1, C4, C5, D2, E1, E3, F7, H10; canvas A10, C6, B20, B22 | ~M | before (sample) | dialogs G1, canvas G7 |
| SG-4 | `PreviewPane` click point | `PreviewPane` reports the image point of a click (eyedroppers, locator) | dialogs B1, E3 | S | before (sample) | dialogs G4 |
| SG-5 | `BrushPresetPicker` props | Open at a canvas point without the closed field, resize grip, Angle/Roundness in the head, Escape reverts all four values | tools 42.6, 42.7; canvas D13 | ~S | before (sample) | tools (BrushPresetPicker props) |
| SG-6 | GPU document display slot | A display slot in the `Canvas` body for an app-painted document (paint callback) sharing `RasterDisplay`'s checkerboard, edge, shadow and pixel-grid rules; tiled copies (Pattern Preview); a source region larger than the document (crop) | canvas A1, A13, B8, B11, B17; top 29 | L | before (canvas) | canvas G1, top 29 |
| SG-7 | Canvas background-press route | The route `TextEditor` asks for to receive presses on the canvas background | tools 31.10, 32.0 | ~S | before (type tool) | tools (canvas tool host gap) |
| SG-8 | Momentary tools and latched modifiers | Momentary Move beside `Momentary` Hand/Zoom (Cmd/Ctrl → Move, Cmd+Alt duplicates, Cmd-drag moves guides, hand-off to `TransformBox`), app-defined momentary tools (~ → eraser), latched modifiers in the runtime input | canvas A11, A12, B6, B13, C4; top 6, 30 | M (momentary) + M (runtime latch) | before (tool host) | canvas G4, top shared 4 |
| SG-9 | OS cursor images | The cursor service rasterises `Painted` cursors and sets them as the OS cursor where the platform allows; paints them otherwise | canvas C1, C2, C3, C4, C5, C6 | L | before (tools) | canvas G2, top 29 gap 3 |

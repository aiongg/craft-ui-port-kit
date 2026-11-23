# panels-w1 — Dock: restore on open, rail mapping, group menu rows, Dock Panel, OS-window file drops

- Repo: fw. Model: opus. Base: the framework branch (fw, after the phase 2 stubs).
- Lines: write 376, delete 27. Write counts lines added or changed, never kept lines; delete counts lines removed.
- Contract items it writes: pn.C1, pn.C2, pn.C3, pn.C4, pn.C5, pn.C6, pn.C7, pn.C8, pn.C9, pn.C57.
- Contract items and PhotoCraft interfaces it calls: fx.F51 (reads `IconicColumnOutput::flyout`).
- Map sections: panels A1, A2, A3, A4.
- Look reference: carried by the map sections named above (their Look reference fields are not shipped in this excerpt).
- Waits on (signatures it codes against): framework-01-w9 (`IconicColumnOutput::flyout: Option<FlyoutResize<P>>`).

## Files

| Path | Action | Write | Delete | What changes |
|---|---|---|---|---|
| `crates/behavior/src/dock/workspace.rs` | edit | 75 | 20 | `apply_all` restores a hidden panel on `Open` (C1); `set_visible` body becomes `apply(Close)` / `apply(Open { anchor: fallback })` (C2); new field `floated` with its bookkeeping in `apply_all` and `reconcile`, included in `PartialEq` (C9); `validate`, `restore_from_hidden`, `reconcile`, `close_locations`, `reversed` stay. |
| `crates/behavior/src/dock/inner.rs` | edit | 4 | 1 | `Float` arm (`inner.rs:43-54`): an absent panel gets a new `StackEntry` instead of `MissingPanel` (C57). Every other arm stays. |
| `crates/behavior/src/dock/apply.rs` | edit | 3 | 1 | Permission check of `Float` (`apply.rs:53`): floating a panel the layout does not contain is an open, allowed while locked, as `OpenAt`'s `opens` rule (`apply.rs:44-46`) (C57). |
| `crates/behavior/tests/dock_apply.rs` | edit | 70 | 0 | Two new tests (Tests table); the five tests stay. |
| `crates/ui-panels/src/docking/rail.rs` | new | 45 | 0 | `rail_actions`, `rail_lit` (C3, C4). |
| `crates/ui-panels/src/docking/mod.rs` | edit | 2 | 0 | `mod rail;` and `pub use rail::{rail_actions, rail_lit};` beside the other `pub use` lines (`mod.rs:33-63`). |
| `crates/ui-panels/src/docking/config.rs` | edit | 10 | 0 | Field `group_order_items` (default false in `Default`, `config.rs:91-107`) and its builder beside `close_others_item` (`config.rs:140`) (C5). |
| `crates/ui-panels/src/docking/commands/dock.rs` | edit | 35 | 0 | `DockCommands::DockPanel` variant; its arm in `actions`; its row in `dock_states`; `DockScene` gains the floated records and a builder (C9). `FloatPanel` … `AutoCollapse`, `move_actions`, `float_actions` stay. |
| `crates/ui-panels/src/docking/floating.rs` | edit | 25 | 0 | A native floating group registers a `WindowDropTarget<OsFiles>`; `FloatingGroupOutput` gains `pub files: Vec<OsFile>` (C8). |
| `crates/ui-panels/src/docking/window_menu.rs` | edit | 2 | 1 | Doc of `WindowMenuRows` (`window_menu.rs:10-13`): a Hidden pick's `Action::open` restores the last place through `Workspace::apply_all`. No code change. |
| `crates/ui-patterns/src/patterns/dock/area.rs` | edit | 60 | 4 | `menu_rows` (`area.rs:639-674`) adds Minimize and Move Group Up/Down for docked groups under `group_order_items`, and Dock Panel for floating groups (C6, C9); `Scene` carries the workspace's floated records into every `DockScene::new` (`area.rs:682, 701, 732, 933, 1004`); `DockAreaOutput::window_files` collected from the floating groups' `files` (C7); `ColumnWork` (`:260`) gains `flyout: Option<FlyoutResize<P>>`, which `column_work` (`:813-830`) turns into `resize_flyout_width`, `resize_group` and, with an offset, `move_flyout_top` (fx.F51). |
| `crates/ui-patterns/tests/it/docking/native.rs` | edit | 45 | 0 | One new trial (Tests table); the nine trials stay. |
| `crates/ui-test-kit/src/windows.rs` | edit | 15 | 2 | `Windows::frame` gives the child pass dropped and hovered OS files as well as events (a `frame_with_files` or a files argument), so a trial can drop files on a native float's own window. |
| `crates/ui-widgets/src/popover/drop_veil.rs` | edit | 4 | 2 | `WholeWindow` (`drop_veil.rs:116-139`), the whole-window `OsFiles` drop target, becomes public and is exported, so `FloatingGroup` uses the same target. |
| `crates/ui-widgets/src/popover/mod.rs` | edit | 1 | 1 | Exports `WholeWindow` beside `DropVeil`. |

## Replaced mechanisms and their readers

| Mechanism (removed or changed) | Reader (path:line at the base) | Owner set | What the reader does instead |
|---|---|---|---|
| `Workspace::set_visible` body (signature unchanged) | `crates/ui-gallery/src/chrome/shell.rs:126` | unowned | Nothing: same call, same result. |
| same | `crates/ui-gallery/src/mock/editor.rs:134` | unowned | Nothing. |
| same | `crates/ui-gallery/src/viewer/state.rs:196`, `:208` | unowned | Nothing. |
| same | `crates/ui-gallery/tests/it/viewer.rs:26-28`, `:57` | unowned | Nothing. |
| same | `crates/behavior/tests/dock_apply.rs:94`, `:158` | panels-w1 | Nothing (tests kept). |
| `Action::Open` of a hidden panel restores its place (C1) | `crates/ui-panels/src/docking/window_menu.rs:49` | panels-w1 | Nothing: the pick now reopens at the last place; doc line updated. |
| `Action::Float` of an absent panel (C57) | tools-w52's Measurement Log and Notes open (met by pn.C57) | tools-w52 | Sends one `Action::float(panel, rect)` for an absent panel. |
| `Workspace` gains `floated` (serde default, skipped when empty) | `crates/behavior/src/dock/workspace.rs:48` (`PartialEq`), `:83` (`replace`) | panels-w1 | `PartialEq` compares `floated`; `replace` keeps it through `..with`. |
| `DockCommands` gains `DockPanel` | `crates/ui-panels/src/docking/commands/dock.rs:171-212` (`actions` match), `:271-302` (`dock_states`) | panels-w1 | New arm and row. No other exhaustive match exists (`git grep StepGroupDown` finds only this file). |
| `DockScene` gains the floated records | `crates/ui-patterns/src/patterns/dock/area.rs:682`, `:701`, `:732`, `:933`, `:1004` | panels-w1 | Each `DockScene::new(..)` adds `.floated(scene.floated)`. |
| `FloatingGroupOutput` gains `files` | `crates/ui-panels/src/docking/floating.rs:282` (only constructor) | panels-w1 | Fills `files`. |
| `IconicColumnOutput` gains `flyout` (framework-01-w9) | `crates/ui-patterns/src/patterns/dock/area.rs:846-848` (the one reader) | panels-w1 | Copies `output.flyout` into `ColumnWork::flyout`; the non-iconic column passes `None`. |
| `DockAreaOutput` gains `window_files` | `crates/ui-patterns/src/patterns/dock/area.rs:369` (only constructor) | panels-w1 | Fills `window_files`. |
| `DockConfig` gains `group_order_items` | `crates/ui-panels/src/docking/config.rs:91` (`Default`, only literal) | panels-w1 | Adds `group_order_items: false`. |
| PhotoCraft `group_header` rows, `rail_click`, `rail_on`, `docking_returns`, `open_window_drops` | `crates/ui-egui/src/panels/panel_docking.rs:1614-1649`, `:863`; `crates/ui-egui/src/dock.rs:350, 513`; `menus/invoke.rs:909`; `menus/workspace_ui.rs:216`; `control/inspect.rs:117` | panels-w14 (`panel_docking.rs`, `dock.rs`), top-w12 (`menus/invoke.rs`), panels-w15 (`menus/workspace_ui.rs`), hub-w2 (`control/inspect.rs`) | Their sets call C3–C9 (PC1, PC7, PC8). |

## Tests

| File | Test | Verdict | Reason; for a rewrite, what it asserts afterwards and through which driver |
|---|---|---|---|
| `crates/behavior/tests/dock_apply.rs` | `apply_all_changes_everything_or_nothing_and_reports_the_closed_panels` (:67) | keep | `apply_all`'s all-or-nothing rule; the C1 branch runs inside the same loop. |
| `crates/behavior/tests/dock_apply.rs` | `reconcile_drops_unknown_panels_and_places_missing_registered_ones` (:80) | keep | Reconcile placement; calls `set_visible(99, true, ..)`, whose result C2 keeps. |
| `crates/behavior/tests/dock_apply.rs` | `a_workspace_set_with_a_floating_group_round_trips_through_json` (:106) | keep | Saved-format boundary; also covers the new `floated` field's serde default. |
| `crates/behavior/tests/dock_apply.rs` | `a_workspace_with_a_bottom_pane_opens_and_closes_it_on_switch` (:126) | keep | Workspace switch rule, unchanged. |
| `crates/behavior/tests/dock_apply.rs` | `only_a_replacement_changes_the_live_revision` (:148) | keep | Revision rule, unchanged. |
| `crates/behavior/tests/dock_apply.rs` | `opening_a_closed_floating_panel_restores_its_window_place` | new | C1: `Open` of a hidden panel follows the hidden-anchor chain to its floating window's rect, and falls back to the anchor on `MissingTarget`. Chain logic nothing else checks. Driver: `Workspace::apply_all` on `docked()`. |
| `crates/behavior/tests/dock_apply.rs` | `a_floated_panel_keeps_where_it_was_docked_until_it_docks_or_closes` | new | C9: floating a docked panel records its docked location; closing it or docking it drops the record; floating it again from a float keeps the first record. State bookkeeping across actions with room for mistakes. Driver: `Workspace::apply_all`. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `the_dock_records_where_the_os_put_its_native_window` (:42) | keep | Unchanged behaviour. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `a_float_opens_an_os_window_where_the_host_reports_window_positions` (:76) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `a_native_dock_window_shows_no_os_title_bar` (:100) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `a_native_float_opens_at_its_own_size` (:120) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `the_os_close_of_a_native_float_closes_it_when_its_panels_may_close` (:138) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `dragging_a_native_palette_by_its_title_row_docks_it_where_the_app_moves_windows` (:220) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `dragging_a_native_palette_by_its_title_row_docks_it_where_the_os_moves_windows` (:264) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `a_native_float_the_os_resizes_or_moves_gets_no_place_back` (:314) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `an_app_change_of_a_native_floats_place_moves_its_window_once` (:338) | keep | Unchanged. |
| `crates/ui-patterns/tests/it/docking/native.rs` | `a_file_dropped_on_a_native_float_reaches_window_files_once` | new | C7/C8: OS files dropped on a floating group's own OS window that no target took reach `DockAreaOutput::window_files` in one pass, and a file a target there took does not. Drop routing across windows is a shared mechanism every app's dock uses. Driver: the `Windows` kit with a child viewport, as the other trials in this file. |

No trial for `rail_actions`/`rail_lit` (a four-arm mapping over `Layout::place`, readable), for C57 (one branch in the `Float` arm) or for C5/C6 (menu rows: wiring).

## Writer notes

1. **C1 body.** In `apply_all`'s loop (`workspace.rs:137-161`), before `apply_with_permissions`: when the action is `Action::Open { panel, anchor }` and `proposed.hidden` holds `panel`, clone `proposed.layout`, call `proposed.restore_from_hidden(&mut layout, &panel)` (it takes `&mut self` for `hidden`, `workspace.rs:243`, so it cannot take `&mut proposed.layout` at the same time), and on `Ok` set `proposed.layout = layout`, apply `Action::Activate { panel }` to it and drop the panel's `hidden` entry; on `Err(DockError::MissingTarget)` fall through to the plain `Open` with the given anchor. The closed/hidden bookkeeping after it (`:135-145`) is unchanged.
2. **C2 body.** `set_visible(panel, true, fallback, ..)`: a panel in the layout keeps today's `Activate` (`:172-174`); otherwise `self.apply(Action::Open { panel, anchor: fallback }, locked, permissions)`. Hiding keeps `:166-171`. The `restore_from_hidden` call at `:176` goes; `reconcile`'s call at `:269` stays.
3. **tp.R9 is dropped from the contract: no code.** `Open` of a panel in the layout is `Activate` (`inner.rs:75-77`), and `Activate` clears a group's and a floating window's `minimized` (`inner.rs:56-68`). No trial: one assignment.
4. **C57 body.** `inner.rs:49`: `let entry = self.take(&panel).unwrap_or(StackEntry { panel: panel.clone(), open: true, height: None });` (keep the `lone` id rule at `:48`). `apply.rs:53`: the `floatable`/`movable` check applies only when `self.contains(panel)`; an absent panel's float is an open and passes in a locked workspace. A hidden panel's `hidden` entry is dropped by `apply_all`'s retain (`workspace.rs:162-163`), so its old place is forgotten: the caller asked for a rect.
5. **C9 record.** `Workspace` gains `#[serde(default, skip_serializing_if = "Vec::is_empty")] pub floated: Vec<(P, Location<P>)>`. In `apply_all`, before each action, take the docked panels' locations the action can float (every panel whose `layout.place` is not `Floating`); after it, a panel that is now `Floating` and was docked gets `(panel, location)` pushed unless it already has a record. After the loop, drop the records of panels that are no longer floating (docked again, closed or gone). `reconcile` drops records of unregistered panels with the rest. `VERSION` stays 3: older readers ignore the field. This is workspace data, not pass state (settled decision S-P2).
6. **C9 command.** `DockCommands::DockPanel` (`#[command(label = "Dock Panel")]`). `DockScene` gains `floated: &'a [(P, Location<P>)]` (empty by default) and `pub fn floated(mut self, records: &'a [(P, Location<P>)]) -> Self`. `actions(DockPanel)`: when `panel` floats and its record's `anchor` is docked, `Action::Move { panel, anchor, placement }` from the record; otherwise `move_actions(scene, &DragUnit::Panel(panel), DockTo::Docked)` (`dock.rs:254-265`, the existing dock-back rule). `dock_states`: enabled while the panel floats and a docked panel exists. `menu_rows` puts Dock Panel right after Float on floating groups (production order: `panel_docking.rs:1624-1627`), with no config flag.
7. **C5/C6 rows.** With `config.group_order_items` and the panel docked (`PanelPlace::Dock`), push `ToggleMinimized`, `StepGroupUp`, `StepGroupDown` after the close rows; their enabled states already come from `dock_states` (`dock.rs:296-298`). Production's order is Collapse, Float/Dock, Move Group Up, Move Group Down, separator, Close Tab Group (`panel_docking.rs:1619-1645`).
8. **C7/C8.** In `FloatingGroup::update` (`floating.rs:256`), when `native` is set, register the drop veil's whole-window target (`WholeWindow`, made public in `drop_veil.rs`; no second copy) in place of a new `struct OsWindowFiles; impl WindowDropTarget<OsFiles> for OsWindowFiles` that accepts any list (pattern: `ui-widgets/src/popover/drop_veil.rs:129-199`); the accepted files go to `FloatingGroupOutput::files`. `DockArea::windows` (`area.rs:900-1024`) appends each group's files to `window_files`. A layer float (no `native`) registers nothing: the main window's own targets take those drops.
9. **Rail mapping.** `rail_actions` reads `layout.place(panel)`: `Dock`/`Node` shown → `SetMinimized { minimized: true }`; minimized → `SetMinimized(false)` then `Activate`; `Floating` → `CloseWindow`; absent → `Open { anchor: None }` (C1 then restores its place). `rail_lit` is `layout.panel_state(panel) != PanelState::Hidden` (`window_menu.rs:43`) and the group not minimized. `PanelRailRequest` (`rails/panel_rail.rs:34`) stays the rail's own output.
10. **fx.F51.** `column_work(column, work)`: after the `width` branch, `if let Some(FlyoutResize { panel, width, height, offset }) = work.flyout { push Action::resize_flyout_width(panel.clone(), Some(width)); push Action::resize_group(panel.clone(), Some(height)); if offset.is_some() { push Action::move_flyout_top(panel, offset) } }` (constructors at `behavior/src/dock/action.rs:452-457`). Only the iconic arm (`:790-797`) has a flyout; the other arm builds `ColumnWork` with `flyout: None`. The open-flyout events (`report.flyout`, `:795`) stay as they are: they carry the open panel, not a size. Upstream's iconic trials stay.

## Requests to other sets

| To set (or "unowned") | Path | What |
|---|---|---|
| unowned | `crates/behavior/src/dock/inner.rs`, `crates/behavior/src/dock/apply.rs`, `crates/ui-panels/src/docking/commands/dock.rs`, `crates/ui-patterns/tests/it/docking/native.rs` | No set owned them; this sheet takes them into panels-w1 (C57, C9, C7 trial). ownership.md should list them here. |
| framework-01-w9 | `crates/ui-panels/src/docking/iconic.rs:70` | `IconicColumnOutput::flyout: Option<FlyoutResize<P>>` (fx.F51); this sheet's `column_work` reads it. |
| panels-w17 | `crates/ui-egui/src/panels/panel_docking/native_tests.rs` (`a_file_dropped_on_a_panel_window_opens_as_a_document`) | The framework trial checks the `window_files` routing; re-judge the PhotoCraft test for what it adds beyond `window_files → open_dropped` wiring. |

## Changes from the consolidated plan

- Added `crates/behavior/src/dock/inner.rs` and `apply.rs`: C57 is not met at the base (`inner.rs:49` returns `MissingPanel` for an absent panel; `apply.rs:53` refuses it while locked), so it is code, not "a trial plus the doc line".
- Added `crates/ui-panels/src/docking/commands/dock.rs`: `DockCommands::DockPanel` (C9) lives there; ownership.md listed no file for it.
- Dropped `crates/ui-panels/tests/it/docking/rail.rs` (new) and its trial: the rail rule is a readable four-arm mapping (brief2: mappings); ui-panels' test binary has no `docking` module, so the file also needed a `mod.rs` and a `main.rs` line no set owned.
- Added `crates/ui-patterns/tests/it/docking/native.rs` with one trial for the new OS-window file route (C7/C8).
- tp.R9 is dropped from the contract and this set's items: `Activate` already clears `minimized` (`inner.rs:56-68`); no trial.
- No C57 trial (one branch); the C1 restore trial and a C9 record trial are the set's two behaviour tests.
- C8 changes `FloatingGroupOutput` (new `files` field), against "no signature change".
- C9 design fixed: the record is `Workspace::floated`, the dock-back fallback is the existing `DockTo::Docked` rule, the row shows on floating groups without a flag.
- Lines 520 / 60 → 376 / 27: counted as lines changed per file; the rail trial file is gone.
- fx.F51: `DockArea::column_work` maps `IconicColumnOutput::flyout` into three actions (`area.rs`, +15 lines); the consolidated plan did not list it for this set.
- The rail rule trial named in coverage-01 (`the_rail_collapses_closes_and_restores_by_where_the_group_is`) is not written: `rail_actions` is a four-arm mapping (brief2) and lives in `ui-panels`, not in `behavior/src/dock/workspace.rs`. The coverage row's file list (`workspace.rs`) is right for C1, C2, C9.
- sheets-04's `report.actions.extend(output.flyout)` is not applied: `flyout` is an `Option<FlyoutResize<P>>`, not actions.

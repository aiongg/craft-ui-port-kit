# dialogs-w19: plan check output

@@@ ITEMS
- [STUB] dialogs.rs, dialogs/tests.rs: I found no `todo!("cx.P2")`, `todo!("cx.P8")`, `todo!("tl.R9")` and no `P3(dialogs-w19)` marker in the tree. `dialogs.rs` still holds the legacy host, so I write the new file from the sheet and the contract rows.
- [RULE] sheet note 5 and `app/framework.rs:54`: `app.framework` has `dialogs: DialogHost` but no `captured` field. hub-w1 adds `captured: BTreeMap<String, serde_json::Value>`. I code against that field name, as the Requests table says, and mark the use `// PLAN: assumed app.framework.captured`.
- [DECIDE] note 8, `move_memories` and the last `PARAM_FAMILIES` row: the generic filter family's `owns` accepts every engine command. "A key some row owns" therefore matches `file.print`, `ui.layersPanelOptions`, `image.adjustments.*`, `file.new`, `filter.liquify` and the rest, and it matches a don't-show-again entry `{"skip": true}` too. The sheet lists routed and kept keys but gives no mechanism.
  - Option A: one explicit table in `dialogs.rs` of "keep" keys, "route elsewhere" keys with their target `SaveKey`, and the generic rule for everything else. A `{"skip": true}` object is kept by shape. Only `dialogs.rs` is touched. This is my pick.
  - Option B: ask each family set to expose its own move hook. This touches many sets and the contract.
- [DECIDE] note 8, routed keys with no name in the sheet: `select.refineEdge.workspace` (dialogs-w41), `edit.contentAwareFill.workspace` (dialogs-w43), `filter.liquify` (dialogs-w44) and `filter.cameraRaw.scope` (dialogs-w17 note 8) have no stated `SaveKey`, and the value types of the `shape.create.*`, `view.newGuide`, `file.export.exportAs` and `file.jpegOptions` routes are not stated either. The named `adjust.last.<kind>` and `craft_draw.shape.create.{kind}` keys are given.
  - Option A: write the table with `// PLAN: assumed` key names and move the JSON values as `serde_json::Value` or `toml::Table`. This is my pick.
  - Option B: leave those keys unmoved until the owning sets name a key. This loses remembered values on first launch.
- [RULE] note 8, the Fill and Stroke `mode` conversion: `blend_from_str` (`engine/src/cmd/layer_params.rs:75`) returns `Option`, and `layers_tree::blend_key` is `pub(crate)` at `panels/layers_tree.rs:30`. A mode string that does not parse is dropped, so the dialog reads its default, as S-O5 does for a null.
- [RULE] test `the_one_time_move_stores_owned_dialog_values_once_and_leaves_engine_read_keys`: `Remembered::store` needs a `craft_host::Host`. `MemorySections` is the in-memory `SectionStore` (`host/src/services.rs:68`) and the host builder defaults to it (`host/src/lib.rs:165`). The test builds a default `Host` and reads back through `Remembered::recall`.
- [RULE] note 9 against the Files table: the table says four lines come into the module list, but note 9 names five (`alerts`, `blend_options`, `file_forms`, `canvas_input`, `format_prompts`). I follow note 9 and add `// PLAN: Files table says four, note 9 lists five`.
- [RULE] note 7: `open_command_dialog` returns `Result<DialogId, String>`, but note 14 says every opener returns `Result<DialogId, String>` while the Requests table says `Option<DialogId>` for `new_group_ui`, `equalize_ui`, `guide_layout_ui`, `adjust_dialog`, `stroke_ui` and `color_range_ui`. I follow note 14 and L-100 and map an `Option` or `Err` into the `Err` text. I mark each call `// PLAN: assumed Option<DialogId>`, with a conversion that works for either return type.
- [RULE] note 5, `answer_requests` and the tests: `ParamFamily::footer` and `take_footer_action`, `take_listing`, `take_eyedropper` and `pick_color` are polled on every open `HostedParamDialog` through `get_mut_by_id` over `host.stack().ids()`. `DialogHost` has no iterator over typed dialogs, so I use `stack().ids()` plus `get_mut_by_id::<HostedParamDialog>`. This does not change the contract.

@@@ END

# dialogs-w19 decisions

- Note 8, `move_memories` and the generic family's `owns`: option A, an explicit table in `dialogs.rs`, with two corrections.
  - `PARAM_FAMILIES`' `owns` decides who opens a command's dialog, not which preference entries are dialog memories, so `move_memories` does not consult it. The table has three parts, checked in this order. **Keep**: the engine-read keys (`ui.layersPanelOptions`, `file.print`, the Save for Web memory; note 8's list) and every don't-show-again key. **Route**: a key that moves to a named `SaveKey` (below). **Generic**: every other entry moves to `photocraft.<key>`.
  - Don't-show-again entries are kept by key, not by the shape `{"skip": true}`. List the pref constant of each successor that reads `skip`: `dont_show_again`'s callers, `delete_layer_prompt::PREF`, `analysis_ui::DELETE_NOTE_PREF`, `contentAwareMove.noPixelsSelected` and any other hit of `grep -rn '"skip"' crates/ui-egui/src` at the base. Telling them apart by value shape would infer the fact from data.
  - Reason: one table, read top to bottom, says what happens to each key. The trial `the_one_time_move_…` asserts one key from each part.
- Note 8, routed keys without names: one naming rule, so the app's `remember(..)` calls and the move table cannot disagree. A key the app passes to a dialog or workspace is `photocraft.<old key>`, like the generic rule. The routes:

  | Old key | New `SaveKey` | Reader |
  |---|---|---|
  | `select.refineEdge.workspace` | `photocraft.select.refineEdge.workspace` | the key dialogs-w41's app code passes to `SelectMaskWorkspace::remember` |
  | `edit.contentAwareFill.workspace` | `photocraft.edit.contentAwareFill.workspace` | dialogs-w43, the same way |
  | `filter.liquify` | `photocraft.filter.liquify` | dialogs-w44, `LiquifyWorkspace::remember` |
  | `filter.cameraRaw.scope` | `craft_imaging.raw_develop.scope` | kept by the RAW workspace itself (dialogs-w17 decisions) |
  | `image.adjustments.<kind>` | `photocraft.adjust.last.<kind>` | given (dialogs-w32) |
  | `shape.create.<kind>` | `craft_draw.shape.create.<kind>` | given; `Memory` is camelCase with `default` (shape_drag/dialog.rs:135-142), so production's object moves as it is |
  | `view.newGuide` | `photocraft.view.newGuide` | the key dialogs-w54 passes to `NewGuideDialog::remember` |
  | `file.export.exportAs` | `photocraft.file.export.exportAs` | the key dialogs-w56 passes to `ExportAsDialog::remember` |
  | `file.jpegOptions` | `photocraft.file.jpegOptions` | dialogs-w59's `saved_value` |

  Values move as the old JSON with nulls dropped, converted with `toml::Table::try_from`, as the generic rule does. A route moves the value unchanged when the receiving type reads production's object shape. When it does not (`file.new`'s `__unit` keys, note 8), the row converts the value, and the reading set names the shape. dialogs-w41, w43, w44, w54, w56 and w59 confirm that their stored type reads production's object. Until each confirms, its row moves the value unchanged, and a value its type refuses opens as the default (S-O5).
- Sheet check: the order "keep, then route, then generic" is the scheme. Worked example: `file.print` is on the keep list, so it stays even though the generic family would accept it; `shape.create.ellipse` routes; `filter.gaussianBlur` takes the generic rule. A second run finds nothing to move, because every moved entry was removed from `Preferences.dialogs`. No platform signal.
- Opener return types (from the dialogs consistency pass): the openers `open_command_dialog` routes to return `Result<DialogId, String>` (L-100), as note 14 says; note 7 and the Requests rows for dialogs-w24 and w40 that say `Option` are wrong.
- From top-w21 (top-2): `ParamFamily` gains `pub cancel: Option<fn(&mut PhotocraftApp, &egui::Context, DialogId)>`, `None` in `ParamFamily::new`; `params::take` calls it for each `DialogResult::Cancel` of a `HostedParamDialog` whose key (`take_keyed`) the family owns (contract row cx.P8 updated). The Smart Object SVG family sets it.
- From dialogs-w43 (shared.md, dialogs-4), cross-set request: `dialogs.rs` declares `pub(crate) mod shared_picture;`; dialogs-w43 writes `crates/ui-egui/src/dialogs/shared_picture.rs`.
- From top-w16 (top-1), cross-set request: the `owns` path for view forms is `menus::view_cmds::is_form` (top-w15 re-exports it).
- From dialogs-w27, cross-set request: `ParamFamily` gains `document: Option<fn(&Value) -> Option<DocId>>` beside `owns` and `cancel` (cx.P8), and `dialogs.rs` gains `cancel_for_closed(app, ctx, closed: &[DocId])`, which cancels every open parameter dialog whose family reports a closed document from its captured value.
- Stub: crates/ui-patterns/src/patterns/form_dialogs/dialog.rs: pub ParamResult::id: DialogId (ParamDialog::result fills DialogId::NULL until the hosted dialog sets it); pub fn HostedParamDialog::clear_field(&mut self, key: &str)

## Batch-1 review rulings that apply to this set (rulings file of the first PhotoCraft batch)
- One app context: passes and tests run on `app.ctx()`; there is no `canvas_ctx`, and no test builds its own `egui::Context::default()` for a canvas pass (R10).
- Canvas test driver: `crate::canvas::testing` (`pub(crate)`): `ctx(&app)`, `to_screen(&app, ..)`, `in_gesture(&app)` take `&PhotocraftApp`; `tool_event(..)` returns the pass's `ToolHostResponse`; no `set_view` (set the view through the view commands) (R11, R24).
- Tool family entry: `tool(scope: &ToolScope, state: &mut <State>, host: CanvasHost)` (R12). Cancel goes through `tools::tool_changed` only; `ToolHost::cancel` cancels with the tool that holds the gesture (R13). A gesture struct carries no "started on" document and no "document went away" check (R20). Helpers tools call take `Mods`, not `egui::Modifiers` (R21).
- Dialog host: `get_mut_by_id::<D>(id)`, `cancel_by_id(id)`; there is no `close` (R15). `open_dialog`/`close_dialog` on the app are gone (hub-w1).
- Window and file commands take `{"document": DocId}` (R18).
- Integration tests under `tests/it` use only the public API; a test that needs crate internals is a unit test in the crate; never widen visibility for a test (R7).
- Reach framework crates through the `craft` facade (`craft::behavior::..`), never `craft_behavior::..` (R17). Match a `#[non_exhaustive]` struct variant with `..`.
- More batch-1 rulings that apply (same rulings file): `notices::post` takes the framework's `Tone` (R44); `ViewOptions::screen_mode` is the framework screen-mode type (R46); one file-dialog reply path on every platform (R47); `AppShell` regions by the framework's region names (R48); Show in Folder only when the platform can reveal a file (R22); Window › Arrange › Tile is the split layout (R23); `PhotocraftApp::new(session, services)` is the headless constructor, main/web use `with_context` (R58); `ToolHost::cancel` is a method on the host built with its stand-ins (R59); `cancel_by_id(ctx, id)` (R64).

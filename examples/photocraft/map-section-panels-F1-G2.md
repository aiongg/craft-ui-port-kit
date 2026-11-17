## F1. Channels panel, its panel menu and row menus

- **Kind**: panel + menu (inventory: Channels [6.8], Channels panel menu and row menus [6.9]).
- **PhotoCraft**: `panels/channels_panel.rs` (664: `show` from `panels/layers.rs:120`; `eye_action` :236-247 (mask view for the layer-mask row, gray-view composite rule); drop slot :226-233; footer Load/Delete on the mask row use the layer mask :494-497, 645; "<layer> Mask copy" :647-648; panel menu :567-585 in Photoshop order; MenuTarget :588-627; `channel.options` dialog :694-718).
- **Framework**: `ChannelsPanel` (imaging/src/ui/channels/panel.rs:103: `new(rows)`, `thumbnails` :118, `thumbnail_size` :125, `start_rename` :133); `ChannelRow`/`ChannelKind` (model.rs:105, :17: Composite, Color, Alpha, Spot, QuickMask, LayerMask); `ChannelsEvent` (model.rs:140: Target, Visibility sweep, LoadSelection, Rename, Options, Reorder, Footer, FooterDrop, Command); `ChannelsCommands` (menu.rs:24: every PhotoCraft panel and row item, overlay colours and opacities); `ChannelsFooterButton` (footer.rs:15-40).
- **Fit**: direct.
- **Gaps**: none found.
- **App glue**: rows from the document's channels, Quick Mask and the active layer's mask; thumbnails from the existing channel thumbnail cache (`ThumbSource`); events → commands: Target → `channel.target` (Quick Mask targets the composite); Visibility → `channel.setVisible` or the mask-view command (`eye_action` table); LoadSelection → `select.loadSelection {channel, operation}`; Rename → `channel.rename`; Options → `channel.options` dialog; Reorder → `channel.move` with the final index; Footer/FooterDrop → `channel.delete`/`channel.new`/`channel.duplicate`/save selection/`select.loadSelection`; Command → the menu ids at `:576-585`. `start_rename` from the Rename command. Deleted: the panel drawing, row interaction, drop geometry, menus (about 520 of 664 lines).
- **Tests**: `panels/channels_panel/tests.rs` (22): table 2 families (event → command: about 10 rows from the 10 panel tests; menu command → command + params on the targeted row: about 6 rows from the 6 menu tests), delete 6 (row painting, drop line position, thumbnails layout). Of the same file, 2 Load/Save-actions and 1 Layer Comps cross-references: keep.
- **look-comparison states** (crop: the Layers group): `channels-rgb`: `setup:"sample"`, `[{"method":"ui.set","params":{"dockTabs":{"layers":1}}}]` (`states.json` `panel-channels`); `channels-alpha`: add `{"method":"engine.execute","params":{"command":"select.all"}}`, `{"method":"engine.execute","params":{"command":"select.saveSelection","params":{}}}`; `channels-quick-mask`: add `select.editInQuickMaskMode`; `channels-mask`: a layer with a mask and `{"maskTarget":true}`.
- **Size**: M. **Depends on**: A1 (dock body).

# G. Colour


## G2. Swatches panel, its menu, import and export

- **Kind**: panel + menu (inventory: Swatches [8.7], Swatches panel menu, import and export [8.8]).
- **PhotoCraft**: `panels/swatches_ui.rs` (`show` from `panels/dock.rs:317`; table cached per library revision and colour settings :33-50; 22 px flush cells :24-25; commands `swatches.use` :55, `.rename` :102, `.delete` :107, `.move` :111, `.renameGroup`/`.deleteGroup` :112-113, `.add` :129, `.newGroup` :137, `.import` :167, `.export` :192, `.reset` :248; `source()` path vs base64 :143-152; import shows the Color group :183).
- **Framework**: `SwatchesPanel` (color/src/ui/swatches/panel.rs:58: `new(Bind<SwatchLibrary>, Bind<SwatchesState>, foreground)` :77, `cmyk` :83; output `used`, `changed` :27-41; `apply_file` :171, `note_lines` :209); `SwatchesMenu` (menu.rs:88: New Swatch…, New Swatch Group…, Import, Replace, Export, Export for Exchange, Reset); `SwatchLibrary` (library.rs:49).
- **Fit**: needs props.
- **Gaps**:
  - FG-9: `SwatchesPanel` edits the bound `SwatchLibrary` itself and reports only `changed` (panel.rs:36-38). PhotoCraft's library lives in the engine and each edit is a journaled command (one undo step: `swatches.rename`, `.delete`, `.move`, `.newGroup`, `.renameGroup`, `.deleteGroup`, `.add`). The panel must report each edit as an event (as `PresetEvent` does for `PresetBrowser`), so the host runs its command; diffing the library after the pass would infer the edit from a side effect (porting rule: use the framework's signals).
  - The library model: PhotoCraft's engine swatch library and craft-color's `SwatchLibrary` must be one type (engine adopts `SwatchLibrary`, or the panel reads a trait). Decide in the brief; the panel API change above is needed either way.
- **App glue**: `used (at, colour, background)` → `swatches.use` (one undo step, also recolours a selected shape's fill, test at `panels/swatches_ui.rs:296-320`) then `apply_color::swatch_picked`; menu → `PresetFileRequest`s answered through the host file service, results into `apply_file`; import status into the status bar. Deleted: the egui table, flush layout, cache, menu drawing.
- **Tests**: `panels/swatches_ui.rs` inline (10): keep 6 (each click one undo step; import/export counts in the status line; path vs bytes source; Reset command; import opens the Color group), delete 4 (22 px flush cells, table cache, layout). `panels/apply_color/tests.rs` (6) 2: keep. `panels/color_tests.rs` 1: keep.
- **look-comparison states**: `swatches-default`: `setup:"sample"`, `[{"method":"ui.set","params":{"dockTabs":{"color":1}}}]` (Pro order, `states.json` `panel-swatches`); `swatches-with-group`: add `{"method":"engine.execute","params":{"command":"swatches.newGroup","params":{"name":"Brand"}}}` and `{"command":"swatches.add","params":{"color":"#e76f51"}}`.
- **Size**: M. **Depends on**: FG-9, N1 (preset browser).


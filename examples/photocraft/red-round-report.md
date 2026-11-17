# PhotoCraft red tests, round E run

Failed in the full run r1: 68 (round D r1: 98). Passing: 12041. New failures against D r1: 1 (below). Stack overflows: 0.

Trees after fmt: the framework integration tree and the app integration tree. Run r1: the full app run script, 1030 s, on framework 6839d23016 and app 59e3cf9c68. A comparison file lists every failing test with its panic line.

## Merges
- framework: red/lage, t1e clean. t23e conflicted in behavior geometry/draft.rs: kept t7d's `locking_shift_drags`, dropped t23e's `locking_drags` field and builder, kept t23e's rule (a non-locking Mixed draft keeps the pointer path under Shift), its trial moved to `locking_shift_drags`. t45e conflicted in focus/nav.rs (took t45e's `move_focus` with `FocusOrigin`) and body/scroll.rs (kept ours). t6e clean. -> 0ea70922fb.
- app: t1e clean; t23e freeform.rs moved to `locking_shift_drags`; t45e, t6e clean. -> 59e3cf9c68.
- No compile errors (app build 723 s; framework test builds of 9 crates, 0 errors).

## Small fix: one scroll trial
`body::scroll::a_pressed_field_in_part_view_stays_put_and_tab_to_it_reveals_it`:
- 6839d23016: the setup measures the field's full height from the first field (wholly in view) instead of the second field's clipped response rect; the Tab reveal checks the whole field is in view.
- 5602d6f271: the trial then failed at "the press focused the field". Focus lands on the field's text part (`widget_id(response.id, text)`), as text/kit.rs already expects; the trial compared the field's response id. It now records the text part's id. Passes (5 s run).

## Framework trials
ui-contract 240/240, behavior 80/80, ui-canvas 263/263, draw 289/289 (round C's bezier anchor-cursor failure passes), text 91/91, ui-panels 217/217, color 143/143, font-manager 53/53, ui-widgets 794/794 after the trial fix above.

## Per track against D r1
| track | tests | fail in D r1 | fail now | fixed since D | new fail |
|---|---|---|---|---|---|
| T1 | 10 | 5 | 2 | 3 | 0 |
| T2 | 7 | 3 | 0 | 3 | 0 |
| T3 | 13 | 4 | 3 | 1 | 0 |
| T4 | 9 | 3 | 2 | 1 | 0 |
| T5 | 5 | 4 | 3 | 1 | 0 |
| T6 | 10 | 6 | 4 | 2 | 0 |
| lag | 26 | 20 | 3 | 17 | 0 |
| T7 | 7 | 5 | 5 | 0 | 0 |
| T8 | 13 | 6 | 5 | 1 | 0 |
| T9 | 10 | 5 | 4 | 1 | 0 |
| T10 | 5 | 5 | 5 | 0 | 0 |
| T11 | 8 | 5 | 5 | 0 | 0 |
| T12 | 16 | 12 | 12 | 0 | 0 |
| T4d/T4e | 4 | 1 | 1 | 0 | 0 |

Fixed this round:
- T1: character_and_paragraph_fields_follow_the_type_units_preference, caret_font_and_face_persist_across_more_font_choices_and_paste, options_bar_hover_previews_with_the_character_picker_also_shown.
- T2: all three (a_carried_on_endpoint_starts_a_new_curvature_run, the_curvature_pen_carries_on_an_open_path, failed_stale_pen_commit_preserves_the_draft_until_retry).
- T3 freeform_refuses_a_locked_shape_before_starting_a_stroke; T4 undo_steps_back_through_the_transform_not_the_document; T5 a_command_held_line_undoes_as_one_box_step_and_commits_as_one_document_step; T6 smoothed_stroke_shows_its_catch_up_tail_while_drawing and gradient_tab_edit_keeps_cmyk_stops_in_their_model; T8 display_p3_is_converted_on_gpu_and_cpu_canvases; T9 size_changing_rotation_preview_is_visible_and_preserves_the_panned_center.
- lag: 17 of the 20 picture-class tests.

## Picture class and arbitrary rotation
- Picture tests: 21 of 24 pass (round D: 4). The darkening (picture at about 0.41 of its colour) is gone. The 3 still failing are live_stroke_canvas::the_canvas_shows_the_committed_stroke_part_0/1/2: at zoom 0.5, hardness 0, 8-bit, the canvas changes by 64/255 on release (the stroke shows while drawing; release changes it).
- Arbitrary rotation: size_changing_rotation_preview_is_visible_and_preserves_the_panned_center passes. preview_toggle_and_cancel_keep_the_document_while_ok_applies_rotation passes every visibility check (no darkening) and now fails later, at :181, the view centre after OK: 226.0, test wants 226.5 (453 px document). For T9.
- transform_undo_tests::transform_preview_stays_visible_while_panning (round D's t12d new failure) still fails "the transformed pixels are visible before panning", although the picture slot no longer darkens: for t12d/T12.

## New failure against D r1 (1)
- `tools::vector_ui::paint_tests::stroke_swatch_gradient_tab_sets_the_next_shapes_stroke` (:512, no node labelled "Blue 01"): **t6e**, fw 98477eec5c. The Stroke chip's Gradient tab palette now takes its content height up to five small control heights and scrolls. "Blue 01" is the first preset of the second group (Blues, after Basics' three), so it most likely sits below the bounded view, and the preset browser shows only the rows in view (production's egui palette keeps every row in the AccessKit tree). Not confirmed by a run. Back to T6: the test has to bring the preset into view (scroll or keyboard) before clicking it, or the palette's bound has to fit it.

## Round D's new failures, now
- Still failing: gradient_map_stop_picker_closed_without_a_colour_changes_nothing (t8d), preferences_apply_waits_for_an_open_picker (t11d), with_the_layers_panel_closed_delete_leaves_the_filter (t12d), transform_preview_stays_visible_while_panning (t12d, above), mask_sections_run_their_edit_commands (unattributed).
- Passes: a_waited_command_reports_progress_serves_other_calls_and_cancels_cleanly (environment, as expected).

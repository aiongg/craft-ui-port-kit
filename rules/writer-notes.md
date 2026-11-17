# Writer notes

Framework rules that every writer of a set needs and that no sheet repeats. `port-set` copies the `## Notes` section below, word for word, into every writer prompt: the one-shot bundle (`port-set run`, `port-set fix`) and the agent prompt (`port-set agent`). The pipeline's own rules (markers, `// PLAN:` notes, tests, deletions) are in `tools/portkit/portset/bundle.py` and apply to any framework.

Written for: craft-libs `next` at `fd73622066`. Each name below was checked there.

When the framework changes a rule here, change the note in the same change. When a review finds a class of defects that one framework rule would have prevented, add the rule as one line. Lints that a script can check go in `rules/lints.toml` instead.

## Notes

- A frame can run two passes, and egui gives a frame's input events only to its first pass. A rule that reads the frame's input or drains a queue says how it behaves on a second pass (a pass applies only its own input), and its trial reruns a pass inside one frame.
- A helper for another set's component takes that component's `Env`; never `Env::of_root`.
- Trial premises: every `Fixture` frame adds 1/60 s (`testing/frames.rs` in craft-ui-contract); two clicks at one point within the double-click time are a double click; a host goes to a trial through `Fixture::host`, never `Host::install`.
- A remembered (SAVED) value is written with `runtime::memory::set_saved_value` and read with `saved_value`; never open a `MemoryStage` outside craft-ui-contract.
- A private `#[component]` the suite registers declares `sample = ..` or has a story that covers it.
- `List::new` is multi-select: a single-selection list says `.select(SelectMode::Single)` and maps `Set`, `Toggle` and `Clear`.
- A request prop such as `start_rename` is sent once, not every pass.
- A canvas story paints document content as a `StoryPicture` of `StoryShape`s, never through `ui.painter()`.
- The framework crates build with `#![warn(missing_docs)]`: every new public item gets a doc comment.

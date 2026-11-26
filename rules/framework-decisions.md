# Framework decisions

Decisions already taken that bind every craft app and every port. A plan, a sheet or a brief that contradicts one of them is wrong: stop and report it (`agent-common.md`). A production app that does otherwise is not matched on that point, even though production is otherwise the look and behaviour reference.

Look rules that bind every app (one arrangement per theme and density, variants as named options, no component-specific theme values) are in `porting-rules.md`, "Look". The pass-model rules every writer needs (state carried between passes, value-edit reruns, per-pass input, the frame budget) are in `porting-rules.md`, "Code", because `port-set` copies that section into every writer prompt. This file gives the reasons behind them and the decisions that are not about code style.

## Panels and docking

- **One panel and docking mechanism.** Every app docks its panels through the framework's one mechanism.
- **A floating window is one column, and the column is the unit.** Collapse to icons is a state of one vertical panel column, docked or floating, and nothing else differs: every group in the column is expanded, or every group is an icon.
- **No links between columns.** No icon in one place expands a panel in another. An app's separate panel rail that opens panels elsewhere is not ported, even when production has one.
- **Collapsed and expanded columns behave the same.** A single floating panel collapses to icons and stays floating. Floating icons drag onto each other to form groups, as expanded panels do. Docking works the same in both states: drag a panel or a group, drop zones show over and beside collapsed columns, and a drop onto a docked or floating collapsed column works. The only difference is that a collapsed panel's contents are hidden.
- **The toolbar docks and floats by dragging**, with no separate move command. A drag sets its columns (or rows) in whole steps, and the other dimension fits the tools, never blank space.

Reason: one model of columns keeps docking predictable and lets every app share the code. A production dock that differs is not matched on these points.

## The pass model

The framework may run more than one pass in a frame (a value-edit rerun, a layout pass, an input filter). egui hands a frame's input events to its first pass only, and nothing rolls back between passes: memory writes back, frame output accumulates, and app state is plain state.

- **A pass applies only the input its own pass receives** (events, deltas, press edges, wheel shares, key intents, pen readings). The frame's input is applied once, in the pass that receives it. A consumer never turns a held fact (a drag or held phase, the latest position, held buttons, the pen's current reading) into an event, and steps time-driven work only by the pass's elapsed time, which is zero on a frame's later passes. The rule lives in the framework's input adapters; consumers add no rerun signal and no frame guard. Injected automation input enters only a frame's first pass.
- **No state carried over from a previous pass**, except the three framework mechanisms listed in `porting-rules.md`: content out of view keeps its last size, an unchanged body reuses its measurement, and a settled region replays its last paint. Reason: state carried between passes is the main source of stale-frame bugs, and each exception is one tracked mechanism, not a per-component cache.
- **A value edit reruns the pass in the same frame only when something earlier in that frame read the edited value**, as the framework records reads. Reason: a rerun on every edit doubles frame time for no visible change.

## Shared engines

- **Text input and IME.** Every app's text input, canvas text tools included, uses the framework's IME engine. The engine keeps one press per pass and handles a click during composition itself. Reason: composition handling is hard to get right and must behave the same in every app.
- **Layer filter types.** craft-layers owns the layer filter types, their controls and their rules. Each app chooses which of them its panel offers (default: all). A missing type is added to craft-layers, never built in one app.
- **Engine jobs.** An app's engine keeps its own job table (undo step, document lock, commit points, wasm stepping). Only the job UI moves to the framework. Reason: the job table is tied to the app's document model; the job UI is the same in every app.

## Crates and dependencies

- **The facade holds every library crate.** The `craft` facade has every framework library crate as an optional member, and app code reaches them through it. Only tools, build and test helpers, and craft-ui's internal crates are listed outside it, each with a reason.
- **Third-party libraries are forks or crates**, never vendored into craft-libs. The crates the framework already vendors (`vendor/`) stay vendored, including the framework's edits to them.
- **Fonts go to the craft fonts set**, never into a crate.
- **The framework's own egui changes** live on a branch of the framework organisation's egui fork, and the framework pins a revision there.
- **App ports push nothing to the egui fork.** A port that meets an egui limit handles it in the app or framework code, the way production did, or files the egui change for the framework maintainers. Reason: the fork is shared by every app, and its revision moves only through the framework.

## Changes one app needs

- **A framework change only one app needs is an option that app selects**, with the default unchanged for every other app: a named variant, a setting or a feature the app turns on. The default changes only when parity with production in every app needs it.
- **Its proof renders the changed components, not the whole gallery:** each component the change reaches, with the default the other apps keep, rendered with `cl render <crate> <Component>` in every theme before and after the change, and the two renders match. Reason: a whole-gallery render per change costs a link of every gallery crate and thousands of shots, and proves no more than the changed components do.

## Landing

- **The framework lands on its `next` branch** (`framework.branch`). Apps keep pinning the framework's main branch until each one ports. `next` merges to main only after that, through a reviewed PR. Reason: an earlier merge would strand the apps that still build against main.
- **Scrub before every push.** Nothing that names a developer's machine, local tools or personal data reaches a public repository, in files or history (`process/10-land.md`).

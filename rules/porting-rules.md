# Porting rules

Rules for every agent in a port: planners, writers, reviewers, fixers and the lead. Every prompt includes this file in full. `tools/port-set` copies the `## Code` section, word for word, into every writer prompt, so that section must stay self-contained and keep its heading.

Where this file and a brief disagree, this file wins (`agent-common.md`, "Source precedence").

## Look

The app after the port looks and works like the production app before it. Production is the reference: an agent uses its look without asking.

- **The old app is the spec.** Before code is written, the old app's design is written down: every screen and region, surface roles, bars and their contents in order, panels and their docking, menus, dialogs, every user action (phase 1's map). Each item maps to a framework piece or to a named framework gap. The port is done when every item is there and looks and behaves the same.
- **The old is not automatically right.** Judge each difference on its own: old better, new better, both have issues (name the target look), or unclear (ask the lead). A look that one theme or mode has and its siblings lack is checked for intent (a code comment, a commit message, an issue) before it is matched. A look that came from an early generated design rather than a design decision is not matched. Never add a framework mechanism or a format change only to reproduce such a look.
- **One arrangement in every theme and density.** Themes change token values (colours, sizes, shapes). Densities change sizes. Neither changes which parts a component has or how they are laid out. A production layout that changes by theme is not matched, and no prop or mechanism is added to reproduce it. Reason: per-theme components multiply the code to maintain and test.
- **App variants are named options.** An app may add its own variant of a shared component when it has a real need (start-aligned number fields, a connected-square reference-point picker). A variant is a named option on the component (an enum or a type role), documented and shown as its own story. Never per-call boolean flags or one-off settings each app sets. The arrangement rule above holds for every variant. Reason: some apps need a different look, but bespoke options on every component would make the suite impossible to unify later.
- **Parts match, pixels may differ.** Shapes, colours, borders, glyphs and visual parts match the old app. Exact pixel values may differ.
- **Nothing overlaps** or cuts into a neighbour, not even by one pixel.
- **No component-specific theme values.** Keep the existing themes and their contrast rules.
- **Behaviour follows the suite's own expectations**, not WAI-ARIA.
- **Dialog footer buttons** follow the platform's order (OK last on macOS and Linux, first on Windows), at the end edge.
- **Compare the framework's defaults with the old library's on every target** before the first screen is compared: fonts, row cross-axis alignment, surfaces, theme mode, control text placement. A changed default (a fallback font face, rows aligned to the top where the old centred them) breaks every screen at once, and no behaviour test notices.
- **Side-by-side gate.** Every screen or state a task changes is compared old and new, in the same theme and window size, at full-size crops (text face and placement, sizes, colours, surfaces, alignment), before the task reports and before the lead accepts it. The lead looks at the pairs, not at the agent's verdict.
- **A port takes no layout or design questions to the developer.** Where the old app answers a question, do what the old app did.

## Old look or standardized look

- The framework's architecture decides how a look is produced: which token, which shared mechanism. The old app decides what it looks like.
- A difference from the old app needs a reason: a standardized mechanism, or one way replacing an old inconsistency. "The new code does it this way" is not a reason.
- Where the old app did the same thing differently in different places, one way applies everywhere: the look most places had.
- What the architecture standardizes: semantic tokens for sizes, spacing, colours and font sizes; panel rounding as a theme role; one focus ring, selection fill, disclosure glyph and dropdown arrow for every component; dialogs sized from their content; one layout for every theme family.
- Look problems are found by broad sampling (every area and crate, plus a random sample), never from a top-N score list. They are fixed by class: one shared cause, one fix for every component it affects.

## Code

- No workarounds or quick fixes. Build the proper design.
- Architectural correctness, extensibility and maintainability come first.
- One mechanism per concept. One set of components; no old code left beside the new.
- Use the framework's own signals: what a story opens, which key was pressed, which kind of component it is, what has focus. Never infer a fact from side effects (focus movement, sizes, text, draw order). If a signal is missing, add it at its mechanism.
- Make the fix where it belongs, in any file, framework included. A framework gap found during a port gets a framework fix at the mechanism, not app code. A workaround for it already in another crate is a bug to report.
- A fix that adds a mechanism removes the one it replaces in the same change. Prefer removing work over adding a cache, a guard or a second path beside the old one. Caches of pure test data are fine.
- No relaxed or removed assertions, suite widenings, lint exceptions, `allow`s, token arithmetic, theme colour changes (restoring a dropped token to its old value is not a change), re-implemented controls or app shims that a later set replaces. No private back door for a test (`#[doc(hidden)]` items, test-only public API). Sizes come from tokens and content.
- No state carried over from a previous pass, with three exceptions, each through its one framework mechanism:
  - content out of view keeps its last shown size;
  - a body reuses its last measurement while its inputs (props, room, content version), as the framework tracks them, are unchanged;
  - a settled region in view (no pointer over it, no focus in it, no animation, no value, size or input change, as the framework tracks them) repaints its last paint and replays its focus and hit records instead of running.
- A value edit reruns the pass in the same frame only when something earlier in that frame read the edited value, as the framework records reads.
- A pass applies only the input its own pass receives. A frame's input is applied once, in the pass that receives it; a held fact (a drag phase, the latest position, held buttons) is never turned into an event.
- Keep the app fast: every interaction is at least as fast per frame as in the production app, and under 8 ms of framework time per frame on a current mid-range developer laptop (for example an Apple M2 or a comparable recent x86 laptop), at full gallery Overview scale.
- Write code and comments as if the code had always been this way. Comment only what the code cannot say: why, constraints, non-obvious invariants.

### UI gallery

The framework's UI gallery (craft-libs `crates/ui-gallery`) is the catalogue of every framework component. Its registration and story mechanism are documented in craft-libs `docs/porting.md` and in the gallery crate: read them there.

- Before planning or writing a component, check the gallery for one that already does the job. Add a component only when nothing there fits. An app variant is a named option on the existing component, shown as its own story.
- Every component or variant the port adds to the framework is registered in the gallery in the same change: stories for its states and for each named variant, at the gallery level of its architectural kind (primitive, control, composite, ...), with a story owner.
- Dialogs, modals and windows start closed in a story. A button in the story opens the real thing.

## Tests and builds

- **The test rule** is `testing-rule.md`. Every test names the regression it guards. Nothing trivial, no exact sizes or strings.
- **Write first, build in batches.** In the batch phases (writing, review fixes, compile fixes, red rounds) writers write code with no build, and fixers build only in the fixer mode `build` (`process/11-build-loop.md`, rule 3). One `tools/cycle` run builds every agent's work together and runs the tests once. Agents write code that compiles by reading carefully: every import path, signature and trait bound checked against the code.
- **One-off tasks with a build tree** (a look fix, a late framework gap) check their own change as they go, in their own warm target dir: build the test binary of each crate they test (`cl test <crate> --no-run`), then run the trials for what they changed. `cl check` only for a crate they change but do not test.
- **Every cargo command goes through `cl`** (`process/11-build-loop.md`). A plain cargo command with other features, `--all-features` or `--bins` builds a second copy of the framework and everything above it. CI runs those.
- **No workspace-wide builds or tests locally.** Whole test binaries and full runs run in the integration tree, through `tools/cycle` or a gate.
- **Format before each commit** as `rules/agent-common.md` says ("Formatting").
- **Count trials for run-model changes.** A change to the pass, the run model or a shared mechanism keeps or adds count trials: a frame runs only what it must (rows in view, passes per frame, runs per interaction), asserted as relations, not times.
- **An app smoke trial** shows the whole app window at a desktop size for a few frames in a debug build, with in-memory settings. A debug-only assert on the first frame is otherwise invisible to release builds and to component trials.
- **Drive it like a user.** Look and behaviour work drives the app with mouse and keyboard through every action on the map, not only through trials (`process/09-look-and-behaviour.md`).
- **Slowness is found by reading**, never by another long run to time it: the code, the build setup, `cl`'s build records and existing timings. Edit, then try the fix with the faster loop itself; that run is the confirmation. When a slow tool must run anyway, that run is the profiled one.
- **Debugging by running** (when a brief gives builds): print the values at the suspected path (`eprintln!` lines starting with `DIAG `), run the one trial, read, repeat. Remove every `DIAG ` line before the work counts as done.

## Efficiency

- Wall time is the bottleneck, not writing code. Every loop (builds, tests, measurement rounds, captures) is cut to the least wall time. A slow loop seen once is fixed at once.
- Plan for the least total wall time to the goal. Judge what a step costs from what is already known (earlier timings, the code, the setup); never run anything only to find out what it costs.
- Everything already known to be needed goes in one batch: all fixes together, one change, one confirming build at the end. Never one fix per round when the others are known.
- **The fixer model.** Fixers write fixes for their whole list (code-only, with `DIAG ` prints where unsure, unless the fixer mode is `build`) and hand back. One `tools/cycle` run merges every fixer's branch, runs one build and one full run, and sends each fixer (the same agent, resumed) its still-failing tests with their panic lines and `DIAG ` output. Reason: one build for all fixes costs the same wall time as one build for one fix.
- A measurement runs only if its result changes what happens next. A separate measurement runs only to find which part of a batch missed its target.
- Before starting anything that waits, say what it costs and why no cheaper path exists.
- Report what was compared, not "done": the screens or states compared and what still differs.

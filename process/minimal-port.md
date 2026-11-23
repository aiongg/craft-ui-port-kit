# Minimal port

A minimal port moves an app that is still on the old UI framework onto craft-libs `next`. Only the APIs that `next` removed change, to next's replacements. The rest of the app's egui UI stays as it is, hosted by next's runtime through the `craft_ui::shell::embed` hooks. The full port ([00-overview.md](00-overview.md)) can follow later, app by app.

This page is the whole runbook of a minimal port. Its steps replace the phase table: a workspace in this mode (`work.mode = "minimal"`) records steps as board tasks, and `track phase` refuses.

| | |
|---|---|
| Use it when | The app has no port in progress and has to move its craft-libs pins to `next` (for example before `next` merges into main). |
| Do not use it when | A full port of the app is under way: that port replaces the same code. |
| Result | One app PR that pins `next` by rev. It also yields craft-libs PRs to `next` for each framework fault the port finds ([Framework fixes](#framework-fixes)). |
| Agents | One or two Opus writers, code only; the same agents take their compile and test rounds. |
| Builds | One warm build after the rewrite, one compile check per round, one test run per round, the app build for the run step. |

## What changes and what stays

| Changes | Stays |
|---|---|
| The craft-libs and egui `[patch]` revs, feature names, new direct dependencies | The app's own egui widgets, panels, dialogs and canvas code |
| Mechanical renames and moved paths (`tools/minimal-port rewrite`) | The app's own command and shortcut tables |
| The runtime host: four embed hooks, the install, fonts, the close path | The saved layout format and the app's `ui.dock` control vocabulary (app-local) |
| The dock: next's `DockArea` with the app's panel bodies inside | The panel bodies and the session or document view |
| Update dialogs on a `DialogHost`; the title bar on `shell::TitleBar` where the app draws one | The app's look inside its panels |
| Removed helpers moved into the app (capture slot, header menus, icon-button painter, `WidgetPalette`, `split_rect`) | |
| `craft_keymap` `Dispatcher` to `Matcher`; the shortcuts dialog to `craft_menu::shortcuts` | |
| Key handling the runtime takes over (the input review) | |
| Tests of removed renderer internals deleted; harnesses install the runtime | The app's own behaviour tests, adapted |

**Visible differences** (seen in the trials at `next` b436ae9925; the PR lists the ones the app shows):

- The dock frame, tabs and drop preview follow craft-theme, not the app's colours. Panel contents keep the app's look.
- Floating windows hold one column. Old saved windows with parts side by side load as several windows.
- The canvas or session view is the canvas group, with no tab of its own.
- Tab and group menus, tab overflow and collapse to icons are next's.
- The update dialogs are next's, without the app icon.
- One key press per pass. Escape reaches the app's own egui code only while one of its widgets has focus.
- F6 is unbound from framework pane navigation where the app binds F6 itself.

## Board tasks

Put every step on the board before it starts, and move it as it runs (`tools/track.md`):

| Task | Step |
|---|---|
| `mp-setup` | 0 |
| `mp-sites` | 1 |
| `mp-repin` | 2 |
| `mp-rewrite` | 3 |
| `mp-write` (one writer) or `mp-host` and `mp-dock` | 4, 5 and 6: the writer keeps its task through its rounds |
| `mp-compile`, `mp-test` | 5 and 6: the lead's gate runs |
| `mp-fw-<n>` | one per framework fix ([Framework fixes](#framework-fixes)) |
| `mp-run` | 7 |
| `mp-land` | 8 |

Create each with `track status <task> todo`, move it with `track status <task> running` when it starts and `done` when its check passes; a failure is `blocked` with `--on` naming what it waits for. Writers report under their own task with the calls in their prompt.

## 0. Setup

1. `tools/init-workspace <dir> --mode minimal --app-name "<App>" --framework <craft-libs clone> --app <app clone> --ui-dir <UI crate dir>`. Ask the developer how to view the dashboard (`--how-served`), as [01-setup.md](01-setup.md) step 3 describes.
2. Ask the landing questions of [01-setup.md](01-setup.md) step 3a that apply: the app repository and branch (`land.push_target`, `land.push_branch`) and the commit identity. Early CI on a fork does not apply.
3. Set `plan.base` to the head of `next` (`framework.branch`), and `framework.repo` to the remote that has it. Create `app.port_branch` (for example `port/minimal`) from the head of `app.base_branch`; write that commit to `plan.app_base`.
4. Run `tools/make-snapshots`. The framework snapshot (`framework.snapshot`, at `plan.base`) is where the writers read next's source.
5. **Baseline.** Take the app's CI result on `plan.app_base` (`gh run list --commit <sha>`). A green run that ran the tests is the baseline: no test fails before the port. When that CI is red or ran no tests, derive the selection on the old manifests (`tools/feature-selection.py`, [01-setup.md](01-setup.md) step 6) and run `tools/test-run baseline --app --baseline` on the old pins instead, as a background task.
6. Set `build.runner` to `timeout <seconds>` (for example `timeout 900`), so each test binary has a limit. A hung binary is killed, and `test-run` marks it `crashed` instead of waiting forever.
7. Check that `minimal.run_platforms` names the platforms the run step covers ([step 7](#7-run-the-app)); add `web` when the app has a web shell.

## 1. Sites report

```sh
tools/minimal-port sites
```

It lists every port item the rules find, by runbook item, with file and line, in `<work.runs>/minimal/sites.md` (`sites.json` for tools). It changes nothing. Exit 0 means no site: the app needs only steps 2, 5, 6, 7 and 8. Read the report in full; it is the writers' work list.

**Writers.** The report's `Writers` line gives the split:

- **One writer (`all`)** when the app has no dock site (no old dock renderer).
- **Two writers (`host` and `dock`)** otherwise, in parallel on their own branches cut from the rewrite commit:
  - *host*: the runtime host, the input review, dialogs, title bar, removed helpers, keymap, manifests, test harnesses, the web shell;
  - *dock*: the dock files and the dock tests.

The host writer owns the app's framework module, `<ui crate>/src/framework.rs`. The dock writer only calls it. Both prompts name its functions up front, so both writers can run at once without editing each other's files:

| Function | Does |
|---|---|
| `install(ctx, ..)` | `embed::install` for the native app: `InstallSpec`, the window system, `UiFonts` |
| `install_headless(ctx)` | the same with no window system, for the web shell and every test harness that runs the app's UI |
| `before_input(ctx, app)` | `embed::before_input` with the app's `FrameInput` (theme mode, scale, `Host`, the F6 overrides) |
| `before_ui(ctx, frame)` | `embed::before_ui` |
| `close_path(ctx, app)` | `embed::logic` with the app's unsaved-changes decision |
| `host_canvas(ctx, id)` | registers the app's own document or session view as the window's canvas, keeping Tab and the edit chords in egui |
| `escape_pressed(ctx)`, `take_window_cancel(ctx)` | Escape from egui or the window's `Intent::Cancel` (peek and take) |
| `app_style(ui)` | the app's own egui style, for panel bodies and the group view where the pin still leaks the dock's style ([Framework fixes](#framework-fixes)) |

A writer that reaches its call budget hands back with a Resume block, and a fresh agent continues from its commits.

Record `track status mp-sites done "<n> sites; writers <split>"`.

## 2. Repin

```sh
tools/minimal-port repin             # the diff, nothing written
tools/minimal-port repin --apply     # writes and commits once
```

It sets every framework dependency to `plan.base`. Each egui `[patch.crates-io]` entry gets the rev the framework's own manifest uses at `plan.base`. It renames or drops the features `next` changed (craft-ui `serde` and `native-windows`; `egui` to `ui` on craft-update, craft-window and craft-quit; craft-keymap `ui`). Read what it lists (a fork the framework does not patch, a features array over several lines) and fix those lines by hand in the same branch.

`Cargo.lock` re-resolves in the first build (step 3). When resolution reports a version conflict between the two revisions' requirements, update that one package: `cl cargo update -p <crate>@<old> --precise <new>` (the SoundCraft trial needed `rustix` 1.1.5 to 1.1.6). Commit the lock with the repin.

Then derive the app's package selection for the new manifests with `tools/feature-selection.py` and write it to `[workspace.metadata.cl]` on the port branch ([01-setup.md](01-setup.md) step 6). Every cl command after this point uses it.

## 3. Rewrite

```sh
tools/minimal-port rewrite --apply
```

One commit with the mechanical part:

- `craft_ui::ComboBox` becomes `egui::ComboBox` (same builder). A chain that calls `show_ui_with_header` or `show_rows_with_header` stays: it becomes a port item.
- The dock model moves to `craft_behavior::dock` (`Placement` becomes `DockPlacement`, `Side` becomes `DockEdge`), and `Monitor` moves to `craft_behavior`.
- `SplitAxis` becomes `craft_behavior::flow::Axis` (`Horizontal` becomes `X`, `Vertical` becomes `Y`), and `SplitSize` moves to `craft_behavior::dock`.
- `Bindable` and `Kind` become `CommandDef` and `CommandKind`, and `craft_keymap::egui::Hit` becomes `craft_keymap::Hit`.
- `craft-behavior` is added to each crate that now uses it.

Run it after the repin, so new dependency lines take the new rev. A second run changes nothing. `--only` and `--skip` take the class names (`combo`, `dock`, `split`, `keymap`, `deps`).

Then start the warm build of the new pins as a background task: `cl test all --no-run` in the app tree. It builds next and the other dependencies while the writers write. Its errors are the port items of step 1, by name. Nobody waits on it.

## 4. Write

Render one prompt per writer and run them as one `swarm.py` job list, role `minimal_write`:

```sh
tools/render-prompt mp-writer ITEMS=host TASK=mp-host OUT=<work>/minimal/mp-host-report.md > <work>/minimal/mp-host.md
```

```json
[{"task": "mp-host", "prompt_file": "mp-host.md", "role": "minimal_write", "cwd": "<tree of mp-host>"},
 {"task": "mp-dock", "prompt_file": "mp-dock.md", "role": "minimal_write", "cwd": "<tree of mp-dock>"}]
```

State the cost first ([costs.md](costs.md), "Minimal port"). Each writer works with no cargo, from `mp-writer`'s item list. The items, with the mechanism of each:

| Item | Mechanism |
|---|---|
| Runtime host | The four hooks in the app's `eframe::App`: `install` in the creator, `before_input` in `raw_input_hook`, `close_path` last in `logic`, `before_ui` first in `ui`. `InstallSpec::new(ShellInfo, window system)`. `FrameInput` with a `RootEnv` carrying the app's theme mode, scale and interface direction, a `Host` for the app name, and command overrides that unbind framework bindings the app uses itself (F6 and Shift+F6 where it binds F6). Fonts go through `craft_ui::fonts::load`, so there is one writer of the font stack. The web shell and the test harnesses use `install_headless`. |
| Close | The unsaved-changes question decides in the `embed::logic` closure (`Close` or `Hold`), or the app's own logic queues `CancelClose` before it. `with_close_requested_on_terminate` is gone. |
| Input review | Every site of the report's `input` item: Escape read without app focus moves to the window's `Intent::Cancel` (`escape_pressed`, `take_window_cancel`, or `runtime::keys::with_window_intents` last in the UI); Tab-toggles-chrome through `RootEnv::tab_toggles_chrome` and `FrameOutput::chrome_toggles`; keyboard zoom through `RootEnv::scale`; the canvas registered with `host_canvas` each pass. |
| Dock | `DockArea::new(label, Bind<Arc<Workspace>>, &Tracked<specs>, &mut impl DockPanels, DockConfig)`. The saved fields stay the source of truth beside a live `Arc<Workspace>`, so the file format, menus and workspaces stay unchanged. The `ui.dock` command vocabulary becomes app-local, mapped onto next's `actions` and `move_actions`. Bodies and the group view run with the app's style. |
| Dock model | next's types are `#[non_exhaustive]`: constructors (`Node::split`, `Column::new().with_width`, `Floating::single`, `Action::...`) instead of literals, `..` in patterns, `Workspace` accessors (`layout()`, `hidden()`), `Rect` instead of `[f32; 4]`, floating windows as one column. |
| Dialogs | `UpdateCheckDialog` and `Updater::run` on a `DialogHost` the app owns, run once per pass after the app's UI. The shortcuts dialog is `craft_menu::shortcuts::ShortcutsDialog` (`show(ui, ..)`). |
| Title bar | Where the app draws its own, `shell::TitleBar` with the app's menus and tools in its slots. The runtime's window host owns the move area and the hit test. |
| Removed helpers | App-local: the capture slot, a header menu on `egui::Popup::menu`, the old icon-button painter where the app needs its own colours, `WidgetVisuals` set directly instead of `WidgetPalette`, a local `split_rect`. |
| Keymap | `Dispatcher` becomes `craft_keymap::Matcher` fed from egui key events, with the same contract (press order, consumed presses, clipboard chords). |
| Tests | Runtime installed (`install_headless`) in every harness that runs the app's UI. Tests of removed renderer internals (hit ids, divider geometry, the old renderer's drags) are deleted with a reason in the report. The app's own behaviour tests (layout, commands, persistence) are kept and adapted. |

Each writer reports a cause it suspects in craft-libs instead of working around it silently ([Framework fixes](#framework-fixes)). The lead merges the writers' branches onto the port branch before the first compile.

## 5. Compile rounds

```sh
tools/compile-gate mp-c1 --app-only
```

Send each writer the errors in its files with `mp-compile-fix` through `swarm.py --follow-up <task> <packet>`. Errors in a file neither writer owns go to the host writer. Repeat until the app compiles: one compile per round, never one per writer.

**Web shell.** When the app has one, run `cl cargo check -p <web crate> --target wasm32-unknown-unknown --bins --tests` once the host compiles. This is the one exception to the no-`--bins` rule ([11-build-loop.md](11-build-loop.md)). A plain check misses wasm-only code, and the wasm target builds in its own directory, so it does not disturb the host build's resolution.

## 6. Test rounds

```sh
tools/test-run mp-t1 --app
```

Send each writer its failing tests with their panic lines through `mp-test-fix`. The fixers write code first and add `DIAG ` prints where unsure; one confirming run follows per round. A test that fails at the baseline is not the port's. The rounds end when no test fails beyond the baseline, or when each remaining failure is a framework fix in flight, named in the report.

## Framework fixes

A fault in craft-libs `next` found during a minimal port is fixed in craft-libs `next`, not in the app.

1. **Who finds it.** A writer or fixer names a suspected framework cause in its report (file and line in craft-libs, the evidence, the app symptom). The lead finds others in the run step.
2. **Who decides.** The lead reads the cause in the framework source. A real framework fault becomes task `mp-fw-<n>`, briefed from [prompts/p8-task-brief.md](../prompts/p8-task-brief.md): the fix goes to `next` as its own PR, with a behaviour test in the framework crate.
3. **The repin.** Once the fix merges, the app moves its pin to the merge commit: set `plan.base`, run `tools/minimal-port repin --apply` (and `rewrite`, which normally finds nothing), and run the next compile and test round on the new pin.
4. **The fallback.** An app-side workaround is allowed only when the fix cannot land before the app's PR. Record it in the report's findings table with the PR it waits for, and remove it at the repin that brings the fix.

The other steps go on while a fix is in flight. Only the run step and landing wait for the repin.

**Known fixes.** These came from the trials and are being fixed in `next`. Check that your pin includes each fix (its PR is merged at or before `plan.base`). For a pin without the fix, use the fallback:

| Finding | Symptom | Fallback for a pin without the fix |
|---|---|---|
| Alt+digit on a host canvas | On Windows and Linux, the runtime's Alt+numpad code entry takes every Alt+digit (egui cannot tell keypad digits from the top row), so app shortcuts such as Alt+1 to Alt+4 never arrive | None in the app: list the dead shortcuts as a visible difference |
| Dock style in panel bodies | Panel bodies and the group view inherit the dock's egui style (spacing), so the app's own code lays out differently than outside the dock | Give bodies and the group view the app's own style (`app_style`) |
| Ctrl+wheel folding | Off macOS, a smooth Ctrl+wheel arrives as `Event::Zoom`, so the app's own Ctrl-scroll handling does not run | Treat the zoom event as the Ctrl-scroll where the app checks its own synthetic input; note the zoom rate |

**Known differences at `next` b436ae9925** (check whether they still hold at your pin; each is a framework fix or a listed difference, never a silent workaround):

- `with_close_requested_on_terminate` is gone: check that Dock Quit and Cmd+Q on macOS still ask to save changes.
- The dock has no `Workspace::reset`, no raise for floating windows, and no hit list for inspection.
- The dock's and dialogs' words come from the `Host`'s i18n. Without one they show in English.
- The update dialogs show no app icon.
- `craft_ui::fonts::load` called during a pass asks for a discard pass, so the UI draws in the first frame. Tests that wait a frame for fonts change.
- next's icon button takes no app colours: apps keep their old painter app-locally until their full port.

## 7. Run the app

Nothing merges before the app has run. After the test rounds, build and launch the real app at the port branch's head, on every platform of `minimal.run_platforms`. Before you start, check that the pin includes every framework fix the port needed.

- **Linux.** Use the look tooling ([tools/look.md](../tools/look.md)). Production is the app built at `plan.app_base` (`look.production_binary`) and the port is the app built at the port branch (`look.port_binary`). Set up `look.driver` from the example driver, and write one states file for the checklist states the app's control channel reaches. `tools/look pair <States> --side both` captures both sides into one compare page; that page gives the before and after screenshots for the report. Check the rows the control channel cannot reach (real drags, the platform quit) by launching the port under the same display and driving it by hand, or hand them to a platform the developer runs.
- **macOS.** Send the developer the commit, the build and launch commands, and the checklist. They run it on their machine and answer each row.
- **Web.** Build the web shell and open it in a browser, with the same checklist rows that apply.

Checklist (one row per item; a row that fails is a bug for the writer, or a framework fix):

| Area | Check |
|---|---|
| Start-up | The app starts; a saved layout from the old version loads with every panel in place |
| Dock | Drag a tab and a group; float a panel; close and reopen it; reset the layout; quit, restart, and the layout is as left |
| Dialogs | The update check dialog opens and closes; the shortcuts dialog opens, assigns a key and saves; every other dialog the port moved |
| Keys | Escape in the canvas and in dialogs; Tab and Shift+Tab; F6 and F10; Alt+digit shortcuts; zoom keys; each app shortcut the report names as colliding with a framework binding |
| Close | Closing the window with unsaved changes asks to save; so does the platform quit (Cmd+Q and Dock Quit on macOS) |
| Look | Panel contents look as before; the dock chrome differs only as the report lists |
| Web | The web build starts and the rows above that apply pass |

Record each platform's result for the commit that ran:

```sh
tools/track event run "linux: checklist passed" --task mp-run --data platform=linux --data sha=<commit> --data result=pass
```

A failed row is `result=fail`, with the row in the text. The landing gate ([step 8](#8-report-and-land)) refuses the app until every platform of `minimal.run_platforms` has passed for the commit it lands. The app's PR stays a draft until then.

## 8. Report and land

1. **Report.** The writers fill `templates/minimal-port-report.md` and the lead completes it: size (files and lines, with and without tests), per item what changed, behaviour differences, deleted tests with reasons, the framework findings table (fix PR or fallback), the run results with screenshots, and the PR text.
2. **Land.** `tools/land/land-app.sh <app tree> <port branch> <plan.base>`. It runs the run gate (`land/exit-gate.py`), scans and scrubs the range, checks the pin, and runs `cl check all` in a clean clone. It prints the push command and never pushes. The developer pushes and opens one PR per app, pinning `next` by rev. The PR text lists the visible differences and links the framework PRs; it carries no AI attribution.
3. **Order with the framework.** craft-libs `next` merges into main only after every app that had a minimal port has passed its run step.

## Exit

- [ ] The sites report's items are all done or named in the report.
- [ ] The app compiles; the web shell passes the wasm check where there is one.
- [ ] No test fails beyond the baseline, or each failure is named in the report with its framework fix.
- [ ] Every framework fix the port needed is merged and in the pin, or recorded as a fallback with its PR.
- [ ] The run passed on every platform of `minimal.run_platforms` for the commit that lands.
- [ ] The report is complete; the landing scan is clean; the PR is open and marked ready.

# look: production and port, state by state

`tools/look` captures every state of a panel or dialog in the app's production build and in the port, and writes one static compare page per panel. Phase 0 sets up the driver and production ([process/01-setup.md](../process/01-setup.md), step 6a), phase 1 writes a states file as each map section is accepted ([process/02-inventory-and-map.md](../process/02-inventory-and-map.md), step 7), the build loop captures pairs whenever the port compiles, and phase 8 ([process/09-look-and-behaviour.md](../process/09-look-and-behaviour.md)) judges every pair and fixes what differs. The lead judges each pair image by image, each at its own size ([Judging at full size](#judging-at-full-size)).

It builds nothing. The build loop builds the port; production is built once with the control hooks.

## Contents

- [Commands](#commands)
- [What a run writes](#what-a-run-writes)
- [The compare page](#the-compare-page)
- [Judging at full size](#judging-at-full-size)
- [look calibrate](#look-calibrate)
- [States files](#states-files)
- [States from the map](#states-from-the-map)
- [The differences file](#the-differences-file)
- [look brief](#look-brief)
- [The phase gate](#the-phase-gate)
- [Driver interface](#driver-interface)
- [Helpers for drivers](#helpers-for-drivers)
- [Dashboard events](#dashboard-events)
- [Config keys](#config-keys)
- [Requirements](#requirements)

## Commands

`--config PATH` before the command picks a port.toml; otherwise the usual resolution applies (`PORT_KIT_CONFIG`, `./port.toml`, a parent directory).

| Command | What it does |
|---|---|
| `look pair PANEL... [--side up\|port\|both] [--only ID,...]` | Captures the panels and writes their pages. Production (`up`) and the port run at the same time, each in its own app instance. Panels run one after the other. |
| `look pair --all` | The same for every states file in `look.states_dir`. |
| `look crops PAGE... [--threshold N] [--gap N] [--pad N] [--max N]` | Recomputes the difference images and region crops of existing pages and redraws them. Captures nothing. `PAGE` is a panel name or a page directory. |
| `look states AREA SECTION [--panel NAME] [--theme NAME] [--force]` | Writes the states of one area map section into a states file. |
| `look calibrate [--side up\|port\|both]` | Reports the scale of each side's capture, the fonts each build embedded and production's revision against the installed release, before any pair is trusted ([look calibrate](#look-calibrate)). |
| `look brief CLASS [--force]` | Writes a look fixer's brief for one class of differences ([look brief](#look-brief)). |

`--side up` or `--side port` captures one side only; the other side keeps its images from the last run, marked with that run's time. `--only` captures some states; the others keep theirs the same way. States with a `needs` field are listed on the page and never captured.

`crops` options: `--threshold` (default `look.threshold`) is the channel difference above which a pixel differs visibly; differing pixels closer than `--gap` (12) join one region; each region grows by `--pad` (6) pixels; at most `--max` (20) crops per state.

Exit codes: `0` every state captured; `1` a capture failed (the page shows the error); `2` a usage, config, states-file or differences-file error.

## What a run writes

| Path | Content |
|---|---|
| `<track.out_dir>/look/<Panel>/index.html` | The compare page |
| `<track.out_dir>/look/<Panel>/up-<state>.png`, `port-<state>.png` | Shots cropped to the panel (the states file's `crop`) |
| `<track.out_dir>/look/<Panel>/full-up-<state>.png`, `full-port-<state>.png` | Full-window shots |
| `<track.out_dir>/look/<Panel>/diff-<state>.png` | The difference image |
| `<track.out_dir>/look/<Panel>/crop-<state>-<n>.png` | One region that differs, at the capture's own pixels: production left and port right, or production above and port below when side by side does not fit in `look.reader_max_px`. A region larger than that is cut into tiles, one crop each. |
| `<track.out_dir>/look/<Panel>/crops.txt` | Each state's result and its regions with their boxes, largest first, for agents that read text |
| `<track.out_dir>/look/<Panel>/manifest.json` | What the page shows: sides with build time, port commit and capture scale (`scale`: image pixels per window pixel), every state's images, errors and differences. Each state's `port` entry carries `head`: `{"app": sha, "framework": sha, "dirty": bool}`, the HEAD of both integration trees when the run started, which the phase gate compares with the trees' current HEAD. `look crops` redraws the page from it. |
| `<track.out_dir>/look/index.html` | Every panel with its counts and the time of its last run |
| `<look.run_dir>/<Panel>/<side>/` | Each app instance's work dir (its log is `app.log`) |
| `<look.run_dir>/procs/<pid>.json` | One record per Xvfb server and app a run started (`portkit.look.display` and `control.launch` write it, `Display.stop` and `App.quit` remove it) |

`look pair` and `look calibrate` start by stopping the processes of earlier runs that died (records whose `look` process is gone) and by emptying every work dir no live process uses, except its `app.log` and `shots/`. A killed capture therefore leaves no display, app or session directory after the next start.

Pages go under the dashboard's output directory, so they are served the same way as the dashboard (tools/track.md, "Viewing the page"). They read the dashboard's stylesheet, follow the light or dark setting, work at phone width, and also work opened as files.

## The compare page

The head shows the counts: states, match, differ, failed, not captured. Under it, each side's build (binary build time; for the port, the integration tree's commit and whether it had local changes) and when it was captured.

A table lists every state with its result:

| Result | Meaning |
|---|---|
| `match` | Same size, and no pixel differs by more than the threshold |
| `differs` | Some pixels differ visibly, or the sizes differ |
| `failed` | A side's driver raised an error; the page shows it |
| `partial` | Only one side has a shot |
| `waiting` | The state has a `needs` field and is not captured |

Each state then shows production, port and the difference image side by side, and the crops of its regions. The view buttons switch every state to side by side, blink (production and port alternate in one frame) or difference only; the choice is remembered in the browser. Every image links its full-window shot. A match by the numbers is not acceptance: the lead looks at every pair at full size (process/09, step 2).

## Judging at full size

An agent's image reader shrinks every image whose longer edge is over `look.reader_max_px` (default 1568), and a shrunk image hides the differences acceptance looks for: icon sizes, stroke weights, text weight. So acceptance, by the lead or a fixer, follows these rules:

- Read one image at a time: one region crop per region, at the capture's native scale. `look pair` cuts every crop to fit the limit.
- Read a production, port or difference image only when it fits the limit. `look brief` marks larger ones `page only`; judge those states from their crops.
- Never judge from a montage, a contact sheet, strips stacked into one image, or a downscaled page. They are for showing the developer.
- Know the scale. Sizes in a crop are image pixels; `look brief` names how many image pixels one interface pixel is on each side. Two sides at different scales do not compare: run `look calibrate`.

## look calibrate

`look calibrate [--side up|port|both]` reports three facts before any pair is trusted, and writes them to `<look.run_dir>/calibrate.json`. Without `--side` it takes every side whose binary exists. It starts each side through the driver once and shoots the app as it opens, at `look.window`.

| Fact | Read from | A problem when |
|---|---|---|
| Scale of each capture | The shot's size against the window | The two sides' scales differ, or width and height scale differently |
| Fonts of each build | The craft-fonts build-script output cargo keeps beside the binary (`<profile dir>/build/<package>-<hash>/output`): the checkout it read and its `craft-fonts:` warnings, among them "has no interface face (role `ui`)" | A side built with no interface face or no craft-fonts checkout, or the sides embed different fonts. `unknown` (no such output) is reported, not a problem. |
| Production's revision | `git describe` of the tree that holds `look.production_binary` (else `app.production`), against `look.installed_version` | `look.installed_version` is not set. A revision difference is reported, not a problem: tell the developer that differences between their installed app and the port may be production's own changes. |

It prints one line per side, the build warnings, the revision and each problem. Exit `0` with no problem, `1` with one, `2` for a usage or config error. It posts one `look-calibrate` event on the task `setup-look`. Run it in phase 0 for production (`--side up`) and again once the port first builds ([process/01-setup.md](../process/01-setup.md), step 6a).

The difference image is the port shot in dim grey, red where a channel differs by more than the threshold, and dark amber where it differs less. Shots of different sizes are compared over their shared area, and the rest counts as differing.

## States files

One JSON file per panel or dialog, `<look.states_dir>/<Panel>.json`. The panel name is also the page's name and the dashboard task's (`look-<Panel>`).

```json
{
 "title": "Layers panel",
 "size": {"width": 1440, "height": 900},
 "theme": "pro",
 "crop": [1150, 374, 1440, 880],
 "setups": {"sample": [{"method": "engine.execute", "params": {"command": "file.new", "params": {}}}]},
 "reset": [{"method": "ui.key", "params": {"key": "Escape"}}],
 "states": [
  {"id": "sample", "title": "Sample document", "setup": "sample", "steps": []},
  {"id": "group-open", "title": "Group open", "setup": "sample",
   "steps": [{"method": "engine.execute", "params": {"command": "layer.groupLayers", "params": {}}}]},
  {"id": "drag-preview", "title": "Drag preview", "steps": [], "needs": "CH-4", "note": "needs a held press"}
 ]
}
```

| Field | Where | Meaning |
|---|---|---|
| `title` | file | The page title |
| `size` | file, state | Window size. Default: `look.window`. |
| `theme` | file, state | Theme the driver sets before the state's steps. Absent: the driver leaves the theme alone. |
| `crop` | file, state | `[x0, y0, x1, y1]` in pixels of the full-window shot: the panel's area. `null` or absent: the whole window. |
| `setups` | file | Named step lists for what a state needs but does not show (a sample document, a fixture). |
| `reset` | file | Steps sent before every state, so no state depends on the one before. |
| `id` | state | Lowercase letters, digits, `.`, `_`, `-`; unique in the file. Used in file names. |
| `title` | state | What the state shows |
| `setup` | state | A name from `setups`, or a step list. The driver runs it when it differs from the setup it ran last in that app instance. |
| `steps` | state | The requests that reach the state. An empty list is the panel as it opens. |
| `up_steps`, `port_steps` | state | Replace `steps` on one side, where production needs other requests to reach the same state. Prefer one list for both: a difference here is a difference the comparison cannot see. |
| `needs` | state | The state is not captured yet: a missing control hook (`CH-n`), `steps` (the map gave none), or a setup to write. |
| `note` | state | Free text shown with a waiting state |

A step is one control request, `{"method": ..., "params": {...}}`, in the app's own method names. `{"method": "@sleep", "params": {"seconds": 2}}` waits instead. This is craft-libs `docs/porting.md` "States file" plus setups, reset, crop and needs.

`look pair` refuses a states file with an unknown setup name, a named setup that is still empty, a repeated id or a step without a method, and names the problem.

## States from the map

`look states AREA SECTION` reads the area's map (`[[areas]]` `map`, else `<work.maps>/<AREA>.md`), finds the section by id (`## A4. Name` or `### A4 Name`, case-insensitive) and reads its **States** field:

- JSON state objects in the field (`{"id": ..., "title": ..., "steps": [...]}`, alone or in a list) are taken as they are.
- Otherwise each list item, or each `;`-separated part, is one state. Its id is a leading `` `id` `` or the words before a colon, else the first words of the text. A JSON step list in the item (`[{"method": ...}]`) becomes its steps; `setup: "name"` its setup.
- An item that names a missing hook (`CH-n`) gets `needs: "CH-n"`. An item without a step list gets `needs: "steps"`, except `default`, the panel as it opens.
- A setup name the file does not define yet is added to `setups` as an empty list, and the command says so.

The file name is the framework panel or dialog type the section's **Framework** field names (the first backticked type ending in `Panel` or `Dialog`, else the first backticked type), else the part name in CamelCase; `--panel` overrides it. States whose id is already in the file are kept as they are, so hand edits survive; `--force` replaces them. New states are added, so several sections on one panel share one file. Each state records its section in `map`.

Read every generated file against its map section before the first `look pair`, and fill in `crop`, the setups and every `needs: "steps"`.

## The differences file

The lead writes every look difference it judges into one file, `look.differences` (default `<work.dir>/look/differences.md`), as rows of a Markdown table. `look brief` and the phase gate read it; other text in the file is free.

```markdown
| Panel | State | What differs | Judgement | Cause | Class | Outcome |
|---|---|---|---|---|---|---|
| LayersPanel | structure | row height 28, production 32 | production better | ListRow default height | row-height | fix |
| LayersPanel | sample | focus ring 2 px, production 1 px | port better | one focus ring for every component | - | kept: the framework's one focus ring |
```

| Column | Holds |
|---|---|
| Panel, State | The states file's name and the state's id, as on the compare page |
| What differs | The region and what it shows, with sizes where they are known |
| Judgement | `production better`, `port better`, `both: <target look>`, or `unclear` while you decide by the rules |
| Cause | The likely shared cause: one token, one default, one mechanism |
| Class | The fix class (lowercase letters, digits, dashes), whose task is `look-fix-<class>`; `-` for none |
| Outcome | `fix` while a class task works on it; `fixed` once a new pair shows it fixed; `kept: <reason>` for a difference that stays, with the reason the rules give |

Rows are per state, not per region: region numbers change with every capture. A state may have several rows, one per difference.

## look brief

`look brief CLASS` writes `<work.dir>/briefs/look-fix-<CLASS>.md` for the agent that fixes one class. It takes the rows of that class whose Outcome is `fix`, and for each state they name:

- the map section the state comes from (the state's `map` field) and that section's **Look reference** field;
- the capture scale of each side (from the page's `manifest.json`);
- the files of its last pair with their sizes: production, port, the difference image (`page only` when larger than `look.reader_max_px`), and every region crop with its box and pixel count (`crops.txt` has the same list as text), plus a `look crops --max` call when a state has more regions than crops;
- the rules that decide (`rules/porting-rules.md`, "Look" and "Old look or standardized look"), and the acceptance rules of [Judging at full size](#judging-at-full-size);
- the fixer's own call per panel: `look pair <Panel> --only <ids>`.

That text fills `{{LOOK}}` in the Look evidence section of `prompts/p8-task-brief.md`, rendered with `TASK=look-fix-<CLASS>`; the file holds the brief block only. The lead fills the fields marked `<...>` (worktree, model, Goal, Reference, Mechanism, Start here) before the agent starts. An existing brief is kept unless `--force`, since the lead may have filled it. It exits 2 when no row of the class has Outcome `fix`.

## The phase gate

`track phase` runs the look rows of `PHASE_EXITS` in `tools/portkit/gates.py` ([tools/track.md](track.md), "The phase gate"):

| Exit of | Row | Passes when |
|---|---|---|
| 0 | The look driver and the production build with its control hooks exist | `look.driver` and `look.production_binary` name files |
| 0 | look calibrate passed on the current production build | `<look.run_dir>/calibrate.json` has the production side of the current `look.production_binary` (same path, size and time) and no problem |
| 1 | Every map section has a states file | Every section of every area map has a **States** field, and every section whose field is not `none` is named by a state's `map` field in `look.states_dir` |
| 1 | Production reaches every state | Every state has no `needs` and a production shot without an error (`look pair --all --side up`) |
| 8 | Every map section has a states file | As at exit 1 |
| 8 | Every state has a pair from the current port head | Every state has both shots, no error and no `needs`, and its port `head` equals the current HEAD of both integration trees, without local changes |
| 8 | Every difference is fixed or has its reason in the differences file | Every state whose pair differs has a `kept: <reason>` row and no `fix` row |
| 8 | The lead accepted every panel | Every `look-<Panel>` task is `done` |

The landing tools run the four phase 8 look rows too (`tools/land/exit-gate.py`, with the tests rows, [process/10-land.md](../process/10-land.md)). The one override for both is `track phase 9 --force "reason"`, recorded as a decision: the landing tools pass when that decision covers every row that fails at landing time.

## Driver interface

A driver is one Python file per app, named by `look.driver`. `look pair` loads it and calls, for each side in its own thread:

```python
def start(side, binary, workdir, window): ...      # -> app (any object)
def shoot(app, side, state, window, out_png): ...  # once per state, in file order
def stop(app): ...                                 # always called, also after an error
```

| Argument | Value |
|---|---|
| `side` | `"up"` (production) or `"port"` |
| `binary` | `look.production_binary` or `look.port_binary` |
| `workdir` | `<look.run_dir>/<Panel>/<side>/`, created and kept between runs; `look` empties it (except `app.log` and `shots/`) at the next start. The driver may clear what it owns in it. |
| `window` | `[width, height]`: the first state's window in `start`, the state's in `shoot` |
| `state` | The state resolved for the side: `id`, `title`, `steps` (this side's), `setup` (a step list, empty when none), `setup_key` (a string naming the setup, or `None`), `reset`, `theme`, `window`, `crop`, and every other field of the state |
| `out_png` | Where `shoot` writes the full-window PNG |

Rules:

- `shoot` raises on any failure. `look pair` records the error on that state and goes on with the next; an error in `start` fails every state of that side.
- `shoot` leaves no state behind that the next state's reset does not clear: a dialog it opened is closed by the reset or by the next `shoot`.
- The driver owns the display. On Linux it runs each instance headless, on its own display; on macOS the app opens a normal window. Both sides run at once, so nothing may be shared between two instances (config dirs, theme stores, ports, display numbers).
- Keep `shoot` in this order: setup when `setup_key` changed, reset, window size, theme, the state's steps, a short settle, the screenshot. One states file then drives both apps the same way.

`examples/photocraft/look-driver/driver.py` is a complete driver, with notes on what is PhotoCraft's own.

## Helpers for drivers

The kit's `tools/` directory is on the import path while `look` runs a driver.

`portkit.look.control`: the craft-automation control channel (one JSON request per line, `{"id", "method", "params"}`; one reply per line, `{"id", "ok", "result" | "error"}`; `auth {token}` first).

| Helper | Does |
|---|---|
| `launch(side, argv, workdir, env=None, token_file=None, token=None, ready=LISTENING, timeout=120)` | Starts the app in its own process group with its output in `<workdir>/app.log`, waits for the `control server listening on 127.0.0.1:<port>` line, reads the token, connects and authenticates. Returns an `App`. |
| `App.call(method, params)` | One request; returns its result, raises `ControlError` on `ok: false` |
| `App.quit()` | `app.quit`, then kills the process group if it is still running after 15 s |
| `App.extra` | A dict for the driver's own state (the setup that last ran, the display) |
| `run_steps(app, steps)` | Sends each step; handles `@sleep` |
| `screenshot(app, name, write_root, out_png, params=None)` | `ui.screenshot {path: name}` (relative to the folder the app lets automation write to), waits until the file is complete, moves it to `out_png`; returns the reply (`width`, `height`) |

`portkit.look.display.Display(screen="1920x1200x24")`: `start()` runs a private Xvfb on Linux and returns `{"DISPLAY": ":<n>"}` to add to the app's environment; Xvfb picks a free display number itself, so instances started at once never collide. Elsewhere it returns `{}` and the app uses the desktop. `stop()` ends it.

## Dashboard events

- Each panel of a `look pair` run posts one `look` event on the task `look-<Panel>`: `look ok|failed (<duration>): <Panel>: <n> states, <d> differ, <m> match, <f> failed, <w> not captured`, with the counts in its data and the page as its `page` link, relative to `track.out_dir`. It is `failed` when any capture failed. The event creates the task when it is new and never changes its state: the lead moves it (process/09).
- `look states` posts a `look-states` event on the same task with the state count and the states file as its `states` link. Running it puts the panel's task on the board.
- `look calibrate` posts a `look-calibrate` event on the task `setup-look`: the scale of each side and the problem count, with `calibrate.json` as its `report` link.
- `look brief` posts a `look-brief` event on the task `look-fix-<CLASS>` with the brief as its `brief` link, which puts the class's task on the board.

## Config keys

The `[look]` section of port.toml; [process/config.md](../process/config.md) has the full table.

| Key | Default | Meaning |
|---|---|---|
| `driver` | unset | The app's driver file |
| `states_dir` | `{work.dir}/look/states` | States files |
| `run_dir` | `{work.dir}/look/run` | App instances' work dirs and the last run's full-window shots |
| `production_binary` | unset | Production built with the control hooks (side `up`) |
| `port_binary` | unset | The port's binary in the app integration tree's target dir (side `port`) |
| `window` | `1440x900` | Window size for states files that name none |
| `installed_version` | unset | The release the developer runs (a tag, a version, a commit, or `none`); `look calibrate` compares production with it |
| `reader_max_px` | `1568` | The longest edge the agents' image reader keeps unscaled; crops fit it |
| `threshold` | `16` | Channel difference (of 255) above which a pixel differs visibly |
| `differences` | `{work.dir}/look/differences.md` | The differences file |

## Requirements

- Python 3.11 or later.
- Pillow and numpy for `pair` and `crops`. Without them, `look` runs itself again under `uv run --with pillow --with numpy` when `uv` is installed; otherwise it says to install them. `states`, `calibrate` and `brief` need neither.
- On Linux, `Xvfb` for drivers that use `Display` (Debian and Ubuntu: package `xvfb`). Rendering without a GPU needs a CPU Vulkan or GL driver (Mesa's lavapipe or llvmpipe); the PhotoCraft driver uses lavapipe when it is installed.

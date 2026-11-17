# Phase 8: look and behaviour

Phase 8 compares the port with production, state by state, and fixes what differs. Tests check behaviour, but none of them looks at the screen: a port can pass every test and still look and work worse than the app it replaces. Every state the area maps list is captured in production and in the port, side by side at the same size and theme, and the lead accepts each pair by looking at it.

| | |
|---|---|
| Starts when | The last build batch passes its red rounds ([08-tests-and-red-rounds.md](08-tests-and-red-rounds.md)). |
| Ends when | Every map section's states are captured in both apps and accepted by the lead; every new framework component is compared through its gallery story; behaviour is driven through every action on the maps. |
| Agents | One agent per component class of differences (a one-off task with a build tree). |
| Builds | Incremental builds of the port in the app integration tree; production built once. |
| Output | States files in the `[look]` states directory; compare pages under `<track.out_dir>/look/<Panel>/`; fix branches merged onto the port branch. |

Record the phase: `tools/track phase 8 "look and behaviour"`.

The rules that decide every judgement in this phase are in [rules/porting-rules.md](../rules/porting-rules.md): "Look" and "Old look or standardized look". Read them before judging a pair.

## How captures work

Both apps are driven through the app's control channel (craft-automation): a request queue in the app that accepts input methods (`ui.click`, `ui.key`), the app's own state methods (open a panel, pick a tool, set the theme, resize the window) and `ui.screenshot`. craft-libs `docs/porting.md`, "6.4 Compare old and new", documents what the library provides and what the app adds, with code for exposing the channel. Read it there; this page does not repeat it.

`tools/look` runs the comparison (`tools/look.md` has the full reference):

| Command | What it does |
|---|---|
| `look pair <Panel>... [--side up\|port\|both] [--only <id>,...]` | Launches production (`up`) and the port at the same time through the app's driver, drives every state in the panel's states file, captures each in both, and writes a static compare page (production and port per state, with blink and difference views) plus crops of the regions that differ. Default: both sides. `--all` takes every states file. It builds nothing; the build loop builds the port first. |
| `look crops <Panel>` | Recomputes the differences and region crops of an existing page (for example with another `--threshold`). Captures nothing. |
| `look states <area> <section>` | Writes the state list of one area map section into the panel's states file, and puts the panel's task `look-<Panel>` on the board. |

The **driver** is a Python file per app with three functions, `start(side, binary, workdir, window)`, `shoot(app, side, state, window, out_png)` and `stop(app)`. It owns the headless display (its own Xvfb per instance on Linux, a normal window on macOS). The kit's `portkit.look.control` (launch, requests, screenshots over the control channel) and `portkit.look.display` (the Xvfb helper) do most of the work. `examples/photocraft/look-driver/` is a worked driver. Its settings are the `[look]` keys in `port.toml`: `driver`, `states_dir`, `production_binary`, `port_binary`, `window` and `threshold` (`tools/look.md`).

Pages go under the dashboard's output directory (`<track.out_dir>/look/<Panel>/`, with `look/index.html` listing every panel), so the developer opens them the same way as the dashboard. Each `look pair` run posts a `look` event with the counts and the page link on the panel's task; it never changes the task's state.

## Step 1: give production its control hooks

Production must answer the same control methods as the port, or its states cannot be reached. The area maps list the missing hooks (`CH-n`).

1. In the app checkout, make a local branch from the production commit the port last merged (the commit `app.production` is at). Never push it.
2. Add the control channel and the methods the states need, following craft-libs `docs/porting.md` ("Expose the control channel in the app"). Keep the methods' names and parameters the same as the port's, so one states file drives both apps.
3. Build production once with the profile the comparison uses, and set `look.production_binary` to it. Rebuild it only when the hooks change.
4. Write the app's driver, starting from `examples/photocraft/look-driver/driver.py` (its README lists what to change), and set `look.driver` to it. Set `look.port_binary` to the port's binary in the app integration tree's target dir.
5. Check the setup on one small panel with one state: `look pair <Panel> --only <id>`. Both sides must reach the state; the page shows a driver error in place of the image.

Hooks change no behaviour of production. They only make its existing states reachable.

## Step 2: write the states files

1. For each area map section, run `look states <area> <section>`. It writes the section's states into the panel's states file (`<look.states_dir>/<Panel>.json`): one state per `id`, with a `title`, an optional `setup` (things the state needs but does not show, such as a sample document, named in the file's `setups`) and the `steps` that reach the state, each one control request (`{method, params}`). The file's head gives the window size, theme, the panel's `crop` and the `reset` sent before every state, so both apps render alike. Sections on one panel share its file. The format is craft-libs `docs/porting.md`, "States file", plus setups, reset, crop and needs (`tools/look.md`, "States files").
2. Read each file against its map section: every state the section lists, every named variant, the empty, mixed and long-text cases the map names. A state that leaves a dialog open ends by closing it, or the reset closes it.
3. Fill in what the map could not give: the panel's `crop`, the steps of each named setup, and the steps of every state marked `needs: "steps"`. A state marked `needs: "CH-n"` waits for its hook (step 1); remove the `needs` field once the hook exists. `look pair` skips every state with `needs` and lists it on the page as not captured.
4. `look states` puts the panel's task on the board (`look-<Panel>`, state `todo`).

## Step 3: compare new framework components through their story

A component the port added to the framework has no production counterpart as a component: production drew that part of the screen with its own code. Compare it in two places:

- **Its gallery story.** Render its stories (`cl render <crate> <Component>`) and check every state and named variant there: shapes, colours, borders, glyphs and parts against the production part it replaces, and against neighbouring framework components for consistency (one focus ring, one selection fill, one disclosure glyph). The story is the reference for the component on its own, and the place its fixes are checked.
- **In the app.** Its map section's states show it in place, in the pair, next to the parts around it.

A component without a story that renders cannot be accepted: send it back to the set that added it ([07-review-combine-compile.md](07-review-combine-compile.md), step 7).

## Step 4: capture and look

1. Build the port in the app integration tree (an incremental build after the last merge), then run `look pair --all` as one background task. Each panel's run posts its page link on its task; `look/index.html` under the dashboard's output directory lists every panel with its counts. `crops.txt` in each page directory lists the differing regions as text, for agents.
2. Look at every pair yourself, at full size: text face and placement, sizes, colours, surfaces, alignment, overlap. An agent's summary or a difference score is not a check.
3. Judge each difference on its own, by the rules: production better, port better, both need work (name the target look), or unclear (yours to decide by the rules; a layout or design question never goes to the developer).
4. Sample broadly before fixing anything: every area and every framework crate the port touched, plus a random sample, never a top-N list of the largest differences. Write each difference as one line in `<work.dir>/look/differences.md`: panel, state, what differs, the judgement, and its likely cause.

## Step 5: fix by class

Group the differences by shared cause: one token read wrongly, one default that differs from the old library's, one mechanism every list uses. Each class becomes one fix for every component it affects.

1. Check that no scheduled set or task already owns the cause, and that the cause is not transitional (code a later set replaces). The class then becomes a one-off task.
2. Run `prompts/precheck.md` on its brief first, so the agent does not stop on a question you could answer now.
3. Write the brief from `prompts/p8-task-brief.md` (goal, the production reference values, the mechanism to build on, where to start, done-when) and put the task on the board: `tools/track status look-fix-<class> todo "<class>"`.
4. The agent writes its plan and stops (`rules/agent-common.md`, "Plan first"). Answer it with "go" or a correction before it edits.
5. It writes in a code-only tree, then takes a build tree to compile, run its trials and rerun `look pair` for every panel its class touches ([06-write.md](06-write.md), "Code-only trees for every writer").
6. Look at its pairs yourself. When they match, merge the fix onto the port branch, record it (`tools/track event merge "look-fix-<class>"`), and rerun `look pair` on the affected panels in the integration tree.

A component the developer flags is looked at by you, production and port side by side at full size, before its fix is briefed.

## Step 6: drive it like a user

Captures check what a state looks like. Behaviour needs every action the maps list done through the app the way a user does it: open, drag, type, undo, cancel, switch tools, dock and float panels, with mouse and keyboard. Script the actions as states files of input steps (`ui.click`, `ui.key`, the app's own methods) and run them in both apps with `look pair`: it compares the picture each action ends on. The kit has no tool that compares results beyond the picture (the document, the undo stack, the selection). Where an action's result is not visible, add a state that shows it (open the layers panel, the history panel), or ask both apps for it through their own state methods with `portkit.look.control` (`tools/look.md`) and compare the answers. Then use the port yourself for the flows the maps call central. A behaviour difference from production is a fix, judged like a look difference.

## Step 7: accept

A panel is accepted when every state's pair matches by the rules and every remaining difference has its reason written in `differences.md`. Record each acceptance: `tools/track status look-<Panel> done "accepted, <k> differences with reasons"`. Report to the developer what was compared (panels, states, what still differs), never only "done".

## Exit

- [ ] Every map section has a states file, and every state has a pair from the current port build.
- [ ] The lead looked at every pair; every difference is fixed or has its reason in `differences.md`.
- [ ] Every component the port added is compared through its gallery story and in its app states.
- [ ] Every action on the maps was driven through the app in both production and the port.
- [ ] Every fix is merged onto the port branch, and the tests still pass (one full run after the last fix: `tools/test-run look-final --app`).
- [ ] The developer has the report of what was compared.

Then record `tools/track phase 9 "land"` and go to [10-land.md](10-land.md).

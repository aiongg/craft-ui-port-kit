# Phase 8: look and behaviour

Phase 8 compares the port with production, state by state, and fixes what differs. Tests check behaviour, but none of them looks at the screen: a port can pass every test and still look and work worse than the app it replaces. Every state the area maps list is captured in production and in the port, side by side at the same size and theme, and the lead accepts each pair by looking at it at full size.

| | |
|---|---|
| Starts when | The last build batch passes its red rounds ([08-tests-and-red-rounds.md](08-tests-and-red-rounds.md)). |
| Ends when | Every map section's states are captured in both apps from the current port head and accepted by the lead; every new framework component is compared through its gallery story; behaviour is driven through every action on the maps. |
| Agents | One agent per class of differences (a one-off task with a build tree). |
| Builds | Incremental builds of the port in the app integration tree; production only when its hooks change. |
| Output | Compare pages under `<track.out_dir>/look/<Panel>/`; the differences file (`look.differences`); fix branches merged onto the port branch. |

Record the phase: `tools/track phase 8 "look and behaviour"`.

The rules that decide every judgement in this phase are in [rules/porting-rules.md](../rules/porting-rules.md): "Look" and "Old look or standardized look". Read them before judging a pair.

## What earlier phases set up

The look comparison does not start here. Phase 0 gave production its control channel, built it and wrote the driver ([01-setup.md](01-setup.md), step 6a). Phase 1 wrote a states file for every map section, added the missing hooks to production and checked that production reaches every state ([02-inventory-and-map.md](02-inventory-and-map.md), step 7). From the first compile on, `tools/cycle` builds the port with `look.port_build` and captures the pairs of the batch's states ([11-build-loop.md](11-build-loop.md)); set that key in phase 0, since `cycle` skips the look step without it, so most differences were seen and fixed while their sets were written. This phase closes what is left.

`tools/look` runs every comparison ([tools/look.md](../tools/look.md) has the full reference):

| Command | What it does |
|---|---|
| `look pair <Panel>... [--side up\|port\|both] [--only <id>,...]` | Drives every state of the panel's states file in production (`up`) and the port at the same time and writes the compare page (production and port per state, blink and difference views) plus full-size crops of the regions that differ. `--all` takes every states file. It builds nothing. |
| `look crops <Panel>` | Recomputes the differences and region crops of an existing page (for example with another `--threshold`). Captures nothing. |
| `look states <area> <section>` | Writes the states of one area map section into the panel's states file. |
| `look brief <class>` | Writes a look fixer's brief for one class of differences from the differences file. |

When production's hooks change (a state needs one more), rebuild production and set `look.production_binary` again. Hooks change no behaviour of production.

## Step 1: compare new framework components through their story

A component the port added to the framework has no production counterpart as a component: production drew that part of the screen with its own code. Compare it in two places:

- **Its gallery story.** Render its stories (`cl render <crate> <Component>`) and check every state and named variant there: shapes, colours, borders, glyphs and parts against the production part it replaces, and against neighbouring framework components for consistency (one focus ring, one selection fill, one disclosure glyph). The story is the reference for the component on its own, and the place its fixes are checked.
- **In the app.** Its map section's states show it in place, in the pair, next to the parts around it.

A component without a story that renders cannot be accepted: send it back to the set that added it ([07-review-combine-compile.md](07-review-combine-compile.md), step 7).

## Step 2: capture and look

1. Build the port in the app integration tree at the head you mean to land, then run `look pair --all` as one background task. Each panel's run posts its page link on its task; `look/index.html` under the dashboard's output directory lists every panel with its counts. Every pair the gate accepts comes from the current HEAD of both integration trees, so rerun after every merge.
2. Look at every pair yourself, at full size: the production, port and difference images and each region crop (production left, port right, at 2×). Check text face and placement, sizes, colours, surfaces, alignment and overlap. A contact sheet or a downscaled page is for showing the developer, never for acceptance; neither is an agent's summary or a difference score.
3. Judge each difference on its own, by the rules: production better, port better, both need work (name the target look), or unclear (yours to decide by the rules; a layout or design question never goes to the developer). Compare sizes with the section's **Look reference** field, which holds the old code's literal values.
4. Sample broadly before fixing anything: every area and every framework crate the port touched, plus a random sample, never a top-N list of the largest differences.
5. Write each difference as one row of the differences file (`look.differences`; format in [tools/look.md](../tools/look.md), "The differences file"): panel, state, what differs, the judgement, the likely cause, its class, and the outcome `fix`, or `kept: <reason>` when the rules keep it.

## Step 3: fix by class

Group the differences by shared cause: one token read wrongly, one default that differs from the old library's, one mechanism every list uses. Each class becomes one fix for every component it affects; its rows share one Class value.

1. Check that no scheduled set or task already owns the cause, and that the cause is not transitional (code a later set replaces). The class then becomes a one-off task.
2. Write the brief: `tools/look brief <class>` writes `<work.dir>/briefs/look-fix-<class>.md` from `prompts/p8-task-brief.md`, with its Look evidence filled: the class's rows, the Look reference of each map section involved, the full-size shots and crops of each state, the rules that decide, and the fixer's own `look pair <Panel> --only <ids>` calls. It puts the task `look-fix-<class>` on the board. Fill the fields marked `<...>`: goal, the production reference values, the mechanism to build on, where to start.
3. Run `prompts/precheck.md` on the brief, so the agent does not stop on a question you could answer now.
4. The agent writes its plan and stops (`rules/agent-common.md`, "Plan first"). Answer it with "go" or a correction before it edits.
5. It writes in a code-only tree, then takes a build tree to compile, run its trials and run its `look pair` calls ([06-write.md](06-write.md), "Code-only trees for every writer").
6. Look at its pairs yourself, at full size. When they match, merge the fix onto the port branch, record it (`tools/track event merge "look-fix-<class>"`), rerun `look pair` on the affected panels in the integration tree, and set the class's rows to `fixed`, or to `kept: <reason>` for what the rules keep.

A component the developer flags is looked at by you, production and port side by side at full size, before its fix is briefed.

## Step 4: drive it like a user

Captures check what a state looks like. Behaviour needs every action the maps list done through the app the way a user does it: open, drag, type, undo, cancel, switch tools, dock and float panels, with mouse and keyboard. Script the actions as states files of input steps (`ui.click`, `ui.key`, the app's own methods) and run them in both apps with `look pair`: it compares the picture each action ends on. The kit has no tool that compares results beyond the picture (the document, the undo stack, the selection). Where an action's result is not visible, add a state that shows it (open the layers panel, the history panel), or ask both apps for it through their own state methods with `portkit.look.control` (`tools/look.md`) and compare the answers. Then use the port yourself for the flows the maps call central. A behaviour difference from production is a fix, judged like a look difference.

## Step 5: accept

A panel is accepted when every state's pair matches by the rules and every remaining difference has a `kept: <reason>` row in the differences file. Record each acceptance: `tools/track status look-<Panel> done "accepted, <k> differences kept"`. Report to the developer what was compared (panels, states, what still differs and why), never only "done".

## Exit

- [ ] Every map section has a states file, and every state has a pair from the current port head.
- [ ] The lead looked at every pair at full size; every difference is fixed or has a `kept: <reason>` row in the differences file.
- [ ] Every panel is accepted (`look-<Panel>` is `done`).
- [ ] Every component the port added is compared through its gallery story and in its app states.
- [ ] Every action on the maps was driven through the app in both production and the port.
- [ ] Every fix is merged onto the port branch, and the tests still pass (one full run after the last fix: `tools/test-run look-final --app`).
- [ ] The developer has the report of what was compared.

Then record `tools/track phase 9 "land"` and go to [10-land.md](10-land.md). `track phase` runs the items a script can check and refuses while one fails ([tools/track.md](../tools/track.md), "The phase gate"); the landing tools run the same look items. When a look item cannot be met and the port must land anyway, record the decision with `tools/track phase 9 --force "reason"`; it is the one override, and the landing tools accept it.

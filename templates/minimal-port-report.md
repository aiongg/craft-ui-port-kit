# Minimal port of {{APP}}: <task or "lead">

Framework pin: `{{FW_BRANCH}}` at `<rev>` (`plan.base`). App base: `{{APP_PLAN_BASE}}`. Port branch: `{{APP_PORT_BRANCH}}`.

## Resume

<Where the next agent picks up: the last commit, what is done, what is left, in two or three lines.>

## Size

| Part | Files | Lines (+/−) |
|---|---|---|
| Repin and rewrite (tools/minimal-port) | | |
| Port, without tests | | |
| Tests | | |
| Total against the app base, without `Cargo.lock` | | |

## Per item

| Item | Files | Lines | What changed |
|---|---|---|---|
| Runtime host | | | |
| Close | | | |
| Input review | | | |
| Dock | | | |
| Dialogs | | | |
| Title bar | | | |
| Removed helpers | | | |
| Keymap | | | |
| Web shell | | | |
| Tests | | | |

## Behaviour differences

<One line each: what the user sees differently, and why (next's component, a framework rule, a fallback). The PR text copies this list.>

## Decisions

<One line each: a choice the rules and production did not settle, the option taken, and why.>

## Framework findings

| Finding | Seen in (file:line, test) | Framework fix: PR and merged rev | App-side fallback, until | Pin includes the fix |
|---|---|---|---|---|
| | | | | yes / no |

<Every known fix of process/minimal-port.md that the app touches gets a row too. A fallback names the PR it waits for and is removed at the repin that brings the fix.>

## Deleted tests

| Test | File | Reason (what removed internal it tested) |
|---|---|---|

## Changes needed in files I do not own

<Writers only: file, the change, why.>

## Compile and test rounds

| Round | Compile errors | Tests passed | Tests failed | Notes |
|---|---|---|---|---|

## Run

| Platform | Commit | Result | Failed rows | Screenshots |
|---|---|---|---|---|
| linux | | | | <the look page> |
| macos | | | | |

## PR text

<Title: "<App>: move to craft-libs next (minimal port)". Body: what changed in a few lines, the pin, the visible differences, the framework PRs it depends on, how it was run. No attribution lines.>

## Progress

<One line per step.>

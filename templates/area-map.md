# {{APP}} port map: {{AREA}}

Area `{{AREA}}`: inventory chunks <first>-<last> (<n> present, <m> entries; none missing | list the missing ones). App paths are relative to <app UI dir> (snapshot <app revision>); framework paths are relative to <framework crates dir> (snapshot <framework revision>).

<Two to five sentences: what in this area uses the framework today, and what is app code only.>

## How to read a section

- **Fit**: `direct` (use as is), `needs props` (listed), `missing component` (what it would be), `app-only` (stays app code, built from framework widgets).
- **Gaps** name framework changes. `FG-n` are the framework gaps listed at the end; `CH-n` are missing control hooks for the old and new captures (list at the end). Section ids (such as `G1`) are this file's.
- **Tests**: `(n)` is the number of test functions in the file (a grep of the snapshot), then the share that concerns this entry. Verdicts: `delete` (behaviour the framework now owns, or code that is deleted; one-line reason), `table` (event-to-command cases fold into a few table-driven tests per event family), `keep` (the app's own decisions: command ids and params, engine effects, saved settings), `new`.
- **States** use the format of the capture states files (tools/look.md, "States from the map"): `{id, title, setup?, steps: [{method, params}]}`; `none`, with the reason, for a part with nothing to show.
- **Size**: S under about 40 agent tool calls, M up to about 100, L about 150 or more (split if larger).

## Inventory corrections (spot checks against the code)

Checked <n> entry points by reading the code, and every referenced test file's test count and gating. <m> corrections, applied in the sections below:

1. [<entry>] <what the inventory said, what the code shows, with file:line>.

Checked and right: <what you verified and found as the inventory said>.

## <ID>. <Part name>

(One section per user-visible part, in the form of templates/map-section.md.)

## Infra in this area

| Id | Infra part | What the port changes | Used by sections |
|---|---|---|---|

## Framework gaps

| Id | Gap | Framework change | Sections that need it | Size |
|---|---|---|---|---|
| FG-1 | | | | |

## Missing control hooks

| Id | What is missing | Sections that wait |
|---|---|---|
| CH-1 | | |

## Suggested order

1. <Framework gaps that unblock many entries>
2. <The shared host or container, then its dependants>
3. <Direct parts, one agent each>
4. <Needs-props parts, after their gap>
5. <Missing components: framework M, app S>
6. <App-only parts, whenever their container is ported>

## Counts

<n> sections cover the <m> inventory entries (infra merged into the part it serves). Fit of each section's main part: <direct> direct, <props> needs props, <missing> missing component, <app> app-only. <g> framework gaps, <h> control hooks.

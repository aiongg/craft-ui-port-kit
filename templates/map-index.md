# {{APP}} port map: index

Index of the area maps that say what each user-visible part of {{APP}}'s UI (`<app UI dir>`, snapshot <app revision>) becomes on the {{FACADE}} framework (snapshot <framework revision>). Each area map has the full material per part: app code, framework components with file:line, gaps, app glue, test verdicts, states.

| Area map | Covers | Inventory chunks |
|---|---|---|
| [<area>.md](<area>.md) | <what the area covers> | <first>-<last> |

Contents: [1. Every user-visible part](#1-every-user-visible-part) · [2. Shared framework gaps](#2-shared-framework-gaps) · [3. Suggested port order](#3-suggested-port-order) · [4. App-side changes](#4-app-side-changes) · [5. Missing control hooks](#5-missing-control-hooks) · [6. Coverage](#6-coverage)

**Fit**: `direct` (a framework component replaces the part), `needs props` (the component lacks props listed in the area map), `missing component`, `app-only` (stays app code, built from framework widgets).

## 1. Every user-visible part

One row per section of an area map (one port task). **Depends on** uses section ids of the same area, `SG-n` for the shared framework gaps in section 2, and `PC-n` for the app-side changes in section 4. **Size** is the app port on the area map's scale: S under about 40 tool calls, M up to about 100, L about 150 or more (split before briefing). `fw` is the framework work when a section sizes it separately.

### 1.1 <Area> (<number of rows>)

| Section | Part | Kind | Framework replacement | Fit | Size | Depends on |
|---|---|---|---|---|---|---|
| [A1](<area>.md#a1-<slug>) | | | | | | |

## 2. Shared framework gaps

The area maps list framework gaps under their own ids. Merged and deduplicated they are the gaps below. Each becomes a framework task.

- **When**: `before` means the gap blocks a whole family of parts, so it lands first; `beside` means it lands with, or just before, the part that needs it.
- **Size**: from the area maps where they size the framework work; `~` marks an estimate made for this index.
- **Area ids**: the gap's id in each area map.

| Id | Gap | Framework change | Entries that need it | Size | When | Area ids |
|---|---|---|---|---|---|---|
| SG-1 | | | | | | |

## 3. Suggested port order

### Step 0: prerequisites

| Work | Needed by |
|---|---|

### Risk ranking

| Rank | Area or section | Missing components | Needs props | Shared gaps | Why it is risky |
|---|---|---|---|---|---|

The riskiest main-surface section with the shell is the pilot; the framework sets the ranking marks riskiest go first in the batch after it.

### Step 1: the first parts, one agent each, in parallel

| Part | Sections | Framework area it exercises | Size | Control calls today |
|---|---|---|---|---|

### Step 2: small framework gaps, beside step 1

### Step 3: the remaining parts, by use and then size

### Step 4: shell pieces, after the parts they host

## 4. App-side changes

| Id | Change | Why | Sections that need it |
|---|---|---|---|
| PC-1 | | | |

## 5. Missing control hooks

Parts that the capture tool cannot reach yet, merged across the area maps.

| Hook | What is missing | Parts that wait | Area ids |
|---|---|---|---|
| H-1 | | | |

## 6. Coverage

| Area | Chunks | Inventory entries (user-visible / infra) | Map sections | Rows in section 1 | Fit of rows: direct / needs props / missing / app-only | Chunks failed |
|---|---|---|---|---|---|---|
| | | | | | | |

- **Failed chunks**: <none | list>.
- **Not mapped**: <no user-visible entry is missing | list>. State how you checked.
- **Left out of section 1**: <test-only files, module roots, with the reason>.
- **Count differences between the inventory and the maps**: <list, with the reason for each>.
- **Parts mapped in more than one area.** Port them together; the first section listed owns the code, the others carry wiring, tests or the caller:

| Part | Sections |
|---|---|

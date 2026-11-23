# {{SET}}: <short title>

- Repo: fw | app. Model: opus | sonnet. Base: <framework revision> (fw) | <app revision> (app).
- Lines: write N, delete M. Write counts lines added or changed, never kept lines; delete counts lines removed.
- Contract items it writes: <ids, or none>.
- Contract items and app interfaces it calls: <ids, or none>.
- Map sections: <area map section ids>.
- Look reference: <for a set that ports a visible part: the literal sizes, paddings, alignments, icon sizes and framework variant from the map sections' Look reference fields, each with `path:line` in the old code; `none` for a set with no visible part>.
- Waits on (signatures it codes against): <set ids, or none>.
- Stories: `<Type>`: <story names> in `crates/<crate>/src/<dir>/stories.rs`. Only in a sheet that adds a framework component or variant; one entry per type, separated by `;`. The set with this line is the type's story owner (rules/porting-rules.md, "UI gallery").

## Files

| Path | Action | Write | Delete | What changes |
|---|---|---|---|---|
| `crates/<crate>/src/x.rs` | edit | 40 | 120 | One line per file: what goes, what comes, which kept functions stay (by name). |

Actions: `new`, `edit` (the writer edits the file in place; most code stays), `rewrite` (most of the file changes; say why), `delete`, `keep` (listed only for its tests). One action per path; never a group action. A path that exists in both repos takes a `(fw)` or `(app)` suffix after the backticks.

## Replaced mechanisms and their readers

| Mechanism (removed or changed) | Reader (path:line at the base) | Owner set | What the reader does instead |
|---|---|---|---|

Every reader that `git grep` finds at the base: production code, tests, examples, benches, re-exports, other crates and apps. A reader in a file that this set does not own is also a row under "Requests to other sets".

## Tests

| File | Test | Verdict | Reason; for a rewrite, what it asserts afterwards and through which driver |
|---|---|---|---|

Every test function in every file of this set, including files it deletes. Verdicts: `keep`, `rewrite`, `delete`, `new`. Judged by the testing rule (rules/testing-rule.md).

## Writer notes

What the phase 5 writer needs beyond the tables and the contract rows: bodies, rules, edge cases, with path:line evidence at the base. Short, numbered. No history.

## Requests to other sets

| To set (or "unowned") | Path | What |
|---|---|---|

## Changes from the consolidated plan

One line each: what this sheet changes against the ownership file or the area plan, and why (evaluation item, code evidence).

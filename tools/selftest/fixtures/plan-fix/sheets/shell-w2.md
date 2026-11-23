# shell-w2: app glue

- Repo: app. Model: sonnet. Base: def (app).
- Lines: write 20, delete 30.
- Contract items it writes: none.
- Contract items and app interfaces it calls: sh.C1, sh.C9.
- Waits on (signatures it codes against): shell-w1.

## Files

| Path | Action | Write | Delete | What changes |
|---|---|---|---|---|
| `src/window.rs` | edit | 20 | 30 | Calls sh.C1. |
| `crates/ui/src/chrome.rs` (fw) | edit | 5 | 0 | Also edits the chrome. |

## Tests

| File | Test | Verdict | Reason; for a rewrite, what it asserts afterwards and through which driver |
|---|---|---|---|
| `src/window.rs` | `opens` | keep | Behaviour. |

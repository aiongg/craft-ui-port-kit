# shell-w1: window chrome

- Repo: fw. Model: opus. Base: abc (fw).
- Lines: write 50, delete 10.
- Contract items it writes: sh.C1.
- Contract items and app interfaces it calls: none.
- Waits on (signatures it codes against): none.

## Files

| Path | Action | Write | Delete | What changes |
|---|---|---|---|---|
| `crates/ui/src/chrome.rs` | edit | 40 | 10 | Title bar through sh.C1. |
| `crates/ui/tests/chrome.rs` | new | 10 | 0 | Behaviour test. |

## Tests

| File | Test | Verdict | Reason; for a rewrite, what it asserts afterwards and through which driver |
|---|---|---|---|
| `crates/ui/tests/chrome.rs` | `title_shows` | new | Title shows. |

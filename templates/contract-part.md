# Contract part {{PART}}

Part file of the framework API contract. Items sit under `### <crate>`, then `#### <file>` (path relative to the crate; a repo-root file says so). Phase 3 compiles `new` and `changed` items as stubs; `removed` items stay until phase 5 removes them with their readers.

### <crate>

#### `<path/to/file.rs>`

| Id | Kind | Signature | Behaviour | Replaces | Writer | Also | Used by | Source | Resolution |
|---|---|---|---|---|---|---|---|---|---|
| {{AREA_CODE}}.<Kind><n> | new / changed / removed | `pub fn name(&self, ...) -> T` (full Rust signature, with derive bounds and visibility) | One or two plain sentences: what it does, in terms a user of the item needs. | The mechanism this item replaces and removes (or "none"). | The set that writes it. | Other sets that edit the same line (or "none"). | Sets that call it. | Chunk plan and map section the item came from. | Settled-question or conflict id that shaped it (or "none"). |

## Dropped in the fix round

| Id | Was | Reason (name the replacement) |
|---|---|---|

Notes:

- `Id` is `<area code>.<Kind letter><number>`, unique in the whole contract. The code is the area's `code` in port.toml.
- A new item takes the next free number of its area.
- `Writer`, `Also` and `Used by` name real sets from the ownership file.
- A signature names only types that exist at the plan base or are themselves contract items.

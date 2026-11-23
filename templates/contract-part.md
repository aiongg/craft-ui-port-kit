# Contract part {{PART}}

Part file of the contract. Items sit under `### <crate>`, then `#### <file>` (path relative to the crate; a repo-root file says so). A framework crate's heading is its name; an app crate's heading is `### <crate> (app)`, and the app's rows sit in parts of their own. Phase 3 compiles `new` and `changed` items as stubs, the app rows in its last stage; `removed` items stay until phase 5 removes them with their readers.

### <crate>

#### `<path/to/file.rs>`

| Id | Kind | Signature | Behaviour | Replaces | Writer | Also | Used by | Source | Resolution |
|---|---|---|---|---|---|---|---|---|---|
| {{AREA_CODE}}.<Kind><n> | new / changed / removed | `pub fn name(&self, ...) -> T` (full Rust signature, with derive bounds and visibility) | One or two plain sentences: what it does, in terms a user of the item needs. | The mechanism this item replaces and removes (or "none"). | The set that writes it. | Other sets that edit the same line (or "none"). | Sets that call it. | Chunk plan and map section the item came from. | Settled-question or conflict id that shaped it (or "none"). |

## Dropped in the fix round

| Id | Was | Reason (name the replacement) |
|---|---|---|

Notes:

- `Id` is `<area code>.<Kind letter><number>`, unique in the whole contract. The code is the area's `code` in port.toml. App rows take the Kind letter `A` (`pn.A3`), so app and framework items never share a number.
- The app part holds every app item that more than one app set uses: constructors, shared view structs, a services or context parameter, the runtime install, the test harness. An item one set writes and uses alone stays in its sheet. Without these rows, each set guesses its siblings' signatures and the guesses meet at the first compile.
- A new item takes the next free number of its area.
- `Writer`, `Also` and `Used by` name real sets from the ownership file.
- A signature names only types that exist at the plan base or are themselves contract items.

# Working on the kit

This file is for sessions that change the kit itself. A session that runs a port loads `skills/craft-ui-port/SKILL.md` instead; nothing here applies to a port.

## Layout

| Path | Holds | Notes |
|---|---|---|
| `skills/craft-ui-port/SKILL.md` | The lead's entry point | Points into everything below; keep its phase table in step with `process/` |
| `.claude-plugin/` | `plugin.json`, `marketplace.json` | Make the repo installable as a Claude Code plugin |
| `hooks/` | `hooks.json`: the plugin's SessionStart hook | Runs `tools/lead-context`; prints text only, and nothing outside a port workspace |
| `process/` | `00-overview.md`, one runbook per phase (`01` to `10`), `11-build-loop.md`, `12-running-agents.md`, `costs.md`, `lessons.md`, `config.md` | Phase numbers are those of the table in `00-overview.md`; runbook files are numbered one higher (phase 0 is `01-setup.md`) |
| `rules/` | Rules every agent or the lead gets in full | Each rule lives in one file; other files link to it |
| `prompts/` | Agent prompts and `lead.md`, rendered by `tools/render-prompt` | `{{NAME}}` placeholders only from `tools/portkit/config.py` or the per-call list in `render-prompt --help` |
| `templates/` | `port.toml.example`, the sheet and contract formats, `STATE.md`, report templates, `claude-settings.json` | `templates/sheet.md` is the format `port-set` parses |
| `workflows/` | The phase 1 and 2 workflow scripts | Run under `tools/swarm.py` or the Workflow tool |
| `tools/` | Every script, `tools/portkit/` (shared Python package), `tools/selftest/` (fixture cases and stubs), `tools/README.md` | Tools read `port.toml` through `portkit.config` and post dashboard events through `portkit.track` |
| `dashboard/` | The static dashboard page `track publish` copies out | Self-contained: no CDN, no external fonts |
| `examples/photocraft/` | Scrubbed excerpts of a real port | Each file's source and snapshot date in its README |

## Rules for changes

- **Run `tools/kit-check` before every commit and push.** The repo is public, and the pre-push hook runs the same check (enable it with `git config core.hooksPath .githooks`). CONTRIBUTING.md has the scrub rule, the private patterns file and the allowlist. Never write a machine path, a person's name or handle, a hostname, a private domain, a private tool or tracker name, or account details.
- **Config keys live in one place:** `KEYS` in `tools/portkit/config.py`. Add or change a key there, then print the key tables with `python3 tools/portkit/config.py doc`, paste them over the "Keys" section of `process/config.md`, and update `templates/port.toml.example`. Docs name keys as `section.key`.
- **One statement per rule.** When two files need the same rule, keep the text in one (agents' rules in `rules/agent-common.md`, the lead's in `rules/lead-rules.md`, process steps in their runbook) and link from the other.
- **Docs match the tools.** A command line in a doc matches the tool's `--help`. When you change a tool's arguments, grep the kit for its name and update every doc and prompt that calls it.
- **Dashboard calls are part of the process.** A doc or prompt that has an agent or the lead work through a step says which `track` call it makes (`tools/track.md` is the interface). Kit tools post their own events through `portkit.track.event()`, `track.recorded()` or `track run`, never by asking an agent.
- **The UI gallery rule** travels with every rule, review and prompt change: check the gallery before adding a component; register every new component or variant with its stories in the same change (`rules/porting-rules.md`, "UI gallery").
- **Measured numbers** go in `process/costs.md` or `process/lessons.md`, labelled with the app and the phase.
- **Writing style:** plain language, short active sentences, one idea each; lead with what the reader needs to act; define kit terms (the glossary in `process/00-overview.md`), not standard engineering terms. Write the result as if it had always been so.

## Checks

The kit has no build. Before a commit:

```sh
tools/kit-check
python3 -I -m py_compile <each Python tool you changed>
bash -n <each shell tool you changed>
tools/check-workflow            # the workflow scripts; plain `node --check` rejects their top-level return
tools/selftest/run              # the fixture cases of the tools, against stubbed cl, cargo and claude
node --check dashboard/app.js
```

Try a tool you changed against scratch data with a scratch `port.toml` (`PORT_KIT_CONFIG=<scratch>/port.toml`), never against a live port's trees.

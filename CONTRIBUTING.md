# Contributing

The kit is public. Most of its content comes from a real port, run on a real machine, so every change gets the same scrub before it is pushed.

## The scrub rule

Nothing in the repo or its history may identify a person, a machine or a private setup. That covers:

- absolute paths from a home directory, a cache directory or a session scratch directory;
- personal names, account handles and email addresses (GitHub noreply addresses are fine);
- hostnames, private domains and IP addresses;
- names of local trees, worktrees and target directories;
- names of private tools, trackers and their issue ids;
- account names, plan quotas and other facts about one person's subscription.

Write a config key or a prompt placeholder instead of a path (process/config.md lists them), a role instead of a tree name ("the app integration tree"), and "your issue tracker" instead of a tracker's name. The only identity in the repo is the repository's own URL, where the kit says how to install it.

## Setting up a clone

1. Enable the pre-push hook:

   ```sh
   git config core.hooksPath .githooks
   ```

2. Create your private patterns file at `~/.config/craft-ui-port-kit/private-patterns.txt`, or anywhere outside the repo with `PORT_KIT_PRIVATE_PATTERNS` pointing at it. List what identifies you and your machine:
   - your home directory path and user name;
   - your hostnames, and the names of machines you build on;
   - your GitHub handle and the forks you push to;
   - your name and every email in your commit identities;
   - the names of your local trees, worktrees and scratch directories;
   - private domains, and the names of your own tools and trackers.

   Format: one Python regular expression per line, matched case-insensitively. Blank lines and lines starting with `#` are ignored. Escape dots in domains (`example\.org`).

The file never goes into the repo. kit-check refuses a push that tracks it, and prints a loud warning when the file is missing.

## kit-check

`tools/kit-check` runs four checks:

1. Every tracked file against the generic patterns. They ship in `tools/portkit/scrub.py` and cover the shapes listed in the scrub rule.
2. The same files against every line of your private patterns file.
3. The commits being pushed (authors, committers, messages and added lines), with both pattern sets. On a first push to a new remote, that is the whole history.
4. The exceptions in `tools/kit-check.allow`.

Each hit prints as `where:line: [pattern] text`, and any hit fails the run. The pre-push hook runs kit-check, with your private patterns required, for every pushed ref. It is the gate: the repo is public, so a check that runs after the push runs after the leak. There is no CI copy of it.

Run it by hand after copying anything from a port:

```sh
tools/kit-check                 # tracked files, and the commits not yet on any remote
tools/kit-check --all-history   # the whole history
```

### Exceptions

`tools/kit-check.allow` takes exact exceptions, one per line: a path, a tab, and a string. A hit passes only when an occurrence of that string in the same line covers it. Add an entry only for text that must appear, such as the repository's URL. Never add a bare name or a whole file.

## Copying material from a port

Process docs, prompts and tools come from a real port. When you copy something in:

- Replace every machine path with its config key or `{{PLACEHOLDER}}`. Replace tree names with their roles.
- Drop run state: dates of one run, account letters, issue ids, the names of people who made a call. Keep the decision and its reason.
- Keep measured numbers in process/costs.md and process/lessons.md, labelled with the app and the phase they come from.
- Examples under `examples/` are excerpts of PhotoCraft's port artifacts, copied and then scrubbed; `examples/photocraft/README.md` names each source and its snapshot date.

## Process and framework docs

This kit is the canonical description of the port process. craft-libs' `docs/porting.md` keeps the framework-facing parts (the reuse ladder, gallery stories, automation capture) and points here. A process change goes into this repo; a framework change goes into craft-libs.

## Before a push

1. `tools/kit-check` passes with your private patterns file present.
2. Python tools compile (`python3 -I -m py_compile <file>`), shell scripts parse (`bash -n <file>`), workflow scripts parse (`tools/check-workflow`; plain `node --check` rejects their top-level `await` and `return`).
3. Someone other than the author reads the change, checking for leaks the patterns miss: a person's name in prose, a description that identifies a machine.

Commit with a GitHub noreply identity. The first push to the public repo is one squashed commit with that identity. The kit is licensed MIT OR Apache-2.0, as craft-libs is.

## Writing style

Plain language: short sentences in the active voice, one idea each. Lead with what the reader needs to act. Don't define standard engineering terms, but do define kit terms (area, set, sheet, contract, bucket, round, track); process/00-overview.md has the glossary.

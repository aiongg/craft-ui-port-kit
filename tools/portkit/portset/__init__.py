"""port-set's modules. tools/port-set is the command line; each module here holds one part of the pipeline.

  context   the port's paths and settings from port.toml (one `ctx` per process)
  sheet     the sheet parser: head keys, Files / Replaced mechanisms / Tests tables, the repo of each path
  scip      read access to the SCIP sqlite indexes
  bundle    the writer bundle: instructions, sheet, settled items, contract rows, file texts, excerpts
  edits     the edits format (EDIT / NEW / DELETE / BLOCKED blocks) and applying it to the set's trees
  checks    the scripted self-check, the lints and the rust-analyzer check of a written set
  model     `claude -p` calls, the usage log, plan-check and agent prompts
  write     the writing commands: tree, bundle, apply, check, racheck, plancheck, run, agent, fix, usage
  plan      the whole plan for the plan-level commands: every sheet, the contract table, writers, file owners, the trees
  validate  `validate`: what the writing commands cannot place in the sheets
  audit     `audit`: the token-free plan checks (stubs, stories, decision files, readers gate writing)
  remap     `remap`: framework line references moved to the writing base
  collect   `collect`: open DECIDE items by area and owners.tsv
  status    `status`: each set's stage from its set dir, beside its dashboard task

A command module defines `register(sub)`, which adds its subparsers with `set_defaults(func=..., owns_state=...)`.
tools/port-set imports the modules listed in its COMMANDS tuple and calls each `register`.
"""

export const meta = {
  name: 'phase2-fix',
  description: 'Phase 2 fix round: re-check every contract part, write one verified sheet per writer set, assign unowned files',
  whenToUse: 'Phase 2 of a port (process/03-plan.md, step 5), after the first evaluation (phase2-final), whatever its error rate: one sweep per error class. Followed by phase2-reconcile.',
  phases: [
    { title: 'Fix', detail: 'contract parts, set sheets and coverage gaps, in parallel jobs that each own their files', model: 'opus (contract parts) and sonnet (sheets, coverage)' },
  ],
}

// The fix round exists because a plan made from maps carries errors in a few repeating classes. Every job runs one
// sweep per class over everything it owns, not only the sampled items: the classes the first evaluation named
// (args.classes) and the six standing ones (prompts/p2-fix-round.md lists them, with the evaluation findings to apply):
//   1. file actions copied from one row to every file in it        4. duplicate or unfounded framework items
//   2. code read at an older revision than the plan base           5. settled decisions that never reached the plan
//   3. incomplete reader lists (tests, examples, re-exports,       6. "rewrite" sized as the whole file
//      other crates, other binaries)
// plus a coverage class: tests without a verdict and files without an owner.
//
// Jobs never edit a file another job owns. What another part must change goes in the job's requests file
// (<fixDir>/requests/<job>.md), which phase2-reconcile applies.
//
// The script reads no files; `tools/render-prompt --workflow-args phase2-fix` builds every input from port.toml, the
// plan files and the evaluation reports. tools/swarm.py runs the same script with the same args when
// pipeline.batch_runner is "swarm".
//
// args:
//   parts, fixDir    work.parts and <plan>/fix (absolute): the jobs write requests/ and logs/ under fixDir
//   models           { sheet_fix, chunk_plan }   from [models] in port.toml: contract parts use chunk_plan (judgement),
//                    sheets and coverage jobs use sheet_fix
//   prompts          { fix_round }: prompts/p2-fix-round.md rendered from port.toml; {{OUT}} {{TASK}} are filled here
//   contract         [{ id: "contract-NN", file: "NN.md", crates: [...], items: N }]   one job per contract part
//   sheets           [{ id: "sheets-<area>-<n>", area, sets: [set ids] }]               one job per group of sets
//   coverage         [{ id: "coverage-NN", scope }]   one job per gap list of eval-coverage.md
//   classes          [{ area, name, kind, count, pattern, find }]   the error classes of every eval-<area>.json
//   only             optional list of job ids

const fill = (text, vars) => text.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m))
const need = (value, name) => {
  if (value === undefined || value === null) throw new Error(`args.${name} is missing: build args with tools/render-prompt --workflow-args phase2-fix`)
  return value
}
const classes = need(args.classes, 'classes')
const classText = classes.length
  ? `\n\n## Classes the evaluation named\n\nSweep each over every file you own, besides the six standing classes:\n${classes.map(c => `- **${c.name}** (${c.kind}; ${c.count} sampled in area ${c.area}): ${c.pattern} Find: ${c.find}`).join('\n')}\n`
  : '\n\n## Classes the evaluation named\n\nNone beyond the six standing classes.\n'
const prompt = id => fill(need(args.prompts, 'prompts').fix_round, { OUT: need(args.fixDir, 'fixDir'), TASK: id })

const RESULT = { type: 'object', required: ['done', 'changed', 'requests', 'open_questions', 'note'], properties: {
  done: { type: 'array', items: { type: 'string' } },
  changed: { type: 'integer' }, requests: { type: 'integer' }, open_questions: { type: 'integer' },
  note: { type: 'string' } } }

const jobs = []
for (const j of args.contract || []) {
  jobs.push({ id: j.id, model: need(args.models, 'models').chunk_plan, text:
    `\n\n## Your job: contract part\n\nJob id \`${j.id}\`. Your part is ${need(args.parts, 'parts')}/${j.file} (crates: ${j.crates.join(', ') || 'none named'}; ${j.items} rows). Edit it in place; it is yours alone.\nReturn \`done\` = the crate names, \`changed\` = rows changed, added or dropped, \`requests\` = rows in your log that affect other sets.\n` })
}
for (const j of args.sheets || []) {
  jobs.push({ id: j.id, model: need(args.models, 'models').sheet_fix, text:
    `\n\n## Your job: set sheets\n\nJob id \`${j.id}\`. Write one sheet for each of these sets (area ${j.area}): ${j.sets.join(', ')}.\nReturn \`done\` = the set ids written, \`changed\` = the number of lines in the sheets' "Changes from the consolidated plan" sections, \`requests\` = rows in your requests file.\n` })
}
for (const j of args.coverage || []) {
  jobs.push({ id: j.id, model: need(args.models, 'models').sheet_fix, text:
    `\n\n## Your job: coverage gaps\n\nJob id \`${j.id}\`. The gap list in the coverage report is: ${j.scope}.\nReturn \`done\` = the files decided, \`changed\` = 0, \`requests\` = rows addressed to sets.\n` })
}
const todo = args.only && args.only.length ? jobs.filter(j => args.only.includes(j.id)) : jobs
if (!todo.length) throw new Error('no fix jobs (args.contract, args.sheets and args.coverage are empty, or "only" names none)')

phase('Fix')
const results = await parallel(todo.map(j => () => agent(prompt(j.id) + j.text + classText,
  { label: j.id, phase: 'Fix', schema: RESULT, model: j.model, role: 'sheet_fix', task: j.id })))

const failed = todo.filter((j, i) => !results[i]).map(j => j.id)
log(`Fix round: ${todo.length - failed.length} of ${todo.length} jobs done, ${classes.length} named classes swept; failed: ${failed.join(', ') || 'none'}`)
return {
  classes: classes.length,
  jobs: todo.map((j, i) => ({ id: j.id, result: results[i] })),
  failed,
  requests: results.filter(Boolean).reduce((n, r) => n + r.requests, 0),
  open_questions: results.filter(Boolean).reduce((n, r) => n + r.open_questions, 0),
  next: failed.length ? `Rerun with only: ${JSON.stringify(failed)}, then run phase2-reconcile` : 'Run phase2-reconcile',
}

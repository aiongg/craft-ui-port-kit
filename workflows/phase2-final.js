export const meta = {
  name: 'phase2-final',
  description: 'Phase 2, consolidation: merge the chunk plans per area, check conflicts, write the one contract, then evaluate the plan with fresh agents',
  whenToUse: 'Phase 2 of a port (process/03-plan.md, step 3 and 4), after phase2-part finished for every chunk. Stage "evaluate" reruns only the evaluations, after a fix round.',
  phases: [
    { title: 'Area merge', detail: 'one agent per area merges its chunk plans into areas/<area>.md', model: 'opus' },
    { title: 'Conflict check', detail: 'one agent over all area plans', model: 'opus' },
    { title: 'Consolidate', detail: 'one contract, the ownership file and the sizing report', model: 'opus' },
    { title: 'Evaluate', detail: 'fresh reviewers per area, a size audit, an answer-accuracy check and the coverage script', model: 'opus' },
  ],
}

// Stage "all" (default): Area merge -> Conflict check -> Consolidate -> Evaluate.
// Stage "evaluate": Evaluate alone, on the plan files as they are (after a fix round or a reconcile).
//
// The evaluation agents wrote none of the plan, and each rates a random sample against the code. The script compares
// their error rates with the thresholds and returns the verdict; the lead decides what to do with a failing area
// (process/03-plan.md, step 4 and 5).
//
// The script reads no files; `tools/render-prompt --workflow-args phase2-final [--stage evaluate]` builds every input
// from port.toml. tools/swarm.py runs the same script with the same args when pipeline.batch_runner is "swarm".
//
// args:
//   stage              "all" | "evaluate"
//   plan, kit          work.plan and the kit root (absolute)
//   models             { area_merge, evaluate }   from [models] in port.toml
//   prompts            { area_merge, conflict_check, consolidate, evaluate_area, answer_accuracy, size_audit }:
//                      prompts/p2-*.md rendered from port.toml; the per-call placeholders {{AREA}} {{AREA_CODE}} {{TASK}}
//                      are left in place and filled here
//   areas              [{ id, code, description, map, repos }] from port.toml [[areas]]
//   evalSchema         templates/eval-result.schema.json: what each area evaluation returns (and writes as JSON)
//   maxErrorRate       plan.max_error_rate           maxWrongAnswers   plan.max_wrong_answers
//   only               optional list of area ids (Area merge and the per-area evaluations)

const fill = (text, vars) => text.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m))
const need = (value, name) => {
  if (value === undefined || value === null) throw new Error(`args.${name} is missing: build args with tools/render-prompt --workflow-args phase2-final`)
  return value
}
const P = () => need(args.prompts, 'prompts')
const M = () => need(args.models, 'models')
const pick = (list, key) => (args.only && args.only.length ? list.filter(x => args.only.includes(x[key])) : list)

const PLAN_SCHEMA = { type: 'object', required: ['sets', 'files', 'contract_items', 'write', 'delete', 'by_model'], properties: {
  sets: { type: 'integer' }, files: { type: 'integer' }, contract_items: { type: 'integer' },
  write: { type: 'integer' }, delete: { type: 'integer' },
  by_model: { type: 'object', properties: { opus: { type: 'integer' }, sonnet: { type: 'integer' } } } } }
const ACCURACY_SCHEMA = { type: 'object', required: ['sampled', 'wrong', 'wrong_share'], properties: {
  sampled: { type: 'integer' }, wrong: { type: 'integer' }, wrong_share: { type: 'number' } } }
const COVERAGE_SCHEMA = { type: 'object', required: ['gaps', 'report'], properties: {
  gaps: { type: 'integer' }, report: { type: 'string' } } }

const RETURN_ACCURACY = '\n\nReturn JSON: {"sampled": <answers checked>, "wrong": <answers marked wrong>, "wrong_share": <wrong over sampled, a fraction between 0 and 1>}.'

const areas = pick(need(args.areas, 'areas'), 'id')
if (!areas.length) throw new Error('no areas to run (args.areas is empty or "only" names none)')
const stage = args.stage || 'all'
const out = { stage }

if (stage === 'all') {
  phase('Area merge')
  const merged = await parallel(areas.map(a => () => agent(
    fill(P().area_merge, { AREA: a.id, AREA_CODE: a.code, TASK: `merge-${a.id}` }) +
      `\n\nThe chunks of area ${a.id} are the entries of ${args.plan}/chunks.json whose area is "${a.id}".\n`,
    { label: `merge:${a.id}`, phase: 'Area merge', model: M().area_merge, task: `merge-${a.id}` })))
  const failedMerge = areas.filter((a, i) => !merged[i]).map(a => a.id)
  out.merge = areas.map((a, i) => ({ area: a.id, summary: merged[i] }))
  if (failedMerge.length || areas.length < args.areas.length) {
    log(`Area merge incomplete (failed: ${failedMerge.join(', ') || 'none'}; ${areas.length} of ${args.areas.length} areas run): conflict check and consolidation skipped`)
    out.failedMerge = failedMerge
    out.next = failedMerge.length ? `Rerun with only: ${JSON.stringify(failedMerge)}` : 'Run the remaining areas, then rerun this stage'
    return out
  }

  phase('Conflict check')
  out.conflicts = await agent(fill(P().conflict_check, { TASK: 'conflict-check' }),
    { label: 'conflict-check', phase: 'Conflict check', model: M().area_merge, task: 'conflict-check' })
  if (!out.conflicts) {
    log('Conflict check failed: consolidation skipped')
    out.next = 'Rerun this stage'
    return out
  }

  phase('Consolidate')
  out.consolidate = await agent(fill(P().consolidate, { TASK: 'consolidate' }),
    { label: 'consolidate', phase: 'Consolidate', schema: PLAN_SCHEMA, model: M().area_merge, task: 'consolidate' })
  if (!out.consolidate) {
    log('Consolidation failed: evaluation skipped')
    out.next = 'Rerun this stage'
    return out
  }
} else if (stage !== 'evaluate') {
  throw new Error(`args.stage must be "all" or "evaluate", got ${JSON.stringify(args.stage)}`)
}

phase('Evaluate')
const evals = await parallel([
  ...areas.map(a => () => agent(
    fill(P().evaluate_area, { AREA: a.id, AREA_CODE: a.code, TASK: `eval-${a.id}` }),
    { label: `eval:${a.id}`, phase: 'Evaluate', schema: need(args.evalSchema, 'evalSchema'), model: M().evaluate, task: `eval-${a.id}` })),
  () => agent(fill(P().size_audit, { TASK: 'eval-size' }),
    { label: 'eval:size', phase: 'Evaluate', model: M().evaluate, task: 'eval-size' }),
  () => agent(fill(P().answer_accuracy, { TASK: 'eval-answers' }) + RETURN_ACCURACY,
    { label: 'eval:answers', phase: 'Evaluate', schema: ACCURACY_SCHEMA, model: M().evaluate, task: 'eval-answers' }),
  () => agent(`Run \`python3 -I ${args.kit}/tools/coverage.py\` once, from the workspace directory (it picks the sheets when they exist, else the ownership file). It reads files and writes ${args.plan}/eval-coverage.md. Edit nothing. Return the total number of gaps its summary prints, and the report path.`,
    { label: 'eval:coverage', phase: 'Evaluate', schema: COVERAGE_SCHEMA, model: 'haiku', role: 'sheet_fix', task: 'eval-coverage' }),
])

const perArea = areas.map((a, i) => (evals[i] ? { area: a.id, error_rate: evals[i].error_rate, checked: evals[i].checked,
  must_fix: evals[i].must_fix.length, file: `${args.plan}/eval-${a.id}.json` } : { area: a.id, failed: true }))
const n = areas.length
const accuracy = evals[n + 1]
const maxErr = need(args.maxErrorRate, 'maxErrorRate')
const maxWrong = need(args.maxWrongAnswers, 'maxWrongAnswers')
out.evaluate = {
  areas: perArea.map(r => ({ ...r, passes: r.error_rate !== undefined && r.error_rate <= maxErr })),
  size: evals[n] ? 'eval-size.md written' : { failed: true },
  answers: accuracy ? { ...accuracy, passes: accuracy.wrong_share <= maxWrong } : { failed: true },
  coverage: evals[n + 2] || { failed: true },
  thresholds: { maxErrorRate: maxErr, maxWrongAnswers: maxWrong },
}
const failing = out.evaluate.areas.filter(r => !r.passes).map(r => r.area)
log(`Evaluation: areas above ${maxErr}: ${failing.join(', ') || 'none'}; answers ${accuracy ? (out.evaluate.answers.passes ? 'pass' : 'fail') : 'not checked'}`)
return out

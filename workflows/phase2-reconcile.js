export const meta = {
  name: 'phase2-reconcile',
  description: 'Phase 2 fix round, second stage: apply the requests between parts, then evaluate the reconciled plan again',
  whenToUse: 'Phase 2 of a port (process/03-plan.md, step 6), after phase2-fix. Run the stages contract, sheets and evaluate in that order (tools/reconcile does under swarm).',
  phases: [
    { title: 'Contract and routing', detail: 'stage contract: each contract part applies its inbox; unowned paths get owners', model: 'opus (contract parts), sonnet (routing)' },
    { title: 'Sheets', detail: 'stage sheets: sheet groups apply their inbox', model: 'sonnet' },
    { title: 'Re-evaluate', detail: 'stage evaluate: fresh reviewers per area', model: 'opus' },
  ],
}

// Agents that each owned one contract part or a few sheets wrote them at the same time, so requests between parts are
// not applied yet. Three stages apply them; scripts run between them, outside any agent:
//   plan-collate          requests, change logs and must-fix items -> inbox/<part|set|route-N>.md, groups.json
//   stage contract        each part applies inbox/contract-NN.md, checking each request against the code (a request
//                         can be wrong); routing jobs give every path addressed to "unowned" an owner set
//   plan-collate          again, so the sheets also see the parts' Reconcile logs and the routing decisions
//   stage sheets          each group applies inbox/<set>.md to its sheets
//   plan-rebuild          ownership file, joined contract, coverage report, sizing
//   stage evaluate        fresh reviewers sample each area again; error rates by kind and must-fix items
// `tools/render-prompt --workflow-args phase2-reconcile --stage S` runs the script before stage S and passes its
// result in (collated, rebuild). The script reads no files. tools/reconcile runs the whole sequence under swarm.py.
// Every job lists its inbox in `inputs`, so under swarm a rerun runs only the jobs whose inbox changed.
//
// args:
//   stage              "contract" | "sheets" | "evaluate"
//   plan, kit, fixDir  work.plan, the kit root and <plan>/fix (absolute)
//   sheets, parts      work.sheets and work.parts (absolute)
//   ownership          work.ownership (absolute)
//   models             { sheet_fix, chunk_plan, evaluate }   from [models] in port.toml
//   prompts            { fix_round, evaluate_area }: prompts/p2-*.md rendered from port.toml; {{AREA}} {{AREA_CODE}}
//                      {{OUT}} {{TASK}} are filled here
//   partList           [{ id: "contract-NN", file, crates, items }]   the contract parts on disk
//   collated           stages contract and sheets: { groups: [{ id, area, sets, rows }], routes, parts, unrouted,
//                      rejected } from the collation
//   rebuild            stage evaluate: the rebuild summary (checks, gaps, totals)
//   evalSchema         stage evaluate: templates/eval-result.schema.json
//   areas              [{ id, code, ... }] from port.toml [[areas]]
//   round              stage evaluate: this evaluation's number (2 for the first re-evaluation): reports go to
//                      eval-<area>-r<round>.md and .json
//   only               optional list of area ids for the evaluations

const fill = (text, vars) => text.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m))
const need = (value, name) => {
  if (value === undefined || value === null) throw new Error(`args.${name} is missing: build args with tools/render-prompt --workflow-args phase2-reconcile --stage ${args.stage}`)
  return value
}
const F = () => need(args.fixDir, 'fixDir')
const fixPrompt = id => fill(need(args.prompts, 'prompts').fix_round, { OUT: F(), TASK: `reconcile-${id}` })
const inbox = id => `${F()}/inbox/${id}.md`

const RESULT = { type: 'object', required: ['done', 'changed', 'open_questions', 'note'], properties: {
  done: { type: 'array', items: { type: 'string' } }, changed: { type: 'integer' },
  open_questions: { type: 'integer' }, note: { type: 'string' } } }
const STAGES = ['contract', 'sheets', 'evaluate']
const stage = args.stage
if (!STAGES.includes(stage)) throw new Error(`args.stage must be one of ${STAGES.join(', ')}, got ${JSON.stringify(stage)}`)
const out = { stage }

if (stage === 'contract') {
  const c = need(args.collated, 'collated')
  out.collated = { parts: c.parts, routes: c.routes, unrouted: c.unrouted, rejected: c.rejected }
  phase('Contract and routing')
  const jobs = [
    ...need(args.partList, 'partList').filter(p => c.parts.includes(p.id)).map(p => ({ id: p.id, run: () => agent(
      `${fixPrompt(p.id)}\n\n## Your job: apply the requests to a contract part\n\nJob id \`${p.id}\`. Your part is ${args.parts}/${p.file} (yours alone). Its inbox: ${inbox(p.id)}.\nApply each inbox row to the part after checking it against the code, or reject it with the reason. Keep the table format and the ids; a new item takes an id no part uses (grep all parts).\nAppend to ${F()}/logs/${p.id}.md a section "## Reconcile": one row per row applied (Id | What changed | Sets that must change their code or sheet), the rejected rows with reasons, and open questions (options, recommendation).\nReturn \`done\` = ids changed, \`changed\` = rows applied, \`open_questions\`, \`note\`.`,
      { label: p.id, phase: 'Contract and routing', schema: RESULT, model: need(args.models, 'models').chunk_plan, task: `reconcile-${p.id}`, inputs: [inbox(p.id)] }) })),
    ...c.routes.map(r => ({ id: r, run: () => agent(
      `${fixPrompt(r)}\n\n## Your job: routing\n\nJob id \`${r}\`. Its inbox is ${inbox(r)}: rows addressed to "unowned", the lead or the ownership file. Every path in it is yours alone.\nFor each path, read it at the base and decide its owner set: the set whose area and mechanism it belongs to (sets and their files: ${args.ownership} and the sheets' Files tables). If no edit is needed, say why, backed by grep. Merge all rows for one path into one decision. A row about an ownership-file error (a wrong action, a file marked new that exists, a path typo) becomes a request to the set that owns the file.\nWrite ${F()}/requests/${r}.md: the table \`To (set id) | Path | What\` (action, lines to write and delete, what changes, a verdict for every test function in the file as "fn: verdict, reason"), then a "No edit" table \`Path | Reason\`, then "Open questions".\nReturn \`done\` = paths decided, \`changed\` = rows written, \`open_questions\`, \`note\`.`,
      { label: r, phase: 'Contract and routing', schema: RESULT, model: need(args.models, 'models').sheet_fix, task: `reconcile-${r}`, inputs: [inbox(r)] }) })),
  ]
  const res = await parallel(jobs.map(j => j.run))
  out.jobs = jobs.map((j, i) => ({ id: j.id, result: res[i] }))
  out.failed = jobs.filter((j, i) => !res[i]).map(j => j.id)
  out.open_questions = res.filter(Boolean).reduce((n, r) => n + r.open_questions, 0)
  out.next = out.failed.length ? 'Rerun stage contract (only the failed jobs run again under swarm)' : 'Run stage sheets'
  log(`Contract and routing: ${jobs.length - out.failed.length} of ${jobs.length} jobs done; failed: ${out.failed.join(', ') || 'none'}`)
  return out
}

if (stage === 'sheets') {
  const c = need(args.collated, 'collated')
  out.collated = { groups: c.groups.length, unrouted: c.unrouted, rejected: c.rejected }
  phase('Sheets')
  const res = await parallel(c.groups.map(g => () => agent(
    `${fixPrompt(g.id)}\n\n## Your job: apply the inbox to sheets\n\nJob id \`${g.id}\`. Your sheets: ${g.sets.map(s => `${args.sheets}/${s}.md`).join(', ')} (yours alone). Each set's inbox is ${F()}/inbox/<set>.md (${g.rows} rows in all): requests from other sheets, the routing files and the coverage files, contract log rows (including each part's "Reconcile" section) that name the set, and must-fix items of the last evaluation.\nFor each inbox row, check it against the code and the contract part it cites, then apply it to the sheet (Files, readers, Tests, Writer notes, contract ids, Waits on, Lines) or reject it with the reason. A contract log row that changes or drops an item this set writes or calls changes the sheet's code plan to match.\nAfter applying, check: every reader row whose owner is this set appears in its Files table; every test function in each owned file has one verdict row; Lines in the header match the Files table's sums.\nWrite ${F()}/logs/${g.id}.md: per set, rows applied, rows rejected with the reason, open questions (options, recommendation).\nReturn \`done\` = sets changed, \`changed\` = rows applied, \`open_questions\`, \`note\`.`,
    { label: g.id, phase: 'Sheets', schema: RESULT, model: need(args.models, 'models').sheet_fix, task: `reconcile-${g.id}`, inputs: g.sets.map(inbox) })))
  out.jobs = c.groups.map((g, i) => ({ id: g.id, result: res[i] }))
  out.failed = c.groups.filter((g, i) => !res[i]).map(g => g.id)
  out.open_questions = res.filter(Boolean).reduce((n, r) => n + r.open_questions, 0)
  out.next = out.failed.length ? 'Rerun stage sheets (only the failed jobs run again under swarm)' : 'Run stage evaluate'
  log(`Sheets: ${c.groups.length - out.failed.length} of ${c.groups.length} groups done; failed: ${out.failed.join(', ') || 'none'}`)
  return out
}

phase('Re-evaluate')
const round = need(args.round, 'round')
const evalSchema = need(args.evalSchema, 'evalSchema')
out.rebuild = need(args.rebuild, 'rebuild')
const areas = need(args.areas, 'areas').filter(a => !args.only || !args.only.length || args.only.includes(a.id))
const evals = await parallel(areas.map(a => () => agent(
  fill(need(args.prompts, 'prompts').evaluate_area, { AREA: a.id, AREA_CODE: a.code, TASK: `eval-${a.id}-r${round}` }) +
  `\n\n## Round ${round}\n\nThe plan was fixed and reconciled since the first evaluation: it is now the sheets (${args.sheets}/${a.id}-w*.md) and the contract parts (${args.parts}/*.md). Judge those, not ${args.plan}/areas/${a.id}.md. You did not write any of it. Sample at least 20 contract items, 20 file rows, 20 reader rows and 20 test verdicts across the area's sets at random.\nWrite the report to ${args.plan}/eval-${a.id}-r${round}.md and the result object to ${args.plan}/eval-${a.id}-r${round}.json instead of the paths above.`,
  { label: `eval:${a.id}-r${round}`, phase: 'Re-evaluate', schema: evalSchema, model: need(args.models, 'models').evaluate, task: `eval-${a.id}-r${round}` })))

out.evaluate = areas.map((a, i) => {
  const e = evals[i]
  return e ? { area: a.id, round, error_rate: e.error_rate, checked: e.checked, must_fix: e.must_fix.length,
    passes: e.error_rate <= need(args.maxErrorRate, 'maxErrorRate'), file: `${args.plan}/eval-${a.id}-r${round}.json` } : { area: a.id, round, failed: true }
})
out.next = 'Areas above plan.max_error_rate: run the three stages again (plan-collate routes their must-fix items), with --only <area> for the evaluation'
log(`Re-evaluation round ${round}: ${out.evaluate.map(r => `${r.area} ${r.failed ? 'failed' : `${r.error_rate} (${r.must_fix} must-fix)`}`).join(', ')}`)
return out

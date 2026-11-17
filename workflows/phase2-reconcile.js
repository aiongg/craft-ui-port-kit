export const meta = {
  name: 'phase2-reconcile',
  description: 'Phase 2 fix round, second stage: apply the requests between parts, rebuild the plan files from the sheets, evaluate the fixed plan again',
  whenToUse: 'Phase 2 of a port (process/03-plan.md, step 6), after phase2-fix. Stage "evaluate" rebuilds and evaluates only.',
  phases: [
    { title: 'Collate', detail: 'one agent sorts every request and change-log row into one inbox per contract part, set and routing file', model: 'sonnet' },
    { title: 'Contract and routing', detail: 'each contract part applies its inbox; unowned paths get owners', model: 'opus (contract parts), sonnet (routing)' },
    { title: 'Sheets', detail: 'sheet groups apply their inbox', model: 'sonnet' },
    { title: 'Rebuild and re-evaluate', detail: 'ownership, joined contract, coverage and sizing from the sheets; fresh reviewers per area', model: 'opus' },
  ],
}

// Agents that each owned one contract part or a few sheets wrote them at the same time, so requests between parts are
// not applied yet. This script applies them:
//   Collate (before)      requests/*.md and logs/*.md -> inbox/<part|set|route-N>.md, groups.json
//   Contract and routing  each part applies inbox/contract-NN.md, checking each request against the code (a request can
//                         be wrong); routing jobs give every path addressed to "unowned" an owner set
//   Collate (after)       the same, so the sheets also see the parts' change logs and the routing decisions
//   Sheets                each group applies inbox/<set>.md to its sheets
//   Rebuild               ownership file, joined contract, coverage report, sizing
//   Re-evaluate           fresh reviewers sample each area again; error rates by kind
// Stage "evaluate" runs the last two steps only.
//
// The script reads no files; `tools/render-prompt --workflow-args phase2-reconcile` builds every input from port.toml.
// tools/swarm.py runs the same script with the same args when pipeline.batch_runner is "swarm".
//
// args:
//   stage              "all" | "evaluate"
//   plan, kit, fixDir  work.plan, the kit root and <plan>/fix (absolute)
//   sheets, parts      work.sheets and work.parts (absolute)
//   ownership          work.ownership (absolute)
//   models             { sheet_fix, chunk_plan, evaluate }   from [models] in port.toml
//   prompts            { fix_round, evaluate_area }: prompts/p2-*.md rendered from port.toml; {{AREA}} {{AREA_CODE}}
//                      {{OUT}} {{TASK}} are filled here
//   partList           [{ id: "contract-NN", file, crates, items }]   the contract parts on disk
//   areas              [{ id, code, ... }] from port.toml [[areas]]
//   round              this evaluation's number (2 for the first re-evaluation): reports go to eval-<area>-r<round>.md
//   only               optional list of area ids for the evaluations

const fill = (text, vars) => text.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m))
const need = (value, name) => {
  if (value === undefined || value === null) throw new Error(`args.${name} is missing: build args with tools/render-prompt --workflow-args phase2-reconcile`)
  return value
}
const F = () => need(args.fixDir, 'fixDir')
const fixPrompt = id => fill(need(args.prompts, 'prompts').fix_round, { OUT: F(), TASK: `reconcile-${id}` })
const COMMON = () => `You apply the requests between parts of the plan in the fix round of the planning phase. The plan is one sheet per writer set (${args.sheets}/<set>.md, format templates/sheet.md in the kit) and the framework contract in parts (${args.parts}/*.md; change logs ${F()}/logs/<job>.md; requests ${F()}/requests/<job>.md). Agents that each owned one part or a few sheets wrote them at the same time, so requests between parts were not applied. Check a request against the code before applying it: a request can be wrong. Read-only on code: edit no code, run no cargo or build, no git command that writes. Write only the files your job names; other agents edit the other files at the same time. Plan text states the plan: no history ("changed from", "now"). Do not start subagents or workflows.\n\n`

const RESULT = { type: 'object', required: ['done', 'changed', 'open_questions', 'note'], properties: {
  done: { type: 'array', items: { type: 'string' } }, changed: { type: 'integer' },
  open_questions: { type: 'integer' }, note: { type: 'string' } } }
const GROUPS = { type: 'object', required: ['groups', 'routes', 'parts'], properties: {
  groups: { type: 'array', items: { type: 'object', required: ['id', 'area', 'sets', 'rows'], properties: {
    id: { type: 'string' }, area: { type: 'string' }, sets: { type: 'array', items: { type: 'string' } }, rows: { type: 'integer' } } } },
  routes: { type: 'array', items: { type: 'string' } }, parts: { type: 'array', items: { type: 'string' } } } }
const EVAL_SCHEMA = { type: 'object', required: ['must_fix', 'error_rate'], properties: {
  must_fix: { type: 'integer' }, error_rate: { type: 'number' } } }
const SETS_PER_GROUP = 4

const stage = args.stage || 'all'
if (stage !== 'all' && stage !== 'evaluate') throw new Error(`args.stage must be "all" or "evaluate", got ${JSON.stringify(args.stage)}`)
const out = { stage }

async function collate(label) {
  return agent(`${COMMON()}## Your job: collate the inbox (${label})

Sort every request row into the inbox of the file it addresses, with a script or by hand, in ${F()}/inbox/ (create it; replace what a previous collation wrote):
- Rows addressed to a set id go to inbox/<set id>.md.
- Rows addressed to "contract <id>" go to inbox/contract-<NN>.md for the part in ${args.parts} that holds the item <id> (find it by grep).
- Rows addressed to "unowned", the lead or the ownership file go to inbox/route-1.md and inbox/route-2.md, alternating by path, so two routing jobs split them. Merge all rows for one path.
- Each set's inbox also gets the contract change-log rows (${F()}/logs/contract-*.md, including their "## Reconcile" sections) for items the set writes or calls, and the rows of the routing decisions (${F()}/requests/route-*.md) addressed to it.
Each row keeps its source file and its text. Then group the sets of each area, ${SETS_PER_GROUP} sets per group (ids "<area>-g<n>"), and write ${F()}/groups.json: {"groups": [{"id", "area", "sets", "rows"}]} with rows = the number of inbox rows of the group's sets.
Return the groups, the route file ids that hold rows ("route-1", "route-2"), and the contract part ids that have an inbox ("contract-01", ...).`,
    { label: `collate:${label}`, phase: 'Collate', schema: GROUPS, model: need(args.models, 'models').sheet_fix, task: `collate-${label}` })
}

if (stage === 'all') {
  phase('Collate')
  const before = await collate('before')
  if (!before) { out.failed = 'collate'; out.next = 'Rerun this stage'; return out }

  phase('Contract and routing')
  const stage1 = await parallel([
    ...need(args.partList, 'partList').filter(p => before.parts.includes(p.id)).map(p => () => agent(
      `${fixPrompt(p.id)}\n\n## Your job: apply the requests to a contract part\n\nJob id \`${p.id}\`. Your part is ${args.parts}/${p.file} (yours alone). Its inbox: ${F()}/inbox/${p.id}.md.\nApply each inbox row to the part after checking it against the code, or reject it with the reason. Keep the table format and the ids; a new item takes an id no part uses (grep all parts).\nAppend to ${F()}/logs/${p.id}.md a section "## Reconcile": one row per row applied (Id | What changed | Sets that must change their code or sheet), the rejected rows with reasons, and open questions (options, recommendation).\nReturn \`done\` = ids changed, \`changed\` = rows applied, \`open_questions\`, \`note\`.`,
      { label: p.id, phase: 'Contract and routing', schema: RESULT, model: need(args.models, 'models').chunk_plan, task: `reconcile-${p.id}` })),
    ...before.routes.map(r => () => agent(
      `${fixPrompt(r)}\n\n## Your job: routing\n\nJob id \`${r}\`. Its inbox is ${F()}/inbox/${r}.md: rows addressed to "unowned", the lead or the ownership file. Every path in it is yours alone.\nFor each path, read it at the base and decide its owner set: the set whose area and mechanism it belongs to (sets and their files: ${args.ownership} and the sheets' Files tables). If no edit is needed, say why, backed by grep. Merge all rows for one path into one decision. A row about an ownership-file error (a wrong action, a file marked new that exists, a path typo) becomes a request to the set that owns the file.\nWrite ${F()}/requests/${r}.md: the table \`To (set id) | Path | What\` (action, lines to write and delete, what changes, a verdict for every test function in the file as "fn: verdict, reason"), then a "No edit" table \`Path | Reason\`, then "Open questions".\nReturn \`done\` = paths decided, \`changed\` = rows written, \`open_questions\`, \`note\`.`,
      { label: r, phase: 'Contract and routing', schema: RESULT, model: need(args.models, 'models').sheet_fix, task: `reconcile-${r}` })),
  ])
  out.contractAndRouting = stage1

  const after = await collate('after')
  if (!after) { out.failed = 'collate-after'; out.next = 'Rerun this stage'; return out }

  phase('Sheets')
  out.sheets = await parallel(after.groups.map(g => () => agent(
    `${fixPrompt(g.id)}\n\n## Your job: apply the inbox to sheets\n\nJob id \`${g.id}\`. Your sheets: ${g.sets.map(s => `${args.sheets}/${s}.md`).join(', ')} (yours alone). Each set's inbox is ${F()}/inbox/<set>.md (${g.rows} rows in all): requests from other sheets, the routing files and the coverage files, and contract log rows (including each part's "Reconcile" section) that name the set.\nFor each inbox row, check it against the code and the contract part it cites, then apply it to the sheet (Files, readers, Tests, Writer notes, contract ids, Waits on, Lines) or reject it with the reason. A contract log row that changes or drops an item this set writes or calls changes the sheet's code plan to match.\nAfter applying, check: every reader row whose owner is this set appears in its Files table; every test function in each owned file has one verdict row; Lines in the header match the Files table's sums.\nWrite ${F()}/logs/${g.id}.md: per set, rows applied, rows rejected with the reason, open questions (options, recommendation).\nReturn \`done\` = sets changed, \`changed\` = rows applied, \`open_questions\`, \`note\`.`,
    { label: g.id, phase: 'Sheets', schema: RESULT, model: need(args.models, 'models').sheet_fix, task: `reconcile-${g.id}` })))
}

phase('Rebuild and re-evaluate')
const round = need(args.round, 'round')
const areas = need(args.areas, 'areas').filter(a => !args.only || !args.only.length || args.only.includes(a.id))
const rebuildP = agent(`${COMMON()}## Your job: rebuild the plan files from the sheets

Keep the previous version of each file you overwrite as <name>.before-reconcile in the same directory (once; leave an existing copy). Work by script where you can; the sheets are the source.
- ${args.ownership}: the summary table (Set | Repo | Model | Files | Write | Delete | Implements | Waits on) parsed from every sheet's header and Files table, then each set's sheet path. Check: no path in two sheets; every sheet parses (list the ones that do not).
- ${args.plan}/contract.md: the parts in ${args.parts} joined in file order (00-head.md first if it exists). Check: every id is unique; every Writer names a sheet that lists the item under "Contract items it writes"; every id a sheet calls exists.
- Coverage: run \`python3 -I ${args.kit}/tools/coverage.py --from sheets\` from the workspace directory. It writes ${args.plan}/eval-coverage.md.
- ${args.plan}/sizing.md: the totals of the sizing report (sets, files by action, lines to write and delete by repo and area, tests keep/rewrite/delete/new), the write split of ${args.plan}/eval-size.md recomputed (framework additions, moves, app production, rewritten tests, new tests), and the sets that wait on an open developer question.
Return \`done\` = the files written, \`changed\` = 0, \`open_questions\` = parse failures plus coverage gaps, \`note\` = the totals and the gap counts.`,
  { label: 'rebuild', phase: 'Rebuild and re-evaluate', schema: RESULT, model: need(args.models, 'models').sheet_fix, task: 'rebuild' })

const evalsP = parallel(areas.map(a => () => agent(
  fill(need(args.prompts, 'prompts').evaluate_area, { AREA: a.id, AREA_CODE: a.code, TASK: `eval-${a.id}-r${round}` }) +
  `\n\n## Round ${round}\n\nThe plan was fixed and reconciled since the first evaluation: it is now the sheets (${args.sheets}/${a.id}-w*.md) and the contract parts (${args.parts}/*.md). Judge those, not ${args.plan}/areas/${a.id}.md. You did not write any of it. Sample at least 20 contract items, 20 file rows, 20 reader rows and 20 test verdicts across the area's sets at random.\nWrite the report to ${args.plan}/eval-${a.id}-r${round}.md instead of the path above, and give the error rate by kind (contract, file, reader, verdict, rule break) and overall.\nReturn JSON: {"must_fix": <must-fix count>, "error_rate": <overall error rate as a fraction between 0 and 1>}.`,
  { label: `eval:${a.id}-r${round}`, phase: 'Rebuild and re-evaluate', schema: EVAL_SCHEMA, model: need(args.models, 'models').evaluate, task: `eval-${a.id}-r${round}` })))
const [rebuild, evals] = await Promise.all([rebuildP, evalsP])

out.rebuild = rebuild
out.evaluate = areas.map((a, i) => ({ area: a.id, round, ...(evals[i] || { failed: true }) }))
log(`Re-evaluation round ${round}: ${out.evaluate.map(r => `${r.area} ${r.error_rate === undefined ? 'failed' : r.error_rate}`).join(', ')}`)
return out

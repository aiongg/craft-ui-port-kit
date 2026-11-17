export const meta = {
  name: 'phase2-part',
  description: 'Phase 2, planning: split each plan chunk into questions, answer them with a fast model, plan each chunk',
  whenToUse: 'Phase 2 of a port (process/03-plan.md, step 2), after the area maps are accepted. Run it for all areas, or for some chunks with "only".',
  phases: [
    { title: 'Questions', detail: 'one agent splits each plan chunk into groups of checkable questions', model: 'opus' },
    { title: 'Answers', detail: 'a fast model answers a few question groups per agent, with file:line evidence', model: 'haiku' },
    { title: 'Chunk plans', detail: 'one agent per chunk writes its contract, file plan, test verdicts and writer sets', model: 'opus' },
  ],
}

// Per plan chunk, a pipeline: a chunk goes on to its next step as soon as its own previous step is done.
//
//   1. Questions   -> <plan>/chunks/<chunk>/questions.json
//   2. Answers     -> <plan>/chunks/<chunk>/answers/<group>.md       (args.answerGroupsPerAgent groups per agent)
//   3. Chunk plan  -> <plan>/chunks/<chunk>/plan.md
//
// The script reads no files (the Workflow tool gives it none); `tools/render-prompt --workflow-args phase2-part` builds
// every input from port.toml, the area maps and the kit. tools/swarm.py runs the same script with the same args when
// pipeline.batch_runner is "swarm". Agents write their own output files. A rerun with the same args repeats no
// finished agent under swarm.py (its resume cache); under the Workflow tool, rerun failed chunks with "only".
//
// args:
//   plan                   work.plan (absolute)
//   models                 { questions, answers, chunk_plan }   from [models] in port.toml
//   prompts                { questions, answers, chunk_plan }: prompts/p2-*.md rendered from port.toml; the per-call
//                          placeholders {{CHUNK}} {{TASK}} are left in place and filled here
//   answerGroupsPerAgent   plan.answer_groups_per_agent
//   chunks                 [{ id, area, map, preamble: [from, to], lines: [from, to], sections: [heading], index_rows: [n] }]
//                          from the area maps, cut at section boundaries (also written to <plan>/chunks.json). A chunk of a
//                          framework-only area has map null: its inputs are the lead's list in <plan>/chunks/<id>/inputs.md.
//   only                   optional list of chunk ids to run

const fill = (text, vars) => text.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m))
const need = (value, name) => {
  if (value === undefined || value === null) throw new Error(`args.${name} is missing: build args with tools/render-prompt --workflow-args phase2-part`)
  return value
}
const P = () => need(args.prompts, 'prompts')
const M = () => need(args.models, 'models')
const pick = (list, key) => (args.only && args.only.length ? list.filter(x => args.only.includes(x[key])) : list)

const Q_SCHEMA = { type: 'object', required: ['groups', 'choices'], properties: {
  groups: { type: 'array', items: { type: 'object', required: ['id', 'section', 'questions'], properties: {
    id: { type: 'string' }, section: { type: 'string' },
    questions: { type: 'array', items: { type: 'object', required: ['id', 'q', 'look_in'], properties: {
      id: { type: 'string' }, q: { type: 'string' }, look_in: { type: 'string' } } } } } } },
  choices: { type: 'array', items: { type: 'object', required: ['section', 'choice'], properties: {
    section: { type: 'string' }, choice: { type: 'string' } } } } } }

const A_SCHEMA = { type: 'object', required: ['files', 'answered', 'not_found', 'needs_choice'], properties: {
  files: { type: 'array', items: { type: 'string' } }, answered: { type: 'integer' },
  not_found: { type: 'array', items: { type: 'string' } }, needs_choice: { type: 'array', items: { type: 'string' } } } }

const PLAN_SCHEMA = { type: 'object', required: ['plan_file', 'api', 'files', 'sets', 'shared_files', 'tests', 'open_questions'], properties: {
  plan_file: { type: 'string' },
  api: { type: 'array', items: { type: 'object', required: ['crate', 'item', 'change'], properties: {
    crate: { type: 'string' }, item: { type: 'string' }, change: { type: 'string', enum: ['new', 'changed', 'removed'] } } } },
  files: { type: 'array', items: { type: 'object', required: ['repo', 'path', 'action', 'set'], properties: {
    repo: { type: 'string', enum: ['fw', 'app'] }, path: { type: 'string' },
    action: { type: 'string', enum: ['new', 'rewrite', 'edit', 'delete', 'keep'] }, set: { type: 'string' } } } },
  sets: { type: 'array', items: { type: 'object', required: ['id', 'files', 'est_lines_write', 'est_lines_delete', 'model'], properties: {
    id: { type: 'string' }, files: { type: 'integer' }, est_lines_write: { type: 'integer' }, est_lines_delete: { type: 'integer' },
    model: { type: 'string', enum: ['opus', 'sonnet'] } } } },
  shared_files: { type: 'array', items: { type: 'string' } },
  tests: { type: 'object', required: ['keep', 'rewrite', 'delete'], properties: {
    keep: { type: 'integer' }, rewrite: { type: 'integer' }, delete: { type: 'integer' } } },
  open_questions: { type: 'array', items: { type: 'object', required: ['id', 'question', 'recommendation'], properties: {
    id: { type: 'string' }, question: { type: 'string' }, recommendation: { type: 'string' } } } } } }

// What the chunk covers. A chunk of a framework-only area has no map: the lead lists its inputs in a file.
function chunkInput(c) {
  if (!c.map) {
    return `\n\n## Your chunk\n\nChunk ${c.id} holds framework work outside the port map. Its inputs are listed in ${args.plan}/chunks/${c.id}/inputs.md. Plan each item there, or drop it with a one-line reason.\n`
  }
  const rows = c.index_rows && c.index_rows.length ? `Rows of the map index for these sections: lines ${c.index_rows.join(", ")} of ${args.maps}/README.md.` : 'No index rows name these sections.'
  return `\n\n## Your chunk\n\nChunk ${c.id} of area ${c.area}: ${c.map}, lines ${c.lines[0]}-${c.lines[1]} (whole sections: ${c.sections.join('; ')}). The map's preamble is lines ${c.preamble[0]}-${c.preamble[1]}. ${rows}\n`
}

const groupIds = (c, n) => Array.from({ length: n }, (_, i) => `${c.id}-g${i + 1}`)
const batches = (list, size) => Array.from({ length: Math.ceil(list.length / size) }, (_, i) => list.slice(size * i, size * (i + 1)))

const chunks = pick(need(args.chunks, 'chunks'), 'id')
const size = args.answerGroupsPerAgent || 3
if (!chunks.length) throw new Error('no plan chunks to run (args.chunks is empty or "only" names none)')

const plans = await pipeline(chunks,
  async c => {
    const qs = await agent(fill(P().questions, { CHUNK: c.id, TASK: `q-${c.id}` }) + chunkInput(c),
      { label: `questions:${c.id}`, phase: 'Questions', schema: Q_SCHEMA, model: M().questions, task: `q-${c.id}` })
    return qs ? { groups: qs.groups.map(g => g.id) } : null
  },
  async (r, c) => {
    if (!r) return null
    const bs = batches(r.groups, size)
    log(`${c.id}: ${r.groups.length} groups, ${bs.length} answer agents`)
    const answers = await parallel(bs.map((b, i) => () => agent(
      fill(P().answer, { CHUNK: c.id, TASK: `a-${c.id}-b${i + 1}` }) + `\n\n## Your groups\n\n${b.join(', ')}\n`,
      { label: `answer:${c.id}-b${i + 1}`, phase: 'Answers', schema: A_SCHEMA, model: M().answers, task: `a-${c.id}-b${i + 1}` })))
    const failed = answers.filter(a => !a).length
    if (failed) log(`${c.id}: ${failed} of ${bs.length} answer agents failed`)
    return { notFound: answers.filter(Boolean).flatMap(a => a.not_found), failed }
  },
  (r, c) => {
    if (!r) return null
    const extra = `\n\nQuestions the answer agents found no answer for: ${r.notFound.length ? r.notFound.join(', ') : 'none'}.` +
      (r.failed ? ` ${r.failed} answer agent(s) failed: their groups have no answer file; read the code for them yourself.` : '') + '\n'
    return agent(fill(P().chunk_plan, { CHUNK: c.id, TASK: `plan-${c.id}` }) + chunkInput(c) + extra,
      { label: `plan:${c.id}`, phase: 'Chunk plans', schema: PLAN_SCHEMA, model: M().chunk_plan, task: `plan-${c.id}` })
  },
)

return plans.map((p, i) => p
  ? { chunk: chunks[i].id, area: chunks[i].area, plan_file: p.plan_file, sets: p.sets.length, files: p.files.length,
      api: p.api.length, tests: p.tests, open: p.open_questions.length }
  : { chunk: chunks[i].id, failed: true })

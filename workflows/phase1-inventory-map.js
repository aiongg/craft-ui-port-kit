export const meta = {
  name: 'phase1-inventory-map',
  description: 'Phase 1 of a craft port: inventory the app UI in chunks, propose areas, then map each area onto the framework and write the index',
  whenToUse: 'Phase 1 of a port (process/02-inventory-and-map.md). Run with stage "inventory" first, then with stage "maps" after the lead has accepted the areas.',
  phases: [
    { title: 'Inventory', detail: 'one reader per chunk of app UI code writes chunk-NN.json', model: 'haiku' },
    { title: 'Areas', detail: 'one agent proposes the areas from the whole inventory' },
    { title: 'Area maps', detail: 'one agent per area writes port-map/<area>.md' },
    { title: 'Index', detail: 'one agent merges the area maps into port-map/README.md' },
  ],
}

// Phase 1 of the port process, in two stages with a lead check between them:
//
//   stage "inventory": Inventory -> Areas. Ends with inventory/chunk-NN.json for every chunk and the areas proposal
//                      (inventory/areas.json, areas.md). The lead reviews the proposal and writes [[areas]] in port.toml.
//                      When chunks fail, the areas step is skipped: rerun the failed chunks with "only", then run
//                      stage "areas".
//   stage "areas":     Areas alone, from the chunk files on disk (args.inventoryList).
//   stage "maps":      Area maps -> Index. Ends with port-map/<area>.md per area and port-map/README.md. When an area
//                      fails, the index is skipped: rerun the failed areas with "only", then run stage "index".
//   stage "index":     Index alone, from the area maps on disk.
//
// The script reads no files (the Workflow tool gives it none); `tools/render-prompt --workflow-args phase1-inventory-map
// --stage <stage>` builds every input from port.toml and the kit. tools/swarm.py runs the same script with the same args
// when pipeline.batch_runner is "swarm". Agents write their own output files; the script checks coverage from what the
// agents return.
//
// args:
//   stage          "inventory" | "areas" | "maps" | "index"
//   inventory      work.inventory (absolute)          maps   work.maps (absolute)
//   models         { inventory, area_map, index }     from [models] in port.toml
//   prompts        { inventory, areas, area_map, index }: prompts/p1-*.md rendered from port.toml; the per-call
//                  placeholders {{CHUNK}} {{AREA}} {{OUT}} {{TASK}} are left in place and filled here
//   chunkSchema    templates/inventory-chunk.schema.json, parsed
//   chunks         stage "inventory": [{ id: "00", lines, files: [{ path, from?, to?, lines }], tests: [path] }]
//                  (the chunk split described in process/02-inventory-and-map.md)
//   inventoryList  stage "areas": one line per entry, "<chunk>.<index> | kind | name | files | lines", built from the
//                  chunk files
//   areas          stages "maps" and "index": [{ id, code, description, chunks: ["00", ...] }] from port.toml [[areas]] joined
//                  with inventory/areas.json
//   moves          stage "maps": [{ entry: "<chunk>.<index>", area, why }] from inventory/areas.json
//   only           optional list of chunk ids (stage "inventory") or area ids (stage "maps") to rerun

const fill = (text, vars) => text.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => (k in vars ? vars[k] : m))
const need = (value, name) => {
  if (value === undefined || value === null) throw new Error(`args.${name} is missing: build args with tools/render-prompt --workflow-args phase1-inventory-map`)
  return value
}
const P = () => need(args.prompts, 'prompts')
const M = () => need(args.models, 'models')
const pick = (list, key) => (args.only && args.only.length ? list.filter(x => args.only.includes(x[key])) : list)

const AREAS_SCHEMA = { type: 'object', required: ['areas', 'moves'], properties: {
  areas: { type: 'array', items: { type: 'object', required: ['id', 'code', 'description', 'chunks', 'entries', 'lines'], properties: {
    id: { type: 'string' }, code: { type: 'string' }, description: { type: 'string' },
    chunks: { type: 'array', items: { type: 'string' } }, entries: { type: 'integer' }, lines: { type: 'integer' } } } },
  moves: { type: 'array', items: { type: 'object', required: ['entry', 'area', 'why'], properties: {
    entry: { type: 'string' }, area: { type: 'string' }, why: { type: 'string' } } } } } }

const MAP_SCHEMA = { type: 'object', required: ['area', 'sections', 'mapped', 'not_mapped', 'fit', 'gaps', 'hooks', 'corrections', 'open_questions'], properties: {
  area: { type: 'string' }, sections: { type: 'integer' }, mapped: { type: 'integer' },
  not_mapped: { type: 'array', items: { type: 'string' } },
  fit: { type: 'object', required: ['direct', 'needs_props', 'missing', 'app_only'], properties: {
    direct: { type: 'integer' }, needs_props: { type: 'integer' }, missing: { type: 'integer' }, app_only: { type: 'integer' } } },
  gaps: { type: 'integer' }, hooks: { type: 'integer' }, corrections: { type: 'integer' }, open_questions: { type: 'integer' } } }

const INDEX_SCHEMA = { type: 'object', required: ['parts', 'shared_gaps', 'app_changes', 'hooks', 'not_mapped', 'multi_area', 'open_questions'], properties: {
  parts: { type: 'integer' }, shared_gaps: { type: 'integer' }, app_changes: { type: 'integer' }, hooks: { type: 'integer' },
  not_mapped: { type: 'array', items: { type: 'string' } }, multi_area: { type: 'integer' }, open_questions: { type: 'integer' } } }

const fileLine = f => `- ${f.path}${f.from ? ` lines ${f.from}-${f.to}` : ''} (${f.lines} lines)`

function chunkInput(c) {
  return `\n\n## Your chunk\n\nChunk ${c.id}, about ${c.lines} lines:\n${c.files.map(fileLine).join('\n')}\n\nTest files beside them (count and name their tests; do not inventory them as parts):\n${(c.tests || []).map(t => `- ${t}`).join('\n') || '- none'}\n`
}

// Compact entry list for the areas agent: enough to group entries without opening every chunk file.
function inventoryList(chunks) {
  return chunks.map(ch => ch.entries.map((e, i) =>
    `${ch.chunk}.${i} | ${e.kind} | ${e.name} | ${e.files.map(f => f.path).join(', ')} | ${e.lines}`).join('\n')).join('\n')
}

// Every file of a chunk must be in an entry or in skipped. Ranged files count when the path appears.
function uncovered(c, result) {
  const seen = new Set([...result.entries.flatMap(e => e.files.map(f => f.path)), ...result.skipped.map(s => s.path)])
  return c.files.map(f => f.path).filter(p => !seen.has(p))
}

async function inventoryStage() {
  const chunks = need(args.chunks, 'chunks')
  const schema = need(args.chunkSchema, 'chunkSchema')
  const todo = pick(chunks, 'id')
  if (todo.length < chunks.length) log(`Rerunning ${todo.length} of ${chunks.length} chunks: ${todo.map(c => c.id).join(', ')}`)

  phase('Inventory')
  const results = await pipeline(todo, c => agent(
    fill(need(P().inventory, 'prompts.inventory'), {
      CHUNK: c.id, OUT: `${args.inventory}/chunk-${c.id}.json`, TASK: `inv-${c.id}`,
    }) + chunkInput(c),
    { label: `inventory:${c.id}`, task: `inv-${c.id}`, phase: 'Inventory', schema, model: M().inventory }))

  const done = results.map((r, i) => ({ c: todo[i], r }))
  const failed = done.filter(d => !d.r).map(d => d.c.id)
  const gaps = done.filter(d => d.r).map(d => ({ chunk: d.c.id, files: uncovered(d.c, d.r) })).filter(g => g.files.length)
  const entries = done.reduce((n, d) => n + (d.r ? d.r.entries.length : 0), 0)
  log(`Inventory: ${entries} entries from ${todo.length - failed.length} chunks; failed: ${failed.join(', ') || 'none'}; chunks with uncovered files: ${gaps.length}`)

  // A partial run skips the areas step: the areas need the whole inventory, which only the chunk files hold then.
  if (todo.length < chunks.length || failed.length) {
    return { stage: 'inventory', entries, failed, gaps, areas: null,
      next: failed.length ? `Rerun with only: ${JSON.stringify(failed)}` : 'All chunks present: run stage "areas"' }
  }
  const proposal = await areasStep(chunks.map(c => c.id), inventoryList(done.map(d => d.r)))
  return { stage: 'inventory', entries, failed, gaps, ...proposal }
}

async function areasStep(chunkIds, list) {
  phase('Areas')
  const areas = await agent(
    fill(need(P().areas, 'prompts.areas'), { OUT: `${args.inventory}/areas.json`, TASK: 'areas' }) +
      `\n\n## The inventory\n\nid | kind | name | files | lines\n${list}\n`,
    { label: 'areas', task: 'areas', phase: 'Areas', schema: AREAS_SCHEMA, model: M().area_map })
  const placed = new Set(areas ? areas.areas.flatMap(a => a.chunks) : [])
  const unplaced = chunkIds.filter(id => !placed.has(id))
  if (unplaced.length) log(`Chunks in no area: ${unplaced.join(', ')}`)
  return { areas, unplaced_chunks: unplaced,
    next: 'Review inventory/areas.md, write [[areas]] in port.toml, then run stage "maps"' }
}

async function mapsStage() {
  const areas = need(args.areas, 'areas')
  const moves = args.moves || []
  const todo = pick(areas, 'id')

  phase('Area maps')
  const maps = await parallel(todo.map(a => () => {
    const inMoves = moves.filter(m => m.area === a.id)
    const outMoves = moves.filter(m => m.area !== a.id && a.chunks.includes(m.entry.split('.')[0]))
    const input = `\n\n## Your area\n\nArea ${a.id} (code ${a.code}): ${a.description}\nChunks: ${a.chunks.join(', ')}\n` +
      `Entries moved in from other chunks: ${inMoves.map(m => m.entry).join(', ') || 'none'}\n` +
      `Entries of these chunks moved to other areas (skip them): ${outMoves.map(m => `${m.entry} -> ${m.area}`).join(', ') || 'none'}\n`
    return agent(fill(need(P().area_map, 'prompts.area_map'), {
      AREA: a.id, AREA_CODE: a.code, OUT: `${args.maps}/${a.id}.md`, TASK: `map-${a.id}`,
    }) + input, { label: `map:${a.id}`, task: `map-${a.id}`, phase: 'Area maps', schema: MAP_SCHEMA, model: M().area_map })
  }))

  const failed = todo.filter((a, i) => !maps[i]).map(a => a.id)
  if (failed.length || todo.length < areas.length) {
    log(`Area maps failed: ${failed.join(', ') || 'none'}; index skipped`)
    return { stage: 'maps', maps: maps.filter(Boolean), failed, index: null,
      next: failed.length ? `Rerun with only: ${JSON.stringify(failed)}` : 'All area maps present: run stage "index"' }
  }
  return { stage: 'maps', maps, failed, index: await indexStep(areas) }
}

// The index merges gaps and hooks across every area, so it waits for all maps.
async function indexStep(areas) {
  phase('Index')
  const index = await agent(fill(need(P().index, 'prompts.index'), { OUT: `${args.maps}/README.md`, TASK: 'map-index' }) +
    `\n\n## The areas\n\n${areas.map(a => `- ${a.id}: ${args.maps}/${a.id}.md (chunks ${a.chunks.join(', ')})`).join('\n')}\n`,
    { label: 'index', task: 'map-index', phase: 'Index', schema: INDEX_SCHEMA, model: M().index })

  log(index ? 'Index written. Next: spot-check each area map against the code (process/02-inventory-and-map.md, step 6)' : 'Index agent failed: run stage "index"')
  return index
}

if (args.stage === 'inventory') return await inventoryStage()
if (args.stage === 'areas') return { stage: 'areas', ...(await areasStep(need(args.chunks, 'chunks').map(c => c.id), need(args.inventoryList, 'inventoryList'))) }
if (args.stage === 'maps') return await mapsStage()
if (args.stage === 'index') return { stage: 'index', index: await indexStep(need(args.areas, 'areas')) }
throw new Error(`args.stage must be "inventory", "areas", "maps" or "index", got ${JSON.stringify(args.stage)}`)

// Progress dashboard page. Reads state.json (written by `track publish`) every few seconds; no external resources.
// Opened from the file system it loads state.js instead, since a file:// page cannot fetch().
// Under `track serve`, GET api/info answers and open questions get an answer form (POST api/answer).
'use strict'

const POLL_MS = 4000
const STATES = ['blocked', 'failed', 'waiting', 'running', 'review', 'todo', 'done']
const OPEN_BY_DEFAULT = { blocked: true, failed: true, waiting: true, running: true, review: true, todo: false, done: false }
const STATE_LABEL = { todo: 'to do', running: 'running', review: 'in review', waiting: 'waiting', blocked: 'blocked', failed: 'failed', done: 'done' }
const LOG_STEP = 60

const S = { state: null, sig: '', qsig: '', loadedAt: 0, error: null, canAnswer: false, open: { ...OPEN_BY_DEFAULT }, logLimit: LOG_STEP, filter: '' }
const $ = (id) => document.getElementById(id)
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const ms = (t) => (t ? Date.parse(t) : NaN)
const num = (n) => (n == null ? '' : Number(n).toLocaleString())

function ago(t) {
  const s = (Date.now() - ms(t)) / 1000
  if (!isFinite(s)) return ''
  if (s < 60) return `${Math.max(0, Math.round(s))} s`
  if (s < 3600) return `${Math.round(s / 60)} min`
  if (s < 172800) return `${Math.floor(s / 3600)} h ${String(Math.round((s % 3600) / 60)).padStart(2, '0')} min`
  return `${Math.round(s / 86400)} d`
}
function clock(t) {
  const d = new Date(ms(t))
  if (isNaN(d)) return ''
  const hm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  return d.toDateString() === new Date().toDateString() ? hm : `${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${hm}`
}
const timeEl = (t) => `<time datetime="${esc(t)}" title="${esc(t)}">${esc(clock(t))}</time>`
const staleMin = (tk) => {
  if (!S.state || (tk.state !== 'running' && tk.state !== 'review')) return null
  const m = (Date.now() - ms(tk.updated)) / 60000
  return m >= S.state.stale_min ? Math.floor(m) : null
}
// URLs open; local paths show their file name, with the whole path in the hover title.
function linkHtml(name, v) {
  if (/^https?:\/\//.test(v)) return `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(name)}</a>`
  // No scheme and not absolute or home-relative: a path relative to this page.
  if (!/^[a-z][a-z0-9+.-]*:/i.test(v) && !/^[\/~]/.test(v)) return `<a href="${esc(v)}">${esc(name)}</a>`
  const base = String(v).split('/').filter(Boolean).pop() || v
  return `${esc(name)} <code title="${esc(v)}">${esc(base)}</code>`
}
const head = (id, title, n) => `<h2 id="${id}">${esc(title)}${n != null ? ` <span class="n">${esc(n)}</span>` : ''}</h2>`

// ---------------------------------------------------------------- loading

async function load() {
  try {
    const st = location.protocol === 'file:' ? await loadScript() : await loadJson()
    S.state = st
    S.loadedAt = Date.now()
    S.error = null
  } catch (e) {
    S.error = String((e && e.message) || e)
  }
  render()
}
async function loadJson() {
  const r = await fetch(`state.json?t=${Date.now()}`, { cache: 'no-store' })
  if (!r.ok) throw new Error(`state.json: HTTP ${r.status}`)
  return r.json()
}
function loadScript() {
  return new Promise((resolve, reject) => {
    const old = document.getElementById('state-js')
    if (old) old.remove()
    const s = document.createElement('script')
    s.id = 'state-js'
    s.src = `state.js?t=${Date.now()}`
    s.onload = () => (window.TRACK_STATE ? resolve(window.TRACK_STATE) : reject(new Error('state.js has no data')))
    s.onerror = () => reject(new Error('cannot load state.js'))
    document.head.appendChild(s)
  })
}
async function probeServer() {
  if (location.protocol === 'file:') return
  try {
    const r = await fetch('api/info', { cache: 'no-store' })
    S.canAnswer = r.ok && !!(await r.json()).answers
  } catch (e) {
    S.canAnswer = false
  }
}

// ---------------------------------------------------------------- render

function render() {
  renderFresh()
  const st = S.state
  if (!st) return
  const sig = `${st.generated}|${st.events}|${st.bytes}`
  const changed = sig !== S.sig
  S.sig = sig
  if (changed) {
    renderHeader()
    renderSkips()
    renderRounds()
    renderEta()
    renderHeads()
    renderLog()
  }
  // Ages and staleness move with the clock, so these redraw on every poll.
  renderQuestions()
  renderSummary()
  renderAttention()
  renderTasks()
}

function renderFresh() {
  const f = $('fresh')
  if (S.error) {
    f.className = 'fresh bad'
    f.textContent = S.state ? `Not updating: ${S.error}` : `Cannot load the data: ${S.error}`
  } else if (S.state) {
    f.className = 'fresh'
    f.textContent = `Last change ${ago(S.state.generated)} ago`
  }
}

function renderHeader() {
  const st = S.state
  const app = st.app || 'Port'
  $('title').textContent = `${app} port`
  document.title = `${app} port progress`
  const ph = st.phase
  $('phase').textContent = ph ? `Phase ${ph.n}${ph.name ? ': ' + ph.name : ''}${ph.note ? ' (' + ph.note + ')' : ''}` : 'Phase not set'
  const b = $('banner')
  const p = st.paused || {}
  b.className = p.on ? 'banner on' : 'banner'
  b.innerHTML = p.on ? `<div>Paused${p.note ? ': ' + esc(p.note) : ''}. Agents start no new step until <code>track resume</code>.</div>` : ''
}

function renderSummary() {
  const st = S.state
  const tasks = Object.values(st.tasks || {})
  const stale = tasks.filter((t) => staleMin(t) != null).length
  const open = (st.questions || []).filter((q) => !q.answer).length
  const chips = []
  if (open) chips.push(`<a class="chip hot" href="#questions"><b>${open}</b> open question${open > 1 ? 's' : ''}</a>`)
  if (stale) chips.push(`<a class="chip hot" href="#attention"><b>${stale}</b> stale</a>`)
  const skips = (st.skips || []).length
  if (skips) chips.push(`<a class="chip hot" href="#skips"><b>${skips}</b> phase move${skips > 1 ? 's' : ''} past failing exit checks</a>`)
  for (const s of STATES) {
    const n = (st.counts || {})[s]
    if (n) chips.push(`<span class="chip" style="--c:var(--${s})"><i></i>${esc(STATE_LABEL[s])} <b>${num(n)}</b></span>`)
  }
  const r = (st.rounds || []).slice(-1)[0]
  if (r) chips.push(`<a class="chip" href="#rounds">Round ${esc(r.n)}: <b>${num(r.fail)}</b> failing, ${num(r.pass)} passing</a>`)
  const e = st.eta || {}
  if (e.left && e.finish_low) chips.push(`<a class="chip" href="#eta">${num(e.left)} left, done ${esc(clock(e.finish_low))}${e.finish_high !== e.finish_low ? '–' + esc(clock(e.finish_high)) : ''}</a>`)
  if (!tasks.length) chips.push('<span class="chip">No tasks yet</span>')
  $('summary').innerHTML = chips.join('')
}

function renderQuestions() {
  const qs = S.state.questions || []
  const open = qs.filter((q) => !q.answer)
  const done = qs.filter((q) => q.answer).reverse()
  const qsig = JSON.stringify([qs.map((q) => [q.id, !!q.answer]), S.canAnswer])
  const el = $('questions')
  const typing = el.contains(document.activeElement) || [...el.querySelectorAll('input[type=text]')].some((i) => i.value)
  // Never redraw under the developer's typing; the next poll after they send or clear it catches up.
  if (qsig === S.qsig || typing) return
  S.qsig = qsig
  if (!qs.length) {
    el.innerHTML = ''
    return
  }
  const forWho = (q) => (q.for === 'developer' ? 'for you' : 'for the lead')
  const item = (q) => {
    const opts = q.options || []
    let body = ''
    if (!q.answer && S.canAnswer) {
      body = (opts.length ? `<div class="opts">${opts.map((o) => `<button type="button" class="opt" data-q="${esc(q.id)}" data-a="${esc(o)}">${esc(o)}</button>`).join('')}</div>` : '') +
        `<form data-q="${esc(q.id)}"><input type="text" name="a" aria-label="Answer to ${esc(q.id)}" placeholder="Answer"><button type="submit">Send</button></form><div class="err" id="err-${esc(q.id)}"></div>`
    } else if (!q.answer) {
      body = (opts.length ? `<div class="opts">${opts.map((o) => `<span class="opt">${esc(o)}</span>`).join('')}</div>` : '') +
        `<div class="meta">Answer in chat with the lead, or run <code>track answer ${esc(q.id)} "…"</code>.</div>`
    } else {
      body = `<div>Answer: ${esc(q.answer.text)} <span class="meta">(${esc(q.answer.by)}, ${timeEl(q.answer.t)})</span></div>`
    }
    // A question asked without --blocking: its asker went on with the recommended option until the batch's rulings.
    const how = q.blocking === false ? ' · proceeding on the recommendation' : (q.answer ? '' : ' · blocking')
    const rec = q.recommend ? `<div class="meta">Recommended: ${esc(q.recommend)}</div>` : ''
    return `<div class="ask"><div class="meta"><b>${esc(q.id)}</b> ${esc(forWho(q))} · task <code>${esc(q.task || '-')}</code> · asked ${timeEl(q.t)}${how}</div><div class="q">${esc(q.text)}</div>${rec}${body}</div>`
  }
  el.innerHTML = head('questions-h', 'Questions', open.length ? `${open.length} open` : 'none open') +
    (open.length ? `<div class="asks">${open.map(item).join('')}</div>` : '<p class="empty">No open questions.</p>') +
    (done.length ? `<details class="answered"><summary>${done.length} answered</summary>${done.map(item).join('')}</details>` : '')
}

async function sendAnswer(qid, text) {
  const err = $(`err-${qid}`)
  try {
    const r = await fetch('api/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ qid, text }) })
    const j = await r.json().catch(() => ({}))
    if (!r.ok || !j.ok) throw new Error(j.error || `HTTP ${r.status}`)
    S.qsig = ''
    const input = document.querySelector(`form[data-q="${CSS.escape(qid)}"] input`)
    if (input) input.value = ''
    if (document.activeElement) document.activeElement.blur()
    await load()
  } catch (e) {
    if (err) err.textContent = `Not sent: ${e.message || e}`
  }
}
document.addEventListener('click', (ev) => {
  const b = ev.target.closest('button.opt[data-q]')
  if (b) sendAnswer(b.dataset.q, b.dataset.a)
})
document.addEventListener('submit', (ev) => {
  const f = ev.target.closest('form[data-q]')
  if (!f) return
  ev.preventDefault()
  const text = f.elements.a.value.trim()
  if (text) sendAnswer(f.dataset.q, text)
})

// Stale tasks: running or in review with no event past the limit. Blocked and failed tasks head the task list.
function renderAttention() {
  const stale = Object.values(S.state.tasks || {}).filter((t) => staleMin(t) != null).sort((a, b) => staleMin(b) - staleMin(a))
  $('attention').innerHTML = stale.length ? head('attention-h', 'Stale', stale.length) +
    stale.map((t) => taskRow(t, `No update for ${staleMin(t)} min (limit ${S.state.stale_min}).`)).join('') : ''
}

// Phase moves recorded with `track phase N --force`: each failing exit item and the lead's reason.
function renderSkips() {
  const sk = (S.state.skips || []).slice().reverse()
  $('skips').innerHTML = sk.length ? head('skips-h', 'Skipped exit checks', sk.length) +
    sk.map((s) => `<div class="row" style="--c:var(--blocked)"><div class="head"><span class="tid">Phase ${esc(s.from)} to ${esc(s.to)}</span><span class="right">${timeEl(s.t)}</span></div>` +
      `<div class="note">Reason: ${esc(s.reason)}</div><ul class="items">${s.items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul></div>`).join('') : ''
}

function taskRow(t, extra) {
  const sm = staleMin(t)
  const label = t.step && t.state !== 'done' ? `${STATE_LABEL[t.state]}: ${t.step}` : STATE_LABEL[t.state]
  const tags = []
  if (t.group) tags.push(`<span>${esc(t.group)}</span>`)
  if (t.model) tags.push(`<span>${esc(t.model)}</span>`)
  if (t.calls) tags.push(`<span>${num(t.calls)} calls</span>`)
  for (const [k, v] of Object.entries(t.links || {})) tags.push(`<span>${linkHtml(k, v)}</span>`)
  const last = t.last ? `<div class="last ${t.last.ok === true ? 'ok' : t.last.ok === false ? 'fail' : ''}">${esc(t.last.text)} · ${timeEl(t.last.t)}</div>` : ''
  const note = t.note
  return `<div class="row" style="--c:var(--${esc(t.state)})">
<div class="head"><span class="tid">${esc(t.id)}</span><span class="ttl">${esc(t.title)}</span><span class="right"><span class="st">${esc(label)}</span> <span class="age${sm != null ? ' stale' : ''}" title="last update ${esc(t.updated)}">${esc(ago(t.updated))}</span></span></div>
${t.on ? `<div class="note"><span class="on">On ${esc(t.on)}</span>${note ? ': ' + esc(note) : ''}</div>` : note ? `<div class="note">${esc(note)}</div>` : ''}
${extra ? `<div class="note on">${esc(extra)}</div>` : ''}${last}
${tags.length ? `<div class="tags">${tags.join('')}</div>` : ''}</div>`
}

function renderTasks() {
  const all = Object.values(S.state.tasks || {})
  const f = S.filter.toLowerCase()
  const hit = (t) => !f || [t.id, t.title, t.note, t.group, t.on, t.step].some((v) => v && String(v).toLowerCase().includes(f))
  const shown = all.filter(hit)
  $('tasks-n').textContent = f ? `${shown.length} of ${all.length}` : `${all.length}`
  if (!all.length) {
    $('task-list').innerHTML = '<p class="empty">No tasks yet. The lead creates them with <code>track import sheets</code>, <code>track import tracks</code> or <code>track status TASK todo</code>.</p>'
    return
  }
  const recent = (a, b) => (a.updated < b.updated ? 1 : -1)
  $('task-list').innerHTML = STATES.map((s) => {
    const rows = shown.filter((t) => t.state === s)
    if (!rows.length) return ''
    if (s !== 'todo') rows.sort(recent)
    const open = f ? true : S.open[s]
    return `<details class="group" data-state="${s}"${open ? ' open' : ''}><summary>${esc(STATE_LABEL[s])} <span class="n">${rows.length}</span></summary>${open ? rows.map((t) => taskRow(t)).join('') : ''}</details>`
  }).join('')
}
$('task-list').addEventListener('toggle', (ev) => {
  const d = ev.target
  if (!d.matches || !d.matches('details.group') || S.filter) return
  const was = S.open[d.dataset.state]
  S.open[d.dataset.state] = d.open
  if (d.open && !was) renderTasks()
}, true)
$('filter').addEventListener('input', (ev) => {
  S.filter = ev.target.value.trim()
  if (S.state) renderTasks()
})

// Failing tests per round: one series, bars from a zero baseline, the newest value labelled, the rest in the
// hover title and the table below.
function renderRounds() {
  const rs = S.state.rounds || []
  const el = $('rounds')
  if (!rs.length) {
    el.innerHTML = ''
    return
  }
  const shown = rs.slice(-24)
  const W = 380, H = 170, L = 40, R = 8, T = 14, B = 26
  const max = Math.max(1, ...shown.map((r) => r.fail || 0))
  const step = Math.pow(10, Math.floor(Math.log10(max)))
  const tick = [1, 2, 5, 10].map((m) => m * step).find((v) => max / v <= 4) || step
  const top = Math.ceil(max / tick) * tick
  const y = (v) => T + (H - T - B) * (1 - v / top)
  const slot = (W - L - R) / shown.length
  const bw = Math.max(4, Math.min(36, slot - 4))
  let svg = ''
  for (let v = 0; v <= top; v += tick) svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${num(v)}</text>`
  shown.forEach((r, i) => {
    const x = L + i * slot + (slot - bw) / 2
    const y0 = y(0), y1 = y(r.fail || 0), h = y0 - y1, rad = Math.min(4, h, bw / 2)
    const path = h > 0 ? `M${x},${y0}V${y1 + rad}Q${x},${y1} ${x + rad},${y1}H${x + bw - rad}Q${x + bw},${y1} ${x + bw},${y1 + rad}V${y0}Z` : ''
    const tip = `Round ${r.n}: ${num(r.fail)} failing, ${num(r.pass)} passing`
    svg += `<g><title>${esc(tip)}</title><rect class="hit" x="${L + i * slot}" y="${T}" width="${slot}" height="${H - T - B}"/>${path ? `<path class="barm" d="${path}"/>` : ''}`
    if (shown.length <= 12 || i % Math.ceil(shown.length / 12) === 0 || i === shown.length - 1) svg += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${esc(r.n)}</text>`
    if (i === shown.length - 1) svg += `<text class="val" x="${x + bw / 2}" y="${y1 - 4}" text-anchor="middle">${num(r.fail)}</text>`
    svg += '</g>'
  })
  const rows = rs.slice().reverse().map((r) => `<tr><td>${esc(r.n)}</td><td class="num">${num(r.fail)}</td><td class="num">${num(r.pass)}</td><td>${timeEl(r.t)}</td><td>${r.log ? linkHtml('log', r.log) : ''}</td></tr>`).join('')
  el.innerHTML = head('rounds-h', 'Failing tests per round') +
    `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Failing tests per round; the table below lists each round">${svg}</svg>` +
    `<details class="tbl"><summary>Table</summary><table><thead><tr><th>Round</th><th class="num">Fail</th><th class="num">Pass</th><th>When</th><th></th></tr></thead><tbody>${rows}</tbody></table></details>`
}

function cycleEtaHtml(c) {
  if (!c || !c.cycles) return ''
  const w = c.weekly
  const lines = [
    `${num(c.cycles)} cycles; median cycle ${c.period_s != null ? esc((c.period_s / 60).toFixed(1)) + ' min' : 'not measured yet'}` +
      (c.per_batch != null ? `, ${esc(c.per_batch)} per finished batch` : '') +
      `; batch ${num(c.batches_seen)}${c.build_batches ? ' of ' + num(c.build_batches) : ''}.`,
    `Cycles left: <b>${c.left != null ? num(c.left) : 'unknown'}</b>${c.cycle_h != null ? ` (${esc(c.cycle_h)} h)` : ''}; sets left: ${num(c.sets_left)}${c.write_h ? ` (${esc(c.write_h)} h)` : ''}. Finish: <b>${c.finish ? esc(clock(c.finish)) : 'not yet measurable'}</b>.`,
  ]
  if (w) lines.push(`<span class="${w.passes ? 'fail' : ''}">Weekly quota: ${esc(w.now_pct)} % used${w.per_h != null ? `, ${esc(w.per_h)} %/h` : ''}${w.at_finish_pct != null ? `, ${esc(w.at_finish_pct)} % at the finish` : ''}${w.passes ? ': passes the allowance' : ''}.</span>`)
  return lines.map((l) => `<p>${l}</p>`).join('') + (c.notes || []).map((n) => `<p class="meta">${esc(n)}</p>`).join('')
}

function renderEta() {
  const e = S.state.eta
  const el = $('eta')
  if (!e || (!e.done && !e.left && !(e.cycles && e.cycles.cycles))) {
    el.innerHTML = ''
    return
  }
  const range = e.finish_low ? (e.finish_low === e.finish_high ? clock(e.finish_low) : `${clock(e.finish_low)} – ${clock(e.finish_high)}`) : 'not yet measurable'
  const groups = Object.entries(e.groups || {}).filter(([, g]) => g.total)
  const steps = Object.entries(e.steps || {})
  el.innerHTML = head('eta-h', 'Projection') +
    cycleEtaHtml(e.cycles) +
    `<p>${num(e.done)} done, ${num(e.left)} left. ${e.left ? `Finish: <b>${esc(range)}</b>.` : 'All tasks done.'}</p><p class="meta">${esc(e.basis)}${e.median_task_h != null ? `; median task ${esc(e.median_task_h)} h from first running to done` : ''}.</p>` +
    (groups.length > 1 ? `<table><thead><tr><th>Group</th><th class="num">Left</th><th class="num">Total</th></tr></thead><tbody>${groups.map(([g, v]) => `<tr><td>${esc(g || '(none)')}</td><td class="num">${num(v.left)}</td><td class="num">${num(v.total)}</td></tr>`).join('')}</tbody></table>` : '') +
    (steps.length ? `<details class="tbl"><summary>Median time per step</summary><table><thead><tr><th>Step</th><th class="num">Median</th><th class="num">Measured</th></tr></thead><tbody>${steps.map(([s, v]) => `<tr><td>${esc(s)}</td><td class="num">${esc(v.median_min)} min</td><td class="num">${num(v.n)}</td></tr>`).join('')}</tbody></table></details>` : '')
}

function renderHeads() {
  const hs = Object.entries(S.state.heads || {})
  $('heads').innerHTML = hs.length ? head('heads-h', 'Branch heads') +
    `<table><tbody>${hs.map(([k, h]) => `<tr><td>${esc(k)}</td><td><code>${esc((h.sha || '').slice(0, 10))}</code> <span class="meta">${esc(h.ref)}</span></td><td class="num">since ${timeEl(h.since)}</td></tr>`).join('')}</tbody></table>` : ''
}

function renderLog() {
  const items = S.state.log || []
  const el = $('log')
  if (!items.length) {
    el.innerHTML = ''
    return
  }
  const li = (e) => `<li>${timeEl(e.t)}${String(e.text || '').startsWith(e.kind) ? '' : `<span class="k">${esc(e.kind)}</span> `}${e.task ? `<code>${esc(e.task)}</code> ` : ''}<span class="${e.ok === true ? 'ok' : e.ok === false ? 'fail' : ''}">${esc(e.text)}</span>${Object.entries(e.links || {}).map(([k, v]) => ' · ' + linkHtml(k, v)).join('')}</li>`
  el.innerHTML = head('log-h', 'Events', items.length) + `<ul class="log">${items.slice(0, S.logLimit).map(li).join('')}</ul>` +
    (items.length > S.logLimit ? '<button type="button" class="more" id="log-more">Show more</button>' : '')
}
document.addEventListener('click', (ev) => {
  if (ev.target.id !== 'log-more') return
  S.logLimit += LOG_STEP
  renderLog()
})

probeServer().then(load)
setInterval(load, POLL_MS)

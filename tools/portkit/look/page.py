"""The compare page of one panel (`<track.out_dir>/look/<Panel>/index.html`) and the index of every panel
(`<track.out_dir>/look/index.html`).

Both pages are static and are rendered from each panel's manifest.json, so `look crops` can redraw a page without
capturing again. They use the dashboard's stylesheet (`<out_dir>/app.css`) for colours, type and light and dark
mode, and add only the layout of the image grid. They work from any static server and from the file system.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

PAGE_STYLE = """
main{max-width:1680px}
.lk-views{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0 4px}
.lk-views button{border:1px solid var(--rule);background:var(--surface);border-radius:999px;padding:3px 14px;cursor:pointer}
.lk-views button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
table.lk-sum{border-collapse:collapse;font-size:.9rem;margin:8px 0}
table.lk-sum td,table.lk-sum th{border-bottom:1px solid var(--rule);padding:4px 10px 4px 0;text-align:left;vertical-align:top}
table.lk-sum .num{text-align:right}
.lk-st{padding:18px 0 8px;border-top:1px solid var(--rule)}
.lk-st h2{font-size:1.05rem;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
.lk-st h2 code{font-weight:400;color:var(--muted)}
.lk-tag{font-size:.8rem;font-weight:600;padding:1px 8px;border-radius:999px;border:1px solid currentColor}
.lk-tag.match{color:var(--done)}.lk-tag.differs{color:var(--waiting)}.lk-tag.failed{color:var(--failed)}.lk-tag.partial{color:var(--muted)}
.lk-pair{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));margin-top:8px}
figure{margin:0;min-width:0}
figcaption{font-size:.82rem;color:var(--muted);margin-top:3px}
.lk-pair img,.lk-crops img{display:block;max-width:100%;height:auto;image-rendering:pixelated;border:1px solid var(--rule);background:var(--sunk)}
.lk-blink{position:relative;display:inline-block;max-width:100%}
.lk-blink img+img{position:absolute;left:0;top:0;animation:look-blink 1.2s steps(1,end) infinite}
@keyframes look-blink{50%{opacity:0}}
body[data-view=side] .v-blink,body[data-view=side] .v-diff{display:none}
body[data-view=blink] .v-up,body[data-view=blink] .v-port,body[data-view=blink] .v-diff{display:none}
body[data-view=diff] .v-up,body[data-view=diff] .v-port,body[data-view=diff] .v-blink{display:none}
body[data-view=all] .v-blink{display:none}
.lk-crops{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px}
.lk-crops figure{max-width:100%}
.lk-err{color:var(--failed);white-space:pre-wrap;overflow-wrap:anywhere;font-family:var(--mono);font-size:.82rem;margin:0}
.lk-wait{color:var(--muted)}
"""

PAGE_SCRIPT = """
(function(){
  var KEY='look-view', b=document.body;
  function set(v){b.dataset.view=v;document.querySelectorAll('.lk-views button').forEach(function(x){x.setAttribute('aria-pressed',x.dataset.v===v)});try{localStorage.setItem(KEY,v)}catch(e){}}
  document.querySelectorAll('.lk-views button').forEach(function(x){x.addEventListener('click',function(){set(x.dataset.v)})});
  var v='all';try{v=localStorage.getItem(KEY)||v}catch(e){}
  set(v);
})();
"""

VIEWS = (("all", "Side by side + difference"), ("side", "Side by side"), ("blink", "Blink"), ("diff", "Difference"))


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def state_status(st: dict) -> str:
    """match | differs | failed | partial (one side missing) | waiting (not captured: `needs`)."""
    if st.get("needs"):
        return "waiting"
    sides = [st.get("up"), st.get("port")]
    if any(s and s.get("error") for s in sides):
        return "failed"
    d = st.get("diff")
    if not d:
        return "partial"
    return "match" if d["visible"] == 0 and d["same_size"] else "differs"


def counts(man: dict) -> dict:
    c = {"match": 0, "differs": 0, "failed": 0, "partial": 0, "waiting": 0}
    for st in man["states"]:
        c[state_status(st)] += 1
    return c


def ensure_css(out_dir: Path, dashboard: Path) -> None:
    """The pages read the dashboard's stylesheet from out_dir; `track publish` puts it there. Copy it when no
    publish has run yet (no store configured)."""
    css = out_dir / "app.css"
    if not css.exists() and (dashboard / "app.css").is_file():
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dashboard / "app.css", css)


def _chip(n, label, color) -> str:
    return f'<span class="chip"><i style="--c:var(--{color})"></i><b>{n}</b> {esc(label)}</span>'


def _side_fig(st: dict, side: str, label: str) -> str:
    s = st.get(side)
    cls = f"v-{side}"
    if not s:
        return f'<figure class="{cls}"><p class="lk-wait">{esc(label)}: not captured yet</p></figure>'
    if s.get("error"):
        return f'<figure class="{cls}"><p class="lk-err">{esc(label)}: {esc(s["error"])}</p></figure>'
    stale = f" (from the run of {esc(s['t'])})" if s.get("stale") else ""
    return (f'<figure class="{cls}"><a href="{esc(s["full"])}"><img src="{esc(s["shot"])}" alt="{esc(label)}: '
            f'{esc(st["title"])}" loading="lazy"></a><figcaption>{esc(label)}{stale} · '
            f'<a href="{esc(s["full"])}">full window</a></figcaption></figure>')


def write_page(page_dir: Path, man: dict) -> Path:
    page_dir = Path(page_dir)
    labels = {"up": man["sides"]["up"].get("label") or "production",
              "port": man["sides"]["port"].get("label") or "port"}
    c = counts(man)
    w, h = man["window"]
    H = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         '<meta name="color-scheme" content="light dark">',
         f'<title>{esc(man["panel"])}: production and port</title>',
         '<link rel="stylesheet" href="../../app.css">', f"<style>{PAGE_STYLE}</style></head>",
         '<body data-view="all"><header class="top"><div class="bar">',
         f'<h1>{esc(man["panel"])}</h1><span class="phase">{esc(man.get("title") or "")}</span>',
         f'<span class="fresh">{esc(man["generated"])}</span></div><div class="summary">',
         _chip(len(man["states"]), "states", "todo"), _chip(c["match"], "match", "done"),
         _chip(c["differs"], "differ", "waiting"), _chip(c["failed"], "failed", "failed"),
         _chip(c["waiting"], "not captured", "todo")]
    if c["partial"]:
        H.append(_chip(c["partial"], "one side only", "todo"))
    H.append('</div></header><main>')
    side_lines = []
    for side in ("up", "port"):
        s = man["sides"][side]
        when = f", captured {esc(s['t'])}" if s.get("t") else ", not captured yet"
        side_lines.append(f"<b>{'Production' if side == 'up' else 'Port'}</b>: {esc(labels[side])}"
                          f"{(' · <code>' + esc(s['version']) + '</code>') if s.get('version') else ''}{when}")
    times = ", ".join(f"{k} {v:.1f} s" for k, v in man.get("times", {}).items())
    H.append(f'<p class="meta">{"<br>".join(side_lines)}</p>')
    H.append(f'<p class="meta">Window {w}×{h}. Images are cropped to the panel; each links its full-window shot. '
             f'Difference: red where a channel differs by more than {man["threshold"]} of 255, dark amber for '
             f'smaller differences, over the port shot in grey. Region crops show production left, port right, '
             f'at {man.get("zoom", 2)}×. {esc(times)}. <a href="../index.html">All panels</a> · '
             f'<a href="../../index.html">Dashboard</a></p>')
    H.append('<div class="lk-views" role="group" aria-label="View">' + "".join(
        f'<button type="button" data-v="{v}" aria-pressed="false">{esc(t)}</button>' for v, t in VIEWS) + "</div>")
    H.append('<div style="overflow-x:auto"><table class="lk-sum"><thead><tr><th>State</th><th>Result</th><th class="num">Visible</th>'
             '<th class="num">Regions</th></tr></thead><tbody>')
    for st in man["states"]:
        status = state_status(st)
        d = st.get("diff") or {}
        vis = f'{d["visible"]:.2f} %' if d else ""
        H.append(f'<tr><td><a href="#s-{esc(st["id"])}">{esc(st["title"])}</a></td><td>{esc(status)}'
                 f'{" (" + esc(st["needs"]) + ")" if st.get("needs") else ""}</td><td class="num">{vis}</td>'
                 f'<td class="num">{st.get("regions", "") if d else ""}</td></tr>')
    H.append("</tbody></table></div>")
    for st in man["states"]:
        status = state_status(st)
        sid = esc(st["id"])
        H.append(f'<section class="lk-st" id="s-{sid}"><h2>{esc(st["title"])} <code>{sid}</code> '
                 f'<span class="lk-tag {esc(status)}">{esc(status)}</span></h2>')
        if st.get("needs"):
            H.append(f'<p class="lk-wait">Not captured: needs {esc(st["needs"])}. {esc(st.get("note") or "")}</p></section>')
            continue
        d = st.get("diff")
        if d:
            size = "" if d["same_size"] else (f'; sizes differ: production {d["up_size"][0]}×{d["up_size"][1]}, '
                                               f'port {d["port_size"][0]}×{d["port_size"][1]}')
            H.append(f'<p class="meta">{d["visible"]:.2f} % of pixels differ visibly, {d["any"]:.2f} % at all; '
                     f'{st.get("regions", 0)} region(s){esc(size)}</p>')
        H.append('<div class="lk-pair">')
        H.append(_side_fig(st, "up", labels["up"]))
        H.append(_side_fig(st, "port", labels["port"]))
        if d:
            up, port = st["up"], st["port"]
            H.append(f'<figure class="v-blink"><span class="lk-blink"><img src="{esc(up["shot"])}" alt="production">'
                     f'<img src="{esc(port["shot"])}" alt="port"></span><figcaption>Blink: production and port '
                     f'alternate</figcaption></figure>')
            H.append(f'<figure class="v-diff"><img src="{esc(d["file"])}" alt="difference" loading="lazy">'
                     f'<figcaption>Difference</figcaption></figure>')
        H.append("</div>")
        if st.get("crops"):
            more = st.get("regions", 0) - len(st["crops"])
            H.append('<div class="lk-crops">' + "".join(
                f'<figure><img src="{esc(cr["file"])}" alt="region {i}" loading="lazy"><figcaption>box '
                f'{",".join(map(str, cr["box"]))} · {cr["px"]} px</figcaption></figure>'
                for i, cr in enumerate(st["crops"], 1)) + "</div>")
            if more > 0:
                H.append(f'<p class="meta">{more} smaller region(s) not shown (see crops.txt).</p>')
        H.append("</section>")
    H.append(f"</main><script>{PAGE_SCRIPT}</script></body></html>")
    out = page_dir / "index.html"
    out.write_text("\n".join(H))
    return out


def write_crops_txt(page_dir: Path, man: dict) -> None:
    L = [f"{man['panel']}: boxes are pixel coordinates in the cropped up-/port- images of the page",
         "region crops: production left, port right"]
    for st in man["states"]:
        status = state_status(st)
        if status != "differs":
            L.append(f"{st['id']}: {status}")
            continue
        L.append(f"{st['id']}: {st.get('regions', 0)} region(s), {st['diff']['visible']:.2f} % visible")
        for cr in st.get("crops", []):
            x0, y0, x1, y1 = cr["box"]
            L.append(f"  {cr['file']}  box {x0},{y0},{x1},{y1} ({x1 - x0}x{y1 - y0})  {cr['px']} px")
    (Path(page_dir) / "crops.txt").write_text("\n".join(L) + "\n")


def write_index(look_dir: Path) -> Path:
    """`look/index.html`: every panel page under look_dir, from its manifest."""
    look_dir = Path(look_dir)
    rows = []
    for m in sorted(look_dir.glob("*/manifest.json")):
        try:
            man = json.loads(m.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        c = counts(man)
        name = m.parent.name
        rows.append(f'<tr><td><a href="{esc(name)}/index.html">{esc(name)}</a></td><td>{esc(man.get("title") or "")}'
                    f'</td><td class="num">{len(man["states"])}</td><td class="num">{c["match"]}</td>'
                    f'<td class="num">{c["differs"]}</td><td class="num">{c["failed"]}</td>'
                    f'<td class="num">{c["waiting"]}</td><td>{esc(man["generated"])}</td></tr>')
    body = ("".join(rows) if rows else '<tr><td colspan="8" class="empty">No panel captured yet.</td></tr>')
    out = look_dir / "index.html"
    out.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">'
        '<title>Look: production and port</title><link rel="stylesheet" href="../app.css">'
        f"<style>{PAGE_STYLE}</style></head><body>"
        '<header class="top"><div class="bar"><h1>Look: production and port</h1>'
        '<span class="meta" style="margin-left:auto"><a href="../index.html">Dashboard</a></span></div></header><main>'
        '<div style="overflow-x:auto"><table class="lk-sum"><thead><tr><th>Panel</th><th>Title</th><th class="num">States</th>'
        '<th class="num">Match</th><th class="num">Differ</th><th class="num">Failed</th><th class="num">Not captured</th>'
        f"<th>Updated</th></tr></thead><tbody>{body}</tbody></table></div></main></body></html>")
    return out

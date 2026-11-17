"""`port-set collect`: gather what the decision pass needs (process/05-plancheck-decide.md, step 4).

Writes:
  <work.decide>/<area>.md   every open DECIDE item, by set, with its option lines and the set's sheet path. Items
                            come from plancheck.md (port-set plancheck) and open.md (port-set run), plus the reason in
                            blocked.md as a `[BLOCKED]` item. A file counts unless it is older than the set's
                            decisions.md: a plan check rerun after the decisions brings its new
                            DECIDE items back.
  <work.decide>/owners.tsv  one line per path a Files table names: `path<TAB>set:action,set:action`, every set whose
                            Files table names it, in sheet order; no header. cross-owner, gate-classify.py and the
                            decision prompts read it.
"""
from __future__ import annotations

import re

from .context import ctx
from .plan import all_sheets, area_of
from .write import Outcome


def open_items(set_id: str) -> list[str]:
    d = ctx.sets / set_id
    dec = d / "decisions.md"
    since = dec.stat().st_mtime if dec.exists() else None
    items = []
    for name in ("plancheck.md", "open.md"):
        f = d / name
        if not f.exists() or (since is not None and f.stat().st_mtime < since):
            continue
        cur = None
        for line in f.read_text().splitlines():
            if line.startswith("- ["):
                cur = line if line.startswith("- [DECIDE]") else None
                if cur:
                    items.append(cur)
            elif cur and line.startswith("  ") and line.strip():
                items[-1] += "\n" + line   # an item's option lines belong to it
            else:
                cur = None
    b = d / "blocked.md"
    if b.exists() and (since is None or b.stat().st_mtime >= since):
        reason = re.sub(r"^# .*\n+", "", b.read_text()).strip()
        items.append("- [BLOCKED] " + reason.replace("\n", "\n  "))
    return list(dict.fromkeys(items))


def owners_tsv(sheets) -> str:
    rows: dict[str, list[str]] = {}
    for s in sheets:
        for p, act in s.files:
            entry = f"{s.id}:{act}"
            if entry not in rows.setdefault(p, []):
                rows[p].append(entry)
    return "".join(f"{p}\t{','.join(v)}\n" for p, v in sorted(rows.items()))


def cmd_collect(a) -> Outcome:
    sheets = all_sheets()
    od = ctx.decide
    od.mkdir(parents=True, exist_ok=True)
    (od / "owners.tsv").write_text(owners_tsv(sheets))
    shared = sum(1 for line in (od / "owners.tsv").read_text().splitlines()
                 if len({e.split(":")[0] for e in line.split("\t")[1].split(",")}) > 1)
    print(f"owners.tsv: {len((od / 'owners.tsv').read_text().splitlines())} paths, {shared} named by more than one set")
    by_area: dict[str, list[tuple[str, list[str]]]] = {}
    for s in sheets:
        items = open_items(s.id)
        if items:
            by_area.setdefault(area_of(s.id), []).append((s.id, items))
    total = 0
    for area, sets in sorted(by_area.items()):
        n = sum(len(i) for _, i in sets)
        total += n
        text = [f"# DECIDE items: {area} ({n} items in {len(sets)} sets)", ""]
        for sid, items in sets:
            text += [f"## {sid}", "", f"Sheet: {s_path(sid)}", ""] + items + [""]
        (od / f"{area}.md").write_text("\n".join(text))
        print(f"{area}: {n} items in {len(sets)} sets")
    for a_ in ctx.cfg.areas:
        if a_["id"] not in by_area and (od / f"{a_['id']}.md").exists():
            print(f"{a_['id']}: no open items now; {od / (a_['id'] + '.md')} is from an earlier collect")
    return Outcome(f"{total} open items in {len(by_area)} areas", log=od,
                   data={"items": total, "areas": {k: sum(len(i) for _, i in v) for k, v in by_area.items()},
                         "shared_paths": shared})


def s_path(set_id: str):
    return ctx.sheets / f"{set_id}.md"


def register(sub) -> None:
    s = sub.add_parser("collect", help="open DECIDE items by area (<work.decide>/<area>.md) and owners.tsv")
    s.set_defaults(func=cmd_collect, owns_state=False)

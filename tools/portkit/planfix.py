"""The scripted steps of the phase 2 reconcile (process/03-plan.md, step 6): the collation of requests into inboxes,
and the rebuild of the plan files from the sheets. tools/plan-collate.py and tools/plan-rebuild.py are their command
lines; tools/render-prompt runs them when it builds the args of a reconcile stage.

Collation reads, in <plan>/fix:
  requests/*.md       tables whose first header cell starts with "To" (`To | Path | What`): the fix round's requests,
                      the coverage jobs' and the routing decisions (requests/route-N.md)
  logs/contract-*.md  the contract parts' change logs, their "## Reconcile" sections included: rows whose first cell
                      is a contract id
and the must-fix items of each area's newest re-evaluation (<plan>/eval-<area>-r<n>.json, checked with
templates/eval-result.schema.json). It writes inbox/<set>.md, inbox/contract-NN.md, inbox/route-1.md and route-2.md,
inbox/unrouted.md (rows no inbox takes, and rejected must-fix items, with the reason) and groups.json.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import config, schema
from .portset.sheet import ID, Sheet, SheetError

SET_ID = re.compile(r"\b[a-z][a-z0-9-]*-w\d+[a-z]?\b")
PART_FILE = re.compile(r"^\d\d\.md$")
ROW_ID = re.compile(rf"^\|\s*`?({ID})`?\s*\|")
EVAL_ROUND = re.compile(r"^eval-(.+)-r(\d+)\.json$")
SETS_PER_GROUP = 4
ROUTES = ("route-1", "route-2")
ROUTE_WORDS = ("unowned", "lead", "ownership")
RULE = re.compile(r"^\|[\s|:-]+\|$")


def cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def tables(text: str):
    """(header cells, body rows as cell lists) for each Markdown table of a text."""
    out, head, body = [], None, []
    for line in text.splitlines() + [""]:
        if line.startswith("|"):
            if head is None:
                head = cells(line)
            elif not RULE.match(line):
                body.append(cells(line))
            continue
        if head is not None:
            out.append((head, body))
        head, body = None, []
    return out


def esc(text: str) -> str:
    return re.sub(r"(?<!\\)\|", r"\\|", text.replace("\n", " ")).strip()


def sheets_of(cfg: config.Config) -> tuple[dict[str, Sheet], list[str]]:
    d = cfg.path("work.sheets")
    out, bad = {}, []
    for f in sorted(d.glob("*.md")) if d.is_dir() else []:
        try:
            out[f.stem] = Sheet(f.stem, f)
        except SheetError as e:
            bad.append(f"{f.name}: {e}")
    return out, bad


def part_files(cfg: config.Config) -> list[Path]:
    d = cfg.path("work.parts")
    return sorted(f for f in d.glob("*.md") if PART_FILE.match(f.name)) if d.is_dir() else []


def part_of_ids(cfg: config.Config) -> dict[str, str]:
    """Contract id -> `contract-NN`, from the rows of each part."""
    out = {}
    for f in part_files(cfg):
        for line in f.read_text().splitlines():
            m = ROW_ID.match(line)
            if m:
                out.setdefault(m.group(1), f"contract-{f.stem}")
    return out


def newest_evals(plan: Path) -> dict[str, tuple[int, Path]]:
    best: dict[str, tuple[int, Path]] = {}
    for f in plan.glob("eval-*-r*.json"):
        m = EVAL_ROUND.match(f.name)
        if m and int(m.group(2)) > best.get(m.group(1), (0, f))[0]:
            best[m.group(1)] = (int(m.group(2)), f)
    return best


class Collation:
    def __init__(self, cfg: config.Config):
        self.cfg = cfg
        self.fix = cfg.path("work.plan") / "fix"
        self.sheets, self.bad_sheets = sheets_of(cfg)
        self.parts = part_of_ids(cfg)
        self.inbox: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        self.unrouted: list[tuple[str, str, str, str]] = []
        self.rejected: list[tuple[str, str]] = []
        self.route_rows: list[tuple[str, str, str]] = []

    def address(self, to: str, src: str, path: str, what: str) -> None:
        """One row to every inbox its To cell names."""
        t = to.replace("`", "").strip()
        if t.lower().startswith("contract"):
            ids = re.findall(ID, t)
            if not ids:
                self.unrouted.append((src, to, path, "names no contract id"))
            for i in ids:
                if i in self.parts:
                    self.inbox[self.parts[i]].append((src, path or i, what))
                else:
                    self.unrouted.append((src, to, path, f"no contract part holds {i}"))
            return
        sets = SET_ID.findall(t)
        if sets:
            for s in sets:
                if s in self.sheets:
                    self.inbox[s].append((src, path, what))
                else:
                    self.unrouted.append((src, to, path, f"no sheet for set {s}"))
            return
        if any(w in t.lower() for w in ROUTE_WORDS):
            self.route_rows.append((src, path, what))
            return
        self.unrouted.append((src, to, path, "the To cell names no set, contract item or `unowned`"))

    def requests(self) -> int:
        n = 0
        for f in sorted((self.fix / "requests").glob("*.md")):
            src = f"requests/{f.name}"
            for head, body in tables(f.read_text()):
                if not head or not head[0].lower().startswith("to"):
                    continue
                for r in body:
                    if len(r) < 2 or not r[0]:
                        continue
                    n += 1
                    self.address(r[0], src, r[1] if len(r) > 2 else "", " | ".join(r[2:] if len(r) > 2 else r[1:]))
        return n

    def contract_logs(self) -> int:
        """Each change-log row goes to the sets that write or call its item and the sets the row names."""
        n = 0
        users: dict[str, set[str]] = defaultdict(set)
        for sid, s in self.sheets.items():
            for i in s.writes + s.calls:
                users[i].add(sid)
        for f in sorted((self.fix / "logs").glob("contract-*.md")):
            section = ""
            for line in f.read_text().splitlines():
                if line.startswith("## "):
                    section = line[3:].strip()
                m = ROW_ID.match(line)
                if not m:
                    continue
                n += 1
                cs = cells(line)
                src = f"logs/{f.name}" + (f" ({section})" if section else "")
                named = {s for c in cs[1:] for s in SET_ID.findall(c) if s in self.sheets}
                for sid in sorted(users[m.group(1)] | named):
                    self.inbox[sid].append((src, m.group(1), " | ".join(cs[1:])))
        return n

    def must_fix(self) -> int:
        item_schema = schema.load("eval-result.schema.json")["properties"]["must_fix"]["items"]
        n = 0
        for area, (rnd, f) in sorted(newest_evals(self.cfg.path("work.plan")).items()):
            try:
                items = json.loads(f.read_text()).get("must_fix")
            except (OSError, ValueError, AttributeError) as e:
                self.rejected.append((f.name, f"unreadable: {e}"))
                continue
            if not isinstance(items, list):
                self.rejected.append((f.name, "must_fix is not a list"))
                continue
            for k, it in enumerate(items, 1):
                ref = f"{f.name} item {k}"
                errs = schema.schema_errors(it, item_schema, path=f"must_fix[{k - 1}]")
                if errs:
                    self.rejected.append((ref, "; ".join(errs)))
                    continue
                n += 1
                self.address(it["to"], f"must-fix {area}-r{rnd}-{k}", it["path"],
                             f"{it['kind']}: {it['what']} (evidence: {it['evidence']})")
        return n

    def routes(self) -> None:
        by_path: dict[str, list] = defaultdict(list)
        for row in self.route_rows:
            by_path[row[1]].append(row)
        for i, p in enumerate(sorted(by_path)):
            self.inbox[ROUTES[i % 2]].extend(by_path[p])

    def groups(self) -> list[dict]:
        by_area: dict[str, list[str]] = defaultdict(list)
        for sid in sorted(self.sheets):
            if self.inbox.get(sid):
                by_area[re.sub(r"-w\d+[a-z]?$", "", sid)].append(sid)
        out = []
        for area, sets in by_area.items():
            for i in range(0, len(sets), SETS_PER_GROUP):
                g = sets[i:i + SETS_PER_GROUP]
                out.append({"id": f"{area}-g{i // SETS_PER_GROUP + 1}", "area": area, "sets": g,
                            "rows": sum(len(self.inbox[s]) for s in g)})
        return out

    def write(self) -> dict:
        d = self.fix / "inbox"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for key, rows in sorted(self.inbox.items()):
            L = [f"# Inbox of {key}", "", f"{len(rows)} rows. Check each against the code before applying it: a row "
                 "can be wrong.", "", "| Source | Path or id | What |", "|---|---|---|"]
            L += [f"| {esc(s)} | {esc(p)} | {esc(w)} |" for s, p, w in rows]
            (d / f"{key}.md").write_text("\n".join(L) + "\n")
        L = ["# Rows no inbox takes", "", "| Source | To | Path | Reason |", "|---|---|---|---|"]
        L += [f"| {esc(s)} | {esc(t)} | {esc(p)} | {esc(r)} |" for s, t, p, r in self.unrouted]
        L += ["", "## Rejected must-fix items", "", "| Item | Schema errors |", "|---|---|"]
        L += [f"| {esc(s)} | {esc(r)} |" for s, r in self.rejected]
        (d / "unrouted.md").write_text("\n".join(L) + "\n")
        groups = self.groups()
        out = {"groups": groups,
               "routes": [r for r in ROUTES if self.inbox.get(r)],
               "parts": sorted(k for k in self.inbox if k.startswith("contract-")),
               "unrouted": len(self.unrouted), "rejected": len(self.rejected),
               "bad_sheets": self.bad_sheets, "inbox": str(d)}
        (self.fix / "groups.json").write_text(json.dumps({"groups": groups}, indent=1) + "\n")
        return out


def collate(cfg: config.Config) -> dict:
    c = Collation(cfg)
    if not (c.fix / "requests").is_dir() and not (c.fix / "logs").is_dir():
        raise FileNotFoundError(f"{c.fix} has no requests/ or logs/: run phase2-fix first")
    counts = {"requests": c.requests(), "contract_logs": c.contract_logs(), "must_fix": c.must_fix()}
    c.routes()
    out = c.write()
    out["counts"] = counts
    return out


# ---------------------------------------------------------------- rebuild

def _int(cell: str) -> int:
    m = re.search(r"\d+", cell.replace(",", ""))
    return int(m.group(0)) if m else 0


def _head_word(s: Sheet, key: str) -> str:
    v = next((v for k, v in s.head.items() if k.startswith(key)), "")
    return v


def _model(s: Sheet) -> str:
    m = re.search(r"Model:\s*`?(\w+)", s.head.get("Repo", ""))
    return m.group(1) if m else "?"


def _is_test(path: str) -> bool:
    return bool(re.search(r"(^|/)(tests?|benches)/|(_tests?|/tests?)\.rs$", path))


def _keep_before(f: Path) -> None:
    b = f.with_name(f.name + ".before-reconcile")
    if f.is_file() and not b.exists():
        shutil.copy2(f, b)


def rebuild(cfg: config.Config, run_coverage: bool = True) -> dict:
    plan = cfg.path("work.plan")
    sheets, bad = sheets_of(cfg)
    checks: list[str] = [f"sheet does not parse: {b}" for b in bad]
    owner: dict[str, list[str]] = defaultdict(list)
    for sid, s in sheets.items():
        for p, _ in s.files:
            owner[f"{p} ({s.hint.get(p, s.repo)})"].append(sid)
    checks += [f"path in two sheets: {p}: {', '.join(v)}" for p, v in sorted(owner.items()) if len(v) > 1]

    # ownership.md
    own = cfg.path("work.ownership")
    _keep_before(own)
    L = ["# Ownership", "", "Rebuilt from the sheets by tools/plan-rebuild.py. Every file the port writes is in exactly "
         "one set.", "", "| Set | Repo | Model | Files | Write | Delete | Implements | Waits on |",
         "|---|---|---|---|---|---|---|---|"]
    per = {}
    for sid, s in sheets.items():
        w = sum(_int(r[2]) for r in s.rows.values() if len(r) > 3)
        dl = sum(_int(r[3]) for r in s.rows.values() if len(r) > 3)
        per[sid] = (w, dl)
        waits = ", ".join(SET_ID.findall(_head_word(s, "Waits on"))) or "none"
        L.append(f"| {sid} | {s.repo} | {_model(s)} | {len(s.files)} | {w} | {dl} | {', '.join(s.writes) or 'none'} "
                 f"| {waits} |")
    for sid, s in sheets.items():
        L += ["", f"### {sid}", "", f"Sheet: {s.path}", ""]
        L += [f"- `{p}` {a}" for p, a in s.files]
    own.write_text("\n".join(L) + "\n")

    # contract.md
    contract = plan / "contract.md"
    _keep_before(contract)
    head = cfg.path("work.parts") / "00-head.md"
    texts = ([head.read_text()] if head.is_file() else []) + [f.read_text() for f in part_files(cfg)]
    contract.write_text("\n\n".join(t.rstrip() for t in texts) + "\n")
    ids: Counter = Counter()
    writer: dict[str, str] = {}
    for t in texts:
        for line in t.splitlines():
            m = ROW_ID.match(line)
            if m:
                ids[m.group(1)] += 1
                cs = cells(line)
                writer[m.group(1)] = cs[5] if len(cs) > 5 else ""
    checks += [f"contract id twice: {i}" for i, n in sorted(ids.items()) if n > 1]
    for i, w in sorted(writer.items()):
        for sid in SET_ID.findall(w):
            if sid in sheets and i not in sheets[sid].writes:
                checks.append(f"{i}: Writer {sid} does not list it under \"Contract items it writes\"")
    for sid, s in sheets.items():
        missing = [i for i in s.writes + s.calls if i not in ids]
        if missing:
            checks.append(f"{sid} names ids no part defines: {', '.join(missing)}")

    # coverage
    cov: dict = {}
    if run_coverage:
        r = subprocess.run([sys.executable, "-I", str(config.KIT_ROOT / "tools" / "coverage.py"), "--from", "sheets"],
                           cwd=cfg.get("work.dir"), capture_output=True, text=True)
        try:
            cov = json.loads(r.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            cov = {"failed": f"coverage.py exit {r.returncode}: {(r.stderr.strip().splitlines() or [''])[-1]}"}

    # sizing.md
    sizing = plan / "sizing.md"
    _keep_before(sizing)
    models = Counter(f"{s.repo} {_model(s)}" for s in sheets.values())
    actions = Counter(a for s in sheets.values() for _, a in s.files)
    by_ra: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    split = Counter()
    for sid, s in sheets.items():
        area = re.sub(r"-w\d+[a-z]?$", "", sid)
        for p, r in s.rows.items():
            if len(r) < 4:
                continue
            repo = s.hint.get(p, s.repo)
            by_ra[(repo, area)][0] += _int(r[2])
            by_ra[(repo, area)][1] += _int(r[3])
            split["test files" if _is_test(p) else f"{'framework' if repo == 'fw' else 'app'} production"] += _int(r[2])
    verdicts = Counter((r[2].strip("` ").lower() if len(r) > 2 else "?") for s in sheets.values() for r in s.tests)
    dq = plan / "developer-questions.md"
    waiting = sorted({sid for sid in SET_ID.findall(dq.read_text())} & set(sheets)) if dq.is_file() else []
    S = ["# Sizing", "", "Rebuilt from the sheets by tools/plan-rebuild.py.", "",
         f"Sets: {len(sheets)} ({', '.join(f'{k}: {v}' for k, v in sorted(models.items()))}).", "",
         f"Files by action: {', '.join(f'{k} {v}' for k, v in sorted(actions.items()))}.", "",
         "| Repo | Area | Write | Delete |", "|---|---|---|---|"]
    S += [f"| {r} | {a} | {w} | {d} |" for (r, a), (w, d) in sorted(by_ra.items())]
    tw, td = sum(v[0] for v in by_ra.values()), sum(v[1] for v in by_ra.values())
    S += [f"| all | all | {tw} | {td} |", "", "Write split (lines to write): "
          + ", ".join(f"{k} {v}" for k, v in sorted(split.items())) + ". Code moved between crates is judged in "
          "eval-size.md.", "", "Test verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(verdicts.items())) + ".",
          "", "Sets named in developer-questions.md: " + (", ".join(waiting) or "none") + "."]
    sizing.write_text("\n".join(S) + "\n")
    return {"written": [str(own), str(contract), str(sizing)] + ([str(plan / "eval-coverage.md")] if cov and "failed" not in cov else []),
            "parse_failures": bad, "gaps": cov.get("gaps"), "coverage": cov, "checks": checks,
            "totals": {"sets": len(sheets), "write": tw, "delete": td, "tests": dict(verdicts)}}

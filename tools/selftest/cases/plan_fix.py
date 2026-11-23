"""plan-collate.py and plan-rebuild.py on a fixture plan: requests, change logs and must-fix items reach their
inboxes, a malformed must-fix item is rejected, the rebuild reports a path in two sheets and puts back dropped Tests
rows, and render-prompt allows one confirming evaluation, only on a clean rebuild."""
import json
import shutil
import sys

from lib import FIXTURES, TOOLS, check

sys.path.insert(0, str(TOOLS))
from portkit import schema  # noqa: E402


def plan(s):
    shutil.copytree(FIXTURES / "plan-fix", s.work / "plan")
    return s.work / "plan"


def inbox(p, key):
    f = p / "fix" / "inbox" / f"{key}.md"
    return f.read_text() if f.exists() else ""


def case_collate_routes_rows(s):
    p = plan(s)
    r = s.run("plan-collate.py")
    check(r.returncode == 0, "plan-collate exits 0", r)
    check("shell-w1\tcrates/ui/tests/chrome.rs\ttitle_shows" in (p / "verdicts.tsv").read_text(),
          "the first collation writes the verdict baseline", r)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    check(out["parts"] == ["contract-01"], f"contract part inbox: {out['parts']}", r)
    check(out["routes"] == ["route-1", "route-2"], f"two routing inboxes, alternating by path: {out['routes']}", r)
    check(out["unrouted"] == 1 and "shell-w7" in inbox(p, "unrouted"), "a row to a set with no sheet is unrouted", r)
    check(out["rejected"] == 1 and "evidence" in inbox(p, "unrouted"), "the must-fix item without evidence is rejected", r)
    w2 = inbox(p, "shell-w2")
    check("Drop the old bar call" in w2 and "Returns `Response`" in w2 and "Signature takes" in w2,
          "shell-w2 gets its request and both change-log rows of sh.C1, which it calls", r)
    check("must-fix shell-r2-1" in inbox(p, "shell-w1"), "a good must-fix item reaches its set", r)
    check("Take a `&Theme` too" in inbox(p, "contract-01") and "Name what it replaces" in inbox(p, "contract-01"),
          "contract requests and must-fix items reach the part that holds the id", r)
    g = json.loads((p / "fix" / "groups.json").read_text())["groups"]
    check(g == [{"id": "shell-g1", "area": "shell", "sets": ["shell-w1", "shell-w2"], "rows": 6}],
          f"one group with the row count: {g}", r)


def case_schema_rejects_like_swarm(s):
    sch = schema.load("eval-result.schema.json")
    reply = json.loads((FIXTURES / "plan-fix" / "eval-shell-r2.json").read_text())
    errs = schema.schema_errors(reply, sch)
    check(errs == ["$.must_fix[2]: missing key 'evidence'"], f"one error, the missing evidence: {errs}")
    reply["must_fix"][0]["to"] = "somebody"
    check(any("does not match" in e for e in schema.schema_errors(reply, sch)), "a To outside the pattern is rejected")


def case_rebuild_writes_and_checks(s):
    p = plan(s)
    r = s.run("plan-rebuild.py")
    check(r.returncode == 1, "findings make exit 1", r)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    own = (p / "ownership.md").read_text()
    check("| shell-w1 | fw | opus | 2 | 50 | 10 | sh.C1 | none |" in own and "### shell-w2" in own,
          "ownership table and per-set sections", r)
    check("sh.C1" in (p / "contract.md").read_text(), "joined contract", r)
    check(any("path in two sheets: crates/ui/src/chrome.rs" in c for c in out["checks"]), f"two owners: {out['checks']}", r)
    check(any("sh.C9" in c for c in out["checks"]), "a called id no part defines", r)
    sizing = (p / "sizing.md").read_text()
    check("| all | all | 75 | 40 |" in sizing and "new 1" in sizing and "keep 1" in sizing, "sizing totals", r)


def case_coverage_audits(s):
    p = plan(s)
    (s.root / "snap" / "src").mkdir(parents=True)
    (s.root / "snap" / "src" / "lib.rs").write_text("\n")
    s.config({"app.snapshot": str(s.root / "snap")})
    (p / "settled.md").write_text(
        "# Settled\n\n| Id | Question | Settled | Reason |\n|---|---|---|---|\n"
        "| S-H1 | Title bar height in shell-w1. | 32 px. | Production. |\n"
        "| L-4 | Who owns the menu glue? | shell-w2. | One hub set. |\n")
    sheet = p / "sheets" / "shell-w1.md"
    sheet.write_text(sheet.read_text() + "\n## Writer notes\n\n1. Title bar 32 px (S-H1).\n"
                     "2. Returns `Result<Vec<T>, E>` and takes a <short> value as before.\n3. Height TBD.\n")
    r = s.run("coverage.py", "--from", "sheets")
    out = json.loads(r.stdout.strip().splitlines()[-1])
    check(out["settled_not_carried"] == 1, f"one uncarried row (L-4 in shell-w2): {out}", r)
    check(out["open_markers"] == 1, f"one marker (TBD), and the prose with angle brackets passes: {out}", r)
    rep = (p / "eval-coverage.md").read_text()
    check("L-4 (settled :6) names shell-w2" in rep and "Height TBD" in rep, f"both listed in the report:\n{rep}", r)


TESTS_HEAD = "## Tests\n\n| File | Test | Verdict | Reason |\n|---|---|---|---|\n"


def row(name, verdict="keep"):
    return f"| `crates/ui/tests/chrome.rs` | `{name}` | {verdict} | Behaviour. |\n"


def case_verdict_guard_restores_rows(s):
    p = plan(s)
    sheet = p / "sheets" / "shell-w1.md"
    head = sheet.read_text().split("## Tests")[0]
    names = ["title_shows", "title_wraps", "close_hides", "drag_moves", "size_exact"]
    sheet.write_text(head + TESTS_HEAD + "".join(row(n) for n in names))
    s.run("plan-rebuild.py")
    check((p / "verdicts.tsv").read_text().count("shell-w1\t") == 5, "the first rebuild keeps 5 rows of shell-w1")
    (p / "fix" / "groups.json").write_text('{"groups": [{"id": "shell-g1", "area": "shell", "sets": ["shell-w1"]}]}')
    (p / "fix" / "logs" / "shell-g1.md").write_text("## shell-w1\n\n- delete `size_exact`: asserts an exact size.\n"
                                                    "- kept `drag_moves` as is.\n")
    sheet.write_text(head + TESTS_HEAD + row("title_shows"))
    r = s.run("plan-rebuild.py")
    check("shell-w1 (job shell-g1): 4 Tests rows dropped, 3 restored, 1 logged as delete or move" in r.stderr,
          "the sheet and its job are named", r)
    text = sheet.read_text()
    check(all(f"`{n}`" in text for n in names[:4]) and "size_exact" not in text,
          f"three rows are back, the logged delete stays out:\n{text}", r)
    check(text.index("title_wraps") > text.index("title_shows") and text.count("| File | Test |") == 1,
          "restored rows join the existing Tests table", r)
    r = s.run("plan-rebuild.py")
    check("verdicts:" not in r.stderr, "a second rebuild finds nothing to restore", r)


def case_one_confirming_evaluation(s):
    p = plan(s)
    s.config({"app.snapshot": str(s.root / "snap")})
    with open(s.root / "port.toml", "a") as f:
        f.write('[[areas]]\nid = "shell"\ncode = "sh"\n[[areas]]\nid = "dock"\ncode = "dk"\n')
    r = s.run("render-prompt", "--workflow-args", "phase2-reconcile", "--stage", "evaluate")
    check(r.returncode == 1 and "waits until the rebuild is clean" in r.stderr and "path in two sheets" in r.stderr,
          "a rebuild with findings refuses the confirming evaluation", r)
    for f in ("shell-w1", "shell-w2"):
        sh = p / "sheets" / f"{f}.md"
        sh.write_text(sh.read_text().replace("| `crates/ui/src/chrome.rs` (fw) | edit | 5 | 0 | Also edits the chrome. |\n", "")
                      .replace(", sh.C9", ""))
    (s.root / "snap" / "src").mkdir(parents=True)
    (s.root / "snap" / "src" / "window.rs").write_text("fn opens() {}\n")
    r = s.run("render-prompt", "--workflow-args", "phase2-reconcile", "--stage", "evaluate")
    check(r.returncode == 0, "a clean rebuild allows it", r)
    args = json.loads(r.stdout)
    check(args["round"] == 2 and args["only"] == ["dock"],
          f"round 2, only for the area without one (the fixture has eval-shell-r2.json): {args['round']}, {args['only']}", r)
    (p / "eval-dock-r2.json").write_text('{"error_rate": 0.2, "checked": 20, "by_kind": {}, "classes": [], "must_fix": []}')
    r = s.run("render-prompt", "--workflow-args", "phase2-reconcile", "--stage", "evaluate")
    check(r.returncode == 1 and "no third evaluation" in r.stderr, "a third evaluation is refused", r)
    r = s.run("render-prompt", "--workflow-args", "phase2-final", "--stage", "evaluate")
    check(r.returncode == 1 and "does not run again" in r.stderr, "so is a rerun of the first evaluation", r)


def case_coverage_citation_drift(s):
    import importlib.util
    spec = importlib.util.spec_from_file_location("coverage_tool", TOOLS / "coverage.py")
    cov = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cov)
    fw = s.root / "snap-fw" / "crates" / "ui" / "src"
    fw.mkdir(parents=True)
    (fw / "panel.rs").write_text("use x;\n\npub struct ChannelsPanel;\nimpl ChannelsPanel {\n    pub fn new() {}\n}\n")
    m = s.work / "map.md"
    m.write_text("## F1. Channels\n\n"
                 "- **Framework**: `ChannelsPanel` (ui/src/panel.rs:3: `new` :5), `ChannelsPanel::new` (ui/src/panel.rs:5), "
                 "`ChannelsPanel` (ui/src/panel.rs:2), `Gone` (ui/src/missing.rs:1), `Far` (ui/src/panel.rs:99)\n")
    bad, n = cov.citation_drift({"A": m}, {}, s.root / "snap-fw")
    check(n == 5 and len(bad) == 3, f"three of five citations drifted: {bad}")
    check("line 2 reads" in bad[0] and "no such file" in bad[1] and "the file has 6 lines" in bad[2], f"reasons: {bad}")


def case_map_section_heading_matches_render_prompt(s):
    import re
    head = (TOOLS.parent / "templates" / "map-section.md").read_text().splitlines()[0]
    text = head.replace("<ID>", "F1").replace("<Part name>", "Channels")
    check(re.match(r"^## ([A-Z]{1,3}\d+[a-z]?)\.?\s", text) and text.startswith("## F1."),
          f"the template's heading is the form render-prompt's section regex reads: {head}")

"""plan-collate.py and plan-rebuild.py on a fixture plan: requests, change logs and must-fix items reach their
inboxes, a malformed must-fix item is rejected, and the rebuild reports a path in two sheets."""
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

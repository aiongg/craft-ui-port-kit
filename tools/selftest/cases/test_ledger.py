"""test-ledger.py: a removed `mod tests;` leaves gone tests with no verdict, which the phase gate and the landing
gate refuse; sheet verdicts (`delete`, `move` to a passing test) clear them; stale marks reach the triage row."""
import json

from lib import check, git

SHEET = """# app-w1: canvas

- Repo: app. Model: sonnet. Base: base (app).

## Files

| Path | Action | Write | Delete | What changes |
|---|---|---|---|---|
| `app/src/canvas.rs` | edit | 1 | 30 | the canvas tests go |

## Tests

| File | Test | Verdict | Reason; for a rewrite, what it asserts afterwards and through which driver |
|---|---|---|---|
| `app/src/canvas.rs` | `one`, `two` | delete | the framework owns it |
| `app/src/canvas.rs` | `three` | move | to `app/tests/it/canvas.rs` `three_through_the_shell` |
"""


def fake_binary(tree, rel, tests):
    f = tree / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("#!/bin/sh\n" + "".join(f"echo '{t}: test'\n" for t in tests))
    f.chmod(0o755)


def run_log(s, keys_counts):
    s.cl_log("test-all-no-run", "".join(f"  Executable app {k} (target/debug/deps/{k}-1)\n" for k in keys_counts))
    s.cl_log("test-all", "".join(f"  ok app {k}: {n} passed, 0 failed, 0 s\n" for k, n in keys_counts.items()))


def case_removed_mod_tests_is_refused_until_ruled(s):
    app = s.tree("app", {"Cargo.toml": "[workspace]\n", "app/Cargo.toml": "[package]\nname = \"app\"\n",
                         "app/src/canvas.rs": "\n", "app/src/other.rs": "\n", "app/tests/it/canvas.rs": "\n"})
    s.tree("fw", {"Cargo.toml": "\n"})
    git(app, "branch", "base")
    s.config({"plan.base": "base"})
    fake_binary(app, "target/debug/deps/lib-1", ["canvas::tests::one", "canvas::tests::two", "canvas::tests::three",
                                                 "other::tests::kept"])
    run_log(s, {"lib": 4})
    check(s.run("test-run", "run0", "--app", "--baseline").returncode == 0, "baseline", s.last)
    fake_binary(app, "target/debug/deps/lib-1", ["other::tests::kept"])    # `mod tests;` of canvas removed
    run_log(s, {"lib": 1})
    p = s.run("test-run", "run1", "--app")
    check("ledger: 3 gone without a verdict" in p.stdout.strip().splitlines()[-1], "test-run names the gone tests", p)
    rows = (s.work / "runs" / "ledger.tsv").read_text().splitlines()
    check(len(rows) == 5 and sum("\tgone\t" in r for r in rows) == 3, f"one row per baseline test: {rows}")
    p = s.run("test-ledger.py", "--check")
    check(p.returncode == 1 and "app lib canvas::tests::one (no set): no verdict" in p.stdout, "the check refuses", p)
    s.run("track", "phase", "0")
    for n in range(1, 9):
        s.run("track", "phase", str(n), "--force", "scratch walk")
    p = s.run("track", "phase", "9")
    check(p.returncode == 1 and "test-ledger.py --check" in p.stdout + p.stderr, "the phase 8 exit refuses", p)
    sha = git(app, "rev-parse", "HEAD").strip()
    p = s.run("land/exit-gate.py", "app", sha)
    check(p.returncode == 1 and "tests gate: 1 tests check(s) fail" in p.stderr, "the landing gate refuses", p)

    (s.work / "plan" / "sheets").mkdir(parents=True)
    (s.work / "plan" / "sheets" / "app-w1.md").write_text(SHEET)
    p = s.run("test-ledger.py", "--check")
    check(p.returncode == 1 and "canvas::tests::three (app-w1): move to app/tests/it/canvas.rs three_through_the_shell "
          "(missing)" in p.stdout and "tests::one" not in p.stdout, "deletes clear, a missing move target does not", p)
    fake_binary(app, "target/debug/deps/canvas-1", ["three_through_the_shell"])
    run_log(s, {"lib": 1, "canvas": 1})
    s.run("test-run", "run2", "--app")
    p = s.run("test-ledger.py", "--check")
    check(p.returncode == 0 and "gone without a verdict 0" in p.stdout, "a passing move target clears it", p)
    led = (s.work / "runs" / "ledger.tsv").read_text()
    check("\tapp-w1\tmove\tapp/tests/it/canvas.rs three_through_the_shell\tpass\tsheet\tgone\trun2" in led,
          f"the move row: {led}")


def case_stale_mark(s):
    s.tree("app", {"Cargo.toml": "\n"})
    p = s.run("test-ledger.py", "stale", "tests::old", "--task", "t1", "reads", "a", "replaced", "label")
    check(p.returncode == 0, "stale recorded", p)
    check((s.work / "runs" / "stale.tsv").read_text() == "tests::old\tt1\treads a replaced label\n", "stale.tsv row")
    p = s.run("test-ledger.py")
    check(p.returncode == 2 and "no baseline" in p.stderr, "no baseline exits 2", p)

"""cycle: merge, compile, lint, test, packets and follow-ups in one command; the fixer mode; conflicts stop it."""
import json

from lib import cargo_metadata, check, git

FAIL_LOG = """  FAILED app lib: 1 passed, 1 failed, 0 s

running 2 tests
test tests::a ... ok
test tests::b ... FAILED

failures:

---- tests::b stdout ----
DIAG b: value was 3
thread 'tests::b' panicked at src/lib.rs:9:5:
assertion failed

failures:
    tests::b

test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

cl: 1 passed, 1 failed, 1 binaries, 0 overflowed stacks, 0 s
  app lib tests::b
"""


def fake_binary(tree, rel, tests):
    f = tree / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("#!/bin/sh\n" + "".join(f"echo '{t}: test'\n" for t in tests))
    f.chmod(0o755)


def setup(s, keys=None):
    """Framework and app trees on `main`, writing bases `base`, one fixer t1 with a branch in each; t1 has a swarm
    session; the stub cl compiles cleanly and the app run fails tests::b."""
    fw = s.tree("fw", {".stub-metadata.json": cargo_metadata([{"name": "crate-a", "dir": "crates/a"}]),
                       "crates/a/Cargo.toml": "[package]\nname = \"crate-a\"\n", "crates/a/src/lib.rs": "\n"})
    app = s.tree("app", {"Cargo.toml": "[workspace]\n[workspace.metadata.cl]\nselection = [\"app\"]\n",
                         "app/Cargo.toml": "[package]\nname = \"app\"\n", "app/src/lib.rs": "\n"})
    for t in (fw, app):
        git(t, "branch", "base")
        git(t, "switch", "-q", "-c", "red/t1")
    s.commit(fw, {"crates/a/src/lib.rs": "fix\n"}, "t1 framework fix")
    s.commit(app, {"app/src/lib.rs": "fix\n// DIAG left\n"}, "t1 app fix")
    for t in (fw, app):
        git(t, "switch", "-q", "main")
    s.config({"framework.writing_base": "base", "app.writing_base": "base", "plan.base": "base", **(keys or {})})
    (s.work / "fixers.txt").write_text("# the round's fixers\nt1\n")
    (s.work / "groups.md").write_text("## t1\n\n### tests::b\n")
    fake_binary(app, "target/debug/deps/app-1", ["tests::a", "tests::b"])
    fake_binary(fw, "target/debug/deps/crate_a-1", ["tests::one"])
    s.cl_log("test-all-no-run", "  Executable app lib (target/debug/deps/app-1)\n")
    s.cl_log("test-all", FAIL_LOG, 1)
    s.cl_log("test-crate-a", "  Executable unittests src/lib.rs (target/debug/deps/crate_a-1)\n"
             "     Running unittests src/lib.rs (target/debug/deps/crate_a-1)\n\nrunning 1 test\ntest tests::one ... ok\n\n"
             "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")
    (s.work / "jobs.json").write_text(json.dumps([{"task": "t1", "prompt": "fix track t1", "role": "red_fixer"}]))
    p = s.run("swarm.py", "jobs.json")
    check(p.returncode == 0, "the fixer's first run", p)
    return fw, app


def claude_calls(s):
    f = s.root / "claude" / "calls.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def case_red_cycle_code_only(s):
    fw, app = setup(s)
    p = s.run("cycle", "b1-run-1", "--fixers", "fixers.txt", "--tracks", "groups.md", "--batch", "b1")
    check(p.returncode == 1, "a failing test leaves work: exit 1", p)
    for t in (fw, app):
        check("cycle b1-run-1: merge red/t1" in git(t, "log", "-3", "--format=%s"), f"red/t1 merged in {t.name}", p)
    keys = [c[:2] for c in s.cl_calls()]
    for k in (["check", "crate-a"], ["check", "all"], ["cargo", "fmt"], ["cargo", "clippy"], ["cargo", "doc"],
              ["test", "crate-a"], ["test", "all"]):
        check(k in keys, f"cl {' '.join(k)} ran: {keys}", p)
    clippy = [c for c in s.cl_calls() if c[:2] == ["cargo", "clippy"]]
    check(any(c[-3:] == ["--", "-D", "warnings"] and "feature-root" in c for c in clippy), f"clippy denies warnings on cl's selection: {clippy}")
    check(any(c[c.index("-p") + 1] == "app" for c in clippy if "--lib" in c), "app clippy names the selection", p)
    j = json.loads((s.work / "runs" / "b1-run-1" / "cycle.json").read_text())
    check(j["tests"]["app"]["failing"] == ["tests::b"], f"failing: {j['tests']['app']}")
    pk = s.work / "runs" / "b1-run-1" / "followup" / "t1.md"
    check(pk.is_file() and "Fixer mode for this round: `code-only`" in pk.read_text() and "tests::b" in pk.read_text(),
          "the packet holds the mode and the failing test", p)
    second = claude_calls(s)[-1]
    check(second["argv"][second["argv"].index("--resume") + 1] == "session-1", "the same fixer is resumed", p)
    check(j["sent"]["t1"]["ok"], f"follow-up ok: {j['sent']}")
    rows = (s.work / "runs" / "cycles.tsv").read_text().splitlines()
    check(rows[0].startswith("label\tstart\tphase") and rows[1].startswith("b1-run-1\t") and rows[1].endswith("\t1\t1"),
          f"cycles.tsv row: {rows}")
    last = p.stdout.strip().splitlines()[-1]
    check(last.startswith("cycle b1-run-1: exit 1; merged 2/2; compile: ok") and "mode code-only" in last, f"summary: {last}")
    ev = [json.loads(l) for l in (s.work / "track" / "events.jsonl").read_text().splitlines()]
    cy = [e for e in ev if e.get("kind") == "cycle"]
    check(len(cy) == 1 and cy[0]["data"]["batch"] == "b1" and cy[0]["data"]["failing"] == 1, f"one cycle event: {cy}")
    # A second cycle with nothing new: the inputs come from the first, the gap is measured.
    p = s.run("cycle", "b1-run-2", "--no-send")
    check(p.returncode == 1 and "merged 2/2" in p.stdout, "second cycle reuses the fixers", p)
    j2 = json.loads((s.work / "runs" / "b1-run-2" / "cycle.json").read_text())
    check(j2["gap_s"] is not None and j2["inputs"]["tracks"].endswith("groups.md"), f"gap and inputs: {j2['gap_s']}, {j2['inputs']}")


def case_fixer_mode_auto(s):
    setup(s, {"pipeline.fixer_mode": "auto", "build.warm_check_s": 60, "build.full_run_s": 50})
    p = s.run("cycle", "r1", "--dry-run")
    check(p.returncode == 0 and "fixer mode build" in p.stdout, "cheap builds give build mode", p)
    p = s.run("cycle", "r1", "--fixers", "fixers.txt", "--tracks", "groups.md", "--no-lint")
    pk = (s.work / "runs" / "r1" / "followup" / "t1.md").read_text()
    check("Fixer mode for this round: `build`" in pk, "the packet names build mode", p)
    s.config({"framework.writing_base": "base", "app.writing_base": "base", "plan.base": "base",
              "pipeline.fixer_mode": "auto", "build.warm_check_s": 900, "build.full_run_s": 900})
    p = s.run("cycle", "r2", "--dry-run")
    check("fixer mode code-only" in p.stdout, "slow builds stay code-only", p)
    p = s.run("render-prompt", "p7-red-fixer", "TRACK=t1", "ROUND=r1", "TASK=t1")
    check("Fixer mode: `code-only`" in p.stdout, "the fixer prompt carries the resolved mode", p)
    s.config({"framework.writing_base": "base", "app.writing_base": "base", "plan.base": "base",
              "pipeline.fixer_mode": "auto", "build.warm_check_s": 60, "build.full_run_s": 50, "build.fw_trial_s": 700})
    p = s.run("cycle", "r3", "--dry-run")
    check("fixer mode code-only" in p.stdout, "slow framework trials alone give code-only", p)


def case_merge_conflict_stops(s):
    fw, app = setup(s)
    s.commit(app, {"app/src/lib.rs": "other\n"}, "integration moved")
    p = s.run("cycle", "r1", "--fixers", "fixers.txt")
    check(p.returncode == 3, "a conflict exits 3", p)
    check(not git(app, "status", "--porcelain", "-uno").strip(), "the merge is aborted; the tree is clean", p)
    check("app/src/lib.rs" in p.stdout and not [c for c in s.cl_calls() if c[0] == "check"], "names the file, compiles nothing", p)


def case_compile_errors_go_to_their_fixer(s):
    fw, app = setup(s)
    s.cl_log("check-crate-a", "crates/a/src/lib.rs:1:1: error[E0425]: cannot find value `x`\n", 101)
    p = s.run("cycle", "r1", "--fixers", "fixers.txt", "--tracks", "groups.md")
    check(p.returncode == 1 and "compile: 1 framework, 0 app errors" in p.stdout, "compile errors", p)
    check(not [c for c in s.cl_calls() if c[0] == "test"], "no tests after a failed compile", p)
    pk = (s.work / "runs" / "r1" / "followup" / "t1.md").read_text()
    check("crates/a/src/lib.rs:1:1: error[E0425]" in pk, "the error goes to the fixer whose commit changed the file", p)


def crate_log(name, test):
    exe = name.replace("-", "_") + "-1"
    return (f"  Executable unittests src/lib.rs (target/debug/deps/{exe})\n"
            f"     Running unittests src/lib.rs (target/debug/deps/{exe})\n\nrunning 1 test\ntest {test} ... ok\n\n"
            "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n")


def case_red_round_runs_each_tracks_crates(s):
    crates = [{"name": f"crate-{x}", "dir": f"crates/{x}"} for x in "abc"]
    fw = s.tree("fw", {".stub-metadata.json": cargo_metadata(crates),
                       **{f"crates/{x}/Cargo.toml": f"[package]\nname = \"crate-{x}\"\n" for x in "abc"},
                       **{f"crates/{x}/src/lib.rs": "\n" for x in "abc"}})
    app = s.tree("app", {"Cargo.toml": "[workspace]\n[workspace.metadata.cl]\nselection = [\"app\"]\n",
                         "app/Cargo.toml": "[package]\nname = \"app\"\n", "app/src/lib.rs": "\n"})
    for t in (fw, app):
        git(t, "branch", "base")
    s.commit(fw, {"crates/c/src/lib.rs": "an earlier batch\n"}, "crate-c changed since the base")
    for task, x in (("t1", "a"), ("t2", "b")):
        git(fw, "switch", "-q", "-c", f"red/{task}", "main")
        s.commit(fw, {f"crates/{x}/src/lib.rs": f"{task} fix\n"}, f"{task} fix")
    git(fw, "switch", "-q", "main")
    s.config({"framework.writing_base": "base", "app.writing_base": "base", "plan.base": "base"})
    (s.work / "fixers.txt").write_text("t1\nt2\n")
    (s.work / "groups.md").write_text("## t1\n\n### tests::a\n\n## t2\n\n### tests::b\n")
    fake_binary(app, "target/debug/deps/app-1", ["tests::a", "tests::b"])
    for x in "abc":
        fake_binary(fw, f"target/debug/deps/crate_{x}-1", [f"{x}::one"])
        s.cl_log(f"test-crate-{x}", crate_log(f"crate-{x}", f"{x}::one"))
    s.cl_log("test-all-no-run", "  Executable app lib (target/debug/deps/app-1)\n")
    s.cl_log("test-all", FAIL_LOG, 1)
    p = s.run("cycle", "r1", "--fixers", "fixers.txt", "--tracks", "groups.md", "--dry-run")
    check("t1: crate-a; t2: crate-b" in p.stdout and "--fw crate-a --fw crate-b" in p.stdout,
          "the dry run lists each red fixer's crates", p)
    p = s.run("cycle", "r1", "--fixers", "fixers.txt", "--tracks", "groups.md", "--no-lint", "--no-send")
    tested = [c[1] for c in s.cl_calls() if c[0] == "test" and c[1] != "all"]
    check(sorted(tested) == ["crate-a", "crate-b"], f"a red round tests only its fixers' crates: {tested}", p)
    s.cl_log("test-all", "  ok app lib: 2 passed, 0 failed, 0 s\ncl: 2 passed, 0 failed, 1 binaries, 0 overflowed stacks, 0 s\n")
    p = s.run("cycle", "r2", "--no-lint", "--no-send")
    tested = [c[1] for c in s.cl_calls() if c[0] == "test" and c[1] != "all"][2:]
    j = json.loads((s.work / "runs" / "r2" / "cycle.json").read_text())
    check(tested == ["crate-a", "crate-b", "crate-c"] and j["tests"]["fw"].get("rest") == ["crate-c"],
          f"a green narrowed round runs the other changed crates before it reports green: {tested}", p)


def case_compile_groups_own_files(s):
    fw, app = setup(s)
    s.commit(app, {f"app/src/{f}.rs": "\n" for f in ("a", "b", "shared")}, "three files")
    errs = s.work / "errors"
    errs.write_text("".join(f"app/src/{f}.rs:{i}:1: error[E0425]: x\n" for f, n in (("a", 4), ("b", 4), ("shared", 1))
                            for i in range(1, n + 1)))
    p = s.run("split-errors.py", str(errs), "2", str(s.work / "groups" / "g"))
    owned = {t: (s.work / "groups" / f"g-{t}.files").read_text().split() for t in (1, 2)}
    owner = next(t for t, fs in owned.items() if "app/src/shared.rs" in fs)
    check(sum("app/src/shared.rs" in fs for fs in owned.values()) == 1, f"one owner for the shared file: {owned}", p)
    for t, fs in owned.items():   # each group edits only its own files, the cause in shared.rs included
        git(app, "switch", "-q", "-c", f"cfix/{t}", "main")
        s.commit(app, {f: f"fixed by group {t}\n" for f in fs}, f"group {t}")
    git(app, "switch", "-q", "main")
    (s.work / "cfix.txt").write_text("".join(f"cfix-g-{t} app:cfix/{t}\n" for t in owned))
    s.cl_log("check-all", "app/src/shared.rs:1:1: error[E0308]: mismatched types\n", 101)
    p = s.run("cycle", "c1", "--fixers", "cfix.txt", "--groups", str(s.work / "groups"), "--no-send")
    check(p.returncode == 1 and "merged 2/2" in p.stdout, "both groups merge without a conflict", p)
    pk = s.work / "runs" / "c1" / "followup" / f"cfix-g-{owner}.md"
    check(pk.is_file() and "app/src/shared.rs:1:1" in pk.read_text(), "the shared file's error goes to its owner", p)

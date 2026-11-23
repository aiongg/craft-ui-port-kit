"""test-run: counts from each binary's own line, crashed and not-run binaries, missing binaries and gone tests."""
import json
import shutil

from lib import FIXTURES, cargo_metadata, check


def fake_binary(tree, rel, tests):
    """A test binary stand-in that lists `tests` for `--list --format terse`."""
    f = tree / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("#!/bin/sh\n" + "".join(f"echo '{t}: test'\n" for t in tests))
    f.chmod(0o755)


def setup(s):
    for f in (FIXTURES / "test-run").iterdir():
        shutil.copy(f, s.root / "cl-logs" / f.name)
    fw = s.tree("fw", {".stub-metadata.json": cargo_metadata([{"name": "crate-a", "dir": "crates/a"}]),
                       "crates/a/Cargo.toml": "[package]\nname = \"crate-a\"\n", "crates/a/src/lib.rs": "\n"})
    app = s.tree("app", {"Cargo.toml": "[workspace]\n"})
    return fw, app


def case_framework_crash_and_not_run(s):
    fw, _ = setup(s)
    fake_binary(fw, "target/debug/deps/crate_a-1", ["tests::one", "tests::two"])
    fake_binary(fw, "target/debug/deps/two-1", ["boom"])
    fake_binary(fw, "target/debug/deps/three-1", ["three"])
    p = s.run("test-run", "fw1", "--fw", "crate-a")
    check(p.returncode == 1, "a crashed binary fails the run", p)
    part = json.loads((s.work / "runs" / "fw1" / "summary.json").read_text())["parts"][0]
    st = {k: (b["status"], b["passed"], b["failed"], b["tests"]) for k, b in part["binaries"].items()}
    check(st == {"unittests src/lib.rs": ("ok", 2, 0, 2), "tests/two.rs": ("crashed", 0, 0, 1),
                 "tests/three.rs": ("not run", 0, 0, 1)}, f"binary states: {st}")
    check("1 crashed, 1 not run" in p.stdout.strip().splitlines()[-1], "summary line counts them", p)


def case_app_missing_binary_and_gone_tests(s):
    _, app = setup(s)
    fake_binary(app, "target/debug/deps/app-1", ["tests::a", "tests::b", "other::tests::c"])
    fake_binary(app, "target/debug/deps/ui-1", ["ui::x", "ui::y"])
    p = s.run("test-run", "run0", "--app", "--baseline")
    check(p.returncode == 0, "clean baseline", p)
    check(json.loads((s.work / "runs" / "baseline.json").read_text()) == {"app": "run0"}, "baseline recorded")
    check((s.work / "runs" / "rounds.tsv").read_text().startswith("0\trun0\t5\t0"), "baseline is round 0")
    check((s.work / "baseline-failures.txt").read_text() == "", "baseline failures written")
    fake_binary(app, "target/debug/deps/app-1", ["tests::a", "tests::b"])   # `mod tests;` of `other` removed
    p = s.run("test-run", "run1", "--app")
    check(p.returncode == 1, "a failing test exits 1", p)
    part = json.loads((s.work / "runs" / "run1" / "summary.json").read_text())["parts"][0]
    check((part["passed"], part["failed"]) == (1, 1), f"counts from cl's line, not doubled: {part['passed']}/{part['failed']}")
    check(part["failing"] == ["tests::b"], f"failing names: {part['failing']}")
    check(part["previous"] == "run0" and part["baseline"] == "run0", f"compared with run0: {part['previous']}, {part['baseline']}")
    check(part["missing"] == ["app ui"], f"missing binary: {part['missing']}")
    check(part["gone"] == ["app lib other::tests::c", "app ui ui::x", "app ui ui::y"], f"gone tests: {part['gone']}")
    md = (s.work / "runs" / "run1" / "compare.md").read_text()
    check("| app ui | missing | ok 2/0, 2 listed |" in md, "compare table", None)
    check("WARNING app: 1 binaries missing, 3 tests gone" in p.stdout, "warns", p)


def case_build_tool_failure(s):
    setup(s)
    s.cl_log("test-all-no-run", "error: failed to select a version for `craft-ui`\n", rc=101)
    (s.root / "cl-logs" / "test-all-no-run.1.log").unlink()
    p = s.run("test-run", "bad", "--app")
    check(p.returncode == 2, "a build failure with no compile error exits 2", p)


def case_no_fail_fast_once(s):
    _, app = setup(s)
    fake_binary(app, "target/debug/deps/app-1", ["tests::a", "tests::b", "other::tests::c"])
    fake_binary(app, "target/debug/deps/ui-1", ["ui::x", "ui::y"])

    def test_call():
        calls = [json.loads(l) for l in (s.root / "cl-logs" / "calls.jsonl").read_text().splitlines()]
        return [c["argv"] for c in calls if c["argv"][:2] == ["test", "all"] and "--no-run" not in c["argv"]][-1]
    s.run("test-run", "r1", "--app")
    check("--no-fail-fast" in test_call(), f"added when cl does not: {test_call()}")
    s.cl_log("--dry-run-test", "cargo test --workspace --no-fail-fast\n")
    s.run("test-run", "r2", "--app")
    check("--no-fail-fast" not in test_call(), f"left out when cl adds it: {test_call()}")

"""compile-gate: every crate checked in one run, errors charged to their crate, a silent nonzero exit is exit 2."""
import json
import shutil

from lib import FIXTURES, cargo_metadata, check, git

PKGS = [{"name": "crate-a", "dir": "crates/a"}, {"name": "crate-b", "dir": "crates/b", "deps": ["crate-a"]},
        {"name": "crate-c", "dir": "crates/c"}, {"name": "crate-d", "dir": "crates/d", "dev": ["crate-c"]},
        {"name": "crate-e", "dir": "crates/e"}]


def framework(s):
    files = {".stub-metadata.json": cargo_metadata(PKGS), "Cargo.toml": "[workspace]\nmembers = [\"crates/*\"]\n",
             "vendor/v/Cargo.toml": "[package]\nname = \"vendored\"\n", "vendor/v/src/lib.rs": "\n"}
    for p in PKGS:
        files[f"{p['dir']}/Cargo.toml"] = f"[package]\nname = \"{p['name']}\"\n"
        files[f"{p['dir']}/src/lib.rs"] = "\n"
    fw = s.tree("fw", files)
    git(fw, "branch", "port/stubs")
    s.commit(fw, {"crates/a/src/lib.rs": "changed\n", "crates/c/src/lib.rs": "changed\n", "vendor/v/src/lib.rs": "x\n"}, "set")
    s.tree("app", {"Cargo.toml": "[workspace]\n"})
    for f in (FIXTURES / "compile-gate").glob("*.log"):
        shutil.copy(f, s.root / "cl-logs" / f.name)
    for k in ("check-crate-a", "check-crate-b", "check-crate-c", "check-crate-d"):
        (s.root / "cl-logs" / f"{k}.rc").write_text("101")
    return fw


def case_every_crate_one_run(s):
    framework(s)
    (s.root / "cl-logs" / "check-crate-d.log").write_text("")
    (s.root / "cl-logs" / "check-crate-d.rc").write_text("0")
    p = s.run("compile-gate", "r1")
    check(p.returncode == 1, "compile errors exit 1", p)
    calls = [c[1] for c in s.cl_calls()]
    check(sorted(calls) == ["crate-a", "crate-b", "crate-c", "crate-d"] and calls.index("crate-a") < calls.index("crate-b"),
          f"dependency order, dependents added, no stop: {calls}", p)
    check(all("--keep-going" in c for c in s.cl_calls()), "every call keeps going")
    sm = json.loads((s.work / "runs" / "r1" / "summary.json").read_text())
    st = {c["crate"]: (c["status"], c["errors"], c["through"]) for c in sm["framework"]["crates"]}
    check(st["crate-a"] == ("failed", 2, []), f"crate-a: {st}")
    check(st["crate-b"] == ("failed-through", 0, ["crate-a"]), f"crate-b: {st}")
    check(st["crate-c"] == ("failed", 1, []), f"crate-c: {st}")
    check(st["crate-d"][0] == "ok", f"crate-d: {st}")
    check(sm["framework"]["errors"] == 3 and sm["framework"]["skipped"] == ["vendored"], f"errors counted once: {sm}")
    check(sm["app"] is None, "the app half waits for a clean framework")
    check(p.stdout.strip().splitlines()[-1].startswith("compile-gate r1: exit 1; framework: 1 ok, 2 failed, 1 failed-through"),
          "summary line", p)


def case_silent_failure_is_tool_failure(s):
    framework(s)
    p = s.run("compile-gate", "r2")
    check(p.returncode == 2, "nonzero exit with no error line exits 2", p)
    check("TOOL FAILURE" in p.stdout and "failed to load manifest" in p.stdout, "names the plain error", p)


def case_app_tool_failure(s):
    framework(s)
    s.cl_log("check-all", "error: no matching package named `craft-x` found\n", rc=101)
    p = s.run("compile-gate", "r3", "--app-only")
    check(p.returncode == 2, "app exit 101 with 0 errors exits 2", p)
    s.cl_log("check-all", "src/main.rs:1:1: error[E0425]: cannot find value `x`\n", rc=101)
    p = s.run("compile-gate", "r4", "--app-only")
    check(p.returncode == 1, "app errors exit 1", p)
    s.cl_log("check-all", "", rc=0)
    p = s.run("compile-gate", "r5", "--app-only")
    check(p.returncode == 0, "clean app exits 0", p)

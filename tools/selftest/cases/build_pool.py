"""build-pool: make seeds a target dir per tree and points each app tree at its slot's framework tree; take hands
out free slots and refuses when none is left; give frees one; no tracked file changes."""
import json
import os

from lib import STUBS, cargo_metadata, check, git

URL = "https://example.invalid/fw"


def setup(s):
    fw = s.tree("fw", {".stub-metadata.json": cargo_metadata([{"name": "craft-ui", "dir": "crates/ui"}]),
                       "Cargo.toml": "[workspace]\n", "crates/ui/Cargo.toml": '[package]\nname = "craft-ui"\n'})
    app = s.tree("app", {".stub-metadata.json": cargo_metadata([{"name": "app", "dir": "app"}]),
                         "Cargo.toml": f'[workspace]\n\n[workspace.dependencies]\ncraft-ui = {{ git = "{URL}" }}\n',
                         "Cargo.lock": f'version = 4\n\n[[package]]\nname = "craft-ui"\nversion = "0.1.0"\n'
                                       f'source = "git+{URL}?rev=abc#abc"\n',
                         "app/Cargo.toml": '[package]\nname = "app"\n'})
    for t in (fw, app):   # a warm target dir beside each integration tree, as cl picks it
        d = t.parent / f"{t.name}-target"
        (d / "debug" / "deps").mkdir(parents=True)
        (d / "CACHEDIR.TAG").write_text("Signature: 8a477f597d28d172789f06886806bc55\n")
        (d / "debug" / "deps" / "libdep-1.rlib").write_text("built\n")
    s.config({"framework.patch_urls": [URL]})
    return fw, app


def case_make_take_give(s):
    fw, app = setup(s)
    env = {"PATH": f"{STUBS}{os.pathsep}{os.environ['PATH']}"}   # seed-target runs `cargo metadata`
    p = s.run("build-pool", "take", "t1")
    check(p.returncode == 1 and "no build pool" in p.stderr, "take without a pool refuses", p)
    p = s.run("build-pool", "make", "2", env=env)
    check(p.returncode == 0, "make 2", p)
    pool = s.work / "trees" / "pool"
    for k in (1, 2):
        for tree in (pool / str(k) / "fw", pool / str(k) / "app" / "tree"):
            check((tree.parent / f"{tree.name}-target" / "debug" / "deps" / "libdep-1.rlib").is_file(),
                  f"{tree}: seeded target dir", p)
            check(git(tree, "status", "--porcelain") == "", f"{tree}: no file changed", p)
        conf = (pool / str(k) / "app" / ".cargo" / "config.toml").read_text()
        check(f'craft-ui = {{ path = "{pool / str(k) / "fw" / "crates" / "ui"}" }}' in conf,
              f"slot {k}'s app tree builds against its own framework tree: {conf}", p)
    p1, p2 = s.run("build-pool", "take", "t1", "--json"), s.run("build-pool", "take", "t2", "--json")
    check(json.loads(p1.stdout)["slot"] == 1 and json.loads(p2.stdout)["slot"] == 2, "two takes, two slots", p2)
    check(json.loads(s.run("build-pool", "take", "t1", "--json").stdout)["slot"] == 1, "a task keeps its slot")
    p = s.run("build-pool", "take", "t3")
    check(p.returncode == 1 and "no free build slot" in p.stderr, "a third take refuses", p)
    tree = pool / "1" / "app" / "tree"
    git(tree, "switch", "-q", "-c", "red/t1")
    (tree / "app" / "Cargo.toml").write_text("changed\n")
    p = s.run("build-pool", "give", "t1")
    check(p.returncode == 1 and "app/Cargo.toml" in p.stderr, "give refuses a tree with uncommitted changes", p)
    git(tree, "checkout", "--", "app/Cargo.toml")
    p = s.run("build-pool", "give", "t1")
    check(p.returncode == 0 and git(tree, "branch", "--show-current").strip() == "", "give frees and detaches", p)
    p = s.run("build-pool", "take", "t3", "--json")
    check(p.returncode == 0 and json.loads(p.stdout)["slot"] == 1, "the freed slot goes to the next task", p)
    for t in (fw, app):
        check(git(t, "status", "--porcelain") == "", f"{t.name} integration tree unchanged")

"""port-set and friends: check.md states racheck's count, apply rejects unmatched blocks, an empty BLOCKED fails,
fix-batch refuses bad lines, track md stays in the workspace, combine-lost exits 1 on a lost line."""
import os
import sys

from lib import TOOLS, check, git


class FakeSheet:
    """The parts of portset.sheet.Sheet that apply_edits, write_check and blocked use."""
    def __init__(self, sid, tree, owned):
        self.id, self._tree, self._owned = sid, tree, set(owned)

    def owned(self):
        return self._owned

    def deleted(self):
        return []

    def fp(self, p):
        return self._tree / p

    def tree(self, repo=None):
        return self._tree

    def repo_of(self, p):
        return "fw"


def portset(s):
    os.environ["PORT_KIT_CONFIG"] = str(s.root / "port.toml")
    sys.path.insert(0, str(TOOLS))
    from portkit import config
    from portkit.portset.context import ctx
    ctx.load(config.load(str(s.root / "port.toml")))
    return ctx


def case_check_md_states_racheck(s):
    portset(s)
    from portkit.portset.checks import write_check
    sh = FakeSheet("set-a", s.root, [])
    write_check(sh, ["scripted: x"], [], None)
    text = (s.work / "sets" / "set-a" / "check.md").read_text()
    check("rust-analyzer: not run (no daemon)" in text, f"no daemon is stated: {text}")
    errs = write_check(sh, [], [], ["compile error (rust-analyzer): a.rs:1 E0425 x"] * 3)
    text = (s.work / "sets" / "set-a" / "check.md").read_text()
    check("rust-analyzer: 3 errors (racheck.md)" in text and len(errs) == 3, f"racheck count in check.md: {text}")


def case_apply_rejects_unmatched_search(s):
    portset(s)
    from portkit.portset.edits import apply_edits
    (s.root / "src").mkdir()
    f = s.root / "src" / "a.rs"
    f.write_text("fn a() {\n    one();\n}\n")
    sh = FakeSheet("set-b", s.root, ["src/a.rs"])
    edits = "@@@ EDIT src/a.rs\n<<<<<<< SEARCH\n    two();\n=======\n}\n>>>>>>> REPLACE\n"
    report, fails = apply_edits(sh, edits)
    check(len(fails) == 1 and "SEARCH matched 0 places" in fails[0], f"SEARCH not in the file fails: {report} {fails}")
    good = "@@@ EDIT src/a.rs\n<<<<<<< SEARCH\n    one();\n=======\n    one();\n    three();\n>>>>>>> REPLACE\n"
    report, fails = apply_edits(sh, good)
    check(not fails and report == ["edited src/a.rs"], f"a matching block applies: {report} {fails}")
    report, fails = apply_edits(sh, good)
    check(not fails and report == ["already applied: src/a.rs"], f"the same block again is already applied: {report} {fails}")


def case_empty_blocked_is_a_failed_write(s):
    portset(s)
    from portkit.portset.write import blocked
    sh = FakeSheet("set-c", s.root, [])
    try:
        blocked(sh, "@@@ BLOCKED\n@@@ END\n")
        raise AssertionError("an empty BLOCKED must fail the command")
    except SystemExit as e:
        check("malformed reply" in str(e.code), f"names the cause: {e.code}")
    check(not (s.work / "sets" / "set-c" / "blocked.md").exists(), "no blocked.md")
    check(blocked(sh, "@@@ BLOCKED\nthe stub lacks X\n@@@ END\n") == "the stub lacks X", "a reason still blocks")


def case_fix_batch_refuses_bad_lines(s):
    (s.work / "f1.md").write_text("finding\n")
    (s.work / "list").write_text("set-a f1.md\nset-b\nset-c missing.md\n")
    p = s.run("fix-batch", "list")
    check(p.returncode == 2 and "set-b (no findings file)" in p.stderr and "set-c missing.md" in p.stderr,
          "bad lines stop the batch", p)
    check(not (s.work / "sets" / "set-a").exists(), "no set ran")


def case_track_md_stays_in_workspace(s):
    p = s.run("track", "md", "--out", str(s.root / "elsewhere.md"))
    check(p.returncode != 0 and not (s.root / "elsewhere.md").exists(), "refuses a path outside the workspace", p)
    p = s.run("track", "md")
    check(p.returncode == 0 and (s.work / "STATUS.md").is_file(), "default path in the workspace", p)


def case_combine_lost_exits_1(s):
    fw = s.tree("fw", {"src/a.rs": "fn a() {}\n"})
    base = git(fw, "rev-parse", "HEAD").strip()
    t = s.work / "trees" / "set-a"
    git(fw, "worktree", "add", "-q", "-b", "port/set/set-a", str(t))
    s.commit(t, {"src/a.rs": "fn a() {}\nfn kept_by_nobody() {}\n"}, "set-a")
    (s.work / "sets" / "set-a").mkdir(parents=True)
    (s.work / "sets" / "set-a" / "base-fw").write_text(base + "\n")
    p = s.run("combine-lost", "set-a", env={"REPO": "fw", "J": str(fw)})
    check(p.returncode == 1 and "LOST set-a src/a.rs: fn kept_by_nobody() {}" in p.stdout, "a lost line exits 1", p)


def case_review_diff_writes_patch(s):
    portset(s)
    from portkit.portset import write
    fw = s.tree("fw", {"src/a.rs": "fn a() {}\n"})
    base = git(fw, "rev-parse", "HEAD").strip()
    t = s.work / "trees" / "set-a"
    git(fw, "worktree", "add", "-q", "-b", "port/set/set-a", str(t))
    s.commit(t, {"src/a.rs": "fn a() {}\nfn added_by_set() {}\n"}, "set-a")
    (s.work / "sets" / "set-a").mkdir(parents=True)
    (s.work / "sets" / "set-a" / "base-fw").write_text(base + "\n")
    sh = FakeSheet("set-a", t, [])
    sh.repos = lambda: ["fw"]
    write.Sheet = lambda sid: sh
    write.cmd_review_diff(type("A", (), {"sets": ["set-a"]})())
    patch = s.work / "sets" / "set-a" / "review-diff.patch"
    check(patch.is_file() and "+fn added_by_set() {}" in patch.read_text(), "review-diff.patch holds the set's change")

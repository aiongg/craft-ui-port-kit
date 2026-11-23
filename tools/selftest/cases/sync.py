"""tools/sync: a clean upstream merge is one merge commit and a syncs.tsv row; a conflict changes nothing and exits
3; after a merge by hand, sync records it."""
from lib import check, git


def setup(s):
    up = s.tree("upstream", {"a.txt": "one\n", "b.txt": "b\n"}, branch="next")
    fw = s.root / "fw"
    git(s.root, "clone", "-q", "-b", "next", str(up), str(fw))
    git(fw, "checkout", "-q", "-b", "port")
    s.config({"framework.repo": str(up), "framework.branch": "next"})
    return up, fw


def rows(s):
    f = s.work / "runs" / "syncs.tsv"
    return [l.split("\t") for l in f.read_text().splitlines()[1:]] if f.exists() else []


def case_clean_merge(s):
    up, fw = setup(s)
    s.commit(fw, {"port.txt": "port\n"}, "port work")
    s.commit(up, {"b.txt": "b2\n"}, "upstream fix")
    r = s.run("sync", "--fw")
    check(r.returncode == 0 and "merged 1 commits" in r.stdout, "merges", r)
    parents = git(fw, "log", "-1", "--format=%P").split()
    check(len(parents) == 2, "one merge commit with two parents", r)
    check(len(rows(s)) == 1 and rows(s)[0][1] == "fw" and rows(s)[0][-1] == "0", f"one row: {rows(s)}", r)


def case_conflict_changes_nothing(s):
    up, fw = setup(s)
    s.commit(fw, {"a.txt": "port\n"}, "port edits a")
    s.commit(up, {"a.txt": "upstream\n"}, "upstream edits a")
    head = git(fw, "rev-parse", "HEAD")
    r = s.run("sync", "--fw")
    check(r.returncode == 3 and "a.txt" in r.stdout and git(fw, "rev-parse", "HEAD") == head, "no change, exit 3", r)
    check(not git(fw, "status", "--porcelain"), "clean tree", r)
    git(fw, "merge", "-q", "--no-ff", "-X", "ours", "-m", "merge by hand", "refs/portkit/upstream/next")
    r = s.run("sync", "--fw")
    check(r.returncode == 0 and "in step" in r.stdout and rows(s)[-1][-1] == "0", "records the merge by hand", r)


def case_cycle_reports_due(s):
    import sys
    from lib import TOOLS
    sys.path.insert(0, str(TOOLS))
    from portkit import config, sync
    up, fw = setup(s)
    s.commit(up, {"b.txt": "b2\n"}, "upstream 1")
    s.commit(up, {"b.txt": "b3\n"}, "upstream 2")
    s.config({"framework.repo": str(up), "framework.branch": "next", "land.sync_after_commits": 1,
              "app.upstream": ""})
    notes = sync.due(config.load(str(s.root / "port.toml")))
    check(notes and notes[0].startswith("sync due: fw is 2 commits behind next"), f"due: {notes}")
    s.config({"framework.repo": str(up), "framework.branch": "next", "land.sync_after_commits": 5, "app.upstream": ""})
    check(sync.due(config.load(str(s.root / "port.toml"))) == [], "under the threshold and synced within a day")

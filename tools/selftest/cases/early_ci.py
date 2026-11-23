"""land/early-ci.sh against scratch bare repos as upstream and fork: without the approval it prints the commands and
pushes nothing; with it, it pushes the scrubbed head and the base branch to the fork alone and opens one draft PR
there through gh; a fork URL that is the upstream is refused."""
import json

from lib import STUBS, check, git


def setup(s, approved):
    up = s.root / "upstream.git"
    seed = s.tree("seed", {"README.md": "framework\n"}, branch="next")
    git(s.root, "clone", "-q", "--bare", str(seed), str(up))
    fork = s.root / "forks" / "me" / "craft-libs.git"
    fork.parent.mkdir(parents=True)
    git(s.root, "clone", "-q", "--bare", str(up), str(fork))
    s.commit(seed, {"crates/a/src/lib.rs": "pub fn a() {}\n"}, "port: add a")
    (s.root / "private.txt").write_text("nothing-matches-this-pattern\n")
    (s.root / "idents.txt").write_text("selftest <selftest@example.invalid>\n")
    s.config({"framework.repo": str(up), "framework.branch": "next", "land.early_ci_fork": str(fork),
              "land.early_ci_approved": approved, "land.private_patterns": str(s.root / "private.txt"),
              "land.known_idents": str(s.root / "idents.txt")})
    s.env.update(PORT_KIT_GH_BIN=str(STUBS / "gh"), STUB_GH_DIR=str(s.root / "gh"))
    return seed, up, fork


def refs(repo):
    return sorted(l.split()[1] for l in git(repo, "for-each-ref", "--format=%(objectname) %(refname)").splitlines())


def gh_calls(s):
    f = s.root / "gh" / "calls.jsonl"
    return [json.loads(l)["argv"] for l in f.read_text().splitlines()] if f.exists() else []


def case_not_approved_prints(s):
    seed, up, fork = setup(s, False)
    before = refs(fork)
    r = s.run("land/early-ci.sh", "fw", str(seed), "next", "pilot")
    check(r.returncode == 0, "exit 0", r)
    check("nothing pushed" in r.stdout and f"push --force {fork} land:refs/heads/port-ci/pilot" in r.stdout
          and "pr create --draft --repo me/craft-libs" in r.stdout, "prints the commands", r)
    check(refs(fork) == before and gh_calls(s) == [], "pushes nothing and calls no gh", r)


def case_approved_pushes_to_fork_only(s):
    seed, up, fork = setup(s, True)
    up_before = {l for l in git(up, "for-each-ref", "--format=%(objectname) %(refname)").splitlines()}
    r = s.run("land/early-ci.sh", "fw", str(seed), "next", "pilot")
    check(r.returncode == 0, "exit 0", r)
    check("refs/heads/port-ci/pilot" in refs(fork), f"scrubbed head on the fork: {refs(fork)}", r)
    check(git(fork, "rev-parse", "port-ci/pilot").strip() == git(seed, "rev-parse", "next").strip(),
          "clean scan: the head is the port's own", r)
    up_after = {l for l in git(up, "for-each-ref", "--format=%(objectname) %(refname)").splitlines()}
    check(up_after == up_before, "the upstream repo is untouched", r)
    calls = gh_calls(s)
    check(len(calls) == 2 and all(c[c.index("--repo") + 1] == "me/craft-libs" for c in calls), f"gh: {calls}", r)
    check(calls[1][:2] == ["pr", "create"] and "--draft" in calls[1], "one draft PR", r)
    (s.root / "gh" / "open.txt").write_text("1\n")
    r = s.run("land/early-ci.sh", "fw", str(seed), "next", "pilot")
    check(r.returncode == 0 and len(gh_calls(s)) == 3 and "updated it" in r.stdout, "a rerun opens no second PR", r)


def case_upstream_as_fork_refused(s):
    seed, up, fork = setup(s, True)
    s.config({"framework.repo": str(up), "land.early_ci_fork": str(up) + "/", "land.early_ci_approved": True,
              "land.private_patterns": str(s.root / "private.txt")})
    r = s.run("land/early-ci.sh", "fw", str(seed), "next", "pilot")
    check(r.returncode == 2 and "never to an upstream" in r.stderr and gh_calls(s) == [], "refused", r)

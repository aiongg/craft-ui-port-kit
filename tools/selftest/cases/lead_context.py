"""lead-context: the kit line says how far the kit checkout is behind its upstream, from git's last fetch."""
import importlib.machinery
import importlib.util

from lib import TOOLS, check, git


def load():
    loader = importlib.machinery.SourceFileLoader("lead_context", str(TOOLS / "lead-context"))
    spec = importlib.util.spec_from_loader("lead_context", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def case_kit_behind(s):
    up = s.tree("kit-upstream", {"README": "one\n"})
    clone = s.root / "kit"
    git(s.root, "clone", "-q", str(up), str(clone))
    git(clone, "fetch", "-q")
    lc = load()
    line = lc.kit_freshness(clone)
    check(line is None, f"a kit in step with a fresh fetch prints nothing: {line}")
    s.commit(up, {"README": "two\n"}, "second")
    git(clone, "fetch", "-q")
    line = lc.kit_freshness(clone)
    check(line is not None and "is 1 commit behind origin/main" in line and "pull --ff-only" in line,
          f"one commit behind after a fetch: {line}")
    check(lc.kit_freshness(s.root) is None, "a directory that is no checkout prints nothing")

"""feature-selection.py: the pin check refuses committed manifests that do not resolve or a lock that does not match
them, reads HEAD (not the working tree), and posts a pin-check event."""
import json

from lib import cargo_metadata, check, git

META = cargo_metadata([{"name": "app", "dir": "app"}])


def events(s, kind):
    f = s.work / "track" / "events.jsonl"
    return [e for e in map(json.loads, f.read_text().splitlines()) if e.get("kind") == kind] if f.exists() else []


def case_pin_check(s):
    app = s.tree("app", {"Cargo.toml": "[workspace]\n"})
    (app / ".stub-metadata.json").write_text(META)    # resolves in the working tree only, not at HEAD
    p = s.run("feature-selection.py")
    check(p.returncode == 3 and "do not resolve" in p.stderr and "port the manifests first" in p.stderr,
          "manifests that do not resolve at HEAD are refused", p)
    check(events(s, "pin-check")[-1].get("ok") is False, "a failed pin-check event")
    s.commit(app, {".stub-metadata.json": META, ".stub-lock-stale": ""}, "pin")
    p = s.run("feature-selection.py")
    check(p.returncode == 3 and "does not match" in p.stderr, "a lock that needs updating is refused", p)
    s.commit(app, {".stub-lock-stale": None}, "lock")
    p = s.run("feature-selection.py")
    check("pin check passed" in p.stderr and "pin check failed" not in p.stderr, "a resolving pin passes", p)
    check(events(s, "pin-check")[-1].get("ok") is True, "an ok pin-check event")
    check(len(git(app, "worktree", "list").splitlines()) == 1, "the temporary worktree is removed")

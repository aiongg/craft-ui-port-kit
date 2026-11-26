"""lead-context: one lead at a time. A second session within the lock's age gets a warning and the lock stays; --take
moves it; a stale lock is replaced; the same session refreshes its own."""
import json
import os

from lib import check


def lock(s):
    return json.loads((s.work / "lead.lock").read_text())


def hook(s, session, *args):
    return s.run("lead-context", *args, stdin=json.dumps({"session_id": session, "source": "startup", "cwd": str(s.work)}))


def case_second_lead_is_warned(s):
    p = hook(s, "lead-a")
    check(p.returncode == 0 and "WARNING" not in p.stdout and lock(s)["session"] == "lead-a", "first session holds it", p)
    p = hook(s, "lead-b")
    check("WARNING" in p.stdout and "lead-a" in p.stdout and lock(s)["session"] == "lead-a", "second is warned, lock kept", p)
    p = hook(s, "lead-a")
    check("WARNING" not in p.stdout, "the holder is not warned", p)
    p = hook(s, "lead-b", "--take")
    check("WARNING" not in p.stdout and lock(s)["session"] == "lead-b", "--take moves the lock", p)


def case_stale_lock_is_replaced(s):
    (s.work / "lead.lock").write_text(json.dumps({"session": "old", "time": 1}))
    p = hook(s, "lead-b")
    check("WARNING" not in p.stdout and lock(s)["session"] == "lead-b", "a stale lock is replaced", p)

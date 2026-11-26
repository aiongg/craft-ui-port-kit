"""collect-logs: sessions of a swarm job whose directory lies outside the workspace are packed, and the count is printed."""
import json
import re
import tarfile

from lib import check


def case_packs_job_sessions_outside_the_workspace(s):
    home = s.root / "home"
    outside = s.root / "elsewhere" / "tree"
    outside.mkdir(parents=True)
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(outside))
    proj = home / ".claude" / "projects" / slug
    proj.mkdir(parents=True)
    (proj / "sess-1.jsonl").write_text(json.dumps({"type": "user", "sessionId": "sess-1"}) + "\n")
    jd = s.work / "swarm" / "jobs" / "jobs" / "k1"
    jd.mkdir(parents=True)
    (jd / "job.json").write_text(json.dumps({"task": "t1", "cwd": str(outside)}))
    (jd / "session").write_text("sess-1")
    (jd2 := s.work / "swarm" / "jobs" / "jobs" / "k2").mkdir()
    (jd2 / "job.json").write_text(json.dumps({"task": "t2"}))
    (jd2 / "session").write_text("sess-missing")
    out = s.root / "out"
    out.mkdir()
    p = s.run("collect-logs", "--out", str(out), env={"HOME": str(home)})
    check(p.returncode == 0 and "1 of 2 swarm job sessions" in p.stdout, "prints how many job sessions were packed", p)
    tgz = next(out.glob("*.tar.gz"))
    with tarfile.open(tgz) as t:
        check(any(n.endswith("sess-1.jsonl") for n in t.getnames()), "the outside session is in the archive", p)

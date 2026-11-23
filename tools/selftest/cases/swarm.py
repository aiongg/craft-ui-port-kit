"""swarm.py: job keys follow input files, roles get their tools, --follow-up resumes the job's session."""
import json

from lib import check


def jobs(s, inputs_text):
    (s.work / "packet.md").write_text(inputs_text)
    (s.work / "jobs.json").write_text(json.dumps([{"task": "rfix-g1", "prompt": "fix the tests in packet.md",
                                                   "role": "red_fixer", "inputs": ["packet.md"]}]))


def calls(s):
    f = s.root / "claude" / "calls.jsonl"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def case_key_follows_inputs(s):
    jobs(s, "test a\n")
    p = s.run("swarm.py", "jobs.json", "--dry-run")
    check(p.returncode == 0, "dry run", p)
    k1 = p.stdout.split("key ")[1].split()[0]
    jobs(s, "test a\ntest b\n")
    k2 = s.run("swarm.py", "jobs.json", "--dry-run").stdout.split("key ")[1].split()[0]
    check(k1 != k2, f"a changed input gives a new key: {k1} {k2}", s.last)


def case_follow_up_resumes(s):
    jobs(s, "test a\n")
    p = s.run("swarm.py", "jobs.json")
    check(p.returncode == 0 and len(calls(s)) == 1, "first call", p)
    allow = calls(s)[0]["argv"][calls(s)[0]["argv"].index("--allowedTools") + 1]
    check("Bash(git commit:*)" in allow and "diag-cut.py" in allow, f"fixer role tools: {allow}")
    (s.work / "packet-2.md").write_text("still failing: test a\n")
    p = s.run("swarm.py", "--follow-up", "rfix-g1", "packet-2.md")
    check(p.returncode == 0, "follow-up ok", p)
    out = json.loads(p.stdout.strip().splitlines()[-1])
    second = calls(s)[1]
    check(second["argv"][second["argv"].index("--resume") + 1] == "session-1", f"resumes session-1: {second['argv']}")
    check(second["prompt"] == "still failing: test a\n", "sends the packet")
    check("Bash(git commit:*)" in second["argv"][second["argv"].index("--allowedTools") + 1], "same tools on resume")
    check(out["ok"] and out["value"] == "reply 2" and out["session_id"] == "session-1", f"result JSON: {out}")
    p = s.run("swarm.py", "--follow-up", "no-such-task", "packet-2.md")
    check(p.returncode == 2 and json.loads(p.stdout)["error"].startswith("no job"), "unknown task exits 2", p)

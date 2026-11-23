"""track usage: the lead's own cost from its session file joins the agents' usage log in the spend."""
import json

from lib import check

USAGE = ("time\tset\tstep\tmodel\tturns\tinput\tcache_write\tcache_read\toutput\tcost_usd\tsecs\n"
         "2026-01-01T10:00\tt1\tjob\tsonnet\t3\t1\t0\t0\t1\t0.600\t10\n"
         "2026-01-01T10:05\tt2\tjob\tsonnet\t3\t1\t0\t0\t1\t0.400\t10\n")


def session(s, sid, cost):
    """A synthetic session file where Claude Code keeps it, with one cost-state record."""
    d = s.root / "claude-config" / "projects" / "-scratch-lead"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.jsonl").write_text(
        json.dumps({"type": "user", "sessionId": sid}) + "\n"
        + json.dumps({"type": "cost-state", "sessionId": sid, "totalCostUSD": cost,
                      "modelUsage": {"model-a": {"costUSD": cost}}}) + "\n")


def case_lead_cost_in_spend(s):
    (s.work / "usage.tsv").write_text(USAGE)
    s.run("track", "phase", "0")
    session(s, "lead-1", 2.5)
    env = {"CLAUDE_CODE_SESSION_ID": "lead-1"}
    p = s.run("track", "usage", "--json", env=env)
    j = json.loads(p.stdout)
    check(p.returncode == 0 and (j["agents_usd"], j["lead_usd"], j["total_usd"]) == (1.0, 2.5, 3.5),
          f"agents plus lead: {j}", p)
    session(s, "lead-1", 3.0)
    j = json.loads(s.run("track", "usage", "--json", env=env).stdout)
    check((j["lead_usd"], j["lead_sessions"]) == (3.0, 1), f"one row per session, the newest cost: {j}", s.last)
    session(s, "lead-2", 1.0)
    j = json.loads(s.run("track", "usage", "--json", env={"CLAUDE_CODE_SESSION_ID": "lead-2"}).stdout)
    check((j["lead_usd"], j["lead_sessions"]) == (4.0, 2), f"a session before a clear stays counted: {j}", s.last)
    j = json.loads(s.run("track", "usage", "--json", env={"CLAUDE_CODE_SESSION_ID": "lead-2", "PORT_KIT_AGENT": "1"}).stdout)
    check(j["sampled"] is None, "an agent's shell records nothing", s.last)
    p = s.run("track", "eta")
    check("spend: $1.00 agents + $4.00 lead (2 sessions) = $5.00" in p.stdout, "track eta shows the spend", p)

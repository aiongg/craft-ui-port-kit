"""Briefs the lead renders for agents carry the common agent rules and fill every placeholder."""
from lib import check


def case_followup_fix_renders(s):
    r = s.run("render-prompt", "p10-followup-fix", "TASK=fix-1", "--strict")
    check(r.returncode == 0 and "{{" not in r.stdout, "p10-followup-fix renders with every placeholder filled", r)
    check("rules/agent-common.md and " in r.stdout and "# Task fix-1" in r.stdout,
          "the brief makes the agent read agent-common.md", r)
    check("seed-target" in r.stdout and "No `sleep`" in r.stdout, "the brief carries the build-tree and wait rules", r)

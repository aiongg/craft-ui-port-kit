"""Briefs the lead renders for agents carry the common agent rules and fill every placeholder."""
from lib import check


def case_followup_fix_renders(s):
    r = s.run("render-prompt", "p10-followup-fix", "TASK=fix-1", "--strict")
    check(r.returncode == 0 and "{{" not in r.stdout, "p10-followup-fix renders with every placeholder filled", r)
    check("rules/agent-common.md and " in r.stdout and "# Task fix-1" in r.stdout,
          "the brief makes the agent read agent-common.md", r)
    check("tools/build-pool take fix-1" in r.stdout and "No bare `sleep`" in r.stdout and "timeout 170" in r.stdout and "end your turn" not in r.stdout, "the brief carries the build-tree and wait rules", r)


def case_app_stub_stage_renders(s):
    r = s.run("render-prompt", "p3-contract-stubs-stage", "STAGE=app", "CRATES=sapp", "TASK=stub-app",
              "PLAN_BASE=abc123", "APP_PLAN_BASE=def456", "--strict")
    check(r.returncode == 0 and "## The app stage" in r.stdout and f"Worktree: {s.root / 'app'}, branch `port/app-base`"
          in r.stdout and "`cl check all`" in r.stdout, "the app stage renders with the app tree, branch and check", r)


def case_minimal_port_prompts_render(s):
    s.config({"plan.base": "abc123", "plan.app_base": "def456"})
    for name, args in (("mp-writer", ["ITEMS=host", "TASK=mp-host", "OUT=/r/mp-host.md"]),
                       ("mp-compile-fix", ["TASK=mp-host", "ROUND=mp-c1"]),
                       ("mp-test-fix", ["TASK=mp-host", "ROUND=mp-t1"])):
        r = s.run("render-prompt", name, *args, "--strict")
        check(r.returncode == 0 and "{{" not in r.stdout and "rules/agent-common.md" in r.stdout
              and "track event finding" in r.stdout, f"{name} renders with every placeholder filled and asks for "
              "framework findings", r)
    r = s.run("render-prompt", "mp-writer", "ITEMS=dock", "TASK=mp-dock", "OUT=/r/mp-dock.md", "--strict")
    check("**dock**" in r.stdout and "install_headless(ctx)" in r.stdout and "app_style(ui)" in r.stdout,
          "the writer prompt names the framework module's functions", r)
    r = s.run("render-prompt", "minimal-port-report.md", "--strict")
    check(r.returncode == 0 and "Framework fix: PR and merged rev" in r.stdout, "the report template renders", r)

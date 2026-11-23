"""The writing commands: tree, bundle, apply, check, racheck, plancheck, run, agent, fix, usage.

Dashboard: tools/port-set wraps every command in `track.recorded("port-set-<command>", task=<set>)`. The commands that
own a set's state (plancheck, run, agent, fix) move its task with `track.status`:

| Moment | State | Note |
|---|---|---|
| The command starts | running | the step and model |
| The plan check leaves DECIDE items (OPEN) | review | the count; the items are in open.md (run) or plancheck.md |
| A standalone plan check leaves no DECIDE item | todo | ready to write |
| The writer answers BLOCKED | blocked, on lead | the reason's first line; blocked.md |
| The writer runs out of turns | blocked, on lead | how to continue (`agent --continue`) |
| Written, scripted check errors or apply failures left | review | the counts; check.md, apply.md |
| Written, scripted check clean | done | rust-analyzer errors, if any, wait for the batch recheck |
| The command fails (claude call, git, a BLOCKED block with no reason) | failed | the error |

The end-of-command event of plancheck is ok unless the command fails; that of run, agent and fix is ok only when the set
ends done. A command module sets `record=False` on a subparser to post no event (quick read-only commands).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from portkit import track

from .bundle import build_bundle, instructions, numbered
from .checks import checks, racheck_set, scripted
from .context import ctx, git
from .edits import apply_edits, blocked_reason, remove, write_apply
from .model import (AGENT_ALLOWED, EDIT_TOOLS, READ_TOOLS, WRITE_NOW, agent_prompt, claude, commit, continue_text,
                    lookup_extra, plan_check, tags_of)
from .sheet import Sheet, writer_sheet


@dataclass
class Outcome:
    """A command's result for its end-of-command dashboard event."""
    text: str
    ok: bool = True
    log: Path | None = None
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------- trees

def make_trees(sheet: Sheet) -> None:
    """One code-only worktree per repo the set writes, on branch port/set/<set>[-<repo>] at the repo's writing base;
    the start commit goes to <set dir>/base-<repo>."""
    ctx.trees.mkdir(parents=True, exist_ok=True)
    for repo in sheet.repos():
        tree = sheet.tree(repo)
        if tree.exists():
            print(f"{tree} exists")
            continue
        r = subprocess.run(["git", "-C", str(ctx.repo_dir(repo)), "worktree", "add", "-q", "-b", sheet.branch(repo),
                            str(tree), ctx.base(repo)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"cannot make {tree}: {r.stderr.strip()}")
        (ctx.set_dir(sheet.id) / f"base-{repo}").write_text(git(tree, "rev-parse", "HEAD").strip() + "\n")
        print(f"{tree} at {ctx.base(repo)}")


def cmd_review_diff(a) -> Outcome:
    """Write <set dir>/review-diff.patch: the set's committed change against its writing base, for the area reviewers
    (their shell runs no `git -C`, which would also allow commits)."""
    done = []
    for sid in a.sets:
        sheet = Sheet(sid)
        parts = []
        for repo in sheet.repos():
            tree = sheet.tree(repo)
            f = ctx.set_dir(sid) / f"base-{repo}"
            if not tree.exists() or not f.exists():
                raise SystemExit(f"{sid}: no tree or base-{repo} for {repo}; run `port-set tree {sid}` first")
            parts.append(f"# repo: {repo} (tree {tree.name})\n" + git(tree, "diff", "--no-color", f.read_text().strip(), "HEAD"))
        out = ctx.set_dir(sid) / "review-diff.patch"
        out.write_text("\n".join(parts))
        done.append(f"{sid}: {out}")
    return Outcome("\n".join(done))


def need_trees(sheet: Sheet) -> None:
    if not all(sheet.tree(r).exists() for r in sheet.repos()):
        make_trees(sheet)


def cmd_tree(a) -> Outcome:
    sheet = Sheet(a.set)
    make_trees(sheet)
    return Outcome(", ".join(str(sheet.tree(r)) for r in sheet.repos()))


def cmd_bundle(a) -> Outcome:
    sheet = Sheet(a.set)
    if a.shared:   # read the base checkouts in place: no worktree or branch is made
        sheet.shared = True
    else:
        need_trees(sheet)
    b = build_bundle(sheet)
    out = ctx.set_dir(sheet.id) / "bundle.md"
    out.write_text(b)
    print(f"{out}: {len(b)} chars, ~{len(b) // 4} tokens")
    return Outcome(f"~{len(b) // 4} tokens", log=out, data={"chars": len(b)})


def cmd_apply(a) -> Outcome:
    sheet = Sheet(a.set)
    need_trees(sheet)
    report, fails = apply_edits(sheet, Path(a.edits).read_text())
    write_apply(sheet, report, fails)
    return Outcome(f"{len(report)} done, {len(fails)} failed", ok=not fails, log=ctx.sets / sheet.id / "apply.md")


def cmd_check(a) -> Outcome:
    sheet = Sheet(a.set)
    need_trees(sheet)
    errs = checks(sheet)
    return Outcome(f"{len(errs)} errors", ok=not errs, log=ctx.sets / sheet.id / "check.md", data={"errors": len(errs)})


def cmd_racheck(a) -> Outcome:
    sheet = Sheet(a.set)
    need_trees(sheet)
    errs = racheck_set(sheet)
    if errs is None:
        raise SystemExit(1)
    return Outcome(f"{len(errs)} rust-analyzer errors", ok=not errs, log=ctx.sets / sheet.id / "racheck.md",
                   data={"errors": len(errs)})


# ---------------------------------------------------------------- state

def blocked(sheet: Sheet, text: str) -> str | None:
    """The writer's BLOCKED reason (written to blocked.md), or None. A BLOCKED block with no reason is a malformed
    reply: the command fails, as for any failed call, and nothing is applied."""
    reason = blocked_reason(text)
    if reason is None:
        return None
    if not reason:
        raise SystemExit(f"{sheet.id}: malformed reply: a BLOCKED block with no reason; nothing applied")
    out = ctx.set_dir(sheet.id) / "blocked.md"
    out.write_text(f"# {sheet.id}: blocked\n\n{reason}\n")
    print(f"BLOCKED: nothing applied; reason in {out}")
    return reason


def first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0][:200]


def end_state(sheet: Sheet, what: str, *, reason=None, out_of_turns=False, continue_cmd=None, errs=(), fails=()) -> Outcome:
    """Move the set's task by the command's exit state; returns the end-of-command outcome."""
    od = ctx.sets / sheet.id
    if reason is not None:
        track.status(sheet.id, "blocked", f"writer answered BLOCKED: {first_line(reason)} (blocked.md)", on="lead")
        return Outcome(f"BLOCKED: {first_line(reason)}", ok=False, log=od / "blocked.md")
    if out_of_turns:
        cont = continue_cmd or f"port-set agent {sheet.id} --continue"
        track.status(sheet.id, "blocked", f"{what}: out of turns; finish with `{cont}`", on="lead")
        return Outcome(f"OUT OF TURNS; finish with `{cont}`", ok=False, log=od / "check.md")
    own = scripted(list(errs))
    ra = len(errs) - len(own)
    counts = {"errors": len(own), "rust_analyzer_errors": ra, "apply_failures": len(fails)}
    if own or fails:
        note = f"{what}; {len(own)} check errors, {len(fails)} apply failures left (check.md, apply.md)"
        track.status(sheet.id, "review", note)
        return Outcome(note, ok=False, log=od / "check.md", data=counts)
    note = f"{what}; check clean" + (f", {ra} rust-analyzer errors wait for the batch recheck" if ra else "")
    track.status(sheet.id, "done", note)
    return Outcome(note, log=od / "check.md", data=counts)


# ---------------------------------------------------------------- model commands

def cmd_plancheck(a) -> Outcome:
    sheet = Sheet(a.set)
    if a.shared:   # a plan check only reads: the shared base checkouts instead of a worktree per set
        sheet.shared = True
    else:
        need_trees(sheet)
    model = a.model or ctx.cfg.require("models.plancheck")
    turns = a.max_turns or ctx.pipeline("plancheck_max_turns")
    track.status(sheet.id, "running", f"plan check ({model})")
    items, _ = plan_check(sheet, model, turns)
    tags = tags_of(items)
    print(f"plancheck {sheet.id}: " + (", ".join(f"{k} {v}" for k, v in tags.items()) if items else "clear"))
    log = ctx.sets / sheet.id / "plancheck.md"
    if tags["DECIDE"]:
        track.status(sheet.id, "review", f"plan check: {tags['DECIDE']} DECIDE items open (plancheck.md)")
        return Outcome(f"{tags['DECIDE']} DECIDE open", log=log, data=tags)
    track.status(sheet.id, "todo", f"plan check: STUB {tags['STUB']}, RULE {tags['RULE']}; ready to write"
                 if items else "plan check clear; ready to write")
    return Outcome("clear" if not items else f"STUB {tags['STUB']}, RULE {tags['RULE']}", log=log, data=tags)


def cmd_run(a) -> Outcome:
    """bundle -> (plan check ->) one write call -> apply -> check -> at most --repairs repair calls."""
    sheet = Sheet(a.set)
    need_trees(sheet)
    model = a.model or ctx.cfg.require("models.write")
    turns = a.max_turns or ctx.pipeline("run_max_turns")
    repairs = ctx.pipeline("repairs") if a.repairs is None else a.repairs
    od = ctx.set_dir(sheet.id)
    bundle = build_bundle(sheet)
    (od / "bundle.md").write_text(bundle)
    print(f"bundle: ~{len(bundle) // 4} tokens")
    track.status(sheet.id, "running", f"write ({model})")
    lookup = lookup_extra()
    if not a.skip_plancheck:
        items, pc = plan_check(sheet, model, ctx.pipeline("plancheck_max_turns"))
        n = tags_of(items)["DECIDE"]
        if n:
            (od / "open.md").write_text(f"# {sheet.id}: open before writing\n\n{items}\n")
            print(f"OPEN: not written; decide the items in {od / 'open.md'}, fix the sheet, then run again "
                  "(--skip-plancheck once they are decided)")
            track.status(sheet.id, "review", f"plan check: {n} DECIDE items open (open.md)")
            return Outcome(f"OPEN: {n} DECIDE items", ok=False, log=od / "open.md")
        reply = claude(WRITE_NOW, sheet, model, READ_TOOLS, turns, "write", extra=lookup, resume=pc.session)
    else:
        reply = claude(bundle, sheet, model, READ_TOOLS, turns, "write", extra=lookup)
    (od / "edits-1.md").write_text(reply.text)
    if (reason := blocked(sheet, reply.text)) is not None:
        return end_state(sheet, "write", reason=reason)
    report, fails = apply_edits(sheet, reply.text)
    fails = write_apply(sheet, report, fails)
    commit(sheet, f"{sheet.id}: written from its sheet")   # racheck reads the set's changes from its commits
    errs = checks(sheet)
    for n in range(1, repairs + 1):
        if not fails and not errs:
            break
        named = "\n".join(fails + errs)
        files = sorted(p for p in sheet.owned() if sheet.fp(p).exists() and p in named)
        texts = "\n\n".join(f"## File {p} (current text)\n\n{numbered(sheet.fp(p).read_text().splitlines())}"
                            for p in files)
        prompt = (instructions(sheet) + f"\n\n## Your sheet ({sheet.id})\n\n{writer_sheet(sheet.text)}\n\n## Repair\n\n"
                  "Your edits were applied. These problems remain; fix only them, with blocks against the current text "
                  "below.\n\n### Apply failures\n\n" + ("\n\n".join(fails) or "none") + "\n\n### Check errors\n\n"
                  + ("\n\n".join(errs) or "none") + "\n\n" + texts)
        reply = claude(prompt, sheet, model, READ_TOOLS, turns, f"repair-{n}", extra=lookup)
        (od / f"edits-{n + 1}.md").write_text(reply.text)
        if (reason := blocked(sheet, reply.text)) is not None:
            return end_state(sheet, f"repair {n}", reason=reason)
        report, fails = apply_edits(sheet, reply.text)
        fails = write_apply(sheet, report, fails)
        commit(sheet, f"{sheet.id}: repair {n}")
        errs = checks(sheet)
    print(f"done: {od}")
    return end_state(sheet, "written", out_of_turns=reply.out_of_turns, errs=errs, fails=fails)


def cmd_agent(a) -> Outcome:
    """The set written by an autonomous `claude -p` agent with edit tools; --continue finishes an earlier agent's
    committed work."""
    sheet = Sheet(a.set)
    need_trees(sheet)
    model = a.model or ctx.cfg.require("models.write")
    turns = a.max_turns or ctx.pipeline("agent_max_turns")
    od = ctx.set_dir(sheet.id)
    (od / "sheet.md").write_text(writer_sheet(sheet.text) + "\n")
    prompt = agent_prompt(sheet)
    if a.cont:
        prompt += continue_text(sheet)
        (od / "agent-prompt-continue.md").write_text(prompt)
    else:
        (od / "agent-prompt.md").write_text(prompt)
        for p in sheet.deleted():
            remove(sheet, p)
    label = "agent-cont" if a.cont else "agent"
    track.status(sheet.id, "running", f"{'agent continue' if a.cont else 'agent write'} ({model})")
    reply = claude(prompt, sheet, model, EDIT_TOOLS, turns, label,
                   extra=("--permission-mode", "acceptEdits", "--allowedTools", AGENT_ALLOWED))
    commit(sheet, f"{sheet.id}: {'finished' if a.cont else 'written'} by an agent")   # racheck reads the commits
    errs = checks(sheet)
    return end_state(sheet, "finished by an agent" if a.cont else "written by an agent",
                     out_of_turns=reply.out_of_turns, errs=errs)


def named_paths(text: str) -> set[str]:
    """Workspace paths a findings file names in full, line suffixes dropped."""
    return set(re.findall(r"\b((?:crates|apps|tools|vendor)/[\w./-]+\.(?:rs|toml|md|svg))", text))


def cmd_fix(a) -> Outcome:
    """One call that fixes review findings on a written set: the bundle of the set's current text plus the findings."""
    sheet = Sheet(a.set)
    need_trees(sheet)
    model = a.model or ctx.cfg.require("models.fix")
    turns = a.max_turns or ctx.pipeline("fix_max_turns")
    od = ctx.set_dir(sheet.id)
    findings = Path(a.findings).read_text()
    label = Path(a.findings).stem
    prompt = (build_bundle(sheet) + "\n## Review findings to fix\n\nYour set is already written: the files above show the "
              "current text. A review found these problems. Fix only them, with blocks against the current text; every "
              "other line stays as it is. Files outside the set's Files table that a finding names by full path may be "
              "edited too (read them first). A finding you cannot fix as asked without a design decision: answer "
              "BLOCKED.\n\n" + findings)
    (od / f"{label}-prompt.md").write_text(prompt)
    track.status(sheet.id, "running", f"review fix {label} ({model})")
    reply = claude(prompt, sheet, model, READ_TOOLS, turns, f"fix-{label}", extra=lookup_extra())
    (od / f"edits-{label}.md").write_text(reply.text)
    if (reason := blocked(sheet, reply.text)) is not None:
        return end_state(sheet, f"review fix {label}", reason=reason)
    report, fails = apply_edits(sheet, reply.text, named_paths(findings))
    write_apply(sheet, report, fails)
    commit(sheet, f"{sheet.id}: review fixes ({label})")
    errs = checks(sheet)
    print(f"done: {od}")
    return end_state(sheet, f"review fix {label}", out_of_turns=reply.out_of_turns,
                     continue_cmd=f"port-set fix {sheet.id} {a.findings} --max-turns <more>", errs=errs, fails=fails)


# ---------------------------------------------------------------- usage

def cmd_usage(a) -> None:
    log = ctx.usage_log
    if not log.exists():
        print("no calls yet")
        return None
    lines = log.read_text().splitlines()
    rows = [l.split("\t") for l in lines[1:] if l.strip()]
    if a.set:
        rows = [r for r in rows if len(r) > 1 and r[1] == a.set]
    print(lines[0])
    for r in rows:
        print("\t".join(r))
    cost = sum(float(r[9]) for r in rows if len(r) > 9 and r[9].replace(".", "", 1).isdigit())
    print(f"# {len(rows)} calls, ${cost:.2f}")
    return None


# ---------------------------------------------------------------- command line

def register(sub) -> None:
    """Add the writing commands. Defaults for --model and --max-turns come from port.toml when the command runs."""
    for name, func, doc in (("tree", cmd_tree, "create the set's code-only worktrees (one per repo it writes)"),
                                                        ("check", cmd_check, "scripted self-check of the set's trees (check.md)"),
                            ("racheck", cmd_racheck, "rust-analyzer errors in the files the set committed (racheck.md)")):
        s = sub.add_parser(name, help=doc)
        s.add_argument("set")
        s.set_defaults(func=func, owns_state=False)
    s = sub.add_parser("review-diff", help="write each set's diff against its writing base to review-diff.patch")
    s.add_argument("sets", nargs="+", metavar="SET")
    s.set_defaults(func=cmd_review_diff, owns_state=False)
    s = sub.add_parser("bundle", help="write the set's one-file context bundle (bundle.md)")
    s.add_argument("set")
    s.add_argument("--shared", action="store_true",
                   help="read the base checkouts (racheck.fw_base, racheck.app_base) in place; make no worktree or branch")
    s.set_defaults(func=cmd_bundle, owns_state=False)
    s = sub.add_parser("apply", help="apply an edits file (EDIT/NEW/DELETE blocks) to the set's trees")
    s.add_argument("set")
    s.add_argument("edits")
    s.set_defaults(func=cmd_apply, owns_state=False)

    s = sub.add_parser("plancheck", help="one call on the write bundle listing what the sheet leaves open")
    s.add_argument("set")
    s.add_argument("--model", help="default models.plancheck")
    s.add_argument("--max-turns", type=int, help="default pipeline.plancheck_max_turns")
    s.add_argument("--shared", action="store_true", help="read the shared base checkouts, no per-set worktree")
    s.set_defaults(func=cmd_plancheck, owns_state=True)

    s = sub.add_parser("run", help="bundle -> plan check -> one write call -> apply -> check -> repair calls")
    s.add_argument("set")
    s.add_argument("--model", help="default models.write")
    s.add_argument("--max-turns", type=int, help="default pipeline.run_max_turns")
    s.add_argument("--repairs", type=int, help="default pipeline.repairs")
    s.add_argument("--skip-plancheck", action="store_true", help="write at once (plan check and decisions done)")
    s.set_defaults(func=cmd_run, owns_state=True)

    s = sub.add_parser("agent", help="the set written by an autonomous agent with edit tools")
    s.add_argument("set")
    s.add_argument("--model", help="default models.write")
    s.add_argument("--max-turns", type=int, help="default pipeline.agent_max_turns")
    s.add_argument("--continue", dest="cont", action="store_true",
                   help="finish a set an earlier agent left incomplete (its work is committed)")
    s.set_defaults(func=cmd_agent, owns_state=True)

    s = sub.add_parser("fix", help="one call that fixes review findings on the written set")
    s.add_argument("set")
    s.add_argument("findings")
    s.add_argument("--model", help="default models.fix")
    s.add_argument("--max-turns", type=int, help="default pipeline.fix_max_turns")
    s.set_defaults(func=cmd_fix, owns_state=True)

    s = sub.add_parser("usage", help="print the usage log (every model call's tokens and cost)")
    s.add_argument("set", nargs="?", help="only this set's calls")
    s.set_defaults(func=cmd_usage, owns_state=False, record=False)

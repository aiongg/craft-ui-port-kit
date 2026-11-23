"""Model calls: one `claude -p` per call, logged in the usage log and on the set's dashboard task.

Usage log (work.usage_log), tab-separated with a header line:
  time  set  step  model  turns  input  cache_write  cache_read  output  cost_usd  secs
`step` is the call's label (plancheck, write, repair-N, agent, agent-cont, fix-<findings>). Each call also posts a
`model-call` event on the set's task with the same numbers.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass

from portkit import config as _config
from portkit import track

from .bundle import build_bundle, task_text
from .context import PORTING_RULES, ctx, git
from .sheet import Sheet

USAGE_HEAD = "time\tset\tstep\tmodel\tturns\tinput\tcache_write\tcache_read\toutput\tcost_usd\tsecs\n"
# The rust-analyzer LSP plugin starts a rust-analyzer on the whole workspace for every agent that edits (several GB
# each); writers get diagnostics from racheck's one shared daemon per repo instead.
SETTINGS = '{"enabledPlugins":{"rust-analyzer-lsp@claude-plugins-official":false}}'
READ_TOOLS = "Read,Bash,Grep,Glob"
EDIT_TOOLS = "Read,Edit,Write,Bash,Glob,Grep"
AGENT_ALLOWED = ("Read,Edit,Write,Glob,Grep,Bash(git grep:*),Bash(git show:*),Bash(git log:*),Bash(grep:*),Bash(rg:*),"
                 "Bash(ls:*),Bash(sed -n:*)")


@dataclass
class Reply:
    text: str
    session: str | None
    turns: int | None
    out_of_turns: bool
    cost: float


def lookup_extra() -> tuple[str, str]:
    return ("--allowedTools", ctx.lookup_tools)


def claude(prompt: str, sheet: Sheet, model: str, tools: str, max_turns: int, label: str, extra=(),
           resume=None) -> Reply:
    """One `claude -p` call in the set's own tree. Its session is saved, so a later call can resume it (its context then
    comes from the prompt cache) and `tools/collect-logs` can send it for review; resume: continue that session with
    this prompt."""
    od = ctx.set_dir(sheet.id)
    env = dict(os.environ, CLAUDE_CODE_MAX_OUTPUT_TOKENS="64000")
    # A headless writer is not the terminal pane it was started from; hooks that read these would report as that pane.
    for k in ("TMUX", "TMUX_PANE"):
        env.pop(k, None)
    env[_config.ENV_AGENT] = "1"
    dirs = [a for r in sheet.repos()[1:] for a in ("--add-dir", str(sheet.tree(r)))]
    for repo in ("fw", "app"):   # the base checkout of a repo the set does not write: the code it calls or moves
        if repo not in sheet.repos() and ctx.ref_tree(repo).exists():
            dirs += ["--add-dir", str(ctx.ref_tree(repo))]
    persist = ["--resume", resume] if resume else []
    cmd = ["claude", "-p", "--model", model, "--tools", tools, "--strict-mcp-config", "--output-format", "json",
           "--settings", SETTINGS, *persist, "--max-turns", str(max_turns), *dirs, *extra]
    t0 = time.time()
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=str(sheet.tree()), env=env)
    secs = time.time() - t0
    try:
        d = json.loads(r.stdout)
        if isinstance(d, list):
            d = next((x for x in reversed(d) if x.get("type") == "result"), d[-1])
    except (json.JSONDecodeError, IndexError):
        (od / f"{label}.err").write_text(r.stdout + r.stderr)
        raise SystemExit(f"claude call failed; see {od}/{label}.err")
    (od / f"{label}.json").write_text(json.dumps(d, indent=1))
    u = d.get("usage", {}) or {}
    cost = float(d.get("total_cost_usd", 0) or 0)
    turns = d.get("num_turns")
    nums = {"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}
    row = [time.strftime("%Y-%m-%dT%H:%M"), sheet.id, label, model, str(turns), *(str(v) for v in nums.values()),
           f"{cost:.3f}", f"{secs:.0f}"]
    log = ctx.usage_log
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text(USAGE_HEAD)
    with log.open("a") as fh:
        fh.write("\t".join(row) + "\n")
    out_of_turns = d.get("subtype") == "error_max_turns"
    summary = (f"{label}: {turns} turns, out {nums['output']}, cache read {nums['cache_read']}, ${cost:.2f}, "
               f"{secs:.0f} s")
    print(summary)
    track.event("model-call", f"{summary} ({model})", task=sheet.id,
                data={"step": label, "model": model, "turns": turns, **nums, "cost_usd": round(cost, 3),
                      "seconds": round(secs), "out_of_turns": out_of_turns})
    if out_of_turns:
        print(f"{label}: OUT OF TURNS ({max_turns}); no reply")
    return Reply(d.get("result") or "", d.get("session_id"), turns, out_of_turns, cost)


def commit(sheet: Sheet, message: str) -> None:
    for repo in sheet.repos():
        tree = sheet.tree(repo)
        git(tree, "add", "-A")
        if subprocess.run(["git", "-C", str(tree), "diff", "--cached", "--quiet"]).returncode == 0:
            continue   # nothing staged: nothing to record
        # Set trees are never pushed (landing re-signs), so signing is off; any other failure (a hook) stops the command.
        r = subprocess.run(["git", "-C", str(tree), "-c", "commit.gpgsign=false", "commit", "-qm", message],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"git commit failed in {tree}: {(r.stderr or r.stdout).strip()}")


# ---------------------------------------------------------------- plan check

PLANCHECK = """
## Before writing: plan check

Do not write code in this reply. Check your sheet against the files above and list only what would make you guess
while writing. Look things up first: when the bundle doesn't show a type, signature, constructor or caller, Read the
file or grep for it (several lookups are fine). Anything a lookup settles is not an item: use what you found. List:

- A design choice the sheet leaves open that changes behaviour or structure.
- A file you must edit that is not in your Files table.
- A sheet statement the code contradicts.
- An instruction that breaks the code rules (a second copy of an existing mechanism, a workaround, old code left
  beside new, a fact inferred from side effects).

Label each item with exactly one tag:

- [STUB] the base already has what a sheet row asks (the contract stubs wrote it): nothing to decide, say what is there.
- [RULE] one option follows from the code rules, the contract or the sheet itself: name that rule or source and the
  option it picks. Only when a reader of the rules would pick the same option without asking.
- [DECIDE] the options are all defensible, or picking one changes another set's files or the contract: name the
  options, the files and sets each one touches, and which you would pick.

Every item rests on what you looked up: a fact you have not confirmed with Read or grep is not an item yet, so look
it up first; never list something "not confirmed".

Always DECIDE, whatever you would pick: a fallback or second path beside an existing mechanism; a hash, cache, guard or
flag standing in for a signal that does not exist; a visibility or API change made only so a test can reach an item;
a choice that depends on the shape of another set's item beyond the signature your sheet or contract rows give. When
you are unsure between RULE and DECIDE, use DECIDE.

Not DECIDE: an item where the code rules, the contract or the sheet name the option outright (for example a library
crate reached through the `{facade}` facade, which holds every library crate): that is RULE. A call into another set's
item that your sheet or contract rows give a signature for, or that you would write with `// PLAN: assumed <signature>`
(the writer rules settle it: RULE at most); an item where you say yourself that no choice is open or that it does not
block (STUB, RULE or leave it out).

Reply in this format and nothing else:

@@@ ITEMS
- [TAG] <where (sheet section or file:line)>: <what>; <the option or options>
@@@ END

or, when nothing is open:

@@@ CLEAR
"""

WRITE_NOW = "Nothing is open. Write the set now: reply with the blocks only, in the bundle's output format."


def plan_check(sheet: Sheet, model: str, max_turns: int) -> tuple[str, Reply]:
    """One call on the write bundle (same prefix, so the write call that resumes it reuses its cache). Writes
    plancheck.md; returns the open items ("" when clear) and the reply."""
    prompt = build_bundle(sheet) + PLANCHECK.replace("{facade}", ctx.facade)
    reply = claude(prompt, sheet, model, READ_TOOLS, max_turns, "plancheck", extra=lookup_extra())
    (ctx.set_dir(sheet.id) / "plancheck.md").write_text(reply.text)
    m = re.search(r"^@@@ ITEMS\s*\n(.*?)(?:^@@@ END|\Z)", reply.text, re.M | re.S)
    return (m.group(1).strip() if m else ""), reply


def tags_of(items: str, own: str | None = None) -> dict[str, int]:
    """Item counts per tag. A RULE item that rests on another set (it names that set's id, or carries a
    `PLAN: assumed` marker) counts as DECIDE: a reader cannot settle it from the rules alone."""
    ids = {p.stem for p in ctx.sheets.glob("*.md")} - {own}
    counts = dict.fromkeys(("STUB", "RULE", "DECIDE"), 0)
    for block in re.split(r"^(?=- \[(?:STUB|RULE|DECIDE)\])", items, flags=re.M):
        m = re.match(r"- \[(STUB|RULE|DECIDE)\]", block)
        if not m:
            continue
        tag = m.group(1)
        if tag == "RULE" and ("PLAN: assumed" in block
                              or any(re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", block) for i in ids)):
            tag = "DECIDE"
        counts[tag] += 1
    return counts


# ---------------------------------------------------------------- agent mode

def agent_prompt(sheet: Sheet) -> str:
    od = ctx.sets / sheet.id
    app_note = ""
    if "app" not in sheet.repos():
        app_note = (f"\n{ctx.app_name}'s source at its writing base is in {ctx.ref_tree('app')} (read only): read the "
                    "code a row moves from there.")
    others = "".join(f"\nFiles of the {r} repo are in {sheet.tree(r)} (tagged ({r}) in the sheet, or found only there)."
                     for r in sheet.repos()[1:])
    return f"""Do not start subagents or workflows. Do not run cargo or any build.

You are the writer of set `{sheet.id}` of the {ctx.app_name} port, working in this git worktree (code only, no builds).{others}
Your plan is the sheet {od / "sheet.md"}: read it in full first, then the set's decisions {od / "decisions.md"} in full if that file exists (where a decision differs from the sheet, the decision holds). Contract rows are in {ctx.parts}/*.md (grep for the ids). Read the code rules in {PORTING_RULES} (the "Code" section and the rules on tests apply).{app_note}

{task_text(sheet)}
Edit the files directly with your tools. Bash runs only the read commands you are allowed (git grep/show/log, grep, rg, ls, sed -n); reach framework crates through the `{ctx.facade}` facade (`{ctx.facade}::<module>::..`), never by crate name; match a `#[non_exhaustive]` struct variant with `..`; make bulk changes with Edit (`replace_all` for repeated text), never with perl, sed -i, xargs or a script, and never ask for permission to run one: a request ends your round unanswered. Files the sheet marks `delete` are deleted for you. When done, reply with a short list of what you wrote and any `// PLAN:` notes."""


def continue_text(sheet: Sheet) -> str:
    d = ctx.sets / sheet.id
    return (f"\n\nAn earlier writer of this set ran out of turns. Its work is committed in this tree: read "
            f"`git show --stat HEAD` and `git log --oneline -5` first, and keep what it wrote. What is left: the Errors "
            f"section of {d}/check.md (untouched rows, missing tests) and the errors in {d}/racheck.md under this set's "
            "own files. Finish exactly those, plus any row of the Files or Tests tables a file you open shows is "
            "unfinished. Do not reread or rewrite finished files beyond what the remaining work needs.\n")

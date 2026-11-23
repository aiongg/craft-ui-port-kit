#!/usr/bin/env python3
"""plan-rebuild.py: rebuild the phase 2 plan files from the sheets and the contract parts.

usage: plan-rebuild.py [--config PORT.TOML]

Writes, keeping the previous version of each as <name>.before-reconcile once:
  work.ownership           a summary table (Set | Repo | Model | Files | Write | Delete | Implements | Waits on) from
                           every sheet's head and Files table, then a `### <set>` section per set: its sheet and files
  <work.plan>/contract.md  the parts of work.parts joined in file order, 00-head.md first
  <work.plan>/sizing.md    sets by repo and model, files by action, lines to write and delete by repo and area, the
                           write split (framework production, app production, test files), test verdict totals,
                           and the sets that developer-questions.md names
and runs `coverage.py --from sheets` from work.dir (it writes <work.plan>/eval-coverage.md). Code moved between
crates is not split out: the size audit judges that in eval-size.md.
Before that it guards the test verdicts: <work.plan>/verdicts.tsv holds every sheet's Tests rows as of the last
rebuild (the collation writes the first one). Each sheet whose rows fell since then is named with the job that owns
it (its group in <work.plan>/fix/groups.json), and each dropped row goes back into the sheet's Tests table unless a
line of that job's log (fix/logs/<job>.md) names the test with `delete` or `move`. Then it writes verdicts.tsv again
from the sheets as they are. These are listed under `verdict_drops`, not as checks.
Checks, listed under `checks`: a sheet that does not parse, a path in two sheets, a contract id twice, a Writer
whose sheet does not list the item, an id a sheet writes or calls that no part defines.

tools/render-prompt runs the same rebuild for `--workflow-args phase2-reconcile --stage evaluate`.
Prints the summary as JSON: {written, parse_failures, gaps, coverage, checks, verdict_drops, totals}.
Exit 0 when there are no checks and no coverage gaps, 1 otherwise, 2 for a config error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, planfix, track  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    try:
        cfg = config.load(a.config)
    except config.ConfigError as e:
        print(f"plan-rebuild.py: {e}", file=sys.stderr)
        return 2
    with track.recorded("plan-rebuild") as rec:
        out = planfix.rebuild(cfg)
        clean = not out["checks"] and not out["gaps"] and "failed" not in out["coverage"]
        line = (f"{out['totals']['sets']} sets, write {out['totals']['write']}, delete {out['totals']['delete']}; "
                f"{len(out['checks'])} check findings; coverage gaps {out['gaps']}")
        rec.result(line, data=out["totals"], ok=clean)
    print(f"plan-rebuild.py: {line}", file=sys.stderr)
    for d in out["verdict_drops"]:
        print(f"  verdicts: {planfix.drop_line(d)}", file=sys.stderr)
    for c in out["checks"]:
        print(f"  {c}", file=sys.stderr)
    print(json.dumps(out))
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())

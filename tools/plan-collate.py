#!/usr/bin/env python3
"""plan-collate.py: sort the phase 2 reconcile's requests into one inbox per set, contract part and routing job.

usage: plan-collate.py [--config PORT.TOML]

Reads <work.plan>/fix/requests/*.md (tables whose first header cell starts with "To": `To | Path | What`),
<work.plan>/fix/logs/contract-*.md (rows whose first cell is a contract id, "## Reconcile" sections included) and the
must-fix items of each area's newest re-evaluation, <work.plan>/eval-<area>-r<n>.json. Each must-fix item is checked
against templates/eval-result.schema.json; an item that fails is rejected and listed, the rest are routed like
requests. Routing by the To cell:
  a set id                 inbox/<set>.md (the set needs a sheet in work.sheets)
  `contract <id>`          inbox/contract-NN.md of the part in work.parts that holds the id
  unowned, lead, ownership inbox/route-1.md or route-2.md, alternating by path, every row of one path together
A contract change-log row goes to every set whose sheet writes or calls its item, and to every set the row names.
Rows no inbox takes, with the reason, and the rejected must-fix items go to inbox/unrouted.md. The sets with rows are
grouped four to a group per area (ids `<area>-g<n>`) in <work.plan>/fix/groups.json. Each run replaces inbox/.

tools/render-prompt runs the same collation for `--workflow-args phase2-reconcile --stage contract|sheets`.
Prints the summary as JSON: {groups, routes, parts, unrouted, rejected, bad_sheets, inbox, counts}.
Exit 0 when it collated (unrouted and rejected rows are counted, not fatal), 1 when <work.plan>/fix has no
requests/ or logs/, 2 for a config error.
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
        print(f"plan-collate.py: {e}", file=sys.stderr)
        return 2
    with track.recorded("plan-collate") as rec:
        try:
            out = planfix.collate(cfg)
        except FileNotFoundError as e:
            print(f"plan-collate.py: {e}", file=sys.stderr)
            rec.result(str(e), ok=False)
            return 1
        line = (f"{sum(g['rows'] for g in out['groups'])} set rows in {len(out['groups'])} groups, "
                f"{len(out['parts'])} contract parts, {len(out['routes'])} routing inboxes; "
                f"{out['unrouted']} unrouted, {out['rejected']} must-fix items rejected")
        rec.result(line, log=str(Path(out["inbox"]) / "unrouted.md"), data=out["counts"])
    print(f"plan-collate.py: {line}", file=sys.stderr)
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

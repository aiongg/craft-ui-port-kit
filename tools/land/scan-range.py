#!/usr/bin/env python3
"""scan-range.py: scan the commits of a range for anything that must not leave the machine.

usage: scan-range.py REPO RANGE [--idents FILE] [--private FILE] [--config PORT.TOML]

REPO is a git clone, RANGE any `git log` range (`base..head`). The scan covers the author and committer of every
commit, its message, and every line the commit adds, against two pattern sets (tools/portkit/scrub.py): the generic
shapes that ship with the kit (home, cache and scratch paths, emails other than noreply, IPv4 addresses other than
127.0.0.1, private host name suffixes) and your private patterns file (`land.private_patterns`: names, handles,
hosts, local tool and tree names). The private file is required: a scan without it checks no names.

An identity listed in the idents file (`--idents`, else `land.known_idents`; one `Name <email>` per line) is accepted
without a pattern check.

Output, one line per hit: `pattern<TAB>commit<TAB>where<TAB>text`, where `where` is IDENT, MESSAGE or the file path.
Then `== summary ==` (hits and files per pattern) and `== idents ==` (every identity, marked known or not). Private
patterns are shown as `private:<line number>`, never by their text, so a report names no one.
Exit 0 when the range is clean, 1 when there are hits, 2 for a usage or setup error. Posts one `scan` event.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portkit import config, scrub, track  # noqa: E402

MESSAGE_WIDTH = 140
LINE_WIDTH = 160


def commits(repo: str, rng: str):
    """Yield (short sha, author, committer, message lines, [(file, line number, added line)])."""
    out = scrub.git(repo, "log", "--reverse", "-p", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                    "--format=%x01%H%x02%an <%ae>%x02%cn <%ce>%x02%B%x03", rng).decode(errors="replace")
    for chunk in out.split("\x01")[1:]:
        head, _, diff = chunk.partition("\x03")
        sha, author, committer, msg = head.split("\x02", 3)
        added, cur, n = [], "?", 0
        for line in diff.splitlines():
            if line.startswith("+++ "):
                cur = line[6:] if line.startswith("+++ b/") else line[4:]
            elif line.startswith("@@"):
                m = re.match(r"@@ -\S+ \+(\d+)", line)
                n = int(m.group(1)) if m else 0
            elif line.startswith("+"):
                added.append((cur, n, line[1:]))
                n += 1
        yield sha[:10], author, committer, msg.splitlines(), added


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("range")
    ap.add_argument("--idents", help="file of accepted `Name <email>` identities (default: land.known_idents)")
    ap.add_argument("--private", help="private patterns file (default: land.private_patterns)")
    ap.add_argument("--config")
    a = ap.parse_args(argv)

    try:
        cfg = config.load(a.config)
        private_file = scrub.private_path(a.private or cfg.get("land.private_patterns"))
        idents_file = a.idents or cfg.get("land.known_idents")
    except config.ConfigError as e:
        print(f"scan-range: {e}", file=sys.stderr)
        return 2
    if not private_file.is_file():
        print(f"scan-range: private patterns file not found: {private_file}\n"
              f"A scan without it checks no names. Create it (CONTRIBUTING.md) or set land.private_patterns.",
              file=sys.stderr)
        return 2
    try:
        patterns = scrub.GENERIC + scrub.load_private(private_file)
        known = set(filter(None, (l.strip() for l in Path(idents_file).expanduser().read_text().splitlines()))) \
            if idents_file else set()
        rows = list(commits(a.repo, a.range))
    except (ValueError, RuntimeError, OSError) as e:
        print(f"scan-range: {e}", file=sys.stderr)
        return 2

    counts: collections.Counter = collections.Counter()
    files = collections.defaultdict(set)
    idents: set[str] = set()

    def hit(name: str, sha: str, where: str, text: str):
        print(f"{name}\t{sha}\t{where}\t{text}")
        counts[name] += 1

    for sha, author, committer, msg, added in rows:
        for who in (author, committer):
            idents.add(who)
            if who not in known:
                for p in patterns:
                    if any(True for _ in p.finditer(who)):
                        hit(p.name, sha, "IDENT", who)
        for line in msg:
            for p in patterns:
                if any(True for _ in p.finditer(line)):
                    hit(p.name, sha, "MESSAGE", line[:MESSAGE_WIDTH])
        for path, _n, line in added:
            for p in patterns:
                if any(True for _ in p.finditer(line)):
                    hit(p.name, sha, path, line[:LINE_WIDTH])
                    files[p.name].add(path)

    print("== summary (hits per pattern) ==")
    for p in dict.fromkeys(p.name for p in patterns):
        print(f"{p}\t{counts[p]}\tfiles={len(files[p])}")
    print("== idents ==")
    for who in sorted(idents):
        print(who, "(known)" if who in known else "")
    total = sum(counts.values())
    track.event("scan", f"{a.range}: {len(rows)} commits, {total} hits", data={"commits": len(rows), "hits": total})
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""pin-framework.py: pin every framework dependency of a repo to a pushed revision.

usage: pin-framework.py REPO REV [--url URL] [--patch-url URL]... [--config PORT.TOML]

Rewrites every tracked Cargo.toml of REPO so each dependency on the framework becomes
`git = "<URL>", rev = "<REV>"`:
  - a git dependency on any patch URL gets URL and REV (a branch or tag key is replaced by rev);
  - a path dependency into a sibling framework checkout (`../framework/...`, the directory name taken from URL)
    becomes a git dependency;
  - a `[patch."<patch URL>"]` section is removed (its comment lines stay), because every dependency now resolves
    from git.
URL defaults to framework.repo, which must be the remote that holds REV: a rev only a fork has does not resolve
for anyone who builds from another URL. Set framework.repo to that remote before pinning. The patch URLs default to
framework.patch_urls. A trailing `.git` is optional in
Cargo.toml. Prints the changed files, one per line. It edits the working tree only: commit it yourself.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portkit import config, track  # noqa: E402


def url_regex(urls: list[str]) -> str:
    alts = []
    for u in urls:
        u = u.rstrip("/")
        alts.append(re.escape(u.removesuffix(".git")) + r"(?:\.git)?")
    return "(?:" + "|".join(alts) + ")"


def pin_text(src: str, url: str, rev: str, patch_urls: list[str]) -> str:
    alt = url_regex(patch_urls)
    git_dep = re.compile(r'git\s*=\s*"' + alt + '"')
    rev_key = re.compile(r'\b(?:rev|branch|tag)\s*=\s*"[^"]*"')
    name = re.escape(url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1])
    path_dep = re.compile(r'\bpath\s*=\s*"(?:\.\./)*' + name + r'/[^"]*"')
    patch_sect = re.compile(r'^\[patch\."' + alt + r'"\]\s*$')
    new_dep = f'git = "{url}", rev = "{rev}"'
    out, skip = [], False
    for line in src.split("\n"):
        if line.startswith("["):
            skip = bool(patch_sect.match(line))
            if skip:
                continue
        if skip:
            if line.strip() == "":
                skip = False
                out.append(line)
            elif line.startswith("#"):
                out.append(line)
            continue
        if git_dep.search(line):
            line = rev_key.sub(f'rev = "{rev}"', git_dep.sub(f'git = "{url}"', line))
            if not rev_key.search(line):
                line = git_dep.sub(new_dep, line)
        elif path_dep.search(line):
            line = path_dep.sub(new_dep, line)
        out.append(line)
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo")
    ap.add_argument("rev")
    ap.add_argument("--url", help="framework URL to pin to (default: framework.repo)")
    ap.add_argument("--patch-url", action="append", default=[],
                    help="URL a manifest may name (default: framework.patch_urls)")
    ap.add_argument("--config")
    a = ap.parse_args(argv)
    try:
        cfg = config.load(a.config)
        url = a.url or cfg.require("framework.repo")
        patch_urls = a.patch_url or list(cfg.get("framework.patch_urls") or [url])
    except config.ConfigError as e:
        print(f"pin-framework: {e}", file=sys.stderr)
        return 2
    if url not in patch_urls:
        patch_urls = [url, *patch_urls]
    r = subprocess.run(["git", "-C", a.repo, "ls-files", "-z", "--", "*Cargo.toml"], capture_output=True, text=True)
    if r.returncode:
        print(f"pin-framework: {r.stderr.strip()}", file=sys.stderr)
        return 2
    changed = []
    for f in filter(None, r.stdout.split("\0")):
        p = Path(a.repo, f)
        src = p.read_text()
        new = pin_text(src, url, a.rev, patch_urls)
        if new != src:
            p.write_text(new)
            changed.append(f)
    print("\n".join(changed))
    track.event("pin", f"{len(changed)} Cargo.toml files pinned to {a.rev[:12]}", data={"files": changed})
    return 0


if __name__ == "__main__":
    sys.exit(main())

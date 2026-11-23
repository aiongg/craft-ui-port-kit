"""Upstream sync of the port's integration trees: what tools/sync merges and what cycle checks.

Each repo has an integration tree and an upstream branch:
  fw   framework.integration   framework.repo   framework.branch
  app  app.integration         app.upstream     app.base_branch
The upstream head is fetched into refs/portkit/upstream/<branch> of the integration tree, so no branch or remote of
the developer's moves. <work.runs>/syncs.tsv holds one row per tools/sync run.
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config

REPOS = {"fw": ("framework.integration", "framework.repo", "framework.branch"),
         "app": ("app.integration", "app.upstream", "app.base_branch")}
TSV_COLS = ("start", "repo", "upstream", "upstream_sha", "before", "after", "behind", "conflicts", "fetch_s", "merge_s",
            "total_s", "exit")
DAY_S = 24 * 3600


def git(tree: Path, *args: str, check: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, check=check, timeout=timeout)


def configured(cfg: config.Config) -> dict[str, tuple[Path, str, str]]:
    """repo -> (integration tree, upstream URL, upstream branch), for each repo whose three keys are set."""
    out = {}
    for repo, (tk, uk, bk) in REPOS.items():
        if cfg.get(tk) and cfg.get(uk) and cfg.get(bk):
            out[repo] = (cfg.path(tk), str(cfg.get(uk)), str(cfg.get(bk)))
    return out


def upstream_ref(branch: str) -> str:
    return f"refs/portkit/upstream/{branch}"


def fetch(tree: Path, url: str, branch: str, timeout: float = 120) -> str:
    """Fetch the upstream branch into its refs/portkit ref; its commit. Raises CalledProcessError or TimeoutExpired."""
    git(tree, "fetch", "-q", "--no-tags", url, f"+{branch}:{upstream_ref(branch)}", timeout=timeout)
    return git(tree, "rev-parse", upstream_ref(branch)).stdout.strip()


def behind(tree: Path, sha: str) -> int:
    return int(git(tree, "rev-list", "--count", f"HEAD..{sha}").stdout.strip() or 0)


def tsv(cfg: config.Config) -> Path:
    return cfg.path("work.runs") / "syncs.tsv"


def last_sync(cfg: config.Config, repo: str) -> float | None:
    """Epoch seconds of the newest syncs.tsv row of the repo that merged or recorded a merge (exit 0)."""
    f = tsv(cfg)
    if not f.is_file():
        return None
    best = None
    for line in f.read_text().splitlines()[1:]:
        r = dict(zip(TSV_COLS, line.split("\t")))
        if r.get("repo") == repo and r.get("exit") == "0":
            best = datetime.strptime(r["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    return best


def due(cfg: config.Config, timeout: float = 60) -> list[str]:
    """One line per repo whose sync is due: more than land.sync_after_commits behind, or more than a day since its
    last sync (without a sync row: since the commit time of the merge base with upstream). A fetch failure is a line
    too; nothing raises."""
    limit = int(cfg.get("land.sync_after_commits"))
    out = []
    for repo, (tree, url, branch) in configured(cfg).items():
        try:
            sha = fetch(tree, url, branch, timeout=timeout)
            n = behind(tree, sha)
            since = last_sync(cfg, repo)
            if since is None:
                base = git(tree, "merge-base", "HEAD", sha, check=False).stdout.strip()
                since = float(git(tree, "show", "-s", "--format=%ct", base).stdout.strip()) if base else None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as e:
            out.append(f"{repo}: could not check upstream {branch}: {getattr(e, 'stderr', '') or e}".strip())
            continue
        hours = (time.time() - since) / 3600 if since else None
        if n > limit or (n and hours is not None and hours * 3600 > DAY_S):
            out.append(f"sync due: {repo} is {n} commits behind {branch} (land.sync_after_commits {limit})"
                       + (f", last sync {hours:.0f} h ago" if hours is not None else "") + ": run tools/sync")
    return out

"""The build pool: a fixed set of build slots, each one build tree per repo with its own seeded target dir.

Layout under build.pool_dir, slot k:
  <k>/fw, <k>/fw-target                 framework build tree (a detached worktree of framework.integration)
  <k>/app/tree, <k>/app/tree-target     app build tree (a detached worktree of app.integration)
  <k>/app/.cargo/config.toml            the framework patch of the app tree, pointing at <k>/fw
cl uses `<worktree>-target` when it exists beside the worktree. Cargo reads the config file because it sits in a
parent directory of the app tree, and its `[patch]` wins over the manifest's, so no tracked file changes. The
framework tree is not below it.

State: <work.dir>/build-pool.json, changed only under an flock on <work.dir>/build-pool.lock.
"""
from __future__ import annotations

import fcntl
import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from . import config as C
from . import track

TOOLS = Path(__file__).resolve().parents[1]
REPOS = {"fw": "framework.integration", "app": "app.integration"}


class PoolError(Exception):
    """A refusal (exit 1): no free slot, a busy tree."""


class SetupError(Exception):
    """A tool or setup failure (exit 2)."""


def tree_of(cfg: C.Config, k: int, repo: str) -> Path:
    base = cfg.path("build.pool_dir") / str(k)
    return base / "fw" if repo == "fw" else base / "app" / "tree"


def target_of(tree: Path) -> Path:
    return tree.parent / f"{tree.name}-target"


def repos(cfg: C.Config) -> dict[str, Path]:
    """The repos that have an integration tree on disk."""
    return {r: cfg.path(k) for r, k in REPOS.items() if cfg.get(k) and cfg.path(k).is_dir()}


def warm_target(cfg: C.Config, integration: Path) -> Path:
    """The integration tree's target dir, as cl picks it: `<tree>-target`, else build.target_dir, else target/."""
    beside = integration.parent / f"{integration.name}-target"
    if beside.is_dir():
        return beside
    if cfg.get("build.target_dir"):
        return cfg.path("build.target_dir")
    return integration / "target"


class Pool:
    def __init__(self, cfg: C.Config):
        self.cfg = cfg
        work = cfg.path("work.dir")
        self.state_file = work / "build-pool.json"
        self.lock_file = work / "build-pool.lock"

    @contextmanager
    def locked(self):
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                st = self.read()
                yield st
                tmp = self.state_file.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(st, indent=1) + "\n")
                tmp.replace(self.state_file)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {"slots": {}}

    def exists(self) -> bool:
        return bool(self.read().get("slots"))

    def slot(self, k: int | str) -> dict:
        """{repo: {"tree", "target"}} of slot k."""
        out = {}
        for r in repos(self.cfg):
            t = tree_of(self.cfg, int(k), r)
            out[r] = {"tree": str(t), "target": str(target_of(t))}
        return out

    # ---- make
    def make(self, n: int, log=print) -> list[int]:
        rs = repos(self.cfg)
        if not rs:
            raise SetupError("no integration tree on disk (framework.integration, app.integration)")
        warm = {r: warm_target(self.cfg, t) for r, t in rs.items()}
        for r, w in warm.items():
            if not (w / "CACHEDIR.TAG").is_file():
                raise SetupError(f"{REPOS[r]}: no warm target dir at {w}; build the integration tree first")
        with self.locked() as st:
            first = max((int(k) for k in st["slots"]), default=0) + 1
            made = []
            for k in range(first, first + n):
                for r in ("fw", "app"):
                    if r in rs:
                        self.add_tree(k, r, rs[r], warm[r], log)
                st["slots"][str(k)] = {"task": None, "since": None}
                made.append(k)
                log(f"slot {k}: " + "; ".join(f"{r} {v['tree']}" for r, v in self.slot(k).items()))
        track.event("build-pool", f"made slots {', '.join(map(str, made))}", data={"slots": made})
        return made

    def add_tree(self, k: int, repo: str, integration: Path, warm: Path, log) -> None:
        tree = tree_of(self.cfg, k, repo)
        if tree.exists():
            raise SetupError(f"{tree} already exists")
        tree.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "-C", str(integration), "worktree", "add", "-q", "--detach", str(tree), "HEAD"])
        _run([str(TOOLS / "seed-target"), str(target_of(tree)), str(warm), str(tree)], cwd=tree)
        if repo == "app" and "fw" in repos(self.cfg):
            conf = tree.parent / ".cargo" / "config.toml"
            _run([sys.executable, "-I", str(TOOLS / "patch-framework"), "--cargo-config", str(conf),
                  str(tree / "Cargo.toml"), str(tree / "Cargo.lock"), str(tree_of(self.cfg, k, "fw"))])
            log(f"  {conf}: the app tree builds against {tree_of(self.cfg, k, 'fw')}")

    # ---- take, give
    def take(self, task: str) -> tuple[int, dict]:
        track.check_task(task)
        with self.locked() as st:
            slots = st["slots"]
            if not slots:
                raise PoolError("no build pool: make one with `tools/build-pool make N`")
            held = next((k for k, v in slots.items() if v["task"] == task), None)
            if held is None:
                held = next((k for k in sorted(slots, key=int) if not slots[k]["task"]), None)
                if held is None:
                    busy = ", ".join(f"{k}: {v['task']}" for k, v in sorted(slots.items(), key=lambda kv: int(kv[0])))
                    raise PoolError(f"no free build slot ({busy})")
                slots[held] = {"task": task, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                track.event("build-pool", f"slot {held} taken", task=task)
        return int(held), self.slot(held)

    def give(self, task: str) -> int | None:
        """Frees the task's slot and detaches its trees; None when it holds none. Refuses while a tree has tracked
        changes other than Cargo.lock (a build rewrites the lock with path sources)."""
        with self.locked() as st:
            held = next((k for k, v in st["slots"].items() if v["task"] == task), None)
            if held is None:
                return None
            for r, v in self.slot(held).items():
                tree = v["tree"]
                dirty = [l[3:] for l in _run(["git", "-C", tree, "status", "--porcelain", "-uno"]).splitlines()
                         if l[3:] != "Cargo.lock"]
                if dirty:
                    raise PoolError(f"slot {held} {r} tree {tree} has uncommitted changes: {', '.join(dirty[:10])}; "
                                    "commit or drop them first")
            for v in self.slot(held).values():
                if subprocess.run(["git", "-C", v["tree"], "symbolic-ref", "-q", "HEAD"],
                                  capture_output=True).returncode == 0:
                    _run(["git", "-C", v["tree"], "switch", "-q", "--detach"])
            st["slots"][held] = {"task": None, "since": None}
        track.event("build-pool", f"slot {held} given back", task=task)
        return int(held)

    # ---- size
    def size(self, peak_gb: float) -> dict:
        avail = _meminfo_gb("MemAvailable")
        d = self.cfg.path("build.pool_dir")
        while not d.exists():
            d = d.parent
        free_gb = shutil.disk_usage(d).free / 2**30
        targets = {r: warm_target(self.cfg, t) for r, t in repos(self.cfg).items()}
        target_gb = sum(_du_gb(t) for t in targets.values() if t.is_dir())
        by_ram = int(avail // peak_gb) if avail is not None and peak_gb > 0 else None
        by_disk = int(free_gb // target_gb) if target_gb > 0 else None
        cands = [x for x in (by_ram, by_disk) if x is not None]
        return {"mem_available_gb": avail, "peak_gb": peak_gb, "by_ram": by_ram, "disk_free_gb": round(free_gb, 1),
                "target_gb": round(target_gb, 1), "by_disk": by_disk, "pool_size": min(cands) if cands else None}


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise SetupError(f"{' '.join(cmd)}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout


def _meminfo_gb(field: str) -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith(field + ":"):
                return round(int(line.split()[1]) / 2**20, 1)
    except OSError:
        pass
    return None


def _du_gb(d: Path) -> float:
    r = subprocess.run(["du", "-sk", str(d)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0]) / 2**20
    except (ValueError, IndexError):
        return 0.0

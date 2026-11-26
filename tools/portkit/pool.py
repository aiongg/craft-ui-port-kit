"""The build pool: a fixed set of build slots, each one build tree per repo with its own seeded target dir.

Layout under build.pool_dir, slot k:
  <k>/fw, <k>/fw-target                 framework build tree (a detached worktree of framework.integration)
  <k>/app/tree, <k>/app/tree-target     app build tree (a detached worktree of app.integration)
  <k>/app/.cargo/config.toml            the framework patch of the app tree, pointing at <k>/fw
cl uses `<worktree>-target` when it exists beside the worktree. Cargo reads the config file because it sits in a
parent directory of the app tree, and its `[patch]` wins over the manifest's, so no tracked file changes. The
framework tree is not below it.

State: <work.dir>/build-pool.json, changed only under an flock on <work.dir>/build-pool.lock.

Trim: removes caches the next build does not need from the target dirs of the integration trees and the slots, but
only from a target dir no build is using: its slot is free, and trim takes every cargo lock in it (`.cargo-lock`, held
by a running cargo) without waiting, and holds them while it deletes, so no build starts meanwhile.
"""
from __future__ import annotations

import fcntl
import json
import os
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
STALE_S = 86400   # incremental units no build wrote for this long are trimmed


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
        self.reseed(int(held))
        return int(held), self.slot(held)

    def reseed(self, k: int) -> None:
        """Seed the target dir of each of slot k's trees again when `trim --retire` removed it."""
        rs = repos(self.cfg)
        for r, integration in rs.items():
            tree = tree_of(self.cfg, k, r)
            if tree.is_dir() and not target_of(tree).exists():
                _run([str(TOOLS / "seed-target"), str(target_of(tree)), str(warm_target(self.cfg, integration)),
                      str(tree)], cwd=tree)
                track.event("build-pool", f"slot {k} {r} target dir seeded again")

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

    # ---- trim
    def targets(self) -> list[tuple[Path, str | None, str | None]]:
        """Every target dir the pool knows: (dir, the task holding it, its slot), the slot None for an integration
        tree."""
        out = [(warm_target(self.cfg, t), None, None) for t in repos(self.cfg).values()]
        for k, v in sorted(self.read()["slots"].items(), key=lambda kv: int(kv[0])):
            out += [(Path(t["target"]), v.get("task"), k) for t in self.slot(k).values()]
        return out

    def trim(self, retire: bool = False, dry_run: bool = False, log=print) -> dict:
        """Trim every target dir no build is using; with retire, also remove the target dir of the least recently
        built free slot (take seeds it again). Returns {"freed_gb", "trimmed", "skipped"}."""
        freed, trimmed, skipped, free_slots = 0, [], [], []
        for target, task, k in self.targets():
            if not target.is_dir():
                continue
            if task:
                skipped.append(str(target))
                log(f"{target}: skipped, held by {task}")
                continue
            held = _lock_all(target)
            if held is None:
                skipped.append(str(target))
                log(f"{target}: skipped, a build is running in it")
                continue
            try:
                paths = _trimmable(target)
                b = sum(_freed_bytes(x) for x in paths)
                if not dry_run:
                    for x in paths:
                        _remove(x)
            finally:
                for fd in held:
                    os.close(fd)
            freed += b
            trimmed.append(str(target))
            log(f"{target}: {'would remove' if dry_run else 'removed'} {len(paths)} paths, frees about {b / 2**30:.1f} GB")
            if k is not None:
                free_slots.append((target, k))
        if retire:
            freed += self.retire(free_slots, dry_run, log)
        gb = round(freed / 2**30, 1)
        if not dry_run:
            track.event("build-pool", f"trim: about {gb} GB freed in {len(trimmed)} target dirs, {len(skipped)} in use",
                        data={"freed_gb": gb, "trimmed": len(trimmed), "skipped": len(skipped), "retire": retire})
        return {"freed_gb": gb, "trimmed": trimmed, "skipped": skipped}

    def retire(self, free: list[tuple[Path, str]], dry_run: bool, log) -> int:
        """Remove the target dirs of the least recently built free slot, under the pool lock so no take races it."""
        slots: dict[str, list[Path]] = {}
        for t, k in free:
            slots.setdefault(k, []).append(t)
        for k, ts in sorted(slots.items(), key=lambda kv: max(map(_last_built, kv[1]))):
            with self.locked() as st:
                if st["slots"].get(k, {}).get("task"):
                    continue
                held = [_lock_all(t) for t in ts]
                try:
                    if any(h is None for h in held):
                        continue
                    b = sum(_freed_bytes(t) for t in ts)
                    if not dry_run:
                        for t in ts:
                            _remove(t)
                finally:
                    for fd in (fd for h in held if h for fd in h):
                        os.close(fd)
            log(f"retire: {'would remove' if dry_run else 'removed'} the target dirs of slot {k} "
                f"({', '.join(map(str, ts))}), frees about {b / 2**30:.1f} GB; `build-pool take` seeds them again")
            return b
        log("retire: no free slot to retire")
        return 0

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


def _lock_all(target: Path) -> list[int] | None:
    """Take every cargo lock under the target dir without waiting: the open descriptors, or None (all released)
    when one is held, that is, a build is running there."""
    fds = []
    for lock in [*target.glob(".cargo-lock"), *target.glob("*/.cargo-lock"), *target.glob("*/*/.cargo-lock")]:
        try:
            fd = os.open(lock, os.O_RDWR)
        except OSError:
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            for f in fds:
                os.close(f)
            return None
        fds.append(fd)
    return fds


def _trimmable(target: Path) -> list[Path]:
    """What the next build does not need: superseded test executables (all but the newest of each name in a deps
    dir), examples, docs, wasm output dirs, tmp, and incremental units no build wrote for STALE_S."""
    out = [p for p in (target / "doc", target / "tmp") if p.is_dir()]
    out += [p for p in target.glob("wasm32-*") if p.is_dir()]
    now = time.time()
    for fp in [*target.glob("*/.fingerprint"), *target.glob("*/*/.fingerprint")]:
        prof = fp.parent
        if prof.parent != target and prof.parent.name.startswith("wasm32-"):
            continue
        if (prof / "examples").is_dir():
            out.append(prof / "examples")
        by_name: dict[str, list[Path]] = {}
        for exe in (prof / "deps").glob("*-*"):
            if "." not in exe.name and exe.is_file() and os.access(exe, os.X_OK):
                by_name.setdefault(exe.name.rsplit("-", 1)[0], []).append(exe)
        for exes in by_name.values():
            out += sorted(exes, key=lambda x: x.stat().st_mtime)[:-1]
        for unit in (prof / "incremental").glob("*"):
            if unit.is_dir() and now - _newest(unit) > STALE_S:
                out.append(unit)
    return out


def _newest(d: Path) -> float:
    t = d.stat().st_mtime
    for root, dirs, files in os.walk(d):
        for n in dirs + files:
            try:
                t = max(t, os.lstat(os.path.join(root, n)).st_mtime)
            except OSError:
                pass
    return t


def _last_built(target: Path) -> float:
    return max((f.stat().st_mtime for f in [*target.glob("*/.fingerprint"), *target.glob("*/*/.fingerprint")]),
               default=0.0)


def _freed_bytes(p: Path) -> int:
    """Bytes that deleting p frees: files with no other hard link (seeded target dirs share theirs)."""
    def one(f):
        try:
            st = os.lstat(f)
        except OSError:
            return 0
        return st.st_size if st.st_nlink == 1 else 0
    if p.is_file():
        return one(p)
    return sum(one(os.path.join(r, n)) for r, _, fs in os.walk(p) for n in fs)


def _remove(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            p.unlink()
        except OSError:
            pass


def _du_gb(d: Path) -> float:
    r = subprocess.run(["du", "-sk", str(d)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0]) / 2**20
    except (ValueError, IndexError):
        return 0.0

"""The port's paths and settings, read once from port.toml.

Repo keys are `fw` (the framework) and `app` (the app being ported). Every path port-set uses comes from a config key
(process/config.md); nothing here names a machine, an app or a tree.
"""
from __future__ import annotations

import re
import subprocess
import tomllib
from functools import cached_property, lru_cache
from pathlib import Path

from portkit import config

REPOS = ("fw", "app")
OTHER = {"fw": "app", "app": "fw"}
RULES_DIR = config.KIT_ROOT / "rules"
PORTING_RULES = RULES_DIR / "porting-rules.md"
WRITER_NOTES = RULES_DIR / "writer-notes.md"


def git(tree, *args, check=True) -> str:
    return subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, check=check).stdout


def section(path: Path, heading: str) -> str:
    """The body of the `## <heading>` section of a Markdown file, up to the next `## ` heading."""
    text = path.read_text() if path.exists() else ""
    m = re.search(rf"^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m or not m.group(1).strip():
        raise SystemExit(f"{path} has no `## {heading}` section; port-set puts it into every writer prompt")
    return m.group(1).strip()


class Ctx:
    """Config-derived values. `ctx.load(cfg)` runs once in tools/port-set; modules read `ctx.<name>`."""

    cfg: config.Config | None = None

    def load(self, cfg: config.Config) -> None:
        self.__dict__.clear()
        self.cfg = cfg

    # ---- workspace paths
    @cached_property
    def sheets(self) -> Path:
        return self.cfg.path("work.sheets")

    @cached_property
    def parts(self) -> Path:
        return self.cfg.path("work.parts")

    @cached_property
    def sets(self) -> Path:
        return self.cfg.path("work.sets")

    @cached_property
    def trees(self) -> Path:
        return self.cfg.path("work.trees")

    @cached_property
    def decide(self) -> Path:
        return self.cfg.path("work.decide")

    @cached_property
    def usage_log(self) -> Path:
        return self.cfg.path("work.usage_log")

    @cached_property
    def scip_dir(self) -> Path:
        return self.cfg.path("work.scip")

    def set_dir(self, set_id: str) -> Path:
        """<work.sets>/<set>/, created: every file a set's commands write."""
        d = self.sets / set_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---- repos
    def repo_dir(self, repo: str) -> Path:
        """The integration worktree of a repo: set worktrees are added from it."""
        return self.cfg.path("framework.integration" if repo == "fw" else "app.integration")

    def base(self, repo: str) -> str:
        """The writing base branch of a repo: every set tree starts there."""
        return self.cfg.require("framework.writing_base" if repo == "fw" else "app.writing_base")

    def ref_tree(self, repo: str) -> Path:
        """The read-only checkout of a repo at its writing base (the racheck daemon's root)."""
        return self.cfg.path("racheck.fw_base" if repo == "fw" else "racheck.app_base")

    @cached_property
    def plan_base(self) -> str:
        return self.cfg.require("plan.base")

    # ---- app and framework
    @cached_property
    def app_name(self) -> str:
        return self.cfg.require("app.name")

    @cached_property
    def facade(self) -> str:
        return self.cfg.require("framework.facade")

    @cached_property
    def facade_dirs(self) -> list[str]:
        return [d.strip("/") for d in self.cfg.get("app.facade_dirs", [])]

    @cached_property
    def facade_members(self) -> dict[str, str]:
        """Framework crates the facade re-exports: Rust crate ident -> package name. A facade dependency is a member
        when it is a framework workspace crate (a `path` dependency, directly or through `[workspace.dependencies]`)."""
        manifest = self.cfg.require("framework.facade_manifest")
        fac = toml_at(self.repo_dir("fw"), self.base("fw"), manifest)
        ws = (toml_at(self.repo_dir("fw"), self.base("fw"), "Cargo.toml").get("workspace") or {}).get("dependencies") or {}
        out = {}
        for name, spec in dependencies(fac).items():
            spec = spec if isinstance(spec, dict) else {}
            local = "path" in spec or (spec.get("workspace") and isinstance(ws.get(name), dict) and "path" in ws[name])
            if local:
                out[name.replace("-", "_")] = name
        return out

    @cached_property
    def edition(self) -> str:
        """The Rust edition rustfmt parses with: the framework workspace's, else 2024."""
        root = toml_at(self.repo_dir("fw"), self.base("fw"), "Cargo.toml")
        return str(((root.get("workspace") or {}).get("package") or {}).get("edition")
                   or (root.get("package") or {}).get("edition") or "2024")

    # ---- pipeline
    def pipeline(self, key: str):
        return self.cfg.require(f"pipeline.{key}")

    def bundle(self, key: str) -> int:
        return self.cfg.require(f"pipeline.bundle.{key}")

    @cached_property
    def lookup_tools(self) -> str:
        return self.cfg.require("pipeline.lookup_tools")

    # ---- rules
    @cached_property
    def code_rules(self) -> str:
        return section(PORTING_RULES, "Code")

    @cached_property
    def writer_notes(self) -> str:
        return section(WRITER_NOTES, "Notes")

    @cached_property
    def lints(self) -> list[dict]:
        """The kit's lints (framework.lints_file) followed by the `[[lints]]` tables of port.toml."""
        f = self.cfg.get("framework.lints_file")
        items = []
        if f and Path(f).exists():
            with open(f, "rb") as fh:
                items = config._lints(tomllib.load(fh).get("lints", []))
        return items + list(self.cfg.lints)


ctx = Ctx()


@lru_cache(maxsize=None)
def toml_at(repo_dir: Path, rev: str, path: str) -> dict:
    """A TOML file of a repo at a revision; {} when it is missing or unreadable."""
    r = subprocess.run(["git", "-C", str(repo_dir), "show", f"{rev}:{path}"], capture_output=True, text=True)
    if r.returncode:
        return {}
    try:
        return tomllib.loads(r.stdout)
    except tomllib.TOMLDecodeError:
        return {}


def dependencies(manifest: dict) -> dict:
    """Every dependency table of a Cargo manifest merged: normal, dev, build and target-specific."""
    out = {}
    tables = [manifest] + [t for t in (manifest.get("target") or {}).values() if isinstance(t, dict)]
    for t in tables:
        for key in ("dependencies", "dev-dependencies", "build-dependencies"):
            out.update(t.get(key) or {})
    return out

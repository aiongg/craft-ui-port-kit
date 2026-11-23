"""Helpers for selftest cases: a scratch workspace with its own port.toml, git trees, tool calls and assertions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
KIT = TOOLS.parent
STUBS = HERE / "stubs"
FIXTURES = HERE / "fixtures"


def git(tree: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="selftest", GIT_AUTHOR_EMAIL="selftest@example.invalid",
               GIT_COMMITTER_NAME="selftest", GIT_COMMITTER_EMAIL="selftest@example.invalid")
    return subprocess.run(["git", "-C", str(tree), *args], check=True, capture_output=True, text=True, env=env).stdout


class Scratch:
    def __init__(self, root: Path):
        self.root = root
        self.work = root / "work"
        self.work.mkdir()
        self.last = None
        self.env = dict(os.environ, PORT_KIT_CONFIG=str(root / "port.toml"), PYTHONDONTWRITEBYTECODE="1",
                        STUB_CL_LOGS=str(root / "cl-logs"), STUB_CLAUDE_DIR=str(root / "claude"),
                        CARGO=str(STUBS / "cargo"), PORT_KIT_CLAUDE_BIN=str(STUBS / "claude"))
        for k in [k for k in self.env if k.startswith("PORT_KIT_") and k not in ("PORT_KIT_CONFIG", "PORT_KIT_CLAUDE_BIN")]:
            del self.env[k]
        (root / "cl-logs").mkdir()
        self.config({})

    def config(self, keys: dict) -> Path:
        """Write port.toml: `section.key` -> value, on top of what every case needs."""
        base = {"work.dir": str(self.work), "app.name": "Selftest", "framework.checkout": str(self.root / "fw"),
                "app.checkout": str(self.root / "app"), "app.ui_dirs": ["src"], "build.cl": str(STUBS / "cl")}
        base.update(keys)
        sections: dict[str, dict] = {}
        for k, v in base.items():
            sec, key = k.rsplit(".", 1) if k.count(".") > 1 else k.split(".", 1)
            sections.setdefault(sec, {})[key] = v
        text = "".join(f"[{sec}]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in kv.items()) + "\n"
                       for sec, kv in sections.items())
        f = self.root / "port.toml"
        f.write_text(text)
        return f

    def tree(self, name: str, files: dict[str, str], branch: str = "main") -> Path:
        """A git repo at <scratch>/<name> holding `files`, committed on `branch`."""
        t = self.root / name
        t.mkdir(parents=True, exist_ok=True)
        git(t, "init", "-q", "-b", branch)
        self.commit(t, files, "base")
        return t

    def commit(self, tree: Path, files: dict[str, str | None], msg: str) -> None:
        for p, text in files.items():
            f = tree / p
            if text is None:
                f.unlink()
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        git(tree, "add", "-A")
        git(tree, "commit", "-q", "--allow-empty", "-m", msg)

    def cl_log(self, key: str, text: str, rc: int = 0) -> None:
        """What the stub cl prints for the command key (see stubs/cl) and its exit status."""
        d = self.root / "cl-logs"
        (d / f"{key}.log").write_text(text)
        (d / f"{key}.rc").write_text(str(rc))

    def cl_calls(self) -> list[list[str]]:
        f = self.root / "cl-logs" / "calls.jsonl"
        return [json.loads(l)["argv"] for l in f.read_text().splitlines()] if f.exists() else []

    def run(self, tool: str, *args: str, env: dict | None = None, stdin: str | None = None, cwd: Path | None = None):
        """Run tools/<tool> with the scratch config; the CompletedProcess (also kept as .last)."""
        path = TOOLS / tool
        cmd = ([sys.executable, "-I", str(path)] if path.suffix == ".py" else [str(path)]) + list(args)
        self.last = subprocess.run(cmd, capture_output=True, text=True, input=stdin, env={**self.env, **(env or {})},
                                   cwd=str(cwd or self.work))
        return self.last


def check(cond: bool, what: str, proc=None) -> None:
    if not cond:
        tail = ""
        if proc is not None:
            tail = "\n    exit %s\n    %s" % (proc.returncode, (proc.stdout + proc.stderr)[-1500:].replace("\n", "\n    "))
        raise AssertionError(what + tail)


def cargo_metadata(packages: list[dict]) -> str:
    """`cargo metadata --no-deps` JSON for packages {name, dir, deps: [name], dev: [name]}; every one a member."""
    out = []
    for p in packages:
        deps = [{"name": d, "kind": None} for d in p.get("deps", [])] + [{"name": d, "kind": "dev"} for d in p.get("dev", [])]
        out.append({"id": f"{p['name']} 0.1.0", "name": p["name"], "dependencies": deps,
                    "manifest_path": f"{p.get('dir', p['name'])}/Cargo.toml",
                    "targets": [{"name": p["name"].replace("-", "_"), "kind": ["lib"]}]})
    return json.dumps({"packages": out, "workspace_members": [p["id"] for p in out]})

#!/usr/bin/env python3
"""racheck: rust-analyzer diagnostics for the files a set changed, without a cargo build.

  racheck.py serve fw|app                daemon: loads a dedicated read-only checkout once, then answers requests on a unix socket (TCP on 127.0.0.1 with a port file where AF_UNIX is missing)
  racheck.py check TREE --repo fw|app --changed P... [--also P...]   one request; prints JSON
  racheck.py stop fw|app                 ask the daemon to exit
  racheck.py status fw|app               rust-analyzer's last server status, or "not running"
  racheck.py canary [fw|app ...] [--sets LIST ...]   the writer canary: 0 errors on an untouched file, per repo

Canary: before a writer batch, each repo's daemon diagnoses one file of its loaded tree that no set has touched: the
facade's src/lib.rs for fw (framework.facade_manifest), the first file under app.ui_dirs that names the facade for
app. That file compiles on the writing base, so any error there means the daemon's view is wrong (a dependency it
cannot resolve, a missing framework patch), and every set's racheck would report false errors. The repos are the
ones named, or those the sets in each LIST (one set id per line) write. Prints `canary <repo>: <file>: <n> errors` per
repo and the first errors. Exit 0 when every canary has 0 errors, 1 when one has errors, 2 when a daemon is not
running or a repo has no canary file.

Every path comes from port.toml (racheck.*, framework.*, app.*, build.memory_cap); process/config.md lists the keys.

Each request overlays the set tree's files (same relative path) on the loaded worktree with didOpen, pulls diagnostics,
then didClose reverts the overlays. Only rust-analyzer's own diagnostics are reported (syntax, unresolved names/imports,
type mismatches, wrong arity, missing fields...); cargo check is off, so borrow-check, trait-solver corner cases and
errors inside macro expansions that rustc alone reports do not appear.
"""
import argparse, json, os, shlex, socket, subprocess, sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portkit import config, track

REPO_NAMES = ("fw", "app")


def repos(cfg):
    """The two daemons' settings. root: the read-only checkout the daemon loads, made from `src` at `rev`."""
    return {
        "fw": dict(root=cfg.path("racheck.fw_base"), src=cfg.path("framework.checkout"), rev=cfg.require("framework.writing_base"),
                   target=str(cfg.path("racheck.fw_target"))),
        "app": dict(root=cfg.path("racheck.app_base"), src=cfg.path("app.checkout"), rev=cfg.require("app.writing_base"),
                    target=str(cfg.path("racheck.app_target"))),
    }


def sock_path(cfg, repo):
    return str(cfg.path("racheck.sockets") / f"racheck-{repo}.sock")


def port_path(cfg, repo):
    return sock_path(cfg, repo) + ".port"


def endpoint_path(cfg, repo):
    """The file that exists while the daemon listens: the unix socket, or the port file."""
    return port_path(cfg, repo) if not hasattr(socket, "AF_UNIX") else sock_path(cfg, repo)


def listen(cfg, repo):
    """The daemon's listening socket: a unix socket at sock_path, or without AF_UNIX (Windows) a TCP socket on
    127.0.0.1 whose port goes into port_path for the clients."""
    sp = sock_path(cfg, repo)
    if hasattr(socket, "AF_UNIX"):
        if os.path.exists(sp):
            os.unlink(sp)
        srv = socket.socket(socket.AF_UNIX)
        srv.bind(sp)
    else:
        srv = socket.socket(socket.AF_INET)
        srv.bind(("127.0.0.1", 0))
        Path(port_path(cfg, repo)).write_text(str(srv.getsockname()[1]))
    srv.listen(4)
    return srv


def connect(cfg, repo):
    """A connected client socket; OSError when no daemon listens (or the port file is missing or stale)."""
    if hasattr(socket, "AF_UNIX"):
        s = socket.socket(socket.AF_UNIX)
        target = sock_path(cfg, repo)
    else:
        s = socket.socket(socket.AF_INET)
        try:
            target = ("127.0.0.1", int(Path(port_path(cfg, repo)).read_text()))
        except ValueError as e:
            raise OSError(str(e))
    s.connect(target)
    return s


def memory_prefix(cfg):
    """The memory-cap command words for the daemon (build.memory_cap with {gb} filled in), or []."""
    cap = cfg.get("build.memory_cap") or ""
    return shlex.split(cap.replace("{gb}", str(cfg.get("racheck.memory_gb")))) if cap else []


class LSP:
    def __init__(self, root, target, log, prefix=()):
        self.root, self.log = Path(root), log
        self.p = subprocess.Popen([*prefix, "rust-analyzer"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                  env={**os.environ, "CARGO_TARGET_DIR": target})
        self.id = 0
        self.cv = threading.Condition()
        self.replies, self.diags, self.quiescent, self.status_seq, self.progress = {}, {}, False, 0, set()
        self.wlock = threading.Lock()
        threading.Thread(target=self.reader, daemon=True).start()

    def send(self, msg):
        b = json.dumps({"jsonrpc": "2.0", **msg}).encode()
        with self.wlock:
            self.p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(b) + b)
            self.p.stdin.flush()

    def request(self, method, params, timeout=600):
        with self.cv:
            self.id += 1
            i = self.id
        self.send({"id": i, "method": method, "params": params})
        with self.cv:
            if not self.cv.wait_for(lambda: i in self.replies, timeout):
                raise TimeoutError(method)
            r = self.replies.pop(i)
        if "error" in r:
            raise RuntimeError(f"{method}: {r['error']}")
        return r.get("result")

    def notify(self, method, params):
        self.send({"method": method, "params": params})

    def reader(self):
        f = self.p.stdout
        while True:
            n = None
            while True:
                line = f.readline()
                if not line:
                    with self.cv:
                        self.replies[-1] = {"error": "server exited"}
                        self.cv.notify_all()
                    return
                line = line.strip()
                if not line:
                    break
                if line.lower().startswith(b"content-length:"):
                    n = int(line.split(b":")[1])
            m = json.loads(f.read(n))
            self.handle(m)

    def handle(self, m):
        meth = m.get("method")
        if meth and "id" in m:  # server request
            res = None
            if meth == "workspace/configuration":
                res = [None] * len(m["params"]["items"])
            self.send({"id": m["id"], "result": res})
        elif meth == "experimental/serverStatus":
            with self.cv:
                self.quiescent = bool(m["params"].get("quiescent"))
                self.last_status = m["params"]
                self.status_seq += 1
                self.cv.notify_all()
        elif meth == "textDocument/publishDiagnostics":
            with self.cv:
                self.diags[m["params"]["uri"]] = m["params"]["diagnostics"]
        elif meth == "$/progress":
            v = m["params"]["value"]
            with self.cv:
                if v.get("kind") == "begin":
                    self.progress.add(str(m["params"]["token"]))
                elif v.get("kind") == "end":
                    self.progress.discard(str(m["params"]["token"]))
                self.cv.notify_all()
        elif "id" in m:
            with self.cv:
                self.replies[m["id"]] = m
                self.cv.notify_all()

    def wait_quiescent(self, timeout=900, settle=0.4):
        end = time.time() + timeout
        time.sleep(settle)
        with self.cv:
            while time.time() < end:
                seq = self.status_seq
                if self.quiescent and not self.progress:
                    if not self.cv.wait_for(lambda: self.status_seq != seq, settle):
                        return True
                else:
                    self.cv.wait(1)
        return False


def uri(p):
    return "file://" + str(p)


def init(lsp, root, target):
    opts = {"checkOnSave": False, "check": {"command": "check", "workspace": False},
            "cargo": {"targetDir": target, "buildScripts": {"enable": True}},
            "procMacro": {"enable": True}, "diagnostics": {"enable": True, "experimental": {"enable": True}},
            "files": {"watcher": "server"}}
    caps = {"experimental": {"serverStatusNotification": True},
            "window": {"workDoneProgress": True},
            "textDocument": {"diagnostic": {"dynamicRegistration": False}, "publishDiagnostics": {}},
            "workspace": {"configuration": True}}
    r = lsp.request("initialize", {"processId": os.getpid(), "rootUri": uri(root), "capabilities": caps,
                                   "workspaceFolders": [{"uri": uri(root), "name": "ws"}],
                                   "initializationOptions": opts})
    lsp.notify("initialized", {})
    return r


def diagnose(lsp, root, tree, changed, also, opened, every=False, overlay=()):
    """Overlay and diagnose. `opened` is the set of URIs currently open. `overlay` holds (loaded file, source
    file) pairs of absolute paths outside the set tree: a combined framework seen through the loaded one."""
    docs = {}
    for dst, src in overlay:
        if Path(src).is_file() and Path(dst).exists():
            docs[dst] = Path(src).read_text(errors="replace")
    for rel in changed + also:
        f = Path(tree) / rel
        if f.is_file() and (Path(root) / rel).exists() or (f.is_file() and rel in changed):
            docs[rel] = f.read_text(errors="replace")
    for rel, text in docs.items():
        u = uri(Path(root) / rel)
        if u in opened:
            lsp.notify("textDocument/didChange", {"textDocument": {"uri": u, "version": int(time.time())},
                                                  "contentChanges": [{"text": text}]})
        else:
            lsp.notify("textDocument/didOpen", {"textDocument": {"uri": u, "languageId": "rust", "version": 1, "text": text}})
            opened.add(u)
    lsp.wait_quiescent()
    out = []
    for rel in docs:
        u = uri(Path(root) / rel)
        try:
            r = lsp.request("textDocument/diagnostic", {"textDocument": {"uri": u}}, timeout=300)
            items = (r or {}).get("items", [])
        except Exception:
            items = lsp.diags.get(u, [])
        for d in items:
            if d.get("severity", 1) not in (1, 2) and not every:
                continue
            c = d.get("code")
            out.append({"path": rel, "line": d["range"]["start"]["line"] + 1,
                        "severity": {1: "error", 2: "warning"}.get(d.get("severity", 1), "hint"),
                        "code": c if c is None or isinstance(c, str) else str(c), "message": d["message"],
                        "also": rel not in changed})
    return out, docs


def revert(lsp, root, opened):
    for u in list(opened):
        lsp.notify("textDocument/didClose", {"textDocument": {"uri": u}})
        opened.discard(u)
    lsp.wait_quiescent()


def serve(cfg, repo):
    rc = repos(cfg)[repo]
    root = rc["root"]
    if not root.exists():
        subprocess.run(["git", "-C", str(rc["src"]), "worktree", "add", "--detach", str(root), rc["rev"]], check=True)
    t0 = time.time()
    sockets = cfg.path("racheck.sockets")
    sockets.mkdir(parents=True, exist_ok=True)
    log = open(sockets / f"racheck-{repo}.rs.log", "ab")
    lsp = LSP(root, rc["target"], log, memory_prefix(cfg))
    init(lsp, root, rc["target"])
    lsp.wait_quiescent(timeout=3600, settle=3)
    print(f"loaded in {time.time() - t0:.0f}s", flush=True)
    srv = listen(cfg, repo)
    opened = set()
    while True:
        c, _ = srv.accept()
        try:
            req = json.loads(c.makefile("r").readline())
            if req.get("op") == "stop":
                c.sendall(b'{"ok":true}\n')
                break
            if req.get("op") == "status":
                c.sendall((json.dumps(getattr(lsp, "last_status", None)) + "\n").encode())
                c.close()
                continue
            t = time.time()
            try:
                d, docs = diagnose(lsp, root, req["tree"], req["changed"], req.get("also", []), opened, req.get("all", False),
                                  [tuple(x) for x in req.get("overlay", [])])
                rep = {"ok": True, "diagnostics": d, "files": sorted(docs)}
            finally:
                revert(lsp, root, opened)
            rep["seconds"] = round(time.time() - t, 1)
        except Exception as e:
            rep = {"ok": False, "error": repr(e)}
        try:
            c.sendall((json.dumps(rep) + "\n").encode())
        except OSError:
            pass  # the client went away; the daemon keeps serving
        c.close()
    try:
        lsp.request("shutdown", None, timeout=30)
        lsp.notify("exit", None)
    except Exception:
        lsp.p.kill()
    if os.path.exists(endpoint_path(cfg, repo)):
        os.unlink(endpoint_path(cfg, repo))


def query(cfg, repo, req):
    try:
        s = connect(cfg, repo)
    except OSError:
        return None
    # A daemon that dies mid-reply is the same to a caller as one that is not running: no answer.
    try:
        s.sendall((json.dumps(req) + "\n").encode())
        s.shutdown(socket.SHUT_WR)
        data = b""
        while chunk := s.recv(1 << 20):
            data += chunk
        return json.loads(data)
    except (OSError, ValueError):
        return None


def check(cfg, tree, repo, changed, also=(), fw_tree=None, fw_changed=(), every=False):
    """One request to the daemon of `repo`; the reply dict, or None when it is not running. With fw_tree, the files
    fw_changed of that framework tree replace the same files in the framework the app daemon has loaded."""
    fw_root = repos(cfg)["fw"]["root"]
    overlay = [[str(fw_root / f), str(Path(fw_tree).resolve() / f)] for f in fw_changed] if fw_tree else []
    return query(cfg, repo, {"tree": str(Path(tree).resolve()), "changed": list(changed), "also": list(also), "all": every,
                             "overlay": overlay})


def canary_file(cfg, repo):
    """The canary's path relative to the daemon's loaded tree, or None."""
    root = repos(cfg)[repo]["root"]
    if repo == "fw":
        rel = str(Path(cfg.require("framework.facade_manifest")).parent / "src" / "lib.rs")
        return rel if (root / rel).is_file() else None
    facade = cfg.require("framework.facade").replace("-", "_")
    for d in cfg.get("app.ui_dirs") or []:
        for f in sorted((root / d).rglob("*.rs")):
            text = f.read_text(errors="replace")
            if f"{facade}::" in text or f"use {facade}" in text:
                return str(f.relative_to(root))
    return None


def canary(cfg, names, set_lists):
    """Exit status of the canary over the repos named or written by the sets in the lists."""
    wanted = list(names)
    if set_lists:
        from portkit.portset.context import ctx
        from portkit.portset.sheet import Sheet
        ctx.load(cfg)
        for lst in set_lists:
            for sid in Path(lst).read_text().split():
                wanted += Sheet(sid).repos()
    code = 0
    for repo in dict.fromkeys(wanted):
        rel = canary_file(cfg, repo)
        if rel is None:
            print(f"canary {repo}: no canary file in {repos(cfg)[repo]['root']}")
            code = 2
            continue
        r = query(cfg, repo, {"tree": str(repos(cfg)[repo]["root"]), "changed": [rel], "also": []})
        if r is None or not r.get("ok"):
            why = "daemon died or is not running" if r is None else r.get("error")
            print(f"canary {repo}: {why} (restart it: racheck.py serve {repo})")
            code = 2
            continue
        errs = [d for d in r["diagnostics"] if d["severity"] == "error"]
        print(f"canary {repo}: {rel}: {len(errs)} errors")
        for d in errs[:5]:
            print(f"  :{d['line']} {d.get('code') or ''} {d['message'][:160]}")
        if errs and code == 0:
            code = 1
    return code


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="port.toml (default: PORT_KIT_CONFIG, ./port.toml, the nearest one above)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "stop", "status"):
        s = sub.add_parser(name); s.add_argument("repo", choices=REPO_NAMES)
    s = sub.add_parser("canary"); s.add_argument("repo", nargs="*")
    s.add_argument("--sets", action="append", default=[], help="a list of set ids; canary every repo they write")
    s = sub.add_parser("check"); s.add_argument("tree"); s.add_argument("--repo", required=True, choices=REPO_NAMES)
    s.add_argument("--all", action="store_true", help="include hints and information"); s.add_argument("--changed", nargs="*", default=[]); s.add_argument("--also", nargs="*", default=[])
    s.add_argument("--fw-tree", help="app only: overlay this framework tree's --fw-changed files on the loaded framework")
    s.add_argument("--fw-changed", nargs="*", default=[])
    a = p.parse_args()
    try:
        cfg = config.load(a.config)
    except config.ConfigError as e:
        sys.exit(f"racheck: {e}")
    if a.cmd == "serve":
        with track.recorded(f"racheck-serve-{a.repo}") as rec:
            serve(cfg, a.repo)
            rec.result("daemon stopped")
    elif a.cmd == "stop":
        print(query(cfg, a.repo, {"op": "stop"}))
    elif a.cmd == "canary":
        bad = [r for r in a.repo if r not in REPO_NAMES]
        if bad:
            sys.exit(f"racheck canary: not a repo: {', '.join(bad)} (fw or app)")
        with track.recorded("racheck-canary") as rec:
            code = canary(cfg, a.repo, a.sets)
            rec.result(f"canary exit {code}", ok=code == 0)
        sys.exit(code)
    elif a.cmd == "status":
        print(query(cfg, a.repo, {"op": "status"}) or "not running")
    else:
        r = check(cfg, a.tree, a.repo, a.changed, a.also, a.fw_tree, a.fw_changed, a.all)
        if r is None:
            print(f"racheck daemon died or is not running: restart it with `racheck.py serve {a.repo}`", file=sys.stderr)
            sys.exit(2)
        print(json.dumps(r, indent=1))


if __name__ == "__main__":
    main()

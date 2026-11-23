#!/usr/bin/env python3
"""Read .rs paths on stdin (relative to the cwd); print every `mod x;` line whose module file is missing.

--unlinked [PATH ...]  the opposite check: print every file that no `mod` line reaches from a crate root (lib.rs,
                       main.rs, build.rs, and files directly in src/bin, tests, examples and benches, or their
                       dir/main.rs). The stdin list must hold every .rs file of the tree, since reachability follows
                       the `mod` lines. With PATHs, only those files are reported (the new files of a change).
                       Output: `<path>: no mod line reaches it`."""
import sys as _sys
if _sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    _sys.exit(0)
import os, re, sys
pat = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(r#)?(\w+)\s*;')
path_attr = re.compile(r'#\[path\s*=\s*"([^"]+)"\]')


def module_dir(path):
    d, base = os.path.split(path)
    return d if base in ("mod.rs", "lib.rs", "main.rs") else os.path.join(d, base[:-3])


def is_root(path):
    parts = path.split("/")
    base = parts[-1]
    if base in ("lib.rs", "main.rs", "build.rs"):
        return True
    for i, p in enumerate(parts[:-1]):
        if p in ("bin", "tests", "examples", "benches"):
            rest = parts[i + 1:]
            if len(rest) == 1 or (len(rest) == 2 and rest[1] == "main.rs"):
                return True
    return False


def unlinked(paths, only):
    """Files of `paths` reached by no `mod` line from a root."""
    known = set(paths)
    reached = {p for p in known if is_root(p)}
    todo = list(reached)
    while todo:
        path = todo.pop()
        here, attrs = module_dir(path), []
        for line in open(path, errors="replace"):
            m = pat.match(line)
            if m:
                pa = next((path_attr.search(a) for a in attrs if path_attr.search(a)), None)
                name = m.group(2)
                cands = ([os.path.normpath(os.path.join(os.path.dirname(path), pa.group(1)))] if pa
                         else [os.path.join(here, name + ".rs"), os.path.join(here, name, "mod.rs")])
                for c in cands:
                    if c in known and c not in reached:
                        reached.add(c)
                        todo.append(c)
            t = line.strip()
            if t.startswith("#["):
                attrs.append(t)
            elif t:
                attrs = []
    return sorted(p for p in (only or known) if p in known and p not in reached)


if sys.argv[1:2] == ["--unlinked"]:
    files = [l.strip() for l in sys.stdin if l.strip().endswith(".rs") and os.path.isfile(l.strip())]
    for p in unlinked(files, set(sys.argv[2:])):
        print(f"{p}: no mod line reaches it")
    sys.exit(0)
for path in (l.strip() for l in sys.stdin):
    if not path.endswith(".rs") or not os.path.isfile(path):
        continue
    d, base = os.path.split(path)
    here = d if base in ("mod.rs", "lib.rs", "main.rs") or "/" not in path and False else os.path.join(d, base[:-3])
    if base in ("mod.rs", "lib.rs", "main.rs"):
        here = d
    attrs = []
    for n, line in enumerate(open(path, errors="replace"), 1):
        m = pat.match(line)
        if m and not any("#[path" in a for a in attrs):
            name = m.group(2)
            if not (os.path.isfile(os.path.join(here, name + ".rs")) or os.path.isfile(os.path.join(here, name, "mod.rs"))):
                print(f"{path}:{n}: mod {name}; has no file")
        t = line.strip()
        if t.startswith("#["):
            attrs.append(t)
        elif t:
            attrs = []

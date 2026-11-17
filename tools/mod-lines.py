#!/usr/bin/env python3
"""Read .rs paths on stdin (relative to the cwd); print every `mod x;` line whose module file is missing."""
import sys as _sys
if _sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    _sys.exit(0)
import os, re, sys
pat = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(r#)?(\w+)\s*;')
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

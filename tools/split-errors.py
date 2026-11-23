#!/usr/bin/env python3
"""Split a compile's error list into N groups of whole files, balanced by error count, keeping a directory together
where it fits. usage: split-errors.py ERRORS N OUTPREFIX

Writes OUTPREFIX-<i>.errors (the group's error lines) and OUTPREFIX-<i>.files (the files the group owns: the files of
its errors, one per line), and prints the groups. Each file has one owner. A fixer edits only the files its group
owns; the lead gives a cause file that has no error to one group by adding it to that group's .files."""
import sys as _sys
if _sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    _sys.exit(0)
import os, sys, collections
errs, n, pre = sys.argv[1], int(sys.argv[2]), sys.argv[3]
os.makedirs(os.path.dirname(pre) or '.', exist_ok=True)
by = collections.defaultdict(list)
for l in open(errs):
    by[l.split(':', 1)[0]].append(l)
# unit = top two path parts under src (e.g. crates/app-ui/src/dialogs), so one module's files stay together
unit = collections.defaultdict(list)
for f in by:
    parts = f.split('/')
    k = '/'.join(parts[:4]) if len(parts) > 4 else f
    unit[k].append(f)
units = sorted(unit.items(), key=lambda kv: -sum(len(by[f]) for f in kv[1]))
groups = [[0, []] for _ in range(n)]
for k, fs in units:
    g = min(groups, key=lambda g: g[0]); g[0] += sum(len(by[f]) for f in fs); g[1] += fs
for i, (c, fs) in enumerate(groups):
    with open(f'{pre}-{i+1}.errors', 'w') as o:
        for f in sorted(fs): o.writelines(by[f])
    with open(f'{pre}-{i+1}.files', 'w') as o:
        o.writelines(f + '\n' for f in sorted(fs))
    print(i + 1, c, 'errors', len(fs), 'files')

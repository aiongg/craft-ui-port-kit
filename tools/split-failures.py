#!/usr/bin/env python3
"""Split failing tests from cargo test logs into groups of whole clusters, at least N and none over M tests.

Usage: split-failures.py <out-dir> <groups> <log>... [--exclude-binary SUBSTR]... [--max-per-track M]

A cluster is the test's module (lib and bin tests: the path minus the test name, cut at the
`tests`/`*_tests` level) or its integration-test file (tests/it/<file>). Groups get whole
clusters, balanced by failure count. No group holds more than M tests (default 25): a cluster
larger than M is cut into parts of at most M tests (in name order), and a part that fits in no
group opens a new one, so a long failure list gives more groups, not bigger ones. Writes
<out-dir>/g<k>.md (each failure: binary, panic site, message, captured output, trimmed) and
<out-dir>/index.md.
"""
import sys as _sys
if _sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    _sys.exit(0)
import collections
import re
import sys
from pathlib import Path

args = sys.argv[1:]
excl = []
cap = 25
if '--max-per-track' in args:
    i = args.index('--max-per-track')
    cap = int(args[i + 1])
    del args[i:i + 2]
    if cap < 1:
        sys.exit('split-failures.py: --max-per-track must be at least 1')
while '--exclude-binary' in args:
    i = args.index('--exclude-binary')
    excl.append(args[i + 1])
    del args[i:i + 2]
out, n, logs = Path(args[0]), int(args[1]), args[2:]
out.mkdir(parents=True, exist_ok=True)

fails = {}  # (binary, test) -> dict
for log in logs:
    lines = open(log, errors='replace').read().split('\n')
    binary = None
    cur = None
    for i, l in enumerate(lines):
        m = re.match(r'^\s+Running (?:unittests )?(\S+) \((\S+)\)', l)
        if m:
            binary = f'{m.group(1)} ({Path(m.group(2)).name})'
            cur = None
            continue
        if binary and any(e in binary for e in excl):
            continue
        m = re.match(r'^test (\S+) \.\.\. FAILED$', l)
        if m:
            fails.setdefault((binary, m.group(1)), {'out': [], 'site': '', 'msg': ''})
            continue
        m = re.match(r'^---- (\S+) stdout ----$', l)
        if m:
            cur = fails.setdefault((binary, m.group(1)), {'out': [], 'site': '', 'msg': ''})
            continue
        if cur is not None:
            if l.startswith('---- ') or l == 'failures:' or l.startswith('test result:'):
                cur = None
                continue
            if 'panicked at' in l and not cur['site']:
                cur['site'] = l.split('panicked at ')[1].rstrip(':')
                cur['msg'] = lines[i + 1] if i + 1 < len(lines) else ''
            if len(cur['out']) < 40 and 'is low on free space' not in l:
                cur['out'].append(l[:300])


def cluster(binary, test, site):
    mods = test.split('::')[:-1]
    if binary.startswith('tests/'):
        # Integration binaries are all called `it`: the panic site names the package's file.
        file = re.sub(r':\d+:\d+$', '', site)
        if '/tests/' in file:
            return file
        return binary + ' :: ' + (mods[0] if mods else '(root)')
    for k, p in enumerate(mods):
        if p == 'tests' or p.endswith('_tests'):
            mods = mods[:k + 1]
            break
    return binary.split(' (')[1].rstrip(')').rsplit('-', 1)[0] + ' :: ' + ('::'.join(mods) or '(root)')


clusters = collections.defaultdict(list)
for (b, t), v in fails.items():
    clusters[cluster(b, t, v['site'])].append((b, t, v))

parts = []  # (cluster label, items): clusters over the cap cut into parts of at most `cap` tests
for c, items in clusters.items():
    items = sorted(items, key=lambda x: x[1])
    if len(items) <= cap:
        parts.append((c, items))
        continue
    cut = [items[i:i + cap] for i in range(0, len(items), cap)]
    parts += [(f'{c} [part {j}/{len(cut)}]', chunk) for j, chunk in enumerate(cut, 1)]
n = max(n, -(-len(fails) // cap))
groups = [[] for _ in range(n)]
load = [0] * n
for c, items in sorted(parts, key=lambda kv: -len(kv[1])):
    k = load.index(min(load))
    if load[k] + len(items) > cap:
        groups.append([])
        load.append(0)
        k = len(load) - 1
    groups[k].append((c, items))
    load[k] += len(items)
groups = [g for g in groups if g]
load = [x for x in load if x]

index = ['# Failure groups', '']
for k, g in enumerate(groups, 1):
    md = [f'# Group g{k}: {sum(len(i) for _, i in g)} failing tests', '']
    for c, items in g:
        md.append(f'## {c} ({len(items)})')
        index.append(f'- g{k}: {c} ({len(items)})')
        for b, t, v in sorted(items, key=lambda x: x[1]):
            md += [f'### {t}', f'binary: {b}', f'panic: {v["site"] or "(no panic line captured)"}', f'message: {v["msg"]}', '```']
            md += [x for x in v['out'] if x.strip()][:30]
            md += ['```', '']
    (out / f'g{k}.md').write_text('\n'.join(md))
(out / 'index.md').write_text('\n'.join(index) + '\n')
print(f'{len(fails)} failures in {len(clusters)} clusters -> {len(groups)} groups of at most {cap}: {load}')

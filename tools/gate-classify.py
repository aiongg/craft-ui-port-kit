#!/usr/bin/env python3
"""Sort a racheck gate's errors in one batch's own files into classes:
  later:<sets>  the error names an item a later batch's set writes (its bundle or decisions mention it)
  ra-gap        a diagnostic rust-analyzer reports wrongly (racheck.gap_patterns: test harness and macro gaps)
  mod-file      E0583, a `mod x;` whose file is missing
  downstream    E0282, a type the compiler could infer once the real error is fixed
  macro         the same line reports more than five errors, or the line is an attribute (derive expansions)
  real          everything else: the batch's writers fix these
usage: gate-classify.py GATE.json BATCH_LISTS... --later LATER_LISTS... [--tsv OUT]
GATE.json is racheck-gate's output; the lists hold one set id per line. Ownership comes from work.decide/owners.tsv
(every set a path's line names, as cross-owner reads it; a row's owner column lists the batch's sets among them),
the later sets' names from <work.sets>/<set>/bundle.md and decisions.md."""
import sys as _sys
if _sys.argv[1:2] in (["-h"], ["--help"]):
    print(__doc__)
    _sys.exit(0)
import json,re,sys,collections,os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portkit import config
cfg=config.load()
sets_dir=str(cfg.path('work.sets')); app=str(cfg.path('app.integration'))+'/'
ui_root=cfg.require('app.ui_dirs')[0].rstrip('/')+'/'
args=sys.argv[1:]; gate=args.pop(0)
i=args.index('--later'); mine=args[:i]; rest=args[i+1:]
out=None
if '--tsv' in rest: j=rest.index('--tsv'); out=rest[j+1]; rest=rest[:j]
sets=lambda fs:{x.strip() for f in fs for x in open(f) if x.strip()}
b1=sets(mine); b2=sets(rest)
own={}
for l in open(str(cfg.path('work.decide'))+'/owners.tsv'):
    f=l.rstrip('\n').split('\t')
    if len(f)>=2: own[f[0]]=[x.split(':')[0] for x in f[1].split(',') if x]
# names a later set's sheet mentions (its bundle is what it will write)
later=collections.defaultdict(set)
for s in b2:
    for fn in ('bundle.md','decisions.md'):
        p=f'{sets_dir}/{s}/{fn}'
        if os.path.exists(p):
            for w in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]{2,}',open(p,errors='replace').read())): later[w].add(s)
RA_GAP=re.compile('|'.join(cfg.get('racheck.gap_patterns') or ['(?!)']))
DOWNSTREAM={'E0282'}
_src={}
def src_line(p,n):
    if p not in _src:
        try: _src[p]=open(app+p,errors='replace').read().split('\n')
        except OSError: _src[p]=[]
    L=_src[p]
    return L[n-1].strip()[:160] if 0<n<=len(L) else '?'
r=json.load(open(gate)); rows=[]
for d in r['diagnostics']:
    if d['severity']!='error': continue
    p=d['path'].replace(app,'')
    o=','.join(x for x in own.get(p,[]) if x in b1)
    if not o: continue
    m=d['message']; names=re.findall(r'`([^`]+)`',m)
    key=[n.split('::')[-1].split('<')[0].strip('&mut ') for n in names]
    if d['code'] in DOWNSTREAM: k='downstream'
    elif RA_GAP.search(m): k='ra-gap'
    elif d['code']=='E0583': k='mod-file'
    elif names and later.get(key[0]): k='later:'+','.join(sorted(later[key[0]])[:3])
    else: k='real'
    rows.append([o,p,d['line'],d['code'],k,' '.join(m.split()),src_line(p,d['line'])])
def mod_owner(p,t):
    # `crate::a::b` in the line: the owners of the module files it names
    root=p.split('/src/')[0]+'/src/' if '/src/' in p else ui_root
    os_=set()
    for m in re.findall(r'crate::((?:[a-z_][a-z0-9_]*::)*[a-z_][a-z0-9_]*)',t):
        parts=m.split('::')
        for k in range(len(parts),0,-1):
            base=root+'/'.join(parts[:k])
            for f in (base+'.rs',base+'/mod.rs'):
                if f in own: os_.update(own[f])
    return os_
for x in rows:
    if x[4]=='real':
        o=mod_owner(x[1],x[6])
        if o and o<=b2|set() and o&b2: x[4]='later:'+','.join(sorted(o&b2))
cnt=collections.Counter((x[1],x[2]) for x in rows if x[4]=='real')
for x in rows:
    if x[4]=='real' and (cnt[(x[1],x[2])]>5 or x[6].startswith('#[')): x[4]='macro'
c=collections.Counter(x[4].split(':')[0] for x in rows); print(dict(c))
per=collections.Counter(x[0] for x in rows if x[4]=='real')
for s,n in per.most_common(): print(n,s)
if out:
    with open(out,'w') as f:
        for x in sorted(rows): f.write('\t'.join(map(str,x))+'\n')

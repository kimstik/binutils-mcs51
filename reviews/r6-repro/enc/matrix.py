import itertools, sys
from multiprocessing import Pool
from ref import OPS,F,expected
import h, os, tempfile, subprocess
def run(args):
    m,ops=args
    line=m+(' '+', '.join(ops) if ops else '')
    src='.using 1\nlbl: '+line
    if not hasattr(h,'_mine'):
        h.D=tempfile.mkdtemp(dir=h.D); h._mine=1
    st,err,data,_=h.asm(src)
    exp=expected(m,ops)
    if st=='CRASH': cls='CRASH'
    elif st=='ERR': cls='ERR-ok' if not exp else 'REJECTS-VALID'
    else:
        if data in exp: cls='OK'
        elif exp: cls='WRONG-BYTES(valid insn)'
        else: cls='SILENT-ACCEPT-INVALID'
    return (cls,line,data.hex(' ') if data else '',' / '.join(e.hex(' ') for e in exp),err.splitlines()[0] if err else '')
mn=sorted(F.keys())
kinds=list(OPS.keys())
jobs=[]
for m in mn:
    jobs.append((m,()))
    for a in kinds: jobs.append((m,(a,)))
    for a in kinds:
        for b in kinds: jobs.append((m,(a,b)))
    if m in ('cjne',):
        for a in kinds:
            for b in kinds: jobs.append((m,(a,b,'lbl')))
    else:
        for a in ['a','0x45','r3','acc.7']:
            for b in ['#0x5a','0x45','a']: jobs.append((m,(a,b,'lbl')))
with Pool(16) as p: res=p.map(run,jobs,chunksize=32)
with open('matrix.tsv','w') as fo:
    for r in res: fo.write('\t'.join(r)+'\n')
from collections import Counter
print(Counter(r[0] for r in res))

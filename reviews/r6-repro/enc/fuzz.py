import random, subprocess, os, tempfile, sys
from multiprocessing import Pool
import h
from ref import F
MN=sorted(F)+['jmp','call','movx','b2b']
TOK=['a','r0','r7','@r0','@r1','@r2','#','#5','#-1','#300','0x45','0x20.3','acc.7','/acc.7','/','c','/c','dptr','@dptr','@a+dptr','@a+pc','ab','lbl','ext','high(','low(','b2b(','b2b(0x20,3)','high(lbl)','low(ext)',')','(',',','.','$','+','-','*','<','>','"x"',"'a'",'ar3','p1','psw.3','1f','1b','0x','#high(','#low(lbl)','( 1 , 2 )',' ','\t','==','.3','0x20 .3','@','#@r0','99999999999999999999','-0x8000000000000000','ext-lbl','lbl-ext',';',"\\", 'b2b(lbl,9)','b2b(ext,-1)','#b2b(','0b','0e1','1.0e5']
def line(r):
    n=r.randint(0,6)
    return r.choice(MN)+' '+''.join(r.choice(TOK)+(r.choice([',','',' ']) ) for _ in range(n))
def run(seed):
    r=random.Random(seed)
    lines=[line(r) for _ in range(40)]
    if not hasattr(h,'_m'): h.D=tempfile.mkdtemp(dir=h.D); h._m=1
    src='.using 1\nlbl: nop\n1:\n'+'\n'.join(lines)+'\n1:\n'
    s=os.path.join(h.D,'f.s'); o=os.path.join(h.D,'f.o')
    open(s,'w').write(src)
    p=subprocess.run([h.AS,'-o',o,s],capture_output=True,text=True,timeout=20)
    e=p.stderr
    if p.returncode<0 or 'nternal' in e or 'atal' in e or 'Segmentation' in e:
        return (seed,p.returncode,[l for l in e.splitlines() if 'nternal' in l or 'atal' in l][:3],lines)
    return None
with Pool(8) as P:
    res=[x for x in P.map(run,range(int(sys.argv[1])),chunksize=20) if x]
print(len(res))
for x in res[:15]: print(x[0],x[1],x[2])
import pickle; pickle.dump(res,open('crash.pkl','wb'))

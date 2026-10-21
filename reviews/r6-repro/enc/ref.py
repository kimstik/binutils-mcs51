# Independent MCS-51 reference encoder (Intel MCS-51 opcode map)
# operand samples -> list of (type, value)
OPS = {
 'a':[('A',0)], 'r3':[('R',3)], '@r1':[('I',1)],
 '0x45':[('dir',0x45),('bit',0x45),('code',0x45)],
 'p1':[('dir',0x90)], 'ar5':[('dir',0x0D)],
 '#0x5a':[('imm',0x5a),('imm16',0x5a)],
 'acc.7':[('bit',0xE7)], '0x20.3':[('bit',0x03)],
 '/acc.7':[('nbit',0xE7)], '/0x20.3':[('nbit',0x03)],
 'c':[('C',0)], 'dptr':[('DPTR',0)], '@dptr':[('ADPTR',0)],
 '@a+dptr':[('AADPTR',0)], '@a+pc':[('AAPC',0)], 'ab':[('AB',0)],
 'lbl':[('code',0)],
 '#0x1234':[('imm16',0x1234)],
}
def rel(t,pc_after): return (t-pc_after)&0xff if -128<=t-pc_after<=127 else None
F={}
def f(m,sig,fn): F.setdefault(m,[]).append((sig,fn))
for m,base in [('add',0x20),('addc',0x30),('subb',0x90)]:
    pass
ALU={'add':0x20,'addc':0x30,'subb':0x90,'orl':0x40,'anl':0x50,'xrl':0x60}
for m,b in ALU.items():
    f(m,('A','R'),lambda v,b=b:[b+8+v[1]])
    f(m,('A','dir'),lambda v,b=b:[b+5,v[1]])
    f(m,('A','I'),lambda v,b=b:[b+6+v[1]])
    f(m,('A','imm'),lambda v,b=b:[b+4,v[1]])
for m,b in [('orl',0x40),('anl',0x50),('xrl',0x60)]:
    f(m,('dir','A'),lambda v,b=b:[b+2,v[0]])
    f(m,('dir','imm'),lambda v,b=b:[b+3,v[0],v[1]])
f('orl',('C','bit'),lambda v:[0x72,v[1]]); f('orl',('C','nbit'),lambda v:[0xA0,v[1]])
f('anl',('C','bit'),lambda v:[0x82,v[1]]); f('anl',('C','nbit'),lambda v:[0xB0,v[1]])
f('acall',('code',),lambda v:[0x11|((v[0]>>8)&7)<<5,v[0]&0xff])
f('ajmp',('code',),lambda v:[0x01|((v[0]>>8)&7)<<5,v[0]&0xff])
f('lcall',('code',),lambda v:[0x12,v[0]>>8,v[0]&0xff])
f('ljmp',('code',),lambda v:[0x02,v[0]>>8,v[0]&0xff])
def br(op,ln):
    return lambda v:[op]+list(v[:-1])+[rel(v[-1],ln)] if rel(v[-1],ln) is not None else None
for m,o in [('sjmp',0x80),('jc',0x40),('jnc',0x50),('jz',0x60),('jnz',0x70)]:
    f(m,('code',),lambda v,o=o:[o,rel(v[0],2)])
for m,o in [('jb',0x20),('jnb',0x30),('jbc',0x10)]:
    f(m,('bit','code'),lambda v,o=o:[o,v[0],rel(v[1],3)])
f('cjne',('A','dir','code'),lambda v:[0xB5,v[1],rel(v[2],3)])
f('cjne',('A','imm','code'),lambda v:[0xB4,v[1],rel(v[2],3)])
f('cjne',('R','imm','code'),lambda v:[0xB8+v[0],v[1],rel(v[2],3)])
f('cjne',('I','imm','code'),lambda v:[0xB6+v[0],v[1],rel(v[2],3)])
f('djnz',('R','code'),lambda v:[0xD8+v[0],rel(v[1],2)])
f('djnz',('dir','code'),lambda v:[0xD5,v[0],rel(v[1],3)])
for m,a,c,bt in [('clr',0xE4,0xC3,0xC2),('cpl',0xF4,0xB3,0xB2)]:
    f(m,('A',),lambda v,a=a:[a]); f(m,('C',),lambda v,c=c:[c]); f(m,('bit',),lambda v,bt=bt:[bt,v[0]])
f('setb',('C',),lambda v:[0xD3]); f('setb',('bit',),lambda v:[0xD2,v[0]])
for m,o in [('da',0xD4),('rl',0x23),('rlc',0x33),('rr',0x03),('rrc',0x13),('swap',0xC4)]:
    f(m,('A',),lambda v,o=o:[o])
for m,b in [('inc',0x00),('dec',0x10)]:
    f(m,('A',),lambda v,b=b:[b+4]); f(m,('R',),lambda v,b=b:[b+8+v[0]])
    f(m,('dir',),lambda v,b=b:[b+5,v[0]]); f(m,('I',),lambda v,b=b:[b+6+v[0]])
f('inc',('DPTR',),lambda v:[0xA3])
f('div',('AB',),lambda v:[0x84]); f('mul',('AB',),lambda v:[0xA4])
f('jmp',('AADPTR',),lambda v:[0x73])
f('nop',(),lambda v:[0]); f('ret',(),lambda v:[0x22]); f('reti',(),lambda v:[0x32])
f('push',('dir',),lambda v:[0xC0,v[0]]); f('pop',('dir',),lambda v:[0xD0,v[0]])
f('mov',('A','R'),lambda v:[0xE8+v[1]]); f('mov',('A','dir'),lambda v:[0xE5,v[1]])
f('mov',('A','I'),lambda v:[0xE6+v[1]]); f('mov',('A','imm'),lambda v:[0x74,v[1]])
f('mov',('R','A'),lambda v:[0xF8+v[0]]); f('mov',('R','dir'),lambda v:[0xA8+v[0],v[1]])
f('mov',('R','imm'),lambda v:[0x78+v[0],v[1]])
f('mov',('dir','A'),lambda v:[0xF5,v[0]]); f('mov',('dir','R'),lambda v:[0x88+v[1],v[0]])
f('mov',('dir','dir'),lambda v:[0x85,v[1],v[0]]); f('mov',('dir','I'),lambda v:[0x86+v[1],v[0]])
f('mov',('dir','imm'),lambda v:[0x75,v[0],v[1]])
f('mov',('I','A'),lambda v:[0xF6+v[0]]); f('mov',('I','dir'),lambda v:[0xA6+v[0],v[1]])
f('mov',('I','imm'),lambda v:[0x76+v[0],v[1]])
f('mov',('C','bit'),lambda v:[0xA2,v[1]]); f('mov',('bit','C'),lambda v:[0x92,v[0]])
f('mov',('DPTR','imm16'),lambda v:[0x90,v[1]>>8,v[1]&0xff])
f('movc',('A','AADPTR'),lambda v:[0x93]); f('movc',('A','AAPC'),lambda v:[0x83])
f('movx',('A','I'),lambda v:[0xE2+v[1]]); f('movx',('A','ADPTR'),lambda v:[0xE0])
f('movx',('I','A'),lambda v:[0xF2+v[0]]); f('movx',('ADPTR','A'),lambda v:[0xF0])
f('xch',('A','R'),lambda v:[0xC8+v[1]]); f('xch',('A','dir'),lambda v:[0xC5,v[1]])
f('xch',('A','I'),lambda v:[0xC6+v[1]]); f('xchd',('A','I'),lambda v:[0xD6+v[1]])
import itertools
def expected(m,ops):
    res=set()
    for sig,fn in F.get(m,[]):
        if len(sig)!=len(ops): continue
        choices=[OPS[o] for o in ops]
        for combo in itertools.product(*choices):
            if all(c[0]==s for c,s in zip(combo,sig)):
                out=fn([c[1] for c in combo])
                if out is not None and None not in out: res.add(bytes(out))
    return res

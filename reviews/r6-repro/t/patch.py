import sys,struct
d=bytearray(open(sys.argv[1],'rb').read())
shoff=struct.unpack('>I',d[32:36])[0]; shentsize,shnum=struct.unpack('>HH',d[46:50])
for i in range(shnum):
    o=shoff+i*shentsize
    name,typ,flags,addr,off,size,link,info,align,ent=struct.unpack('>IIIIIIIIII',d[o:o+40])
    if typ==2:
        for j in range(size//16):
            so=off+j*16
            nm,val,sz,inf,oth,shn=struct.unpack('>IIIBBH',d[so:so+16])
            if (inf&0xf)==3 and shn==int(sys.argv[3]):
                struct.pack_into('>H',d,so+14,int(sys.argv[4],0)); print('patched sym',j)
open(sys.argv[2],'wb').write(d)

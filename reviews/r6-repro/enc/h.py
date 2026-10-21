import subprocess, os, sys, tempfile
B='/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/work/modern/build'
AS=B+'/gas/as-new'; OC=B+'/binutils/objcopy'; OD=B+'/binutils/objdump'
D=tempfile.mkdtemp(dir='/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/review/enc')
def asm(src, relocs=False):
    s=os.path.join(D,'t.s'); o=os.path.join(D,'t.o'); b=os.path.join(D,'t.bin')
    open(s,'w').write(src+'\n')
    if os.path.exists(o): os.remove(o)
    r=subprocess.run([AS,'-o',o,s],capture_output=True,text=True)
    err=r.stderr.strip().replace(s+':','')
    if r.returncode<0 or 'internal' in err.lower() or 'fatal' in err.lower():
        return ('CRASH',err,None,'')
    if r.returncode!=0 or not os.path.exists(o):
        return ('ERR',err,None,'')
    subprocess.run([OC,'-O','binary','--only-section=.text',o,b],check=True)
    data=open(b,'rb').read() if os.path.exists(b) else b''
    rel=''
    if relocs:
        rel=subprocess.run([OD,'-r',o],capture_output=True,text=True).stdout
        rel='\n'.join(l for l in rel.splitlines() if l[:1] in '0123456789' and 'R_' in l)
    return ('OK',err,data,rel)
if __name__=='__main__':
    src=sys.stdin.read()
    st,err,data,rel=asm(src,True)
    print(st, data.hex(' ') if data is not None else '', '|', err, '|', rel)

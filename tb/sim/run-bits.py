#!/usr/bin/env python3
"""Run the bit-addressing cases of tb/isa/bits.py against the port.

Assembly cases are assembled alone and their .text bytes compared with the
expected encoding; a case without expected bytes must make the assembler
exit nonzero and say why.  Link cases assemble one B2B against an undefined
symbol and link it with the byte address supplied by --defsym, so the fold
being checked is the linker's.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'isa'))
import bits


class Tools:
    def __init__(self, build):
        self.as_ = os.path.join(build, 'gas', 'as-new')
        self.ld = os.path.join(build, 'ld', 'ld-new')
        self.objcopy = os.path.join(build, 'binutils', 'objcopy')
        for t in (self.as_, self.ld, self.objcopy):
            if not os.path.exists(t):
                sys.exit('missing %s' % t)

    def assemble(self, source, work, obj='in.o'):
        s, o = os.path.join(work, 'in.s'), os.path.join(work, obj)
        open(s, 'w').write('\t.text\n\t.global _START\n_START:\n\t'
                           + source + '\n')
        r = subprocess.run([self.as_, '-o', o, s], capture_output=True, text=True)
        if r.returncode:
            return None, r.stderr.strip()
        return o, None

    def text(self, elf, work):
        b = os.path.join(work, 'out.bin')
        r = subprocess.run([self.objcopy, '-O', 'binary', '--only-section=.text',
                            elf, b], capture_output=True, text=True)
        if r.returncode:
            sys.exit('objcopy failed: %s' % r.stderr.strip())
        return open(b, 'rb').read()

    def link(self, obj, work, defsyms):
        e = os.path.join(work, 'out.elf')
        cmd = [self.ld, '-o', e, obj]
        for k, v in defsyms.items():
            cmd += ['--defsym', '%s=0x%x' % (k, v)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return (e if r.returncode == 0 else None), (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    args = ap.parse_args()
    t = Tools(args.build)

    total = len(bits.ASM_CASES) + len(bits.DIR_CASES) + len(bits.LINK_CASES)
    print('== bits: %d cases' % total)
    bad = []

    with tempfile.TemporaryDirectory() as work:
        for c in bits.ASM_CASES + bits.DIR_CASES:
            obj, err = t.assemble(c['src'], work)
            flat = c['src'].replace('\n\t', ' ; ')
            if c['want'] is None:
                if obj is not None:
                    bad.append('%-18s %-30s accepted, must be rejected'
                               % (c['name'], flat))
                elif c['msg'] and c['msg'] not in err:
                    bad.append('%-18s %-30s rejected, but not for `%s\': %s'
                               % (c['name'], flat, c['msg'],
                                  err.splitlines()[0] if err else ''))
                continue
            if obj is None:
                bad.append('%-18s %-30s %s'
                           % (c['name'], flat, err.splitlines()[-1] if err else 'as failed'))
                continue
            got = t.text(obj, work)
            want = bytes.fromhex(c['want'])
            if got != want:
                bad.append('%-18s %-30s want %s got %s'
                           % (c['name'], flat, want.hex(), got.hex() or 'nothing'))

        for c in bits.LINK_CASES:
            src = 'setb B2B(BDVAR,%d)' % c['off']
            obj, err = t.assemble(src, work, 'link.o')
            if obj is None:
                bad.append('%-18s %-30s %s' % (c['name'], src, err))
                continue
            elf, log = t.link(obj, work, {'BDVAR': c['addr']})
            what = '%s BDVAR=0x%02x' % (src, c['addr'])
            if c['want'] is None:
                if c['msg'] not in log:
                    bad.append('%-18s %-30s expected `%s\', got: %s'
                               % (c['name'], what, c['msg'],
                                  log.splitlines()[-1] if log else 'a clean link'))
                continue
            if elf is None:
                bad.append('%-18s %-30s link failed: %s'
                           % (c['name'], what, log.splitlines()[-1] if log else ''))
                continue
            got = t.text(elf, work)
            if len(got) < 2 or got[1] != c['want']:
                bad.append('%-18s %-30s want bit 0x%02x got %s'
                           % (c['name'], what, c['want'],
                              '0x%02x' % got[1] if len(got) > 1 else 'nothing'))
            elif log:
                bad.append('%-18s %-30s linked, but complained: %s'
                           % (c['name'], what, log.splitlines()[-1]))

    print('   checked:  %d/%d' % (total - len(bad), total))
    for line in bad:
        print('     ' + line)
    print('FAIL: %d' % len(bad) if bad else 'PASS')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

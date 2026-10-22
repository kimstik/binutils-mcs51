#!/usr/bin/env python3
"""Run the literal-branch cases of tb/isa/branch.py against the port.

Every case is assembled at its stated .text offset, linked with .text at
address 0, and the linked bytes are compared with the hand-derived
encoding; a case without expected bytes must make the assembler or the
linker exit nonzero.  A branch to a constant address is only final once
the address of the branch is, so its range is the linker's to judge.
"""

import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'isa'))
import branch

def assemble(as_, ld, objcopy, source, work):
    """Return (linked .text bytes, None) or (None, the error line)."""
    s, o, e, b = (os.path.join(work, n)
                  for n in ('in.s', 'in.o', 'in.elf', 'in.bin'))
    open(s, 'w').write(source + '\n')
    for cmd in ([as_, '-o', o, s], [ld, '-o', e, o]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            return None, (r.stderr.strip().splitlines()
                          or ['%s failed' % cmd[0]])[-1]
    r = subprocess.run([objcopy, '-O', 'binary', '--only-section=.text', e, b],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit('objcopy failed: %s' % r.stderr.strip())
    return open(b, 'rb').read(), None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    args = ap.parse_args()

    as_ = os.path.join(args.build, 'gas', 'as-new')
    ld = os.path.join(args.build, 'ld', 'ld-new')
    objcopy = os.path.join(args.build, 'binutils', 'objcopy')
    for t in (as_, ld, objcopy):
        if not os.path.exists(t):
            sys.exit('missing %s' % t)

    print('== branch: %d cases' % len(branch.CASES))
    bad = []
    # Cases that reported, not messages: the numerator has to stay a count of
    # cases that passed even if a case ever grows a second complaint.
    failed = set()

    def fail(name, detail):
        bad.append('%-16s %s' % (name, detail))
        failed.add(name)

    with tempfile.TemporaryDirectory() as work:
        for c in branch.CASES:
            pad = c['skip']
            source = ('.skip 0x%x\n' % pad if pad else '') + c['src']
            got, err = assemble(as_, ld, objcopy, source, work)

            if c['want'] is None:
                if err is None:
                    fail(c['name'], '%-22s accepted, must be rejected'
                         % c['src'])
                continue

            want = bytes(pad) + bytes.fromhex(c['want'])
            if err is not None:
                fail(c['name'], '%-22s %s' % (c['src'], err))
            elif got[:len(want)] != want:
                if got[:pad] == want[:pad]:
                    what = 'want %s got %s' % (want[pad:].hex(),
                                               got[pad:].hex() or 'nothing')
                else:
                    what = 'padding differs, want %d zero bytes' % pad
                fail(c['name'], '%-22s %s' % (c['src'], what))

    print('   checked:  %d/%d' % (len(branch.CASES) - len(failed),
                                  len(branch.CASES)))
    for line in bad:
        print('     ' + line)
    print('FAIL: %d' % len(bad) if bad else 'PASS')
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main())

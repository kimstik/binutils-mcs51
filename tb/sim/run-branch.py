#!/usr/bin/env python3
"""Run the literal-branch cases of tb/isa/branch.py against the port.

Every case is assembled at its stated .text offset and the raw section
bytes are compared with the hand-derived encoding; a case without
expected bytes must make the assembler exit nonzero.
"""

import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'isa'))
import branch

def assemble(as_, objcopy, source, work):
    """Return (.text bytes, None) or (None, assembler error line)."""
    s, o, b = (os.path.join(work, n) for n in ('in.s', 'in.o', 'in.bin'))
    open(s, 'w').write(source + '\n')
    r = subprocess.run([as_, '-o', o, s], capture_output=True, text=True)
    if r.returncode:
        return None, (r.stderr.strip().splitlines() or ['as failed'])[-1]
    r = subprocess.run([objcopy, '-O', 'binary', '--only-section=.text', o, b],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit('objcopy failed: %s' % r.stderr.strip())
    return open(b, 'rb').read(), None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    args = ap.parse_args()

    as_ = os.path.join(args.build, 'gas', 'as-new')
    objcopy = os.path.join(args.build, 'binutils', 'objcopy')
    for t in (as_, objcopy):
        if not os.path.exists(t):
            sys.exit('missing %s' % t)

    print('== branch: %d cases' % len(branch.CASES))
    bad = []
    with tempfile.TemporaryDirectory() as work:
        for c in branch.CASES:
            pad = c['skip']
            source = ('.skip 0x%x\n' % pad if pad else '') + c['src']
            got, err = assemble(as_, objcopy, source, work)

            if c['want'] is None:
                if err is None:
                    bad.append('%-16s %-22s accepted, must be rejected'
                               % (c['name'], c['src']))
                continue

            want = bytes(pad) + bytes.fromhex(c['want'])
            if err is not None:
                bad.append('%-16s %-22s %s' % (c['name'], c['src'], err))
            elif got != want:
                if got[:pad] == want[:pad]:
                    what = 'want %s got %s' % (want[pad:].hex(),
                                               got[pad:].hex() or 'nothing')
                else:
                    what = 'padding differs, want %d zero bytes' % pad
                bad.append('%-16s %-22s %s' % (c['name'], c['src'], what))

    print('   checked:  %d/%d' % (len(branch.CASES) - len(bad),
                                  len(branch.CASES)))
    for line in bad:
        print('     ' + line)
    print('FAIL: %d' % len(bad) if bad else 'PASS')
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main())

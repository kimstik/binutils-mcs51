#!/usr/bin/env python3
"""Instruction-level gate for the MCS-51 port.

  table     assemble every line of 8051.txt and compare with the golden bytes.
            Those came from c51asm, an assembler sharing no ancestry with ours,
            so agreement means both agree with the ISA rather than with each other.
  decode    feed the same golden bytes to our disassembler; every one must decode.
  program   assemble testall.asm, a real self-checking program. Covers what a
            one-instruction-per-line table cannot: branches, fixups, tables.
"""

import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialect


def hex_payload(record):
    """Bytes carried by one Intel HEX data record."""
    raw = bytes.fromhex(record[1:])
    return raw[4:4 + raw[0]]


def read_table(path):
    out = []
    for n, line in enumerate(open(path), 1):
        line = line.strip()
        if line and not line.startswith('#') and '|' in line:
            src, rec = line.split('|', 1)
            out.append((n, src.strip(), hex_payload(rec.strip())))
    return out


class Tools:
    def __init__(self, build):
        self.as_ = os.path.join(build, 'gas', 'as-new')
        self.objcopy = os.path.join(build, 'binutils', 'objcopy')
        self.objdump = os.path.join(build, 'binutils', 'objdump')
        for t in (self.as_, self.objcopy, self.objdump):
            if not os.path.exists(t):
                sys.exit('missing %s' % t)

    def assemble(self, source, work):
        """Assemble a fragment; return its .text bytes, or an error string."""
        s, o, b = (os.path.join(work, n) for n in ('in.s', 'in.o', 'in.bin'))
        open(s, 'w').write(source + '\n')
        r = subprocess.run([self.as_, '-o', o, s], capture_output=True, text=True)
        if r.returncode:
            return (r.stderr.strip().splitlines() or ['as failed'])[-1]
        r = subprocess.run([self.objcopy, '-O', 'binary', '--only-section=.text', o, b],
                           capture_output=True, text=True)
        if r.returncode:
            return r.stderr.strip() or 'objcopy failed'
        return open(b, 'rb').read()

    def decodes(self, data, work):
        """True if our disassembler makes sense of these bytes."""
        b = os.path.join(work, 'out.bin')
        open(b, 'wb').write(data)
        r = subprocess.run([self.objdump, '-D', '-b', 'binary', '-m', 'i51', b],
                           capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.strip() and '(bad)' not in r.stdout


def report(what, entries, bad):
    print('   %-9s %d/%d' % (what + ':', len(entries) - len(bad), len(entries)))
    for line in bad[:20]:
        print('     ' + line)
    if len(bad) > 20:
        print('     ... %d more' % (len(bad) - 20))
    return len(bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    ap.add_argument('--table', help='naken_asm style instruction|hex table')
    ap.add_argument('--program', help='assembly program to assemble')
    ap.add_argument('--dialect', action='store_true',
                    help='rewrite --program from Intel/ASEM-51 spelling first')
    args = ap.parse_args()

    tools = Tools(args.build)
    failures = 0

    with tempfile.TemporaryDirectory() as work:
        if args.table:
            entries = read_table(args.table)
            print('== table: %d instructions' % len(entries))

            bad = []
            for n, src, want in entries:
                got = tools.assemble(src, work)
                if isinstance(got, str):
                    bad.append('line %-4d %-28s want %-12s %s' % (n, src, want.hex(), got))
                elif got != want:
                    bad.append('line %-4d %-28s want %-12s got %s'
                               % (n, src, want.hex(), got.hex()))
            failures += report('assemble', entries, bad)

            bad = ['line %-4d %-28s bytes %s' % (n, src, want.hex())
                   for n, src, want in entries if not tools.decodes(want, work)]
            failures += report('decode', entries, bad)

        if args.program:
            print('== program: %s' % os.path.basename(args.program))
            source = open(args.program, encoding='latin-1').read()
            if args.dialect:
                source = dialect.translate(source)
            got = tools.assemble(source, work)
            if isinstance(got, str):
                print('   FAILED: %s' % got)
                failures += 1
            else:
                print('   assembled, %d bytes of text' % len(got))

    print('FAIL: %d' % failures if failures else 'PASS')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

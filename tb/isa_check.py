#!/usr/bin/env python3
"""Instruction-level gate for the MCS-51 port.

Three checks, each with its own kind of evidence:

  table       assemble every line of 8051.txt and compare with the golden bytes.
              The golden column came from c51asm, an assembler with no shared
              ancestry with ours, so agreement means both agree with the ISA.
  decode      feed those same golden bytes to our disassembler and require that
              every one of them decodes.
  program     assemble testall.asm, a real self-checking program. Covers what a
              one-instruction-per-line table cannot: branches, fixups, tables.
"""

import argparse
import os
import subprocess
import sys
import tempfile


def hex_payload(record):
    """Bytes carried by one Intel HEX data record."""
    raw = bytes.fromhex(record[1:])
    count = raw[0]
    return raw[4:4 + count]


def read_table(path):
    out = []
    for n, line in enumerate(open(path), 1):
        line = line.strip()
        if not line or line.startswith('#') or '|' not in line:
            continue
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

    def assemble(self, source, workdir):
        """Assemble one fragment, return its .text bytes or an error string."""
        s = os.path.join(workdir, 'in.s')
        o = os.path.join(workdir, 'in.o')
        b = os.path.join(workdir, 'in.bin')
        with open(s, 'w') as fh:
            fh.write(source + '\n')
        r = subprocess.run([self.as_, '-o', o, s], capture_output=True, text=True)
        if r.returncode:
            return r.stderr.strip().splitlines()[-1] if r.stderr else 'as failed'
        r = subprocess.run([self.objcopy, '-O', 'binary', '--only-section=.text', o, b],
                           capture_output=True, text=True)
        if r.returncode:
            return r.stderr.strip() or 'objcopy failed'
        return open(b, 'rb').read()

    def disassemble(self, data, workdir):
        b = os.path.join(workdir, 'out.bin')
        open(b, 'wb').write(data)
        r = subprocess.run([self.objdump, '-D', '-b', 'binary', '-m', 'i51', b],
                           capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr


def check_table(tools, entries, work):
    bad = []
    for n, src, want in entries:
        got = tools.assemble(src, work)
        if isinstance(got, str):
            bad.append((n, src, want, got))
        elif got != want:
            bad.append((n, src, want, got.hex()))
    return bad


def check_decode(tools, entries, work):
    bad = []
    for n, src, want in entries:
        rc, out, err = tools.disassemble(want, work)
        if rc or '(bad)' in out or 'unknown' in out.lower() or not out.strip():
            bad.append((n, src, want, (err or out).strip().splitlines()[-1:] or ['no output']))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    ap.add_argument('--table', help='naken_asm style instruction|hex table')
    ap.add_argument('--program', help='assembly program to assemble')
    ap.add_argument('--sed', help='dialect translation applied to --program first')
    args = ap.parse_args()

    tools = Tools(args.build)
    failures = 0

    with tempfile.TemporaryDirectory() as work:
        if args.table:
            entries = read_table(args.table)
            print('== table: %d instructions' % len(entries))

            bad = check_table(tools, entries, work)
            print('   assemble: %d/%d match' % (len(entries) - len(bad), len(entries)))
            for n, src, want, got in bad[:20]:
                print('     line %-4d %-28s want %-14s got %s'
                      % (n, src, want.hex(), got))
            if len(bad) > 20:
                print('     ... %d more' % (len(bad) - 20))
            failures += len(bad)

            bad = check_decode(tools, entries, work)
            print('   decode:   %d/%d decode' % (len(entries) - len(bad), len(entries)))
            for n, src, want, why in bad[:20]:
                print('     line %-4d %-28s bytes %-14s %s' % (n, src, want.hex(), why))
            if len(bad) > 20:
                print('     ... %d more' % (len(bad) - 20))
            failures += len(bad)

        if args.program:
            print('== program: %s' % os.path.basename(args.program))
            source = open(args.program, encoding='latin-1').read()
            if args.sed:
                source = subprocess.run(['sed', '-f', args.sed], input=source,
                                        capture_output=True, text=True).stdout
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

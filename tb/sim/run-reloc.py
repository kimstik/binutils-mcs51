#!/usr/bin/env python3
"""End-to-end coverage of every relocation kind the port emits.

The instruction gate never links, and the project testbench links only what
those ten programs happen to contain.  Between them no test says which
relocation an instruction produces, what the linker must leave in the byte
when it resolves it, or where each kind's range ends.  That is what this
does, in six steps:

  emit      one object holding every relocation kind, checked against the
            exact list of (offset, type, symbol) it has to carry.
  resolve   the same object linked with the symbols supplied by --defsym,
            checked byte for byte.  A howto whose size or shift is wrong
            shows up here, because the wrong number of bytes moves.
  range     the two relocations with a range rule - the 8-bit displacement
            of R_I51_7_PCREL and the 2K page of R_I51_11 - linked one unit
            inside and one unit outside their limit, on both sides.
  fold      the same relocations when gas resolves them itself, because the
            symbol turns out to be one it can resolve - absolute, or defined
            in the section the instruction is in: the second copy of every
            range rule lives there, in md_apply_fix.
  data      HIGH() and LOW() in a data directive, which reach the assembler
            through TC_PARSE_CONS_EXPRESSION rather than through operand
            parsing.  They are how a little-endian datum is written on a
            target whose .word is high byte first, so both orders sit in
            one image and cannot silently become the same thing.
  identity  the same program linked straight, through `ld -r', and out of
            an archive member, all three of which must produce the same
            bytes.

  usage: run-reloc.py --build BUILD-DIR
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

# Every relocation kind, one instruction each, in one section.  Symbols are
# undefined on purpose: an assembler that folds them early emits no
# relocation and the first step notices.
PROBE = """\
\t.text
\t.global _START
_START:
\tmov\ta,#DVAR
\tmov\ta,#LOW(XSYM)
\tmov\ta,#HIGH(XSYM)
\tsetb\tBITSYM
\tsetb\tB2B(BDVAR,1)
\tsjmp\tNEAR
\tajmp\tPAGE
\tljmp\tFAR
\tmov\tdptr,#XSYM
\tmov\tDVAR,#0x11
\tsetb\tB2B(LOCALBD,3)
\t.bdata
LOCALBD:\t.byte\t0
"""

# offset, type, symbol.  LOCALBD is local, so its relocation is against the
# section symbol and the byte address arrives as the addend.
WANT_RELOCS = [
    (0x01, 'R_I51_8',       'DVAR'),
    (0x03, 'R_I51_L',       'XSYM'),
    (0x05, 'R_I51_H',       'XSYM'),
    (0x07, 'R_I51_8_BIT',   'BITSYM'),
    (0x09, 'R_I51_8_B2B',   'BDVAR'),
    (0x0b, 'R_I51_7_PCREL', 'NEAR'),
    (0x0c, 'R_I51_11',      'PAGE'),
    (0x0f, 'R_I51_16',      'FAR'),
    (0x12, 'R_I51_16',      'XSYM'),
    (0x15, 'R_I51_8',       'DVAR'),
    (0x18, 'R_I51_8_B2B',   '.bdata'),
]

DEFS = {'DVAR': 0x35, 'XSYM': 0x1234, 'BITSYM': 0x7f, 'BDVAR': 0x2f,
        'NEAR': 0x0020, 'PAGE': 0x0345, 'FAR': 0x1234}

#   74 35        mov a,#DVAR            R_I51_8      -> 0x35
#   74 34        mov a,#LOW(0x1234)     R_I51_L      -> 0x34
#   74 12        mov a,#HIGH(0x1234)    R_I51_H      -> 0x12
#   d2 7f        setb 0x7f              R_I51_8_BIT  -> 0x7f
#   d2 79        setb B2B(0x2f,1)       R_I51_8_B2B  -> (0x2f-0x20)*8+1
#   80 14        sjmp 0x20              R_I51_7_PCREL-> 0x20-0x0c
#   61 45        ajmp 0x345             R_I51_11     -> A10..A0 of 0x345
#   02 12 34     ljmp 0x1234            R_I51_16
#   90 12 34     mov dptr,#0x1234       R_I51_16
#   75 35 11     mov 0x35,#0x11         R_I51_8      -> 0x35
#   d2 03        setb B2B(.bdata+0,3)   R_I51_8_B2B  -> .bdata is 0x20
#   22           the RET stub the default script appends
WANT_TEXT = '743574347412d27fd27980146145021234901234753511d20322'

# The same two operators reaching a data directive, and left to the linker
# rather than folded by gas.  XSYM is 0x1234, so the LOW/HIGH pair reads
# 34 12 - a little-endian datum - and the .word after it reads 12 34, which
# is the target's own order.  Both spellings sit in one image so the two
# cannot silently become the same thing.
DATA_PROBE = """\
\t.text
\t.global _START
_START:
\t.byte\tLOW(XSYM)
\t.byte\tHIGH(XSYM)
\t.word\tXSYM
"""
DATA_RELOCS = [
    (0x00, 'R_I51_L',  'XSYM'),
    (0x01, 'R_I51_H',  'XSYM'),
    (0x02, 'R_I51_16', 'XSYM'),
]
#   34 12     .byte LOW(XSYM), .byte HIGH(XSYM)   low byte first
#   12 34     .word XSYM                          high byte first
#   22        the RET stub the default script appends
DATA_TEXT = '3412' '1234' '22'

# The range probes are linked with sim/link.ld, which places .text at 0 and
# nothing else: the default script starts the RAM spaces at the end of
# .text, and a probe with 2K of padding would trip its RAM overflow assert
# before any relocation was applied.
#
# sjmp at .text+0x100: its displacement byte is at 0x101 and the
# instruction ends at 0x102, so the reachable window is 0x082..0x181.
PCREL_PROBE = '\t.text\n\t.global _START\n_START:\n\t.skip 0x100\n\tsjmp NEAR\n'
PCREL_CASES = [('pcrel-back-min', 0x082, True),
               ('pcrel-back-over', 0x081, False),
               ('pcrel-fwd-max', 0x181, True),
               ('pcrel-fwd-over', 0x182, False)]

# ajmp at .text+0x7fe ends at 0x800, so its 2K page is 0x800..0xfff.
PAGE_PROBE = '\t.text\n\t.global _START\n_START:\n\t.skip 0x7fe\n\tajmp PAGE\n'
PAGE_CASES = [('page-cross-ok', 0x802, True),
              ('page-below', 0x7fd, False),
              ('page-top', 0xfff, True),
              ('page-above', 0x1000, False)]

def fcase(name, src, want, msg=None):
    return {'name': name, 'src': src, 'want': want, 'msg': msg}


# A symbol defined after the instruction is still local and absolute, so gas
# resolves the fixup itself and md_apply_fix - not the linker - applies the
# relocation and its range check.
FOLD_CASES = [
    fcase('fold-16',      'ljmp S\nS = 0x1234',            '02 12 34'),
    fcase('fold-16-dptr', 'mov dptr,#S\nS = 0xbeef',       '90 be ef'),
    fcase('fold-high',    'mov a,#HIGH(S)\nS = 0x1234',    '74 12'),
    fcase('fold-low',     'mov a,#LOW(S)\nS = 0x1234',     '74 34'),
    fcase('fold-high-k',  'mov a,#HIGH(0x1234)',           '74 12'),
    fcase('fold-low-k',   'mov a,#LOW(0x1234)',            '74 34'),
    fcase('fold-8',       'mov a,#S\nS = 0xff',            '74 ff'),
    fcase('fold-8-over',  'mov a,#S\nS = 0x100',           None, 'out of range'),
    fcase('fold-high-max', 'mov a,#HIGH(S)\nS = 0xffff',    '74 ff'),
    fcase('fold-high-over', 'mov a,#HIGH(S)\nS = 0x12345', None, 'out of range'),
    fcase('fold-8-konst', 'mov a,#0x1234',                 None, 'out of 8-bit range'),
    fcase('fold-16-konst', 'mov dptr,#0x12345',            None, 'out of 16-bit range'),
    # A branch operand names an address; HIGH/LOW/B2B on one is meaningless
    # and has to be refused rather than silently truncating the target.
    fcase('fold-prefix-ljmp', 'ljmp LOW(S)\nS = 0x1234',   None, 'not allowed'),
    fcase('fold-prefix-sjmp', 'sjmp LOW(S)\nS = 0x1234',   None, 'not allowed'),

    # A relative branch to a label defined in this file and this section.
    # gas folds a local label away before md_apply_fix, so that fixup
    # arrives with no symbol at all; a global one keeps its symbol - the
    # linker may override it - and arrives with the symbol value already
    # applied to the displacement.  A label at offset 0 encodes the same
    # byte either way, so none of the three below sits there.
    fcase('pcrel-local',   'nop\n\tnop\nLOC:\tsjmp LOC', '00 00 80 fe'),
    fcase('pcrel-global',  'nop\n\tnop\n\t.global G\nG:\tsjmp G', '00 00 80 fe'),
    fcase('pcrel-global-fwd', '.global G\n\tsjmp G\n\tnop\n\tnop\nG:\tnop',
          '80 02 00 00 00'),

    # .pcode carries a 13-bit exec address in a 16-bit word whose top three
    # bits are flags. Nothing else in the testbench reaches it, in either
    # the assembler or the linker.
    fcase('pcode-min',    '.pcode 0x100',                  '01 00 00'),
    fcase('pcode-max',    '.pcode 0x1fff',                 '1f ff 00'),
    fcase('pcode-over',   '.pcode 0x2000',                 None, 'out of 13-bit range'),
    fcase('pcode-under',  '.pcode 0xff',                   None, 'underflow'),
    fcase('pcode-sym',    '.pcode S\nS = 0x123',           '01 23 00'),
    fcase('pcode-sym-under', '.pcode S\nS = 0xff',         None, 'underflow'),

    # HIGH() and LOW() in a data directive.  .word is high byte first, so
    # this is how a little-endian datum is written on this target, and the
    # operators have to reach .byte the same way they reach an operand.
    fcase('data-low',      '.byte LOW(S)\nS = 0x1234',     '34'),
    fcase('data-high',     '.byte HIGH(S)\nS = 0x1234',    '12'),
    fcase('data-pair',     '.byte LOW(S),HIGH(S)\nS = 0x1234', '34 12'),
    fcase('data-lowercase', '.byte low(S)\nS = 0x1234',    '34'),
    fcase('data-spaced',   '.byte HIGH (S)\nS = 0x1234',   '12'),
    fcase('data-word',     '.word S\nS = 0x1234',          '12 34'),
    # The keyword ends where it ends: LOWMARK is a symbol, not LOW applied
    # to MARK, and neither is HIGHEST.
    fcase('data-name-guard', '.byte LOWMARK\nLOWMARK = 0x5a', '5a'),
    fcase('data-name-guard2', '.byte HIGHEST\nHIGHEST = 0x77', '77'),
    # Both relocations write one byte and have no wider form.
    fcase('data-low-word', '.word LOW(S)\nS = 0x1234',     None, 'one byte operand'),
]

# `.pcode PSYM' left to the linker: R_I51_13_PCODE. want is the first three
# bytes of the linked .text; msg means the link has to say so instead.
PCODE_LINK = [
    ('pcode-link',       0x0123, '012300', None),
    # Both of these fail the link now: the field has thirteen bits and the top
    # three are flags, so a target that does not fit has nowhere to go, and a
    # relocation the port cannot apply must not leave a byte meaning something
    # else behind it.  want None with a msg means ld has to refuse and say so.
    ('pcode-link-wrap',  0x2345, None, 'truncated to fit'),
    ('pcode-link-under', 0x00ff, None, 'out of range'),
]

A_SRC = """\
\t.text
\t.global _START
_START:\tljmp\tFUN
\tsjmp\tFUN2
\tmov\ta,#LOW(FUN)
\tsetb\tB2B(BVAR,1)
"""
B_SRC = """\
\t.text
\t.global FUN
\t.global FUN2
FUN:\tnop
FUN2:\tret
\t.bdata
\t.global BVAR
BVAR:\t.byte\t0
"""

HERE = os.path.dirname(os.path.abspath(__file__))

RELOC = re.compile(r'^([0-9a-f]+)\s+[0-9a-f]+\s+(\S+)\s+[0-9a-f]+\s+(\S+)')


class Tools:
    def __init__(self, build):
        self.as_ = os.path.join(build, 'gas', 'as-new')
        self.ld = os.path.join(build, 'ld', 'ld-new')
        self.ar = os.path.join(build, 'binutils', 'ar')
        self.objcopy = os.path.join(build, 'binutils', 'objcopy')
        self.readelf = os.path.join(build, 'binutils', 'readelf')
        for t in (self.as_, self.ld, self.ar, self.objcopy, self.readelf):
            if not os.path.exists(t):
                sys.exit('missing %s' % t)
        self.work = None

    def path(self, name):
        return os.path.join(self.work, name)

    def assemble(self, source, name):
        s, o = self.path(name + '.s'), self.path(name + '.o')
        open(s, 'w').write(source)
        r = subprocess.run([self.as_, '-o', o, s], capture_output=True, text=True)
        if r.returncode:
            sys.exit('as failed on %s: %s' % (name, r.stderr.strip()))
        return o

    def relocs(self, obj):
        r = subprocess.run([self.readelf, '-r', '--wide', obj],
                           capture_output=True, text=True)
        out = []
        for line in r.stdout.replace('\r', '').splitlines():
            m = RELOC.match(line.strip())
            if m and m.group(2).startswith('R_I51'):
                out.append((int(m.group(1), 16), m.group(2), m.group(3)))
        return out

    def link(self, objs, name, defs=None, extra=()):
        e = self.path(name + '.elf')
        cmd = [self.ld, '-o', e] + list(extra) + list(objs)
        for k, v in (defs or {}).items():
            cmd += ['--defsym', '%s=0x%x' % (k, v)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return (e if r.returncode == 0 else None), (r.stdout + r.stderr).strip()

    def text(self, elf, name):
        b = self.path(name + '.bin')
        r = subprocess.run([self.objcopy, '-O', 'binary', '--only-section=.text',
                            elf, b], capture_output=True, text=True)
        if r.returncode:
            sys.exit('objcopy failed: %s' % r.stderr.strip())
        return open(b, 'rb').read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    args = ap.parse_args()
    t = Tools(args.build)

    bad = []
    checks = 0

    def fail(what, detail):
        bad.append('%-18s %s' % (what, detail))

    with tempfile.TemporaryDirectory() as work:
        t.work = work

        # ---- emit -----------------------------------------------------
        obj = t.assemble(PROBE, 'probe')
        got = t.relocs(obj)
        checks += 1
        if got != WANT_RELOCS:
            for w, g in zip(WANT_RELOCS, got + [None] * len(WANT_RELOCS)):
                if w != g:
                    fail('emit', 'want %s got %s' % (w, g))
            if len(got) != len(WANT_RELOCS):
                fail('emit', '%d relocations, expected %d'
                     % (len(got), len(WANT_RELOCS)))

        # ---- resolve --------------------------------------------------
        checks += 1
        elf, log = t.link([obj], 'probe', DEFS)
        if elf is None:
            fail('resolve', 'link failed: %s' % (log.splitlines()[-1] if log else ''))
        else:
            img = t.text(elf, 'probe').hex()
            if img != WANT_TEXT:
                fail('resolve', 'image %s\n%18s expected %s' % (img, '', WANT_TEXT))

        # An 8-bit absolute relocation does not complain about a value that
        # does not fit; it keeps the low byte.  Pinned because it is the
        # contract the projects rely on, not because it is pretty.
        checks += 1
        elf, log = t.link([obj], 'trunc', dict(DEFS, DVAR=0x1234))
        if elf is None:
            fail('resolve-trunc', 'link failed: %s' % log.splitlines()[-1])
        elif t.text(elf, 'trunc')[1] != 0x34:
            fail('resolve-trunc', 'R_I51_8 of 0x1234 left 0x%02x, expected 0x34'
                 % t.text(elf, 'trunc')[1])

        # ---- data directives ------------------------------------------
        dobj = t.assemble(DATA_PROBE, 'data')
        checks += 1
        got = t.relocs(dobj)
        if got != DATA_RELOCS:
            fail('data-emit', 'want %s got %s' % (DATA_RELOCS, got))

        checks += 1
        elf, log = t.link([dobj], 'data', DEFS)
        if elf is None:
            fail('data-resolve', 'link failed: %s'
                 % (log.splitlines()[-1] if log else ''))
        else:
            img = t.text(elf, 'data').hex()
            if img != DATA_TEXT:
                fail('data-resolve', 'image %s, expected %s' % (img, DATA_TEXT))

        # ---- range ----------------------------------------------------
        for probe, cases, sym, name in ((PCREL_PROBE, PCREL_CASES, 'NEAR', 'pcrel'),
                                        (PAGE_PROBE, PAGE_CASES, 'PAGE', 'page')):
            o = t.assemble(probe, name)
            for case, value, ok in cases:
                checks += 1
                elf, log = t.link([o], case, {sym: value},
                                  extra=['-T', os.path.join(HERE, 'link.ld')])
                if ok and elf is None:
                    fail(case, 'rejected 0x%x, which is in range: %s'
                         % (value, log.splitlines()[-1] if log else ''))
                elif not ok and elf is not None:
                    fail(case, 'accepted 0x%x, which is out of range' % value)
                elif not ok and 'truncated to fit' not in log:
                    fail(case, 'rejected 0x%x but not as an overflow: %s'
                         % (value, log.splitlines()[-1] if log else ''))

        # ---- fold -----------------------------------------------------
        for c in FOLD_CASES:
            checks += 1
            src = '\t.text\n\t.global _START\n_START:\n\t%s\n' % c['src']
            path = t.path('fold.s')
            open(path, 'w').write(src)
            r = subprocess.run([t.as_, '-o', t.path('fold.o'), path],
                               capture_output=True, text=True)
            flat = c['src'].replace('\n', ' ; ')
            if c['want'] is None:
                if r.returncode == 0:
                    fail(c['name'], '%-28s accepted, must be rejected' % flat)
                elif c['msg'] not in r.stderr:
                    fail(c['name'], '%-28s rejected, but not for `%s\': %s'
                         % (flat, c['msg'], r.stderr.strip().splitlines()[-1]))
                continue
            if r.returncode:
                fail(c['name'], '%-28s %s'
                     % (flat, r.stderr.strip().splitlines()[-1]))
                continue
            got = t.text(t.path('fold.o'), 'fold')
            want = bytes.fromhex(c['want'])
            if got != want:
                fail(c['name'], '%-28s want %s got %s'
                     % (flat, want.hex(), got.hex() or 'nothing'))

        for name, value, want, msg in PCODE_LINK:
            checks += 1
            o = t.assemble('\t.text\n\t.global _START\n_START:\n\t.pcode PSYM\n',
                           name)
            elf, log = t.link([o], name, {'PSYM': value})
            if want is None:
                # A refused link leaves no ELF; what must be true either way is
                # that ld said why.
                if msg not in log:
                    fail(name, 'PSYM=0x%x expected `%s\', got: %s'
                         % (value, msg, log.splitlines()[-1] if log else 'a clean link'))
                continue
            if elf is None:
                fail(name, 'PSYM=0x%x link failed: %s' % (value, log))
                continue
            got = t.text(elf, name)[:3].hex()
            if got != want:
                fail(name, 'PSYM=0x%x left %s, expected %s' % (value, got, want))

        # ---- identity -------------------------------------------------
        a, b = t.assemble(A_SRC, 'a'), t.assemble(B_SRC, 'b')
        elf, log = t.link([a, b], 'direct')
        if elf is None:
            fail('identity', 'straight link failed: %s' % log)
        else:
            straight = t.text(elf, 'direct')

            checks += 1
            comb, log = t.link([a, b], 'partial', extra=['-r'])
            if comb is None:
                fail('relink', 'ld -r failed: %s' % log)
            else:
                elf2, log = t.link([comb], 'relinked')
                if elf2 is None:
                    fail('relink', 'final link of the -r output failed: %s' % log)
                else:
                    img = t.text(elf2, 'relinked')
                    if img != straight:
                        fail('relink', 'via -r %s, straight %s'
                             % (img.hex(), straight.hex()))

            checks += 1
            lib = t.path('libprobe.a')
            r = subprocess.run([t.ar, 'rcs', lib, b], capture_output=True, text=True)
            if r.returncode:
                fail('archive', 'ar failed: %s' % r.stderr.strip())
            else:
                elf3, log = t.link([a, lib], 'fromar')
                if elf3 is None:
                    fail('archive', 'link against the archive failed: %s' % log)
                else:
                    img = t.text(elf3, 'fromar')
                    if img != straight:
                        fail('archive', 'from archive %s, straight %s'
                             % (img.hex(), straight.hex()))

    print('== reloc: %d checks' % checks)
    print('   checked:  %d/%d' % (checks - len(bad), checks))
    for line in bad:
        print('     ' + line)
    print('FAIL: %d' % len(bad) if bad else 'PASS')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Instruction-level gate for the MCS-51 port.

  assemble  assemble every line of 8051.txt and compare with the golden bytes.
            Those came from c51asm, an assembler sharing no ancestry with ours,
            so agreement means both agree with the ISA rather than with each other.
  decode    feed the same golden bytes to our disassembler.  Each must come back
            as exactly one instruction that consumes exactly those bytes and
            carries a mnemonic rather than the `.byte 0xNN ; ????' fallback.
            print_insn_i51 never emits `(bad)', so a check for that string alone
            would be a condition this disassembler cannot violate; the byte span
            and the mnemonic are conditions it can.
  roundtrip take the instruction `decode' printed, feed it back to the assembler
            and require the same bytes again.  Where the two ways of printing a
            branch target disagree - the displacement in the operand against the
            absolute address in the comment - that is caught first, because
            re-assembly goes through the absolute one and would not see it.
            gas and the disassembler share include/opcode/i51.h, so the round
            trip says nothing about the opcode bytes themselves - but `assemble'
            above has already pinned those against an unrelated assembler, which
            leaves this step asking the question that is left: does the decoder
            agree with the encoder about mnemonic, operands, operand order,
            branch displacement and instruction length.
  program   assemble testall.asm and report the size of the text it produces.
            Nothing here inspects a byte of it: this step says the program still
            assembles, no more.  Its branches, fixups and tables are checked by
            executing it - `make -C tb sim', which runs the same program in ucsim
            and reads the verdict the program itself computes.

`decode' and `roundtrip' are one pass over the corpus split in two: an entry that
fails to decode is reported by `decode' and not counted again by `roundtrip'.
Which stages run is --stages; `make -C tb isa' runs assemble+decode, `make -C tb
roundtrip' runs roundtrip, and neither repeats the other's work.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dialect

STAGES = ('assemble', 'decode', 'roundtrip')


class CorpusError(Exception):
    """The instruction table itself is damaged."""


def hex_payload(record):
    """Bytes carried by one Intel HEX data record.

    Damage to the golden column has to be an error, not a smaller payload that
    silently becomes the new expected value, so the record type and the
    checksum are both verified.
    """
    if not record.startswith(':'):
        raise CorpusError('%r is not an Intel HEX record' % record)
    try:
        raw = bytes.fromhex(record[1:])
    except ValueError:
        raise CorpusError('%r is not hexadecimal' % record)
    if len(raw) < 5:
        raise CorpusError('%r is too short for a HEX record' % record)
    if raw[3] != 0x00:
        raise CorpusError('%r is record type %02x, want 00 (data)'
                          % (record, raw[3]))
    if len(raw) != 5 + raw[0]:
        raise CorpusError('%r carries %d bytes, its length byte says %d'
                          % (record, len(raw) - 5, raw[0]))
    if sum(raw) & 0xFF:
        raise CorpusError('%r has a bad checksum' % record)
    return raw[4:4 + raw[0]]


def read_table(path):
    """Parse an instruction|hex table.

    Every line that is not blank and not a comment has to parse.  Dropping the
    ones that do not would let a damaged corpus - a lost separator, a truncated
    file - shrink the gate silently and still report PASS.
    """
    out = []
    for n, line in enumerate(open(path), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '|' not in line:
            raise CorpusError('%s:%d: no `|\' separator: %r' % (path, n, line))
        src, rec = line.split('|', 1)
        try:
            out.append((n, src.strip(), hex_payload(rec.strip())))
        except CorpusError as e:
            raise CorpusError('%s:%d: %s' % (path, n, e))
    return out


# objdump's disassembly lines: "   4:\t85 64 b1 \tmov\t0xb1, 0x64".
INSN_LINE = re.compile(r'^\s*([0-9a-f]+):\t([0-9a-f]{2}(?: +[0-9a-f]{2})*) *\t(.+)$')


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

    def disassemble(self, data, work):
        """Disassemble DATA at address 0.  Returns (instructions, error).

        An instruction is (address, raw bytes as hex, text, comment)."""
        b = os.path.join(work, 'out.bin')
        with open(b, 'wb') as f:
            f.write(data)
        # -z: without it objdump elides an all-zero payload as `...', which is
        # every one-byte `nop'.
        r = subprocess.run([self.objdump, '-D', '-z', '-b', 'binary',
                            '-m', 'i51', b], capture_output=True, text=True)
        if r.returncode:
            return None, (r.stderr.strip().splitlines() or ['objdump failed'])[-1]
        out = []
        for line in r.stdout.splitlines():
            m = INSN_LINE.match(line)
            if not m:
                continue
            text, comment = m.group(3), ''
            if ';' in text:
                text, comment = text.split(';', 1)
            out.append((int(m.group(1), 16), m.group(2).replace(' ', ''),
                        ' '.join(text.split('\t')).strip(), comment.strip()))
        if not out:
            return None, 'nothing decoded'
        return out, None

    def decodes(self, data, work):
        """Decode DATA.  Returns (instruction, why-it-is-not-one).

        Exactly one of the two is None.  What is asserted: objdump succeeds, the
        payload comes back as exactly one instruction, that instruction consumes
        exactly these bytes - which pins the decoded length - and it is named
        rather than dumped as data.  Feeding it back to the assembler is the
        separate `roundtrip' stage, which takes the instruction returned here.
        """
        insns, err = self.disassemble(data, work)
        if err:
            return None, err
        if len(insns) != 1:
            return None, ('decoded as %d instructions, want 1: %s'
                          % (len(insns), ' / '.join(i[2] for i in insns)))
        insn = insns[0]
        _, raw, text, comment = insn
        if raw != data.hex():
            return None, ('one instruction covering %s, want %s'
                          % (raw, data.hex()))
        # `.byte 0x47 ; ????' is what print_insn_i51 prints for an opcode it
        # does not recognise - and gas takes it back happily, so a round trip
        # alone would close over exactly the case that matters most.
        if text.split()[0] == '.byte' or '(bad)' in text or '????' in text + comment:
            return None, 'not decoded to an instruction: %s' % text
        return insn, None


REL = re.compile(r'\.[-+]0x[0-9A-Fa-f]+')
ADDR = re.compile(r'^0x[0-9A-F]{4}$')


def mismatch(text, comment):
    """The two ways a branch target is printed must agree.

    A relative branch prints the displacement from the start of the
    instruction and, in the comment, the absolute target.  The bytes are
    disassembled at address 0 here, so the two are the same number - and
    the displacement is the half that resyntax throws away, which would
    otherwise let a wrong one through unnoticed."""
    m = REL.search(text)
    if not m:
        return None
    target = comment.split()[0] if comment else ''
    if not ADDR.match(target):
        return None
    tok = m.group(0)                      # `.+0x04' / `.-0x7E'
    disp = int(tok[2:], 16)
    if tok[1] == '-':
        disp = -disp
    if (disp & 0xFFFF) != int(target, 16):
        return 'prints `%s\' but says %s' % (m.group(0), target)
    return None


def resyntax(text, comment):
    """Disassembly to something the assembler will take back.

    Only relative branch operands need help: they print as a displacement
    from the instruction, and the absolute target is in the comment. Nothing
    else is rewritten - if the assembler will not take what objdump printed,
    that is the disagreement this check is looking for."""
    if REL.search(text):
        target = comment.split()[0] if comment else ''
        if not ADDR.match(target):
            return None
        text = REL.sub(target, text)
    return text


def report(what, total, bad):
    print('   %-9s %d/%d' % (what + ':', total - len(bad), total))
    for line in bad[:20]:
        print('     ' + line)
    if len(bad) > 20:
        print('     ... %d more' % (len(bad) - 20))
    return len(bad)


def run_table(tools, args, stages, work):
    """The corpus stages.  Returns the number of failures."""
    try:
        entries = read_table(args.table)
    except CorpusError as e:
        sys.exit('corpus damaged: %s' % e)
    print('== table: %d instructions' % len(entries))
    # A table that parsed to nothing would otherwise pass every check.
    if not entries:
        print('   FAILED: no instructions in %s' % args.table)
        return 1

    failures = 0

    if 'assemble' in stages:
        bad = []
        for n, src, want in entries:
            got = tools.assemble(src, work)
            if isinstance(got, str):
                bad.append('line %-4d %-28s want %-12s %s' % (n, src, want.hex(), got))
            elif got != want:
                bad.append('line %-4d %-28s want %-12s got %s'
                           % (n, src, want.hex(), got.hex()))
        failures += report('assemble', len(entries), bad)

    # One disassembly per entry feeds both of the stages below: `decode' judges
    # whether it is an instruction at all, `roundtrip' whether it is the right
    # one.  An entry `decode' has already reported is not counted again.
    decoded = {}
    if 'decode' in stages:
        bad = []
        for n, src, want in entries:
            insn, why = tools.decodes(want, work)
            if why is not None:
                bad.append('line %-4d %-28s bytes %-12s %s'
                           % (n, src, want.hex(), why))
            else:
                decoded[n] = insn
        failures += report('decode', len(entries), bad)

    if 'roundtrip' in stages:
        bad = []
        considered = 0
        for n, src, want in entries:
            insn = decoded.get(n)
            if insn is None:
                if 'decode' in stages:
                    continue            # already counted by `decode'
                insn, why = tools.decodes(want, work)
                if why is not None:
                    considered += 1
                    bad.append('line %-4d %-28s bytes %-12s %s'
                               % (n, src, want.hex(), why))
                    continue
            considered += 1
            _, _, text, comment = insn
            why = mismatch(text, comment)
            if why:
                bad.append('line %-4d %-28s %s' % (n, src, why))
                continue
            back = resyntax(text, comment)
            if back is None:
                bad.append('line %-4d %-28s no target in `%s ; %s\''
                           % (n, src, text, comment))
                continue
            got = tools.assemble(back, work)
            flat = ' '.join(back.split())
            if isinstance(got, str):
                bad.append('line %-4d %-28s -> %-26s %s' % (n, src, flat, got))
            elif got != want:
                bad.append('line %-4d %-28s -> %-26s want %s got %s'
                           % (n, src, flat, want.hex(), got.hex()))
        failures += report('roundtrip', considered, bad)

    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    ap.add_argument('--table', help='naken_asm style instruction|hex table')
    ap.add_argument('--program', help='assembly program to assemble')
    ap.add_argument('--dialect', action='store_true',
                    help='rewrite --program from Intel/ASEM-51 spelling first')
    ap.add_argument('--stages', default='assemble,decode',
                    help='corpus stages to run, comma separated, from %s '
                         '(default: assemble,decode)' % ','.join(STAGES))
    args = ap.parse_args()

    stages = [s for s in args.stages.split(',') if s]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        sys.exit('unknown stage(s): %s' % ','.join(unknown))

    # An invocation that would check nothing has to be an error.  Both of the
    # cases below used to run to the end and print PASS: with neither --table
    # nor --program there is nothing to check at all, and `--stages ""' with a
    # table reads the corpus and then runs no stage over it, so a damaged or
    # mistyped stage list would report success for a table nothing touched.
    # --stages governs the corpus stages only, so an empty one is not an error
    # when there is no --table: the program is still assembled.
    if not args.table and not args.program:
        sys.exit('nothing to check: pass --table, --program, or both')
    if args.table and not stages:
        sys.exit('--stages is empty: %s would be read and no stage run over it'
                 % args.table)

    tools = Tools(args.build)
    failures = 0

    with tempfile.TemporaryDirectory() as work:
        if args.table:
            failures += run_table(tools, args, stages, work)

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
                # Assembles, nothing more: the bytes are judged by `make sim'.
                print('   assembled, %d bytes of text (not compared; '
                      'run `make -C tb sim\' to execute it)' % len(got))

    print('FAIL: %d' % failures if failures else 'PASS')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

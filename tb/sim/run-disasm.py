#!/usr/bin/env python3
"""Which symbols may name an address, judged on a linked ELF.

Every other objdump call in this testbench passes `-b binary': the isa and
roundtrip stages hand the disassembler a flat image that carries no symbol
table at all.  So i51_symbol_is_valid - the hook opcodes/i51-dis.c installs
through disassemble_init_for_target, and the only reason the MCS-51's five
address spaces do not name each other's addresses - had never once been
executed by the gate.

Handing objdump a .o would not have executed it either.  Its
find_symbol_for_address asks sym_ok, and sym_ok rejects a symbol from
another section on its own whenever want_section is set - which it is on a
relocatable object, because the file carries relocations and the address
being named lies inside the section being disassembled.  What the hook says
is invisible there.

On a linked executable HAS_RELOC is clear, want_section is false, and the
fallback loop walks down to the nearest preceding symbol the hook accepts,
from whatever section.  That is the one configuration in which the filter
decides anything, so this stage links the probe and reads the name objdump
prints beside a code address.

The probe puts two symbols the filter has to refuse below a code address:

  RAMMARK   .rdata, 0x40   a RAM-space symbol: not absolute, not code
  P1        *ABS*, 0x90    an SFR equate - md_undefined_symbol builds those
                           with symbol_new (..., absolute_section, ...)

and branches to 0x50 and 0x98, code addresses with no symbol of their own,
each just above one of them.  The nearest preceding symbol is therefore the
wrong one in both cases, and the name that has to appear instead is _START,
the code label at 0.  Asserting that some annotation appeared, or that the
address was right, would pass with the filter removed; the name is what
tells the two apart.

The same address 0x50 read from inside .rdata has to name RAMMARK again:
outside a code section the filter lets every symbol through, which is what
keeps the RAM spaces their own labels in `objdump -D'.

Checked before any of that, because each would leave the assertions above
passing for a reason of their own: objdump reads the file as i51, it is an
executable with no relocations, .text is code and .rdata is not, both sit
where the script puts them, and the two symbols the filter must refuse are
really in the symbol table at those values.

  usage: run-disasm.py --build BUILD-DIR

exit: 0 pass, 1 a check failed or the probe would not link
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'disasm.ld')

# The probe's layout.  Both branch targets are code addresses with no symbol
# of their own, each just above a symbol the filter has to refuse.
TEXT_SIZE = 0xa0
RDATA_VMA = 0x40                # RAMMARK sits at the start of .rdata
SFR_VMA   = 0x90                # P1, from the operand table in tc-i51.c
T_RAM     = 0x50                # code address just above RAMMARK
T_ABS     = 0x98                # code address just above P1

# `.global P1' is the whole SFR equate: the name is not a symbol yet, so
# symbol_find_or_make hands it to md_undefined_symbol, which builds it in
# absolute_section at the value the operand table gives it.  The .global
# only makes sure the linker keeps it.
#
# The three bytes in .rdata are `ljmp T_RAM' as data: they name the same
# code address from a section that carries none.
PROBE = """\
\t.text
\t.global\t_START
_START:
\tljmp\t0x%04X
\tljmp\t0x%04X
\t.skip\t0x%X
\t.global\tP1
\t.rdata
\t.global\tRAMMARK
RAMMARK:
\t.byte\t0x02, 0x%02X, 0x%02X
""" % (T_RAM, T_ABS, TEXT_SIZE - 6, T_RAM >> 8, T_RAM & 0xFF)

# name, section, address, mnemonic, the name objdump has to print beside the
# operand, and the name it prints when the filter accepts what it must
# refuse.  None means there is nothing for the filter to change there.
CASES = [
    ('code-ram', '.text',  0x00, 'ljmp',
     '_START+0x%x' % T_RAM,  'RAMMARK+0x%x' % (T_RAM - RDATA_VMA)),
    ('code-abs', '.text',  0x03, 'ljmp',
     '_START+0x%x' % T_ABS,  'P1+0x%x' % (T_ABS - SFR_VMA)),
    ('data-any', '.rdata', RDATA_VMA, 'ljmp',
     'RAMMARK+0x%x' % (T_RAM - RDATA_VMA), None),
]

# Value and section every symbol the cases above rest on has to have.
WANT_SYMS = [('_START', 0x00, '.text'),
             ('RAMMARK', RDATA_VMA, '.rdata'),
             ('P1', SFR_VMA, 'ABS')]

# "Disassembly of section .text:" and "   3:\t02 00 98 \tljmp\t98 <_START+0x98>"
SECTION = re.compile(r'^Disassembly of section (\S+):')
INSN = re.compile(r'^\s*([0-9a-f]+):\t([0-9a-f]{2}(?: +[0-9a-f]{2})*) *\t(.+)$')
ANNOT = re.compile(r'<([^<>]*)>')
# "architecture: i51, flags 0x00000012:" with the flag names on the next line.
ARCH = re.compile(r'^architecture:\s*([^,]+),\s*flags\s')
# "  1 .text         000000a0  00000000  00000000  00000034  2**0"
SECHDR = re.compile(r'^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s')
# "  [ 1] .text             PROGBITS        00000000 ..."
ELFSEC = re.compile(r'^\s*\[\s*(\d+)\]\s+(\S+)\s')
# "     4: 00000090     0 NOTYPE  GLOBAL DEFAULT  ABS P1"
ELFSYM = re.compile(r'^\s*\d+:\s+([0-9a-f]+)\s+\S+\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S+)\s*$')


class Tools:
    def __init__(self, build):
        self.as_ = os.path.join(build, 'gas', 'as-new')
        self.ld = os.path.join(build, 'ld', 'ld-new')
        self.objdump = os.path.join(build, 'binutils', 'objdump')
        self.readelf = os.path.join(build, 'binutils', 'readelf')
        for t in (self.as_, self.ld, self.objdump, self.readelf):
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

    def link(self, obj, name):
        e = self.path(name + '.elf')
        r = subprocess.run([self.ld, '-T', SCRIPT, '-o', e, obj],
                           capture_output=True, text=True)
        return (e if r.returncode == 0 else None), (r.stdout + r.stderr).strip()

    def run(self, tool, *args):
        r = subprocess.run([tool] + list(args), capture_output=True, text=True)
        if r.returncode:
            sys.exit('%s %s failed: %s'
                     % (os.path.basename(tool), ' '.join(args[:-1]),
                        r.stderr.strip()))
        return r.stdout.replace('\r', '').splitlines()

    def file_flags(self, elf):
        """(architecture, set of bfd file flags) from objdump -f."""
        arch, flags = None, set()
        lines = self.run(self.objdump, '-f', elf)
        for i, line in enumerate(lines):
            m = ARCH.match(line)
            if m and i + 1 < len(lines):
                arch = m.group(1).strip()
                flags = set(f.strip() for f in lines[i + 1].split(','))
        return arch, flags

    def sections(self, elf):
        """name -> (vma, set of bfd section flags) from objdump -h."""
        out = {}
        lines = self.run(self.objdump, '-h', elf)
        for i, line in enumerate(lines):
            m = SECHDR.match(line)
            if m and i + 1 < len(lines):
                out[m.group(1)] = (int(m.group(3), 16),
                                   set(f.strip()
                                       for f in lines[i + 1].split(',')))
        return out

    def symbols(self, elf):
        """name -> (value, section name or ABS) from readelf."""
        index = {}
        for line in self.run(self.readelf, '-S', '--wide', elf):
            m = ELFSEC.match(line)
            if m:
                index[m.group(1)] = m.group(2)
        out = {}
        for line in self.run(self.readelf, '-s', '--wide', elf):
            m = ELFSYM.match(line)
            if m:
                out[m.group(3)] = (int(m.group(1), 16),
                                   index.get(m.group(2), m.group(2)))
        return out

    def disassemble(self, elf):
        """(section, address) -> decoded text, from objdump -D.

        -z so that a run of zero bytes cannot elide a line as `...'; -D
        because the RAM spaces are not code and -d would skip them."""
        out, sec = {}, None
        for line in self.run(self.objdump, '-D', '-z', elf):
            m = SECTION.match(line)
            if m:
                sec = m.group(1)
                continue
            m = INSN.match(line)
            if m and sec is not None:
                out[(sec, int(m.group(1), 16))] = ' '.join(
                    m.group(3).split('\t')).strip()
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', required=True, help='binutils build directory')
    args = ap.parse_args()
    t = Tools(args.build)

    bad = []
    checks = 0

    def fail(what, detail):
        bad.append('%-10s %s' % (what, detail))

    with tempfile.TemporaryDirectory() as work:
        t.work = work
        elf, log = t.link(t.assemble(PROBE, 'probe'), 'probe')
        if elf is None:
            print('== disasm: the probe does not link')
            print(log)
            return 1

        # ---- the configuration the filter is observable in --------------
        arch, flags = t.file_flags(elf)
        checks += 1
        if arch != 'i51':
            fail('arch', 'objdump reads the linked ELF as `%s\', not i51'
                 % arch)
        checks += 1
        if 'EXEC_P' not in flags:
            fail('exec', 'not an executable: %s' % ', '.join(sorted(flags)))
        checks += 1
        if 'HAS_RELOC' in flags:
            fail('reloc', 'the linked ELF still carries relocations, so '
                          'objdump matches sections itself and the filter '
                          'decides nothing')
        checks += 1
        if 'HAS_SYMS' not in flags:
            fail('syms', 'no symbol table: %s' % ', '.join(sorted(flags)))

        sections = t.sections(elf)
        for name, vma, want_code in (('.text', 0x00, True),
                                     ('.rdata', RDATA_VMA, False)):
            checks += 1
            if name not in sections:
                fail(name.lstrip('.'), 'section %s is not in the linked ELF'
                     % name)
                continue
            got, secflags = sections[name]
            if got != vma:
                fail(name.lstrip('.'), '%s is at 0x%02x, the script puts it '
                     'at 0x%02x' % (name, got, vma))
            elif 'CONTENTS' not in secflags:
                fail(name.lstrip('.'), '%s carries no contents: %s'
                     % (name, ', '.join(sorted(secflags))))
            elif ('CODE' in secflags) != want_code:
                fail(name.lstrip('.'), '%s flags %s, %sCODE expected'
                     % (name, ', '.join(sorted(secflags)),
                        '' if want_code else 'no '))

        # A symbol the filter must refuse has to be there to be refused: if
        # it is missing, objdump names the code symbol whatever the hook
        # says and the cases below pass without meaning anything.
        syms = t.symbols(elf)
        for name, value, sec in WANT_SYMS:
            checks += 1
            if name not in syms:
                fail('sym', '%s is not in the linked symbol table' % name)
            elif syms[name] != (value, sec):
                fail('sym', '%s is 0x%02x in %s, expected 0x%02x in %s'
                     % (name, syms[name][0], syms[name][1], value, sec))

        # ---- the name objdump prints beside the address -----------------
        insns = t.disassemble(elf)
        for name, sec, addr, mnem, want, loose in CASES:
            checks += 1
            where = '0x%02x in %s' % (addr, sec)
            text = insns.get((sec, addr))
            if text is None:
                fail(name, 'nothing decoded at %s' % where)
                continue
            m = ANNOT.search(text)
            got = m.group(1) if m else None
            if not text.startswith(mnem + ' '):
                fail(name, '%s decoded as `%s\', expected %s'
                     % (where, text, mnem))
            elif got is None:
                fail(name, '%s prints `%s\' - no symbol named at all, want '
                     '<%s>' % (where, text, want))
            elif got != want:
                why = (' - the filter passed a symbol it has to refuse'
                       if got == loose else '')
                fail(name, '%s names <%s>, want <%s>%s'
                     % (where, got, want, why))

    print('== disasm: %d checks' % checks)
    print('   checked:  %d/%d' % (checks - len(bad), checks))
    for line in bad:
        print('     ' + line)
    print('FAIL: %d' % len(bad) if bad else 'PASS')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

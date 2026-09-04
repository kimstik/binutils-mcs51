#!/usr/bin/env python3
"""The r_offset bounds check at the head of i51_final_link_relocate ().

Five relocations - R_I51_7_PCREL, R_I51_11, R_I51_8_B2B, R_I51_13_PCODE and
R_I51_16 - index the section contents with rel->r_offset and then read and
write there themselves.  Every other kind falls through to
_bfd_final_link_relocate (), which checks the offset for itself; those five
are covered by nothing but the bfd_reloc_offset_in_range () call the port
makes before the switch.  Take that call out and the rest of the gate stays
green while an object with a crafted r_offset makes the linker read and
write at an arbitrary distance from the contents buffer - bfd_getb16 () past
the end for R_I51_11 and R_I51_13_PCODE, bfd_put_8 () and bfd_putb16 () past
it for the rest.

The malformed objects are made here, not shipped: each probe is assembled by
the build under test, its single relocation is found by walking the section
headers, and r_offset alone is rewritten.  Nothing else about the object
differs, so a case that fails can only be about the offset.

What is asserted is the diagnostic, not the exit status.  A refused
relocation reaches ld through info->callbacks->warning, whose ld end is a
plain einfo carrying neither %X nor %F: the link SUCCEEDS, ld exits 0 and
writes an output file, and the message on stderr is the only thing that says
the check fired at all.  That weakness is the port's, it is deliberately not
papered over here, and this stage is keyed on the one signal that today
tells a checked write from an unchecked one.

  usage: run-guard.py --build BUILD-DIR
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile

# Elf32 field offsets, from docs/reviews-round3/fuzz/elfmangle.py, made
# endian-aware: the port's objects are ELFDATA2MSB, container and contents
# alike, and that mangler unpacks every field little-endian whatever
# e_ident[EI_DATA] says.
EH = {'e_shoff': (32, 'I'), 'e_shentsize': (46, 'H'), 'e_shnum': (48, 'H')}
SH = {'sh_name': (0, 'I'), 'sh_type': (4, 'I'), 'sh_flags': (8, 'I'),
      'sh_addr': (12, 'I'), 'sh_offset': (16, 'I'), 'sh_size': (20, 'I'),
      'sh_link': (24, 'I'), 'sh_info': (28, 'I'), 'sh_addralign': (32, 'I'),
      'sh_entsize': (36, 'I')}
SHT_RELA = 4
RELA_SIZE = 12

# Relocation number -> name and the size of the field it writes, in bytes.
# The numbers are include/elf/i51.h; the sizes are the third HOWTO argument
# in bfd/elf32-i51.c, and they are what bfd_reloc_offset_in_range () adds to
# the offset before comparing against the end of the section.  Only the five
# kinds i51_final_link_relocate () handles itself are listed: for anything
# else the generic code makes the same check, so deleting the port's would
# not be visible.
R_I51 = {3:  ('R_I51_7_PCREL', 1),
         4:  ('R_I51_11', 2),
         9:  ('R_I51_16', 2),
         10: ('R_I51_8_B2B', 1),
         11: ('R_I51_13_PCODE', 2)}

# One probe per kind: the smallest instruction that emits it, against an
# undefined symbol so the relocation survives into the object.  The symbol
# values are the ones sim/run-reloc.py links these kinds with, chosen so
# that the relocation itself is in range - the offset is the only thing
# wrong with the mangled objects below.
PROBES = [
    ('pcrel', 3,  '\tsjmp\tNEAR\n',         {'NEAR': 0x0020}),
    ('page',  4,  '\tajmp\tPAGE\n',         {'PAGE': 0x0345}),
    ('word',  9,  '\tmov\tdptr,#XSYM\n',    {'XSYM': 0x1234}),
    ('b2b',   10, '\tsetb\tB2B(BDVAR,1)\n', {'BDVAR': 0x2f}),
    ('pcode', 11, '\t.pcode\tPSYM\n',       {'PSYM': 0x0123}),
]

# The offset docs/reviews-round3/fuzz/repro used to reach the wild write:
# far past any section this testbench assembles, so with the check gone the
# linker writes into whatever follows the contents buffer.
WILD_OFFSET = 0xffff

# What ld prints for bfd_reloc_outofrange, from the switch in
# elf32_i51_relocate_section ().  Matched loosely on purpose: a fix that
# turns the warning into an error is free to reword the rest of the line.
DIAG = 'out of range'


def rd(buf, end, off, fmt):
    return struct.unpack_from(end + fmt, buf, off)[0]


class Elf:
    """Just enough Elf32 to find a relocation and move it."""

    def __init__(self, data):
        if data[:4] != b'\x7fELF' or data[4] != 1:
            raise ValueError('not a 32-bit ELF object')
        if data[5] not in (1, 2):
            raise ValueError('e_ident[EI_DATA] is %d' % data[5])
        self.end = '<' if data[5] == 1 else '>'
        self.data = data
        shoff = rd(data, self.end, *EH['e_shoff'])
        shentsize = rd(data, self.end, *EH['e_shentsize'])
        shnum = rd(data, self.end, *EH['e_shnum'])
        self.shdrs = []
        for i in range(shnum):
            base = shoff + i * shentsize
            self.shdrs.append({k: rd(data, self.end, base + o, f)
                               for k, (o, f) in SH.items()})

    def relocs(self):
        """(file offset of the entry, r_offset, r_type, target section)."""
        for sh in self.shdrs:
            if sh['sh_type'] != SHT_RELA:
                continue
            esz = sh['sh_entsize'] or RELA_SIZE
            for i in range(sh['sh_size'] // esz):
                base = sh['sh_offset'] + i * esz
                yield (base,
                       rd(self.data, self.end, base, 'I'),
                       rd(self.data, self.end, base + 4, 'I') & 0xff,
                       self.shdrs[sh['sh_info']])

    def with_r_offset(self, base, value):
        b = bytearray(self.data)
        struct.pack_into(self.end + 'I', b, base, value & 0xffffffff)
        return bytes(b)


class Tools:
    def __init__(self, build):
        self.as_ = os.path.join(build, 'gas', 'as-new')
        self.ld = os.path.join(build, 'ld', 'ld-new')
        for t in (self.as_, self.ld):
            if not os.path.exists(t):
                sys.exit('missing %s' % t)
        self.work = None

    def path(self, name):
        return os.path.join(self.work, name)

    def assemble(self, source, name):
        src = '\t.text\n\t.global _START\n_START:\n' + source
        s, o = self.path(name + '.s'), self.path(name + '.o')
        open(s, 'w').write(src)
        r = subprocess.run([self.as_, '-o', o, s], capture_output=True, text=True)
        if r.returncode:
            sys.exit('as failed on %s: %s' % (name, r.stderr.strip()))
        return o

    def link(self, obj, name, defs):
        cmd = [self.ld, '-o', self.path(name + '.elf'), obj]
        for k, v in defs.items():
            cmd += ['--defsym', '%s=0x%x' % (k, v)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, (r.stdout + r.stderr).strip()


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

        for tag, rtype, source, defs in PROBES:
            name, size = R_I51[rtype]
            obj = t.assemble(source, tag)
            e = Elf(open(obj, 'rb').read())

            # The probe has to carry exactly the one relocation it is here
            # for.  Anything else and the offsets computed below would be
            # moving something other than what the case claims.
            found = [r for r in e.relocs() if r[2] in R_I51]
            checks += 1
            if len(found) != 1 or found[0][2] != rtype:
                fail(tag + '/emit', 'expected one %s, got %s'
                     % (name, [R_I51[r[2]][0] for r in found]))
                continue
            base, natural, _, target = found[0]
            end = target['sh_size']

            # bfd_reloc_offset_in_range () wants the whole field inside the
            # section: offset <= end and offset + size <= end.  The last
            # legal position is therefore end - size, and both halves of the
            # rule get a case - a field that straddles the end, and one
            # wholly past it.
            cases = [('legal', end - size, False),
                     ('straddle', end - size + 1, True),
                     ('past-end', end, True)]
            if size == 1:
                del cases[1]              # straddle and past-end coincide
            if rtype == 9:
                cases.append(('wild', WILD_OFFSET, True))

            checks += 1
            rc, log = t.link(obj, tag + '-base', defs)
            if rc != 0 or DIAG in log:
                fail(tag + '/baseline',
                     'r_offset 0x%x is the one gas wrote and has to link '
                     'clean: rc=%d %s' % (natural, rc, log))

            for case, offset, want in cases:
                checks += 1
                mangled = t.path('%s-%s.o' % (tag, case))
                open(mangled, 'wb').write(e.with_r_offset(base, offset))
                rc, log = t.link(mangled, '%s-%s' % (tag, case), defs)
                if (DIAG in log) == want:
                    continue
                if want:
                    fail('%s/%s' % (tag, case),
                         '%s at r_offset 0x%x, section ends at 0x%x: read and '
                         'written without a word (rc=%d) %s'
                         % (name, offset, end, rc, log))
                else:
                    fail('%s/%s' % (tag, case),
                         '%s at r_offset 0x%x is the last position that fits '
                         'a section ending at 0x%x, and was refused: %s'
                         % (name, offset, end, log))

    print('== guard: %d checks' % checks)
    print('   checked:  %d/%d' % (checks - len(bad), checks))
    for line in bad:
        print('     ' + line)
    print('FAIL: %d' % len(bad) if bad else 'PASS')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())

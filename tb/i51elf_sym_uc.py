#!/usr/bin/env python3
"""
Convert all symbol names in an ELF object to uppercase.

Byte order is taken from EI_DATA, so an ELFDATA2MSB object - what this port
produces - and an ELFDATA2LSB one are read alike: every field of the ELF
header and of the section headers is unpacked with the order the object
itself declares.

The rewrite is the string table of every symbol table, over itself.
Upper-casing is ASCII and changes no string's length, so every name keeps
its offset: the symbol table still points where it pointed, section sizes
and offsets are unchanged, and no other byte of the object is touched.
"""
import struct
import sys

SHT_SYMTAB = 2
SHT_STRTAB = 3
EHDR_SIZE = 52                  # sizeof(Elf32_Ehdr)
SHDR_SIZE = 40                  # sizeof(Elf32_Shdr)
SYM_ENTSIZE = 16                # sizeof(Elf32_Sym)


class NotAnObject(Exception):
    """The input is not an ELF object this script can read."""


class Elf:
    """A 32-bit ELF object, read with the byte order it declares."""

    ORDER = {1: '<', 2: '>'}    # EI_DATA: ELFDATA2LSB, ELFDATA2MSB

    def __init__(self, data):
        self.data = data
        if data[0:4] != b'\x7fELF':
            raise NotAnObject('not an ELF file')
        if len(data) < EHDR_SIZE:
            raise NotAnObject('%d bytes, shorter than an ELF header'
                              % len(data))
        if data[4] != 1:
            raise NotAnObject('EI_CLASS is %d, want 1 (32-bit)' % data[4])
        if data[5] not in self.ORDER:
            raise NotAnObject('EI_DATA is %d, want 1 (LSB) or 2 (MSB)'
                              % data[5])
        self.end = self.ORDER[data[5]]
        self.order = 'ELFDATA2LSB' if self.end == '<' else 'ELFDATA2MSB'
        self.e_shoff = self.u32(32)
        self.e_shentsize = self.u16(46)
        self.e_shnum = self.u16(48)
        if self.e_shnum and self.e_shentsize < SHDR_SIZE:
            raise NotAnObject('e_shentsize is %d, want %d or more'
                              % (self.e_shentsize, SHDR_SIZE))
        if self.e_shoff + self.e_shnum * self.e_shentsize > len(data):
            raise NotAnObject('%d section headers at 0x%x run past the end of '
                              'a %d byte file'
                              % (self.e_shnum, self.e_shoff, len(data)))

    def u16(self, off):
        return struct.unpack(self.end + 'H', self.data[off:off + 2])[0]

    def u32(self, off):
        return struct.unpack(self.end + 'I', self.data[off:off + 4])[0]

    def sections(self):
        """(index, sh_type, sh_offset, sh_size, sh_link) for every section."""
        for i in range(self.e_shnum):
            sh = self.e_shoff + i * self.e_shentsize
            yield (i, self.u32(sh + 4), self.u32(sh + 16), self.u32(sh + 20),
                   self.u32(sh + 24))


def uppercase_strtab(strtab):
    """Upper-case every string of a string table, keeping its size."""
    out = bytearray()
    for s in strtab.split(b'\0'):
        out += s.upper() + b'\0'
    return out[:len(strtab)]


def uppercase_symbols(input_file, output_file):
    with open(input_file, 'rb') as f:
        data = bytearray(f.read())

    try:
        elf = Elf(data)
    except NotAnObject as e:
        print(f"Error: {input_file}: {e}", file=sys.stderr)
        return False

    print(f"Processing {input_file}...")
    print(f"  {elf.order}, sections: {elf.e_shnum}, "
          f"section header offset: 0x{elf.e_shoff:x}")

    strtabs = {}
    symtabs = []
    for i, sh_type, sh_off, sh_size, sh_link in elf.sections():
        if sh_type == SHT_STRTAB:
            strtabs[i] = (sh_off, sh_size)
        elif sh_type == SHT_SYMTAB:
            symtabs.append((i, sh_off, sh_size, sh_link))

    for sec_idx, sym_off, sym_size, str_idx in symtabs:
        print(f"  Processing symbol table section {sec_idx}...")

        if str_idx not in strtabs:
            print(f"Error: {input_file}: symbol table {sec_idx} links section "
                  f"{str_idx}, which is no string table", file=sys.stderr)
            return False
        str_off, str_size = strtabs[str_idx]
        if str_off + str_size > len(data):
            print(f"Error: {input_file}: string table {str_idx} runs past the "
                  f"end of the file", file=sys.stderr)
            return False

        strtab = data[str_off:str_off + str_size]
        data[str_off:str_off + str_size] = uppercase_strtab(strtab)
        print(f"    Converted {sym_size // SYM_ENTSIZE} symbols to uppercase")

    with open(output_file, 'wb') as f:
        f.write(data)

    print(f"Successfully wrote {output_file}")
    return True


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.obj> <output.obj>", file=sys.stderr)
        sys.exit(1)

    if not uppercase_symbols(sys.argv[1], sys.argv[2]):
        sys.exit(1)

#!/usr/bin/env python3
"""
Byte-swap a 2001 i51 ELF object: big-endian container, machine 0x7262 ->
little-endian container, machine EM_8051 = 165.

STALE.  The little-endian half is no longer a format this project uses, and
`le2be' in the name has been backwards since the port went ELFDATA2MSB.
Measured: all 30 loose objects in tb/base.7z are EI_DATA = 2 with e_machine
165, and this script followed by i51elf_sym_uc.py turns tb/base2001.7z's
cgi/bd.obj into an EI_DATA = 1 object hashing 47d84c73..., against
base.7z's 702ced5b....  It does not reproduce the staged tree in
docs/objects-report/staged/ either: those 28 files are EI_DATA = 1 but
e_machine 0x1051.  This chain reproduces nothing that exists.

The transform that does reproduce tb/base.7z, measured over every file in
tb/base2001.7z: leave EI_DATA at 2, rewrite only e_machine as a big-endian
halfword, upper-case every SHT_STRTAB linked from a SHT_SYMTAB, and touch
nothing else - 28 of 28 loose objects and 4 of 4 archives come out
byte-identical.  This script does not do that.
"""
import struct
import sys

def convert_elf(input_file, output_file):
    with open(input_file, 'rb') as f:
        data = bytearray(f.read())

    # Check ELF magic
    if data[0:4] != b'\x7fELF':
        print(f"Error: {input_file} is not an ELF file")
        return False

    # Check class (32-bit)
    if data[4] != 1:
        print(f"Error: Only 32-bit ELF supported")
        return False

    # Check old format
    if data[5] != 2:  # Big-endian
        print(f"Warning: Not big-endian format")

    # Convert to little-endian
    print(f"Converting {input_file} from big-endian to little-endian...")
    data[5] = 1  # EI_DATA: little-endian

    # Read and convert ELF header (big-endian -> little-endian)
    # e_type at offset 16 (2 bytes)
    e_type = struct.unpack('>H', data[16:18])[0]
    data[16:18] = struct.pack('<H', e_type)

    # e_machine at offset 18 (2 bytes) - change from 0x7262 to EM_8051 (165)
    old_machine = struct.unpack('>H', data[18:20])[0]
    print(f"  Old machine type: 0x{old_machine:04x}")
    data[18:20] = struct.pack('<H', 165)

    # e_version at offset 20 (4 bytes)
    e_version = struct.unpack('>I', data[20:24])[0]
    data[20:24] = struct.pack('<I', e_version)

    # e_entry at offset 24 (4 bytes)
    e_entry = struct.unpack('>I', data[24:28])[0]
    data[24:28] = struct.pack('<I', e_entry)

    # e_phoff at offset 28 (4 bytes)
    e_phoff = struct.unpack('>I', data[28:32])[0]
    data[28:32] = struct.pack('<I', e_phoff)

    # e_shoff at offset 32 (4 bytes)
    e_shoff = struct.unpack('>I', data[32:36])[0]
    data[32:36] = struct.pack('<I', e_shoff)

    # e_flags at offset 36 (4 bytes)
    e_flags = struct.unpack('>I', data[36:40])[0]
    data[36:40] = struct.pack('<I', e_flags)

    # e_ehsize at offset 40 (2 bytes)
    e_ehsize = struct.unpack('>H', data[40:42])[0]
    data[40:42] = struct.pack('<H', e_ehsize)

    # e_phentsize at offset 42 (2 bytes)
    e_phentsize = struct.unpack('>H', data[42:44])[0]
    data[42:44] = struct.pack('<H', e_phentsize)

    # e_phnum at offset 44 (2 bytes)
    e_phnum = struct.unpack('>H', data[44:46])[0]
    data[44:46] = struct.pack('<H', e_phnum)

    # e_shentsize at offset 46 (2 bytes)
    e_shentsize = struct.unpack('>H', data[46:48])[0]
    data[46:48] = struct.pack('<H', e_shentsize)

    # e_shnum at offset 48 (2 bytes)
    e_shnum = struct.unpack('>H', data[48:50])[0]
    data[48:50] = struct.pack('<H', e_shnum)

    # e_shstrndx at offset 50 (2 bytes)
    e_shstrndx = struct.unpack('>H', data[50:52])[0]
    data[50:52] = struct.pack('<H', e_shstrndx)

    print(f"  Sections: {e_shnum}, Section header offset: 0x{e_shoff:x}")

    # Convert section headers
    for i in range(e_shnum):
        sh_offset = e_shoff + (i * e_shentsize)
        if sh_offset + 40 > len(data):
            break

        # sh_name (4 bytes)
        sh_name = struct.unpack('>I', data[sh_offset:sh_offset+4])[0]
        data[sh_offset:sh_offset+4] = struct.pack('<I', sh_name)

        # sh_type (4 bytes)
        sh_type = struct.unpack('>I', data[sh_offset+4:sh_offset+8])[0]
        data[sh_offset+4:sh_offset+8] = struct.pack('<I', sh_type)

        # sh_flags (4 bytes)
        sh_flags = struct.unpack('>I', data[sh_offset+8:sh_offset+12])[0]
        data[sh_offset+8:sh_offset+12] = struct.pack('<I', sh_flags)

        # sh_addr (4 bytes)
        sh_addr = struct.unpack('>I', data[sh_offset+12:sh_offset+16])[0]
        data[sh_offset+12:sh_offset+16] = struct.pack('<I', sh_addr)

        # sh_offset (4 bytes)
        sh_off = struct.unpack('>I', data[sh_offset+16:sh_offset+20])[0]
        data[sh_offset+16:sh_offset+20] = struct.pack('<I', sh_off)

        # sh_size (4 bytes)
        sh_size = struct.unpack('>I', data[sh_offset+20:sh_offset+24])[0]
        data[sh_offset+20:sh_offset+24] = struct.pack('<I', sh_size)

        # sh_link (4 bytes)
        sh_link = struct.unpack('>I', data[sh_offset+24:sh_offset+28])[0]
        data[sh_offset+24:sh_offset+28] = struct.pack('<I', sh_link)

        # sh_info (4 bytes)
        sh_info = struct.unpack('>I', data[sh_offset+28:sh_offset+32])[0]
        data[sh_offset+28:sh_offset+32] = struct.pack('<I', sh_info)

        # sh_addralign (4 bytes)
        sh_addralign = struct.unpack('>I', data[sh_offset+32:sh_offset+36])[0]
        data[sh_offset+32:sh_offset+36] = struct.pack('<I', sh_addralign)

        # sh_entsize (4 bytes)
        sh_entsize = struct.unpack('>I', data[sh_offset+36:sh_offset+40])[0]
        data[sh_offset+36:sh_offset+40] = struct.pack('<I', sh_entsize)

        # Convert symbol table if this is a SYMTAB section
        if sh_type == 2:  # SHT_SYMTAB
            print(f"  Converting symbol table in section {i}")
            sym_count = sh_size // sh_entsize if sh_entsize > 0 else 0
            for j in range(sym_count):
                sym_offset = sh_off + (j * sh_entsize)
                if sym_offset + 16 > len(data):
                    break

                # st_name (4 bytes)
                st_name = struct.unpack('>I', data[sym_offset:sym_offset+4])[0]
                data[sym_offset:sym_offset+4] = struct.pack('<I', st_name)

                # st_value (4 bytes)
                st_value = struct.unpack('>I', data[sym_offset+4:sym_offset+8])[0]
                data[sym_offset+4:sym_offset+8] = struct.pack('<I', st_value)

                # st_size (4 bytes)
                st_size = struct.unpack('>I', data[sym_offset+8:sym_offset+12])[0]
                data[sym_offset+8:sym_offset+12] = struct.pack('<I', st_size)

                # st_info and st_other are 1 byte each, st_shndx is 2 bytes
                st_shndx = struct.unpack('>H', data[sym_offset+14:sym_offset+16])[0]
                data[sym_offset+14:sym_offset+16] = struct.pack('<H', st_shndx)

        # Convert relocation sections (RELA type)
        if sh_type == 4:  # SHT_RELA
            print(f"  Converting relocation table in section {i}")
            rel_count = sh_size // sh_entsize if sh_entsize > 0 else 0
            for j in range(rel_count):
                rel_offset = sh_off + (j * sh_entsize)
                if rel_offset + 12 > len(data):
                    break

                # r_offset (4 bytes)
                r_offset = struct.unpack('>I', data[rel_offset:rel_offset+4])[0]
                data[rel_offset:rel_offset+4] = struct.pack('<I', r_offset)

                # r_info (4 bytes)
                r_info = struct.unpack('>I', data[rel_offset+4:rel_offset+8])[0]
                data[rel_offset+4:rel_offset+8] = struct.pack('<I', r_info)

                # r_addend (4 bytes)
                r_addend = struct.unpack('>i', data[rel_offset+8:rel_offset+12])[0]
                data[rel_offset+8:rel_offset+12] = struct.pack('<i', r_addend)

    # Write converted file
    with open(output_file, 'wb') as f:
        f.write(data)

    print(f"Successfully converted to {output_file}")
    return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.obj> <output.obj>")
        sys.exit(1)

    if not convert_elf(sys.argv[1], sys.argv[2]):
        sys.exit(1)

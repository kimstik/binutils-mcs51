#!/usr/bin/env python3
"""
Convert all symbol names in an ELF object to uppercase.

Little-endian objects only: every field is unpacked `<' whatever EI_DATA
says.  Measured on an ELFDATA2MSB object - tb/base.7z's cgi/bd.obj, or any
member of its lib/libk80.a - it reads the header as `Sections: 3072,
Section header offset: 0xe8000000' and then dies with `struct.error:
unpack requires a buffer of 4 bytes', writing no output.  Upper-casing an
ELF string table is itself endian-independent; only the header and
section-header reads are not.
"""
import struct
import sys

def uppercase_symbols(input_file, output_file):
    with open(input_file, 'rb') as f:
        data = bytearray(f.read())

    # Check ELF magic
    if data[0:4] != b'\x7fELF':
        print(f"Error: {input_file} is not an ELF file")
        return False

    # Read ELF header
    e_shoff = struct.unpack('<I', data[32:36])[0]
    e_shnum = struct.unpack('<H', data[48:50])[0]
    e_shentsize = struct.unpack('<H', data[46:48])[0]
    e_shstrndx = struct.unpack('<H', data[50:52])[0]

    print(f"Processing {input_file}...")
    print(f"  Sections: {e_shnum}, Section header offset: 0x{e_shoff:x}")

    # Find string table sections
    strtab_sections = []
    symtab_sections = []

    for i in range(e_shnum):
        sh_offset = e_shoff + (i * e_shentsize)
        sh_type = struct.unpack('<I', data[sh_offset+4:sh_offset+8])[0]
        sh_off = struct.unpack('<I', data[sh_offset+16:sh_offset+20])[0]
        sh_size = struct.unpack('<I', data[sh_offset+20:sh_offset+24])[0]
        sh_link = struct.unpack('<I', data[sh_offset+24:sh_offset+28])[0]

        if sh_type == 3:  # SHT_STRTAB
            strtab_sections.append((i, sh_off, sh_size))
        elif sh_type == 2:  # SHT_SYMTAB
            symtab_sections.append((i, sh_off, sh_size, sh_link))

    # Process each symbol table
    for sec_idx, sym_off, sym_size, str_idx in symtab_sections:
        print(f"  Processing symbol table section {sec_idx}...")

        # Find the associated string table
        str_off = None
        str_size = None
        for idx, off, size in strtab_sections:
            if idx == str_idx:
                str_off = off
                str_size = size
                break

        if str_off is None:
            print(f"    Warning: Could not find string table for section {sec_idx}")
            continue

        # Read string table
        strtab = data[str_off:str_off+str_size]
        new_strtab = bytearray()
        str_map = {}  # Maps old offset to new offset

        # Process each string, converting to uppercase
        pos = 0
        while pos < len(strtab):
            # Find null terminator
            end = pos
            while end < len(strtab) and strtab[end] != 0:
                end += 1

            # Get string and convert to uppercase
            old_str = strtab[pos:end]
            new_str = old_str.upper()

            # Record mapping
            str_map[pos] = len(new_strtab)

            # Add to new string table
            new_strtab.extend(new_str)
            new_strtab.append(0)

            pos = end + 1

        # Update string table in data
        data[str_off:str_off+len(strtab)] = new_strtab[:len(strtab)]

        if len(new_strtab) > str_size:
            print(f"    Warning: New string table is larger than old ({len(new_strtab)} > {str_size})")
            print(f"    Some symbols may be truncated")

        # Update symbol table entries to point to new offsets
        sh_entsize = 16  # sizeof(Elf32_Sym)
        sym_count = sym_size // sh_entsize

        for j in range(sym_count):
            sym_offset = sym_off + (j * sh_entsize)
            st_name = struct.unpack('<I', data[sym_offset:sym_offset+4])[0]

            # Update st_name to point to new offset
            if st_name in str_map:
                new_offset = str_map[st_name]
                data[sym_offset:sym_offset+4] = struct.pack('<I', new_offset)

        print(f"    Converted {sym_count} symbols to uppercase")

    # Write output file
    with open(output_file, 'wb') as f:
        f.write(data)

    print(f"Successfully wrote {output_file}")
    return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.obj> <output.obj>")
        sys.exit(1)

    if not uppercase_symbols(sys.argv[1], sys.argv[2]):
        sys.exit(1)

#!/usr/bin/env python3
"""Systematic ELF32 mutator for the i51 port's robustness harness.

Reads one well-formed little-endian ELF32 object and writes a directory of
mutants, one per single-field corruption or truncation.  Nothing here is
random: every mutant is named after the field it damages, so a crash names
its own input.

  ./elfmangle.py good.o outdir/
"""

import os
import struct
import sys

EI_NIDENT = 16

# Elf32_Ehdr field offsets (after e_ident).
EH = {
    "e_type":      (16, "H"),
    "e_machine":   (18, "H"),
    "e_version":   (20, "I"),
    "e_entry":     (24, "I"),
    "e_phoff":     (28, "I"),
    "e_shoff":     (32, "I"),
    "e_flags":     (36, "I"),
    "e_ehsize":    (40, "H"),
    "e_phentsize": (42, "H"),
    "e_phnum":     (44, "H"),
    "e_shentsize": (46, "H"),
    "e_shnum":     (48, "H"),
    "e_shstrndx":  (50, "H"),
}

# Elf32_Shdr field offsets within one section header.
SH = {
    "sh_name":      (0, "I"),
    "sh_type":      (4, "I"),
    "sh_flags":     (8, "I"),
    "sh_addr":      (12, "I"),
    "sh_offset":    (16, "I"),
    "sh_size":      (20, "I"),
    "sh_link":      (24, "I"),
    "sh_info":      (28, "I"),
    "sh_addralign": (32, "I"),
    "sh_entsize":   (36, "I"),
}

SHT_SYMTAB = 2
SHT_RELA = 4
SHT_REL = 9

# Elf32_Sym
SYM_SIZE = 16
SYM = {
    "st_name":  (0, "I"),
    "st_value": (4, "I"),
    "st_size":  (8, "I"),
    "st_info":  (12, "B"),
    "st_other": (13, "B"),
    "st_shndx": (14, "H"),
}

# The port's processor-specific section indices (include/elf/i51.h).
SHN_I51 = {
    "REGBANK":   0xFF00,
    "RDATA_C":   0xFF01,
    "BDATA_C":   0xFF02,
    "IDATA_C":   0xFF03,
    "XDATA_C":   0xFF04,
    "EDATA_C":   0xFF05,
    "BITDATA_C": 0xFF06,
    "OOR":       0xFF07,   # one past the last one the port knows
    "LOPROC_HI": 0xFF1F,
}

WILD = [0, 1, 0x7F, 0x100, 0xFFFF, 0x10000, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFE,
        0xFFFFFFFF]


def rd(buf, off, fmt):
    return struct.unpack_from("<" + fmt, buf, off)[0]


def wr(buf, off, fmt, val):
    b = bytearray(buf)
    size = struct.calcsize(fmt)
    struct.pack_into("<" + fmt, b, off, val & ((1 << (8 * size)) - 1))
    return bytes(b)


class Elf:
    def __init__(self, data):
        self.data = data
        self.shoff = rd(data, *EH["e_shoff"])
        self.shentsize = rd(data, *EH["e_shentsize"])
        self.shnum = rd(data, *EH["e_shnum"])
        self.shstrndx = rd(data, *EH["e_shstrndx"])
        self.shdrs = []
        for i in range(self.shnum):
            base = self.shoff + i * self.shentsize
            s = {k: rd(data, base + o, f) for k, (o, f) in SH.items()}
            s["_base"] = base
            s["_idx"] = i
            self.shdrs.append(s)
        strtab = self.shdrs[self.shstrndx]
        self.shstr = data[strtab["sh_offset"]:strtab["sh_offset"] + strtab["sh_size"]]

    def name(self, sh):
        n = sh["sh_name"]
        end = self.shstr.find(b"\0", n)
        return self.shstr[n:end].decode("latin1")


def emit(out, tag, blob):
    path = os.path.join(out, tag + ".o")
    with open(path, "wb") as f:
        f.write(blob)


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    data = open(src, "rb").read()
    e = Elf(data)
    n = 0

    # ---- 1. truncation ------------------------------------------------
    cuts = {len(data) // 2, len(data) - 1, 1, 4, 16, 52, EI_NIDENT}
    cuts.add(e.shoff)
    cuts.add(e.shoff + 1)
    for sh in e.shdrs:
        cuts.add(sh["sh_offset"])
        cuts.add(sh["sh_offset"] + sh["sh_size"])
        cuts.add(sh["sh_offset"] + sh["sh_size"] // 2)
    for c in sorted(x for x in cuts if 0 < x < len(data)):
        emit(out, "trunc_%06d" % c, data[:c])
        n += 1

    # ---- 2. ELF header fields ----------------------------------------
    for fld in ("e_shoff", "e_shnum", "e_shentsize", "e_shstrndx",
                "e_phoff", "e_phnum", "e_phentsize", "e_ehsize",
                "e_machine", "e_type", "e_version", "e_entry", "e_flags"):
        off, fmt = EH[fld]
        lim = (1 << (8 * struct.calcsize(fmt))) - 1
        for v in WILD:
            if v > lim:
                continue
            if v == rd(data, off, fmt):
                continue
            emit(out, "eh_%s_%08x" % (fld, v), wr(data, off, fmt, v))
            n += 1

    # ---- 3. section header fields ------------------------------------
    for sh in e.shdrs:
        nm = e.name(sh).strip(".") or "null"
        nm = "".join(c if c.isalnum() else "_" for c in nm)
        for fld in ("sh_type", "sh_flags", "sh_offset", "sh_size", "sh_link",
                    "sh_info", "sh_addralign", "sh_entsize", "sh_name"):
            off, fmt = SH[fld]
            for v in WILD:
                if v == sh[fld]:
                    continue
                emit(out, "sh%02d_%s_%s_%08x" % (sh["_idx"], nm, fld, v),
                     wr(data, sh["_base"] + off, fmt, v))
                n += 1
        # sh_flags carrying the port's SHF_CDATA space codes
        for code, val in (("REGBANK", 0x20000000), ("RDATA", 0x40000000),
                          ("BDATA", 0x60000000), ("IDATA", 0x80000000),
                          ("XDATA", 0xA0000000), ("EDATA", 0xC0000000),
                          ("CDATA", 0xE0000000)):
            off, fmt = SH["sh_flags"]
            emit(out, "sh%02d_%s_shf_%s" % (sh["_idx"], nm, code),
                 wr(data, sh["_base"] + off, fmt, sh["sh_flags"] | val))
            n += 1

    # ---- 4. relocations ----------------------------------------------
    for sh in e.shdrs:
        if sh["sh_type"] not in (SHT_REL, SHT_RELA):
            continue
        esz = sh["sh_entsize"] or (12 if sh["sh_type"] == SHT_RELA else 8)
        cnt = sh["sh_size"] // esz if esz else 0
        for i in range(min(cnt, 4)):
            rbase = sh["sh_offset"] + i * esz
            info = rd(data, rbase + 4, "I")
            sym = info >> 8
            # out-of-range relocation types (the port defines 0..11)
            for t in (12, 13, 0x40, 0x7F, 0x80, 0xFE, 0xFF):
                emit(out, "rel%d_r%d_type%02x" % (sh["_idx"], i, t),
                     wr(data, rbase + 4, "I", (sym << 8) | t))
                n += 1
            # out-of-range symbol indices
            for s in (0x00FFFF, 0x7FFFFF, 0xFFFFFF, 0x000100):
                emit(out, "rel%d_r%d_sym%06x" % (sh["_idx"], i, s),
                     wr(data, rbase + 4, "I", (s << 8) | (info & 0xFF)))
                n += 1
            # r_offset past the end of the section it applies to
            for o in (0xFFFFFFFF, 0x7FFFFFFF, 0x10000, 0xFFFF):
                emit(out, "rel%d_r%d_off%08x" % (sh["_idx"], i, o),
                     wr(data, rbase, "I", o))
                n += 1

    # ---- 5. symbols ---------------------------------------------------
    for sh in e.shdrs:
        if sh["sh_type"] != SHT_SYMTAB:
            continue
        cnt = sh["sh_size"] // SYM_SIZE
        for i in range(1, min(cnt, 8)):
            sbase = sh["sh_offset"] + i * SYM_SIZE
            for tag, v in list(SHN_I51.items()) + [
                    ("OORSEC", e.shnum), ("OORSEC2", e.shnum + 1),
                    ("HUGE", 0xFFFE), ("ABS", 0xFFF1), ("COMMON", 0xFFF2)]:
                emit(out, "sym%d_shndx_%s" % (i, tag),
                     wr(data, sbase + SYM["st_shndx"][0], "H", v))
                n += 1
            for v in (0xFFFFFFFF, 0x7FFFFFFF, 0x10000):
                emit(out, "sym%d_name_%08x" % (i, v),
                     wr(data, sbase + SYM["st_name"][0], "I", v))
                emit(out, "sym%d_size_%08x" % (i, v),
                     wr(data, sbase + SYM["st_size"][0], "I", v))
                emit(out, "sym%d_value_%08x" % (i, v),
                     wr(data, sbase + SYM["st_value"][0], "I", v))
                n += 3
            for v in (0x0F, 0xF0, 0xFF, 0x13):
                emit(out, "sym%d_info_%02x" % (i, v),
                     wr(data, sbase + SYM["st_info"][0], "B", v))
                n += 1

    # ---- 6. structural -------------------------------------------------
    # overlapping section offsets: point every section at offset 0
    b = data
    for sh in e.shdrs[1:]:
        b = wr(b, sh["_base"] + SH["sh_offset"][0], "I", 0)
    emit(out, "struct_all_offsets_zero", b)
    # every section claims the whole file
    b = data
    for sh in e.shdrs[1:]:
        b = wr(b, sh["_base"] + SH["sh_size"][0], "I", len(data))
    emit(out, "struct_all_sizes_whole_file", b)
    # section headers overlap the ELF header
    emit(out, "struct_shoff_zero", wr(data, EH["e_shoff"][0], "I", 0))
    # zero-length everything
    b = data
    for sh in e.shdrs[1:]:
        b = wr(b, sh["_base"] + SH["sh_size"][0], "I", 0)
    emit(out, "struct_all_sizes_zero", b)
    n += 4

    print("%d mutants in %s" % (n, out))


if __name__ == "__main__":
    main()

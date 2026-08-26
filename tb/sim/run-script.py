#!/usr/bin/env python3
"""Linker-script coverage: every `*(...)' arm gets a real input.

The bug this exists to catch is the one that hid `reset_network' for the life
of this repository.  `lib/www51.sc' shipped with `*(reset_network)' commented
out; the section was still assembled, still linked, and still had a symbol -
it just became an orphan placed past `_etext', so `objcopy -j .text' dropped
it and every ROM was three bytes short.  Nothing went red.  A dropped arm
loses code without losing a symbol, a section, or an exit status, so no test
that only links and compares symbols can see it.

Both scripts are covered:

  * the port's own default script, `ld/scripttempl/elf32i51.sc', through a
    link with the default emulation - no -T,
  * `lib/www51.sc' out of tb/base.7z, which is what all ten projects link
    with, through -T.

Each arm gets its own input section carrying one identifiable byte, and the
run asserts

  * the whole `objcopy -j .text' image, byte for byte: the markers of the
    code-space arms in script order.  A dropped arm loses exactly its byte.
  * the address of a marker symbol in every RAM-space arm.  A dropped arm
    turns its input into an orphan and moves it.
  * the content of every non-allocated (stabs / DWARF) output section.
  * that /DISCARD/ still discards.
  * that the output has no section beyond the expected set - an orphan from
    a dropped arm shows up here as well.

Arms that no input can reach are not faked.  They are listed, with the reason,
and counted separately; `--list' prints the whole inventory.

  usage: run-script.py --build BUILD-DIR [--base tb/base.7z] [--list]

exit: 0 pass, 1 a check failed, 2 bad usage / toolchain / archive
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TB = os.path.dirname(HERE)


# --------------------------------------------------------------- input arms
#
# kind:  'dir'   a gas directive of that name opens the section
#        'sec'   .section NAME,"<flags>",%<type>
#        'comm'  .comm SYM,1,1  -> SHN_COMMON, the *(COMMON) arm
#
# The stabs / DWARF arms do not use any of these: their inputs are added with
# objcopy --add-section, because gas either refuses the name outright or emits
# DWARF of its own when it sees it (see DEF_DEBUG below).
#
# An arm is (pattern, input-section, kind, marker, symbol, expected address).
# `symbol' None means the arm is checked through the image or through the
# section content instead of through a symbol.

def A(pattern, sec, kind, marker, sym=None, addr=None):
    return dict(pattern=pattern, sec=sec, kind=kind, marker=marker,
                sym=sym, addr=addr)


# ---- ld/scripttempl/elf32i51.sc

# .text, in script order.  The image is these markers followed by the BYTE
# (0x22) RET stub the script emits, so it pins order as well as presence.
DEF_TEXT = [
    A("KEEP (*(.vectors))",     ".vectors",           "sec", 0x01),
    A("KEEP (*(vectors))",      "vectors",            "sec", 0x02),
    A("*(.init)",               ".init",              "sec", 0x03),
    A("*(.init.*)",             ".init.p",            "sec", 0x04),
    A("*(.text)",               ".text",              "dir", 0x05),
    A("*(.text.*)",             ".text.p",            "sec", 0x06),
    A("*(.gnu.linkonce.t.*)",   ".gnu.linkonce.t.p",  "sec", 0x07),
    A("*(.rodata)",             ".rodata",            "sec", 0x08),
    A("*(.rodata.*)",           ".rodata.p",          "sec", 0x09),
    A("*(.gnu.linkonce.r.*)",   ".gnu.linkonce.r.p",  "sec", 0x0a),
    A("*(.fini)",               ".fini",              "sec", 0x0b),
    A("*(.fini.*)",             ".fini.p",            "sec", 0x0c),
]
DEF_TEXT_IMAGE = "0102030405060708090a0b0c22"
DEF_ETEXT = 0x0d

# Every RAM space.  One byte per arm, so each address below follows from the
# script's own size arithmetic and nothing else.
DEF_RAM = [
    A("*(.regbank)",          ".regbank",           "sec", 0x11, "A_REGBANK",  0x00),
    A("*(.rdata)",            ".rdata",             "dir", 0x12, "A_RDATA",    0x01),
    A("*(.rdata.*)",          ".rdata.p",           "sec", 0x13, "A_RDATAP",   0x02),
    A("*(.rbss)",             ".rbss",              "dir", None, "A_RBSS",     0x03),
    A("*(.rbss.*)",           ".rbss.p",            "sec", None, "A_RBSSP",    0x04),
    A("*(.bdata)",            ".bdata",             "dir", 0x14, "A_BDATA",    0x20),
    A("*(.bdata.*)",          ".bdata.p",           "sec", 0x15, "A_BDATAP",   0x21),
    A("*(.bbss)",             ".bbss",              "dir", None, "A_BBSS",     0x22),
    A("*(.bbss.*)",           ".bbss.p",            "sec", None, "A_BBSSP",    0x23),
    A("*(.bitdata)",          ".bitdata",           "dir", "bit", "A_BIT",     0x20),
    A("*(.bitdata.*)",        ".bitdata.p",         "sec", "bit", "A_BITP",    0x21),
    A("*(.bitbss)",           ".bitbss",            "dir", "bit", "A_BITBSS",  0x22),
    A("*(.bitbss.*)",         ".bitbss.p",          "sec", "bit", "A_BITBSSP", 0x23),
    A("*(.data)",             ".data",              "dir", 0x16, "A_DATA",     0x25),
    A("*(.data.*)",           ".data.p",            "sec", 0x17, "A_DATAP",    0x26),
    A("*(.gnu.linkonce.d.*)", ".gnu.linkonce.d.p",  "sec", 0x18, "A_LINKD",    0x27),
    A("*(.bss)",              ".bss",               "dir", None, "A_BSS",      0x28),
    A("*(.bss.*)",            ".bss.p",             "sec", None, "A_BSSP",     0x29),
    A("*(COMMON)",            "COMMON",             "comm", None, "A_COMMON",  0x2a),
    A("*(.idata)",            ".idata",             "dir", 0x19, "A_IDATA",    0x2b),
    A("*(.idata.*)",          ".idata.p",           "sec", 0x1a, "A_IDATAP",   0x2c),
    A("*(.ibss)",             ".ibss",              "dir", None, "A_IBSS",     0x2d),
    A("*(.ibss.*)",           ".ibss.p",            "sec", None, "A_IBSSP",    0x2e),
    A("*(.xdata)",            ".xdata",             "dir", 0x1b, "A_XDATA",    0x00),
    A("*(.xdata.*)",          ".xdata.p",           "sec", 0x1c, "A_XDATAP",   0x01),
    A("*(.xbss)",             ".xbss",              "dir", None, "A_XBSS",     0x02),
    A("*(.xbss.*)",           ".xbss.p",            "sec", None, "A_XBSSP",    0x03),
    A("*(.edata)",            ".edata",             "dir", 0x1d, "A_EDATA",    0x00),
    A("*(.edata.*)",          ".edata.p",           "sec", 0x1e, "A_EDATAP",   0x01),
    A("*(.ebss)",             ".ebss",              "dir", None, "A_EBSS",     0x02),
    A("*(.ebss.*)",           ".ebss.p",            "sec", None, "A_EBSSP",    0x03),
    A("*(.eeprom)",           ".eeprom",            "dir", 0x1f, "A_EEPROM",   0x00),
    A("*(.eeprom.*)",         ".eeprom.p",          "sec", 0x20, "A_EEPROMP",  0x01),
]

# Section addresses the script computes, checked alongside the symbols.
DEF_SEC_ADDR = {
    ".text": 0x00, ".regbank": 0x00, ".rdata": 0x01, ".rbss": 0x03,
    ".bdata": 0x20, ".bbss": 0x22, ".bit": 0x20, ".bitbss": 0x22,
    ".data": 0x25, ".bss": 0x28, ".idata": 0x2b, ".ibss": 0x2d,
    ".xdata": 0x00, ".xbss": 0x02, ".edata": 0x00, ".ebss": 0x02,
    ".eeprom": 0x00,
}

# The stabs / DWARF arms.  These are added with objcopy, not assembled: gas
# aborts on a hand-written .stab (obj-elf.c set_additional_section_info) and
# emits DWARF of its own the moment a .debug_info exists, which this target
# has no 32-bit relocation to express.  Each output section is checked by the
# set of marker bytes it ends up holding.
DEF_DEBUG = [
    (".stab",           [(".stab",            0x41)]),
    (".stabstr",        [(".stabstr",         0x42)]),
    (".stab.excl",      [(".stab.excl",       0x43)]),
    (".stab.exclstr",   [(".stab.exclstr",    0x44)]),
    (".stab.index",     [(".stab.index",      0x45)]),
    (".stab.indexstr",  [(".stab.indexstr",   0x46)]),
    (".comment",        [(".comment",         0x47)]),
    (".debug",          [(".debug",           0x48)]),
    (".line",           [(".line",            0x49)]),
    (".debug_srcinfo",  [(".debug_srcinfo",   0x4a)]),
    (".debug_sfnames",  [(".debug_sfnames",   0x4b)]),
    (".debug_aranges",  [(".debug_aranges",   0x4c)]),
    (".debug_pubnames", [(".debug_pubnames",  0x4d)]),
    (".debug_info",     [(".debug_info",      0x4e),
                         (".gnu.linkonce.wi.p", 0x4f)]),
    (".debug_abbrev",   [(".debug_abbrev",    0x50)]),
    (".debug_line",     [(".debug_line",      0x51),
                         (".debug_line.p",    0x52),
                         (".debug_line_end",  0x53)]),
    (".debug_frame",    [(".debug_frame",     0x54)]),
    (".debug_str",      [(".debug_str",       0x55)]),
    (".debug_loc",      [(".debug_loc",       0x56)]),
    (".debug_macinfo",  [(".debug_macinfo",   0x57)]),
    (".debug_weaknames", [(".debug_weaknames", 0x58)]),
    (".debug_funcnames", [(".debug_funcnames", 0x59)]),
    (".debug_typenames", [(".debug_typenames", 0x5a)]),
    (".debug_varnames", [(".debug_varnames",  0x5b)]),
    (".debug_pubtypes", [(".debug_pubtypes",  0x5c)]),
    (".debug_ranges",   [(".debug_ranges",    0x5d)]),
    (".debug_macro",    [(".debug_macro",     0x5e)]),
]

# /DISCARD/ : { *(.note.GNU-stack) *(.gnu_debuglink) *(.gnu.lto_*) }
DEF_DISCARD = [(".note.GNU-stack", 0x5f), (".gnu_debuglink", 0x60),
               (".gnu.lto_.p", 0x61)]


# ---- lib/www51.sc, as tb/base.7z ships it

WWW_TEXT = [
    A("*(vectors)",         "vectors",          "sec", 0x01),
    A("*(.init)",           ".init",            "sec", 0x02),
    A("*(.progmem.gcc*)",   ".progmem.gcc.p",   "sec", 0x03),
    A("*(.progmem*)",       ".progmem.p",       "sec", 0x04),
    A("*(reset_begin)",     "reset_begin",      "sec", 0x05),
    A("*(reset_device)",    "reset_device",     "sec", 0x06),
    A("*(reset_network)",   "reset_network",    "sec", 0x07),
    A("*(reset_end)",       "reset_end",        "sec", 0x08),
    A("*(one_times)",       "one_times",        "sec", 0x09),
    A("*(fast_begin)",      "fast_begin",       "sec", 0x0a),
    A("*(fast)",            "fast",             "sec", 0x0b),
    A("*(fast_end)",        "fast_end",         "sec", 0x0c),
    A("*(slow_begin)",      "slow_begin",       "sec", 0x0d),
    A("*(slow)",            "slow",             "sec", 0x0e),
    A("*(slow_end)",        "slow_end",         "sec", 0x0f),
    A("*(cpu_rom)",         "cpu_rom",          "sec", 0x10),
    A("*(cpu_dir_begin)",   "cpu_dir_begin",    "sec", 0x11),
    A("*(cpu_dir)",         "cpu_dir",          "sec", 0x12),
    A("*(cpu_dir_end)",     "cpu_dir_end",      "sec", 0x13),
    A("*(cpu_files)",       "cpu_files",        "sec", 0x14),
    A("*(.text)",           ".text",            "dir", 0x15),
    A("*(.text.*)",         ".text.p",          "sec", 0x16),
    A("*(.fini)",           ".fini",            "sec", 0x17),
]
WWW_TEXT_IMAGE = "0102030405060708090a0b0c0d0e0f1011121314151617"
WWW_ETEXT = 0x17

WWW_RAM = [
    A("*(.regbank)",          ".regbank",          "sec", 0x21, "W_REGBANK", 0x00),
    A("*(.rdata*)",           ".rdata",            "dir", 0x22, "W_RDATA",   0x01),
    A("*(.rbss*)",            ".rbss",             "dir", None, "W_RBSS",    0x02),
    A("*(.bdata*)",           ".bdata",            "dir", 0x23, "W_BDATA",   0x20),
    A("*(.bbss*)",            ".bbss",             "dir", None, "W_BBSS",    0x21),
    A("*(.bitdata*)",         ".bitdata",          "dir", "bit", "W_BIT",    0x10),
    A("*(.bitbss*)",          ".bitbss",           "dir", "bit", "W_BITBSS", 0x11),
    A("*(.data)",             ".data",             "dir", 0x24, "W_DATA",    0x23),
    A("*(.gnu.linkonce.d*)",  ".gnu.linkonce.d.p", "sec", 0x25, "W_LINKD",   0x24),
    A("*(.bss*)",             ".bss",              "dir", None, "W_BSS",     0x25),
    A("*(COMMON)",            "COMMON",            "comm", None, "W_COMMON", 0x26),
    A("*(.idata)",            ".idata",            "dir", 0x26, "W_IDATA",   0x27),
    A("*(buf_data)",          "buf_data",          "sec", None, "W_BUFDATA", 0x90),
    A("*(.ibss)",             ".ibss",             "dir", None, "W_IBSS",    0x91),
    A("*(ee_config)",         "ee_config",         "sec", 0x31, "W_EECONFIG", 0x00),
    A("*(ee_dir_begin)",      "ee_dir_begin",      "sec", 0x32, "W_EEDIRB",  0x01),
    A("*(ee_dir)",            "ee_dir",            "sec", 0x33, "W_EEDIR",   0x02),
    A("*(ee_dir_end)",        "ee_dir_end",        "sec", 0x34, "W_EEDIRE",  0x03),
    A("*(ee_files)",          "ee_files",          "sec", 0x35, "W_EEFILES", 0x04),
    A("*(.eeprom*)",          ".eeprom",           "dir", 0x36, "W_EEPROM",  0x05),
]

WWW_SEC_ADDR = {
    ".text": 0x00, ".reg": 0x00, ".rbss": 0x02, ".bdata": 0x20, ".bbss": 0x21,
    ".bit": 0x10, ".bitbss": 0x11, ".data": 0x23, ".bss": 0x25, ".idata": 0x27,
    ".ibss": 0x90, ".eeprom": 0x00,
}

# The four arms whose region the script declares with LENGTH = 0.  Nothing can
# be placed through them, and that is a property of the script, not of the
# port: putting a byte in each makes ld refuse the link, naming the output
# section the arm feeds.  Those four diagnostics are the assertion - a deleted
# arm makes the input an orphan and the diagnostic goes away.
WWW_ZERO_REGION = [
    ("*(.xdata*)", ".xdata", "dir", "section `.xdata' will not fit in region `xdata'"),
    ("*(.xbss*)",  ".xbss",  "dir", "section `.ixdata' is not within region `xdata'"),
    ("*(.edata*)", ".edata", "dir", "section `.edata' will not fit in region `edata'"),
    ("*(.ebss*)",  ".ebss",  "dir", "section `.iedata' is not within region `edata'"),
]

WWW_DEBUG = [
    (".stab",           [(".stab",            0x41)]),
    (".stabstr",        [(".stabstr",         0x42)]),
    (".stab.excl",      [(".stab.excl",       0x43)]),
    (".stab.exclstr",   [(".stab.exclstr",    0x44)]),
    (".stab.index",     [(".stab.index",      0x45)]),
    (".stab.indexstr",  [(".stab.indexstr",   0x46)]),
    (".comment",        [(".comment",         0x47)]),
    (".debug",          [(".debug",           0x48)]),
    (".line",           [(".line",            0x49)]),
    (".debug_srcinfo",  [(".debug_srcinfo",   0x4a)]),
    (".debug_sfnames",  [(".debug_sfnames",   0x4b)]),
    (".debug_aranges",  [(".debug_aranges",   0x4c)]),
    (".debug_pubnames", [(".debug_pubnames",  0x4d)]),
    (".debug_info",     [(".debug_info",      0x4e),
                         (".gnu.linkonce.wi.p", 0x4f)]),
    (".debug_abbrev",   [(".debug_abbrev",    0x50)]),
    (".debug_line",     [(".debug_line",      0x51)]),
    (".debug_frame",    [(".debug_frame",     0x54)]),
    (".debug_str",      [(".debug_str",       0x55)]),
    (".debug_loc",      [(".debug_loc",       0x56)]),
    (".debug_macinfo",  [(".debug_macinfo",   0x57)]),
]

# A handful of input sections cannot carry the name of the arm that collects
# them, because the arm is a wildcard.  Everything else is named literally.
SEC2PAT = {
    ".gnu.linkonce.wi.p": ".gnu.linkonce.wi.*",
    ".debug_line.p": ".debug_line.*",
    ".gnu.lto_.p": ".gnu.lto_*",
}

# Arms no input can reach, with the reason.  Not faked and not skipped
# silently: they are named here, printed on every run, and the audit below
# accepts a script arm only if it is either covered or listed here - so an arm
# added to either script cannot slip past this file unnoticed.
DYNAMIC = [".hash", ".dynsym", ".dynstr", ".gnu.version", ".gnu.version_d",
           ".gnu.version_r"]

UNFEEDABLE = [
    (DYNAMIC.__contains__, " ".join(DYNAMIC),
     "dynamic-linking sections; this target emits no dynamic objects, and a "
     "hand-made section of that name is written back with the wrong sh_type, "
     "after which the tools no longer recognise the file as an ELF"),
    (lambda p: p.startswith((".rel.", ".rela.")), ".rel.* .rela.*",
     "relocation sections are consumed by the linker itself and are never "
     "offered to a script arm in a final link; a hand-made SHT_PROGBITS called "
     ".rel.text is written back as SHT_REL and the output stops being readable"),
]


# ------------------------------------------------------------------ helpers

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class Probe:
    """Assembles and links the probe, and answers questions about the result."""

    def __init__(self, build, work):
        self.build, self.work = build, work
        self.AS = os.path.join(build, "gas", "as-new")
        self.LD = os.path.join(build, "ld", "ld-new")
        self.OBJCOPY = os.path.join(build, "binutils", "objcopy")
        self.READELF = os.path.join(build, "binutils", "readelf")
        self.NM = os.path.join(build, "binutils", "nm-new")

    def tools_ok(self):
        return [t for t in (self.AS, self.LD, self.OBJCOPY, self.READELF, self.NM)
                if not os.access(t, os.X_OK)]

    # -- input construction

    @staticmethod
    def _emit(arm):
        """One arm's worth of assembly."""
        out = []
        if arm["kind"] == "comm":
            return ["        .comm %s,1,1" % arm["sym"]]
        if arm["kind"] == "dir":
            out.append("        %s" % arm["sec"])
        else:
            nobits = arm["marker"] is None and arm["sec"].startswith(
                (".rbss", ".bbss", ".bitbss", ".bss", ".ibss", ".xbss", ".ebss",
                 "buf_data"))
            flags = "aw" if arm["sec"].startswith(
                (".regbank", ".rdata", ".rbss", ".bdata", ".bbss", ".bitdata",
                 ".bitbss", ".data", ".gnu.linkonce.d", ".bss", ".idata",
                 ".ibss", ".xdata", ".xbss", ".edata", ".ebss", ".eeprom",
                 "buf_data", "ee_")) else "ax"
            if arm["sec"] in (".rodata", ".rodata.p", ".gnu.linkonce.r.p"):
                flags = "a"
            out.append('        .section %s,"%s",%%%s'
                       % (arm["sec"], flags, "nobits" if nobits else "progbits"))
        if arm["sym"]:
            out.append("        .global %s" % arm["sym"])
            out.append("%s:" % arm["sym"])
        if arm["marker"] == "bit":
            out.append("        .bit 0")
        elif arm["marker"] is None:
            out.append("        .space 1")
        else:
            out.append("        .byte 0x%02x" % arm["marker"])
        return out

    def assemble(self, name, arms):
        src = os.path.join(self.work, name + ".s")
        with open(src, "w") as fh:
            for arm in arms:
                fh.write("\n".join(self._emit(arm)) + "\n")
        obj = os.path.join(self.work, name + ".o")
        p = run([self.AS, "-o", obj, src])
        if p.returncode:
            raise RuntimeError("as-new failed on %s:\n%s" % (src, p.stderr))
        return obj

    def add_sections(self, name, groups):
        """A stub object plus one objcopy-added section per (name, marker).

        The stub contributes nothing to any allocated section, so the image
        stays exactly the markers of the code-space arms.
        """
        stub = self.assemble(name + "-stub", [])
        cmd = [self.OBJCOPY]
        for _out, arms in groups:
            for sec, marker in arms:
                blob = os.path.join(self.work, "b-%s" % sec.replace("/", "_"))
                with open(blob, "wb") as fh:
                    fh.write(bytes([marker]))
                cmd += ["--add-section", "%s=%s" % (sec, blob),
                        "--set-section-flags", "%s=readonly,debug" % sec]
        obj = os.path.join(self.work, name + ".o")
        p = run(cmd + [stub, obj])
        if p.returncode:
            raise RuntimeError("objcopy --add-section failed:\n%s" % p.stderr)
        return obj

    # -- link and read back

    def link(self, out, objs, script=None):
        cmd = [self.LD, "-o", out] + list(objs)
        if script:
            cmd = [self.LD, "-T", script, "--no-check-sections", "-o", out] + list(objs)
        p = run(cmd)
        return p.returncode, p.stderr

    def image(self, elf, section=".text"):
        """The ROM image, made the way the projects make theirs."""
        binf = elf + ".bin"
        p = run([self.OBJCOPY, "-O", "binary", "--only-section=" + section,
                 elf, binf])
        if p.returncode:
            raise RuntimeError("objcopy failed:\n%s" % p.stderr)
        with open(binf, "rb") as fh:
            return fh.read()

    def content(self, elf, section):
        """Raw bytes of one output section, allocated or not."""
        dst = os.path.join(self.work, "dump" + section.replace("/", "_"))
        p = run([self.OBJCOPY, "--dump-section", "%s=%s" % (section, dst),
                 elf, os.devnull])
        if p.returncode or not os.path.exists(dst):
            raise RuntimeError("objcopy --dump-section %s failed:\n%s"
                               % (section, p.stderr))
        with open(dst, "rb") as fh:
            return fh.read()

    def sections(self, elf):
        """name -> (addr, size)."""
        p = run([self.READELF, "-S", "--wide", elf])
        out = {}
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            line = line[line.index("]") + 1:].split()
            # A section name need not start with a dot - www51.sc places
            # `vectors', `reset_network', `cpu_files' and a dozen more.
            if len(line) < 5 or line[0] in ("NULL", "Name"):
                continue
            try:
                out[line[0]] = (int(line[2], 16), int(line[4], 16))
            except ValueError:
                continue
        return out

    def symbols(self, elf):
        p = run([self.NM, elf])
        out = {}
        for line in p.stdout.splitlines():
            f = line.split()
            if len(f) == 3:
                out[f[2]] = int(f[0], 16)
        return out


# -------------------------------------------------------------------- checks

class Check:
    def __init__(self):
        self.fail = []
        self.n = 0

    def eq(self, what, got, want):
        self.n += 1
        if got != want:
            self.fail.append("%s: %s, expected %s" % (what, got, want))
            return False
        return True

    def true(self, what, cond):
        self.n += 1
        if not cond:
            self.fail.append(what)
            return False
        return True


def check_script(pr, ck, label, script, text_arms, text_image, etext,
                 ram_arms, sec_addr, debug, discard, sym_prefix):
    """One script: assemble the probe, link it, verify every arm."""
    arms = list(text_arms) + list(ram_arms)
    obj = pr.assemble(label + "-probe", arms)
    dbg = pr.add_sections(label + "-debug", debug + [("/DISCARD/", discard)])
    elf = os.path.join(pr.work, label + ".elf")
    rc, err = pr.link(elf, [obj, dbg], script)
    if rc:
        ck.fail.append("%s: link failed\n%s" % (label, err))
        return
    if err.strip():
        print("   ld stderr (%s): %s" % (label, err.strip()))

    img = pr.image(elf).hex()
    ck.eq("%s .text image" % label, img, text_image)

    secs = pr.sections(elf)
    syms = pr.symbols(elf)

    for name, addr in sorted(sec_addr.items()):
        if ck.true("%s: output section %s missing" % (label, name), name in secs):
            ck.eq("%s: %s address" % (label, name), "0x%02x" % secs[name][0],
                  "0x%02x" % addr)

    for arm in ram_arms:
        sym = arm["sym"]
        if ck.true("%s: %s (%s) has no symbol %s in the output"
                   % (label, arm["pattern"], arm["sec"], sym), sym in syms):
            ck.eq("%s: %s -> %s" % (label, arm["pattern"], sym),
                  "0x%02x" % syms[sym], "0x%02x" % arm["addr"])

    ck.eq("%s: _ETEXT/_etext" % label,
          "0x%02x" % syms.get(sym_prefix, -1), "0x%02x" % etext)

    for out, group in debug:
        if not ck.true("%s: output section %s missing" % (label, out), out in secs):
            continue
        ck.eq("%s: %s address" % (label, out), secs[out][0], 0)
        content = sorted(pr.content(elf, out))
        ck.eq("%s: %s content" % (label, out), content,
              sorted(m for _s, m in group))

    for sec, _marker in discard:
        ck.true("%s: /DISCARD/ did not discard %s" % (label, sec),
                sec not in secs)

    expected = set(sec_addr) | {o for o, _ in debug}
    strays = sorted(n for n in secs
                    if n not in expected
                    and n not in (".symtab", ".strtab", ".shstrtab"))
    ck.true("%s: unexpected output sections %s - an arm that no longer collects "
            "its input leaves the input as an orphan section" % (label, strays),
            not strays)


def bare(pattern):
    """`KEEP (*(.vectors))' -> `.vectors'."""
    return pattern.split("*(", 1)[1].split(")", 1)[0].strip()


def declared(text_arms, ram_arms, debug, discard, zero=()):
    """Every script arm this file claims to cover, as the script spells it."""
    out = {bare(a["pattern"]) for a in list(text_arms) + list(ram_arms)}
    out |= {bare(p) for p, _s, _k, _m in zero}
    for _o, group in debug:
        out |= {SEC2PAT.get(sec, sec) for sec, _m in group}
    out |= {SEC2PAT.get(sec, sec) for sec, _m in discard}
    return out


def script_arms(path):
    """Every `*(...)' pattern in a linker script, in the order it appears."""
    out = []
    for group in re.findall(r"\*\(([^)]*)\)", open(path, errors="replace").read()):
        out += group.split()
    return out


def audit(ck, label, path, have):
    """No arm of the script may be missing from this file's inventory."""
    unreachable = []
    for pattern in script_arms(path):
        if pattern in have:
            continue
        if any(match(pattern) for match, _n, _w in UNFEEDABLE):
            unreachable.append(pattern)
            continue
        ck.fail.append("%s: %s has an arm *(%s) that run-script.py does not "
                       "feed - add an input for it, or record why none can "
                       "reach it" % (label, os.path.basename(path), pattern))
        ck.n += 1
    return unreachable


def extract_www51(base, work):
    p = run(["7z", "x", "-o" + work, "-y", base, "lib/www51.sc"])
    sc = os.path.join(work, "lib", "www51.sc")
    if p.returncode or not os.path.exists(sc):
        raise RuntimeError("cannot extract lib/www51.sc from %s:\n%s"
                           % (base, p.stdout + p.stderr))
    return sc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", required=True)
    ap.add_argument("--base", default=os.path.join(TB, "base.7z"))
    ap.add_argument("--list", action="store_true",
                    help="print the arm inventory and exit")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    covered = (len(DEF_TEXT) + len(DEF_RAM)
               + sum(len(g) for _o, g in DEF_DEBUG) + len(DEF_DISCARD)
               + len(WWW_TEXT) + len(WWW_RAM) + len(WWW_ZERO_REGION)
               + sum(len(g) for _o, g in WWW_DEBUG))

    if args.list:
        for label, arms in (("elf32i51.sc .text", DEF_TEXT),
                            ("elf32i51.sc RAM", DEF_RAM),
                            ("www51.sc .text", WWW_TEXT),
                            ("www51.sc RAM", WWW_RAM)):
            print("== %s" % label)
            for a in arms:
                print("   %-26s <- %s" % (a["pattern"], a["sec"]))
        print("== arms no input can reach")
        for _match, names, why in UNFEEDABLE:
            print("   %s\n      %s" % (names, why))
        print("\n%d arms covered" % covered)
        return 0

    build = os.path.abspath(args.build)
    pr = Probe(build, "")
    missing = pr.tools_ok()
    if missing:
        print("run-script: missing tool(s): %s" % " ".join(missing),
              file=sys.stderr)
        return 2
    if not os.path.exists(args.base):
        print("run-script: no %s" % args.base, file=sys.stderr)
        return 2

    work = tempfile.mkdtemp(prefix="run-script.")
    pr.work = work
    ck = Check()
    unreachable = []
    try:
        sc = extract_www51(args.base, work)

        # The inventory has to account for every arm both scripts actually
        # carry.  elf32i51.sc is read as ld generated it, not as the template
        # in mcs51/additions.patch spells it.
        gen = os.path.join(build, "ld", "ldscripts", "elf32i51.x")
        if os.path.exists(gen):
            unreachable += audit(ck, "default", gen,
                                 declared(DEF_TEXT, DEF_RAM, DEF_DEBUG,
                                          DEF_DISCARD))
        else:
            ck.fail.append("default: no %s to audit the arm inventory against"
                           % gen)
        unreachable += audit(ck, "www51", sc,
                             declared(WWW_TEXT, WWW_RAM, WWW_DEBUG, [],
                                      WWW_ZERO_REGION))

        check_script(pr, ck, "default", None, DEF_TEXT, DEF_TEXT_IMAGE,
                     DEF_ETEXT, DEF_RAM, DEF_SEC_ADDR, DEF_DEBUG, DEF_DISCARD,
                     "_ETEXT")
        check_script(pr, ck, "www51", sc, WWW_TEXT, WWW_TEXT_IMAGE, WWW_ETEXT,
                     WWW_RAM, WWW_SEC_ADDR, WWW_DEBUG, [], "_etext")

        # The four www51.sc arms whose memory region is declared LENGTH = 0.
        zobj = pr.assemble("www51-zero",
                           [A("*(.text)", ".text", "dir", 0x15)]
                           + [A(p, s, k, None if "bss" in s else 0x41)
                              for p, s, k, _m in WWW_ZERO_REGION])
        rc, err = pr.link(os.path.join(work, "www51-zero.elf"), [zobj], sc)
        ck.true("www51: a byte in each LENGTH=0 region must make ld refuse the "
                "link", rc != 0)
        for pattern, sec, _k, msg in WWW_ZERO_REGION:
            ck.true("www51: %s <- %s: ld did not report %r\n%s"
                    % (pattern, sec, msg, err), msg in err)
    except RuntimeError as exc:
        print("run-script: %s" % exc, file=sys.stderr)
        return 2
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print("   probe tree kept in %s" % work)

    print("== script arms: %d covered, %d checks, %d unreachable"
          % (covered, ck.n, len(unreachable)))
    for _match, names, why in UNFEEDABLE:
        print("   unreachable  %s" % names)
    if unreachable:
        print("   (%s)" % " ".join(sorted(set(unreachable))))
    if ck.fail:
        for f in ck.fail:
            print("FAIL %s" % f)
        print("\nrun-script: FAIL (%d of %d checks)" % (len(ck.fail), ck.n))
        return 1
    print("run-script: PASS (every reachable *(...) arm of elf32i51.sc and "
          "lib/www51.sc placed its own input at its own address)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

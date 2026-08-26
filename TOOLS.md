# The rest of binutils on i51

Every previous round judged this port by `as`, `ld` and the disassembler.
This one runs the tools that ship in the same tarball and that nobody had
pointed at an i51 object: `nm`, `readelf`, `objdump`, `objcopy`, `strip`,
`ar`, `ranlib`, `addr2line`, `size`, `strings`.

Toolchain: `make -C tb build` (binutils 2.47 + `mcs51/*.patch`, `--target=i51-elf`).
Inputs: a hand-written object covering every memory space, a two-object link
with the port's own default script, and the ten testbench projects, which
link with the 2001 `lib/www51.sc` and produce a real 8128-byte ROM.

    $ B=work/modern/build
    $ $B/gas/as-new -o spaces.o spaces.s
    $ $B/ld/ld-new  -o img.elf spaces.o second.o
    $ E=work/tb/projekt/serial/www8051.o          # a real linked image

## Verdict

| tool | verdict |
|---|---|
| `readelf` | fine |
| `nm` / `nm-new` | fine on objects and archives; `?` for every data symbol on an image linked with the port's own script |
| `objdump` | fine, and better than it was — symbol names, colour and space-aware symbol lookup were all missing, all three fixed here |
| `objcopy` | every option works; `-O binary`/`ihex`/`srec` **silently corrupt** a multi-space image |
| `strip` | fine |
| `ar` | fine |
| `ranlib` | fine |
| `strings` | fine |
| `size` | `-A` fine; the default Berkeley output is arithmetic across four address spaces and is not a memory budget |
| `addr2line` | function names only, never `file:line`, and cannot be made to |

---

## S1 — `objcopy -O binary` silently writes a corrupt ROM

The ten projects link `.text` at 0 and `.eeprom` at 0. Those are different
address spaces on the chip. BFD has one. `objcopy` takes the lowest VMA as
the origin and writes both there.

    $ $B/binutils/objcopy -O binary       $E all.bin ; echo rc=$?
    rc=0
    $ $B/binutils/objcopy -O binary -j .text $E just.bin
    $ ls -l all.bin just.bin
    -rwxr-xr-x 1 root root 8384 all.bin
    -rwxr-xr-x 1 root root 8128 just.bin
    $ od -An -tx1 -N6 all.bin ; od -An -tx1 -N6 just.bin
     00 00 e8 ee 10 35          <- .eeprom
     02 00 26 02 02 eb          <- ljmp RESET, the real reset vector
    $ cmp -l all.bin just.bin | wc -l
    1952

Exit status 0, no diagnostic, 1952 wrong bytes, and the first three of them
are the reset vector. `ihex` is the same:

    $ $B/binutils/objcopy -O ihex $E all.hex
    $ # sort the type-00 records by address, count the ones that start
    $ # inside the record before them
    data records: 644 overlapping: 125 highest addr: 0x20c0

125 of 644 records overwrite an earlier one. `srec` behaves identically.

`tb/Makefile` and the project makefiles always pass `-j .text`, so the
testbench never sees this. A user following the README will not.

Not fixable in `objcopy`: it has no notion of a second address space. What
*is* in the port's hands is the linker script, and the port's own default
script already does the right thing — every non-code space is `(INFO)`, i.e.
not `SEC_ALLOC`, so `bfd`'s binary/ihex/srec writers skip it:

    $ $B/binutils/objcopy -O binary img.elf o.bin        # port's default script
    $ $B/binutils/objcopy -O binary -j .text img.elf ot.bin
    $ cmp o.bin ot.bin && echo SAME
    SAME

So: the defect belongs to any script that allocates more than one space, and
the 2001 `lib/www51.sc` that the ten projects use is such a script. The port
should say in the README that `-O binary`/`ihex`/`srec` on this target must
be given `-j .text` unless every non-code space is `(INFO)`. Making `objcopy`
warn on overlapping output sections is an upstream change.

## S1 — (outside this axis, found while reading disassembly) `as` mis-assembles a relative branch to a global label

Not a tool defect. Found because `objdump -d` printed a branch that could not
be right, and it is not.

    $ cat sj3.s
            .text
            nop
            nop
            nop
            nop
            nop
    loc1:   nop
            sjmp loc1
            .global glo1
    glo1:   nop
            sjmp glo1
            nop
            sjmp fwd
            nop
    fwd:    nop
    $ $B/gas/as-new -o sj3.o sj3.s && $B/binutils/objdump -dr sj3.o
    00000005 <LOC1>:
       5:   00          nop
       6:   80 fd       sjmp    .-0x01          ; 0x0005     <- correct, LOC1 is local
    00000008 <GLO1>:
       8:   00          nop
       9:   80 05       sjmp    .+0x07          ; 0x0010     <- wrong, GLO1 is 0x8
       b:   00          nop
       c:   80 01       sjmp    .+0x03          ; 0x000F     <- correct, FWD is local

No relocation is emitted for either, so the linker cannot repair it. The
error is exactly the symbol's value:

    encoded = correct + S_GET_VALUE(target)

`gas/config/tc-i51.c:790`, in `md_apply_fix`:

    else if (fixp->fx_pcrel)
      {
        segT s = S_GET_SEGMENT (fixp->fx_addsy);
        if (fixp->fx_addsy && (s == seg || s == absolute_section))
          {
            value = S_GET_VALUE (fixp->fx_addsy) + *valuep;   /* <-- */
            fixp->fx_done = 1;
          }

For a *local* symbol in the same section, `fixup_segment` has already folded
the symbol value into the fixup and cleared `fx_addsy`, so the first branch of
`md_apply_fix` runs and the result is right. For a *global* one `fx_addsy`
survives, `*valuep` already carries `S + A - PC`, and this line adds `S` a
second time. The 2001 idiom stopped matching gas's semantics somewhere between
2.11.2 and now.

This affects every `J`-operand instruction — `sjmp jz jnz jc jnc jb jnb jbc
cjne djnz` — whenever the target is `.global` and defined in the same file.

Not fixed here. It is one line (`value = *valuep;`), but it changes emitted
bytes, and the ten reference ROMs are 2001 artefacts that may encode the same
fault. Whoever fixes it has to run `make -C tb check` and decide what the
reference means if it moves. `tb/sim/run-branch.py` covers relative branches to
*numeric* addresses only, which is why nothing caught this; a branch-to-global
case belongs in it.

## S2 — `size` on an i51 image is arithmetic across four address spaces

    $ $B/binutils/size $E
       text    data     bss     dec     hex filename
      10128     157      99   10384    2890 www8051.o
    $ $B/binutils/size -A $E
    section    size   addr
    .text      8128      0      <- code space
    .reg         27      0      <- register banks
    .bbss         6     32      <- bit-addressable RAM
    .bitbss      45     48      <- BIT SPACE: 45 bits, not bytes
    .data        18     44
    .bss         48     62
    .ibss       112    144      <- indirect RAM
    .eeprom    2000      0      <- EEPROM, its own space, also based at 0
    Total     10384

`text` 10128 = 8128 bytes of ROM plus 2000 bytes of EEPROM image in a
different space. `bss` 99 = 54 real bytes plus 45 *bits* counted as bytes.
The ROM is 8128 bytes and nothing in the Berkeley output says so.

With the port's own default script it is worse, because every space is
`(INFO)` and therefore not `SEC_ALLOC`:

    $ $B/binutils/size img.elf
       text    data     bss     dec     hex filename
         71       0       0      71      47 img.elf
    $ $B/binutils/size -A img.elf
    .text 71   .rbss 6   .bbss 4   .bitbss 2   .bss 6   .ibss 12   .xbss 24   .ebss 6

`bss 0` with 60 bytes of RAM allocated. `size -A` is the only honest form.
Fixing this properly needs a target hook in `binutils/size.c` — upstream.

## S2 — `nm` prints `?` for every data symbol in an image linked with the port's script

    $ $B/binutils/nm-new -n img.elf
    00000000 ? ELOCAL
    00000000 ? RLOCAL
    00000000 ? XLOCAL
    00000000 T _START
    00000000 ? __EDATA_START
    00000000 ? __EEPROM_END
    ...
    00000021 ? BITVAR
    00000028 ? CVAR
    0000002b ? ILOCAL

Cause is mechanical. The script marks every non-code output section `(INFO)`;
`ld/ldlang.c:4527` turns that into `flags = SEC_HAS_CONTENTS` with no
`SEC_ALLOC`; `bfd/syms.c:decode_section_type` has no case for
"contents, not readonly, not data, not code" and falls through to `?`.

`?` is honest — it says "unknown" — but a user who runs `nm` on a link and
sees no `B`, `D` or `b` anywhere will not know why. Two forms do work and
should be what the README recommends:

    $ $B/binutils/nm-new --format=sysv img.elf
    BCVAR   |00000022|  ? |OBJECT|00000002| |.bbss
    BITLOC  |00000020|  ? |NOTYPE|        | |.bitbss
    BITVAR  |00000021|  ? |OBJECT|00000001| |.bitbss
    $ $B/binutils/objdump -t img.elf | grep bitbss
    00000020 g       .bitbss 00000000 __BIT_START
    00000021 g     O .bitbss 00000001 BITVAR
    00000022 g     O .bbss   00000002 BCVAR

Both name the space. Note this is a property of the *default* script only —
the ten projects use `lib/www51.sc`, whose sections are ordinary `WA`, and
`nm` on those images is completely normal:

    $ $B/binutils/nm-new $E | awk '{print $2}' | sort | uniq -c | sort -rn
       2851 a
        316 t
        168 T
         75 B
         36 D
         24 A

The values are right in both cases. Every symbol was checked against the
declared layout: `XCVAR` = 8 in xdata (after an 8-byte local), `BITVAR` = 0x21
in bit space (after a 1-bit local at 0x20), `RCVAR` = 2 in rdata, `CVAR` =
0x28 in `.bss` (0x25 + 3). Bit symbols carry bit addresses, not byte
addresses: `ACC.0`..`ACC.7` come out 0xE0..0xE7.

## S3 — no DWARF, so `addr2line` can never give a line number

`as -g` produces nothing:

    $ $B/gas/as-new -g -o dbg.o spaces.s
    $ $B/binutils/readelf -S --wide dbg.o | grep -ci debug
    0

`gas/config/tc-i51.c` never calls `dwarf2_emit_insn`, and `generate_lineno_debug`
in `gas/read.c` deliberately does nothing for `DEBUG_DWARF2` without it. `.loc`
is accepted and silently dropped. Even by hand it cannot be built, because the
port has no 32-bit data relocation:

    $ printf '\t.text\nL:\tnop\n\t.long L\n' > l.s && $B/gas/as-new -o l.o l.s
    l.s:3: Error: reloc 2 not supported by object file format

(`.word L` is fine — `R_I51_16`.) So `addr2line` is limited to what the symbol
table gives it, which it does correctly:

    $ $B/binutils/addr2line -f -e $E 0x26 0x2eb
    RESET
    ??:?
    _RETI_
    ??:?

Making this work needs `R_I51_32` in the ABI plus `dwarf2_emit_insn` and
`DWARF2_LINE_MIN_INSN_LENGTH` in `tc-i51.c`. That is a new relocation number,
not a small fix; it goes upstream to whoever owns the ABI.

## S3 — `readelf` does not name the memory-space section indices

    $ $B/binutils/readelf -s --wide spaces.o | tail -7
    22: 00000001  4 OBJECT GLOBAL DEFAULT PRC[0xff01] RCVAR
    23: 00000001  2 OBJECT GLOBAL DEFAULT PRC[0xff02] BCVAR
    24: 00000001  8 OBJECT GLOBAL DEFAULT PRC[0xff03] ICVAR
    25: 00000001 16 OBJECT GLOBAL DEFAULT PRC[0xff04] XCVAR
    26: 00000001  4 OBJECT GLOBAL DEFAULT PRC[0xff05] ECVAR
    27: 00000001  1 OBJECT GLOBAL DEFAULT PRC[0xff06] BITVAR
    28: 00000001  3 OBJECT GLOBAL DEFAULT        COM  CVAR

`PRC[0xff0n]` is what a *stock* readelf prints for a processor-specific index,
so nothing is wrong and nothing is garbage. But `readelf.c:get_symbol_index_type`
has a per-machine switch — `SHN_X86_64_LCOMMON` prints `LARGE_COM`,
`SHN_IA_64_ANSI_COMMON` prints `ANSI_COM` — and the port does not use it. An
`EM_8051` case returning `RDATA_C`, `XDATA_C`, `BIT_C` and so on is four lines.

Deliberately not done here: `tb/sim/run-commons.sh` asserts the exact string
`PRC[0xff01]` in seven places and is part of the merge gate. Changing the two
together is a one-commit job for whoever owns that test, not a drive-by.

The `SHF_*` space codes in `include/elf/i51.h` (0x20000000..0xC0000000) are
never emitted — `i51_elf_fake_sections` is a documented no-op — so there is
nothing there for `readelf -S` to decode either. `readelf -A` correctly prints
nothing; there is no attributes section. `Flags: 0x0` in the header is right;
no `EF_I51_*` exists.

## S3 — `objdump -d` disassembles data as code, unavoidably

The port's script folds `*(.rodata)` into `.text`, so a string table becomes
instructions:

    $ $B/binutils/objdump -d img.elf | sed -n '/XTAB/,+5p'
    00000021 <XTAB>:
      21:   01 02       ajmp    2 <_START+0x2>
      23:   03          rr      A
      24:   04          inc     A
      25:   68          xrl     A, R0
      26:   65 6c       xrl     A, 0x6C

Those bytes are `01 02 03 04 "hello world"`. Same for `.eeprom` in the ten
projects, whose script marks it `WAX`:

    $ $B/binutils/objdump -d $E | grep 'Disassembly of section'
    Disassembly of section .text:
    Disassembly of section .eeprom:

There are no `$d`/`$t` mapping symbols on this target and no
`elf_backend_special_sections`, so `objdump` has nothing to go on. `-j .text`
and `objdump -s` are the answers. Recorded, not fixed.

## S3 — `nm` on a real project image is 2851 duplicate absolute symbols

    $ $B/binutils/nm-new $E | grep -c ' a '
    2851
    $ $B/binutils/nm-new $E | grep -E '^0*e0 a ACC$' | wc -l
    4

The SFR equates come in once per object that includes the header, and `ld`
keeps every copy: the symtab is 56 KB on a 75 KB image of an 8 KB ROM.
Correct, useless, and `nm --defined-only` does not help because they are all
defined. A cosmetic problem for a `.inc` file, not for binutils.

---

## Fixed here

All three in `opcodes/`. Two of them were reported missing by earlier rounds;
the third is what the first one turned out to need.

### `print_address_func` — symbol names on code addresses

`print_insn_i51` printed every absolute code target as a bare number. It now
hands `ajmp`/`acall` (11-bit) and `ljmp`/`lcall` (16-bit) targets to
`info->print_address_func`, which is the only hook that lets a consumer name
the address.

Before:

       0:   02 00 03    ljmp    0x0003
       5:   12 00 1a    lcall   0x001A
       8:   11 1a       acall   0x001A

After:

       0:   02 00 03    ljmp    3 <MAIN>
       5:   12 00 1a    lcall   1a <HELPER>
       8:   11 1a       acall   1a <HELPER>

On the real image this turns the interrupt vector table into something a
person can read:

    $ $B/binutils/objdump -d $E | grep -m4 ljmp
           0:   02 00 26    ljmp    26 <RESET>
           3:   02 02 eb    ljmp    2eb <INTIE0>
           b:   02 02 cf    ljmp    2cf <INTTF0>
          13:   02 02 eb    ljmp    2eb <INTIE0>

`--prefix-addresses` and `--no-addresses`, which are built entirely on that
hook, work for the first time:

    $ $B/binutils/objdump -d --prefix-addresses img.elf | sed -n '6,9p'
    00000000 <_START> ljmp     00000003 <MAIN>
    00000003 <MAIN> mov        A, #0x42        ; #66   #'B'
    00000005 <MAIN+0x2> lcall  0000001a <HELPER>
    00000008 <MAIN+0x5> acall  0000001a <HELPER>

With no symbol table — `objdump -D -b binary -m i51`, which is what
`tb/isa_check.py` uses — objdump prints `0x3` where the old code printed
`0x0003`. Still assembles, and the round trip is unchanged:

    $ make -C tb roundtrip BUILD=work/modern/build
    == table: 280 instructions
       roundtrip: 280/280
    PASS   (and 3/3, 18/18 for extra.txt and zeroops.txt)

Relative branches are left alone on purpose: their `.-0x06 ; 0x0006` form is
what `isa_check.py` reads back to re-assemble them, and the displacement half
is the only thing that pins a branch the comment agrees with.

### `symbol_is_valid` — the annotation had to be told which space it is in

Naming an address is only an improvement if the name is right, and the first
version of the change above was wrong one time in ten. The MCS-51 has five
address spaces that all start at zero; `objdump`'s
`find_symbol_for_address` picks the nearest symbol by value and, when nothing
in the current section matches, takes one from anywhere. Its own comment says
so: *"this may be wrong for some symbol references if the sections have
overlapping memory ranges"*. This target is nothing but overlapping ranges,
and worse, the 2001 headers define about 2851 absolute SFR equates covering
0x00-0xFF, i.e. exactly the addresses a short subroutine lives at.

Measured over all ten project images — count every `ljmp`/`lcall`/`ajmp`/`acall`
whose annotation names a symbol, look up that symbol's section in
`objdump -t`, count the ones that are not in `.text`:

    2342 annotated code targets, 239 named a symbol outside .text  (10.2%)
      *ABS*  151     e.g.  lcall e0 <ACC.2>   - an SFR equate
      .eeprom 76
      .reg    23     .bss 13   .bitbss 8   .ibss 3   .bbss 3

`opcodes/i51-dis.c` now supplies `i51_symbol_is_valid`, registered in
`disassemble_init_for_target`: while a section carrying code is being
disassembled, only a symbol from a section carrying code may name an address
in it. Everywhere else — `objdump -D` walking `.rbss`, `.xbss` and the rest —
every symbol is let through, so those sections keep their own labels. Same
measurement afterwards:

    2342 annotated code targets, 76 named a symbol outside .text  (3.2%)
      .eeprom 76

All 151 SFR misnamings are gone. The 76 that remain are all `.eeprom`, and
they are not fixable from here: the 2001 `lib/www51.sc` gives that section
`WAX`, so the EEPROM image genuinely carries the code flag and is
indistinguishable from `.text` to anything downstream — it is also why
`objdump -d` disassembles it (see S3).

The other half of the filter is that `-D` on a data section keeps its labels:

    $ $B/binutils/objdump -D img.elf | sed -n '/section .rbss/,/section .bbss/p'
    Disassembly of section .rbss:
    00000000 <__RDATA_START>:
            ...
    00000002 <RCVAR>:
       2:   00          nop

An earlier draft that filtered unconditionally printed `<.rbss>:` there
instead, which is why the filter looks at `info->section` rather than only at
the symbol.

### `fprintf_styled_func` — `--disassembler-color` works

Every write went through `info->fprintf_func`, so the disassembler emitted no
style information and `objdump --disassembler-color=on` produced plain text.
All of them now go through `info->fprintf_styled_func`, with the style chosen
from the operand's own syntax (`#` immediate, `.` displacement, `0x`/`/`
address, anything else a register), and `bfd_arch_i51` is registered in
`disassemble_init_for_target` with `created_styled_output = true`.

Before — `objdump -d --disassembler-color=on img.elf | cat -v`, not one escape
sequence anywhere in the output. After:

       0:  02 00 03    ^[[33mljmp^[[0m  ^[[35m3^[[0m <^[[32mMAIN^[[0m>
       3:  74 42       ^[[33mmov^[[0m   ^[[34mA^[[0m, ^[[35m#0x42^[[0m  ; #66  #'B'
       5:  12 00 1a    ^[[33mlcall^[[0m ^[[35m1a^[[0m <^[[32mHELPER^[[0m>

Plain-text output is byte-identical to before except for the address form
noted above.

### What the three changes were tested against

    isa          280/280 assemble, 280/280 decode, testall.asm assembles
    roundtrip    280/280, 3/3, 18/18
    branch       24/24
    bits         50/50
    reloc        36/36
    defaultlink  PASS
    commons      PASS
    check        all 10 projects match the reference ROMs

`sim` needs ucsim, which is not installed here; it exercises the assembler and
the simulator, neither of which these changes touch.

---

## Verified working, no defect found

Everything below was checked against a value, not against the fact that output
appeared.

**`readelf`** — `-h -S -s -r -a -x -A`, objects and linked images.
Machine named from the registered number:

    Machine: Intel 8051 and variants

and the 2001 unregistered value too, after `tb/i51elf_le2be.py`:

    Machine: MCS-51 8-bit microcontroller (legacy web51 value)

Relocation types all decode (`elf_i51_reloc_type` is wired into
`dump_relocations`, and `guess_is_rela` knows both machine numbers):

    $ $B/binutils/readelf -r --wide spaces.o
    00000001  00001509 R_I51_16      00000003   MAIN + 0
    00000008  00000104 R_I51_11      00000000   .text + 1a
    00000013  00000e05 R_I51_8_BIT   00000000   .bitbss + 0

Each one matches the instruction at that offset: `ljmp`→`R_I51_16` at +1,
`acall`→`R_I51_11` at +0, `setb`→`R_I51_8_BIT` at +1.

**`nm`** — object files, archives, `--format=sysv`, `--print-armap`,
`-S`. Every common comes out `C` with the size in the value field, which is
the ELF common convention, and `--format=sysv` recovers the space from the
fabricated section name:

    RCVAR |00000004| C |OBJECT|00000004| |.rbss
    BITVAR|00000001| C |OBJECT|00000001| |.bitbss
    CVAR  |00000003| C |OBJECT|00000003| |*COM*

`__RB__`, the register-bank marker gas emits for `.using`, is the
`SHN_I51_REGBANK` (0xff00) case and behaves the same way:

    $ $B/binutils/readelf -s --wide rb.o | grep RB
    5: 00000010 24 OBJECT GLOBAL DEFAULT PRC[0xff00] __RB__
    $ $B/binutils/nm-new --format=sysv rb.o
    __RB__ |00000018| C |OBJECT|00000018| |.regbank

24 = three register banks in use for `.using 2`. The `st_value` of 16 is
bfd's default common alignment, not a port value; a linked `.regbank` comes
out 0x18 long at address 0, which is right.

**`objdump`** — `-h -t -s -r -d -D -dr -j --syms --disassemble-all`.
`-h` reports the section flags bfd holds; `-t` names the space for every
symbol, including the fabricated commons; `-s` dumps contents; `-dr`
interleaves relocations at the right offsets. Value/size look swapped for a
common in `-t` output (`00000003 O *COM* 00000001 CVAR`) — that is generic
bfd behaviour for ELF commons, verified identical for a plain `*COM*` symbol
on x86-64, not a port artefact.

**`objcopy`** — with the caveat in S1, every option asked for works:

    --only-section=.ibss       one section survives, at 0x2b, 12 bytes
    --remove-section=.xbss     that one section gone, the rest untouched
    --gap-fill 0xFF --pad-to 0x60   output 96 bytes, tail is ff
    --change-addresses 0x100   every VMA and LMA moved by 0x100
    -O ihex / -O srec          checksums verified by hand
    -I ihex -O elf32-i51 -B i51   round-trips to a byte-identical binary
    -I srec -O binary             likewise

The ihex checksum on the first record of `img.elf` was recomputed by hand
(0x2E sum, 0xD2 two's complement) and matches. Byte order in ihex and srec is
the byte order of `.text` — these formats carry a byte stream, so the
big-endian-code / little-endian-ELF split does not reach them.

`--change-addresses` shifts every space by the same amount, which is
meaningless on a machine with four of them. Generic objcopy semantics, worth
knowing before using it.

**`strip`** — removes the symtab, leaves the image bytes identical:

    $ $B/binutils/strip-new img-strip.elf
    $ $B/binutils/objcopy -O binary img-strip.elf s.bin && cmp s.bin o.bin && echo SAME
    SAME

1948 -> 676 bytes. `--strip-debug` on an object leaves every symbol. Works on
an archive too, member by member.

**`ar` / `ranlib`** — `rc`, `t`, the symbol index, and a link that pulls a
member out of the archive by symbol:

    $ $B/binutils/nm-new --print-armap lib.a | head -3
    Archive index:
    _START in spaces.o
    MAIN in spaces.o
    $ $B/ld/ld-new -o u.elf u.o lib.a && $B/binutils/nm-new u.elf | grep SECOND
    00000004 T SECOND_FN

`ranlib` regenerates the same index. `objdump --syms` and `size` walk an
archive member by member and label each one `(ex lib.a)`.

**`strings`** — finds `hello world` and `SECOND-OBJECT-STRING` in the image.

**`size -A`** — correct per-section sizes and addresses; see S2 for what the
default format does with them.

---

## Small notes

`(INFO)` also means `SEC_HAS_CONTENTS`, so `ld` writes the zero bytes of
`.bss`, `.xbss`, `.ibss` and the rest into the ELF file and turns `NOBITS`
into `PROGBITS`:

    object:  [ 4] .bss  NOBITS   00000000 000050 000003 WA
    image:   [ 5] .bss  PROGBITS 00000025 0000a7 000006 W

60 bytes of zeros in the file for the two-object test link. Harmless — the
image is not what gets flashed — but it is why `readelf -S` on a link shows
`PROGBITS` where the object said `NOBITS`.

`objcopy --only-section` prints
`warning: empty loadable segment detected at vaddr=0` when the kept section is
not the one in the `PT_LOAD`. Generic objcopy noise, no output damage.

`objdump -d -j .eeprom` reports `Address 0x6 is out of bounds` where a
three-byte opcode straddles the next symbol — standard objdump behaviour when
data is decoded as code, not a port fault.

`bfd/cpu-i51.c` sets `section_align_power` to 1 for a machine whose natural
alignment is a byte. Every section still comes out `2**0` because gas sets the
alignment explicitly, so nothing observable follows from it; noted in passing.

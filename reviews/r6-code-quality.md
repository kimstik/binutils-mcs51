# MCS-51 (i51) binutils 2.47 port: code-quality and integration review

Scope: the C sources the port adds (gas/config/tc-i51.[ch], bfd/elf32-i51.c, bfd/cpu-i51.c,
opcodes/i51-dis.c, include/elf/i51.h, include/opcode/i51.h, ld emulparams and script) and
every hunk of mcs51/modifications.patch.

Paths below are relative to the patched tree
`/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/work/modern/binutils-2.47`.
All repros were run with the reference build in `.../work/modern/build` (`AS=gas/as-new`,
`LD=ld/ld-new -Lld`, `OD=binutils/objdump`, `RE=binutils/readelf`). They are reproduced as
files in `/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/review/t/`.

Items that were already known are not repeated here: `jmp lbl`, address-space-blind relocs,
R_I51_16 masking, and case folding.

Severity scale: CRITICAL means the output is wrong and nothing is reported. HIGH means UB, a
crash, or wrong-but-diagnosable behaviour that input can reach. MEDIUM means a latent bug or a
portability problem. LOW means a style or upstream-submission issue.

---

## CRITICAL

### C1. Trailing text after the third operand of `cjne` is assembled as a new instruction
`gas/config/tc-i51.c:698-712, 728`. In md_assemble, after the third (`J`) operand of `cjne`
is parsed, nothing checks for junk. `input_line_pointer = line;` then leaves the pointer in
the middle of the line. read.c does `*input_line_pointer++ = nul_char` after `assemble_one`,
which overwrites the next character with the end-of-line character and re-parses the rest as
a new statement.
```
lbl: cjne a,#1,lbl,nop      ->  b4 01 fd 00     (extra NOP, no diagnostic)
lbl: cjne a,#1,lbl  xnop    ->  b4 01 fd 00     ('x' is eaten, "nop" is assembled)
```
Every error path that returns after `input_line_pointer` was moved has the same mechanism.
There it causes spurious second diagnostics and shifts line numbers: `cjne r0,#2,lbl inc a`
on line 2 is reported as line 3, "unknown opcode `nc'". **Fix:** check the third operand for
junk, and always restore `input_line_pointer` to the end of the statement, as other ports do
with a save/restore around `expression()`.

### C2. A PC-relative branch to a weak or global symbol in the same section is resolved by gas, so the override is lost
`tc-i51.c:821`. `if (s == seg || s == absolute_section) fixp->fx_done = 1;` ignores
`S_FORCE_RELOC`/weak, even though the comment above it says the linker "may override" the
symbol.
```
w.s: .weak handler / sjmp handler / ljmp handler / handler: ret
s.s: .globl handler / .skip 0x10 / handler: nop
ld w.o s.o  ->  sjmp goes to the weak copy at 0x05; ljmp goes to the strong one at 0x16
```

### C3. A branch to an absolute address is resolved against the section offset, and no reloc is emitted
`tc-i51.c:1785` (fixup8 always makes a JUMP_REL fixup), `:780` (md_pcrel_from_section), `:821`
(`absolute_section` gives fx_done), `:896-915` (I51_11 page check against the section-relative
PC). `sjmp 0x10`, `jc 5`, `ajmp 0x123` and `acall 0x100` are encoded as if `.text` were at 0,
and the object carries no relocation.
```
pad.s: .skip 0x100      d.s: sjmp 0x0000 / ajmp 0x0000
ld pad.o d.o  ->  0x100: 80 fe  "sjmp ."  (an infinite loop instead of "out of range")
ld -Ttext=0x800 a.o: sjmp 0x10 goes to 0x810, ajmp 0x123 goes to 0x923, jc 5 goes to itself
```
**Fix:** keep the reloc against the absolute section symbol, as the generic code does. Do not
set fx_done for pcrel or in-page fixups unless the target is in the same section.

### C4. The linker ignores SEC_MERGE for local-symbol relocations
`bfd/elf32-i51.c:561-563`. `relocation = sec->output_section->vma + sec->output_offset +
sym->st_value` has no `_bfd_elf_rela_local_sym()` call. A reference into a merged string
section gets the offset it had before the merge.
```
m1.s/m2.s: .section .rodata.str1.1,"aMS",@progbits,1 / L: .asciz "hello" / M: .asciz "wN" / .text / mov dptr,#M
ld m1.o m2.o  ->  second "mov dptr,#0x0018"; the merged "w2" is at 0x0F, and 0x18 is past the image
```
Any C front end (or hand-written "aMS" sections) reaches this.

### C5. `.byte ARn` and `ARn+k` keep the register bank that was in force on first use
`tc-i51.c:1104-1127`. md_undefined_symbol creates a permanent absolute symbol `ARn = regbank+n`
the first time the name is seen. Later `.using` changes do not affect it. The operand-hash path
(`push ar0`) is recomputed each time, so the two paths disagree.
```
.using 0 / push ar0 / .byte ar1 / mov a,ar2+0 / .using 1 / push ar0 / .byte ar1 / mov a,ar2+0
-> c0 00 01 e5 02 c0 08 01 e5 02    (should end ... c0 08 09 e5 0a)
```
The fake AR1/AR2 (and ACC, P1, ...) symbols also leak into `.symtab` as LOCAL ABS.

### C6. `.pcode` silently truncates an exec address that is forward-referenced or defined by equ
`tc-i51.c:940-948`. The BFD_RELOC_I51_13_PCODE fx_done path checks only the lower bound `<0x100`
and then masks with `& 0x1FFF`. The direct constant path (`:2863`) and the linker (`elf32-i51.c:452`)
both reject values above 0x1FFF.
```
.pcode M / M = 0x2345   ->   03 45 ...   (no error; `.pcode 0x2345` does give an error)
```

### C7. `@BYTE` in `.pcode` gives a different value for a forward reference than for a backward one
`tc-i51.c:2639-2657`. For a constant, gas writes `value-1`. For a symbol it writes 0xFF in
place and makes an R_I51_8 fixup. The linker adds the in-place 0xFF because src_mask is 0xff
even though the reloc is RELA, so the result is value-1. When the symbol is an equ defined
later, md_apply_fix overwrites the byte with the plain value.
```
K=5 / .pcode 0x200 @BYTE K   -> 04
.pcode 0x200 @BYTE L / L=5   -> 05
```
Related: every howto has a non-zero `src_mask` with `partial_inplace=false`. The linker
therefore adds whatever bytes are in place, while `readelf -r` shows addend 0 for the same
field (`elf32-i51.c:38-255`).

### C8. R_I51_8_BIT never checks for overflow
`elf32-i51.c:115-127` uses `complain_overflow_dont`. A bit operand whose symbol resolves to
more than 0xFF is truncated without a word. In gas, the fx_done path accepts -256..255 for
bits (`tc-i51.c:876`), and `check_range(I51_OP_BIT)` accepts -128..255.
```
.globl ext at 0x100 / jbc ext,start  ->  "10 00 d3" : bit 0x00
```

---

## HIGH

### H1. `.local` replaces the generic ELF `.local` directive
`tc-i51.c:75, 1064-1100`. `.local foo` / `.comm foo,4` produces a **GLOBAL** common FOO, so two
objects that use the idiom (for example compiler output) silently share storage. The
`symbol_get_obj(...)->local` branch in i51_common (`:2247-2372`, about 125 lines across 7
copies) can no longer be reached. The name also conflicts with the generic `.local` that
as.texi documents. **Fix:** rename the directive (for example `.unreserve`), restore
`obj_elf_local`, and delete or repair the dead branch.

### H2. B2B() on a non-bit operand is accepted, and the result depends on whether the operand is a constant
`tc-i51.c:1854-1863` (IMM8 path) and `:1804-1830` (constant path); parse_operand2 allows B2B
whenever op_expr1 is unset.
- `mov a,B2B(0x20,1)` gives `e5 01`: the bit address is used as a byte address.
- `mov a,B2B(x,1)` gives `e5 00` + R_I51_8 X: the offset is dropped.

Neither form produces a diagnostic. In the same way, HIGH/LOW on a bit operand that refers to
a symbol (`setb HIGH(sym)`) is dropped and an R_I51_8_BIT against the full value is emitted
(`fixup8` I51_OP_BIT ignores the prefix).

### H3. `sym.N` works only for constants
`tc-i51.c:447-471`. `x=0x20` / `setb x.3` emits R_I51_8_BIT against an undefined symbol `X.3`
(the error appears only at link time). `setb x .3`, with a space, folds correctly to 0x03.

---

## MEDIUM

- **M1. `.rcomm X` followed by `.xcomm X` in the same file is accepted, and the last directive
  wins.** `tc-i51.c:2373-2400`. The linker refuses the same pair across files
  (`elf32-i51.c:1004`).
- **M2. The `.comm` resize warning is false.** `tc-i51.c:2212` warns "Not changed to %d", but
  `:2375` then sets the new size. `.comm bar,2` / `.comm bar,4` gives size 4.
- **M3. `as -g`, `--gdwarf-5` and `.loc` silently produce no debug sections.** md_assemble
  never calls `dwarf2_emit_insn()`. There is also no 32-bit data reloc (`.long x` gives
  "cannot relocate 4 bytes"), so DWARF could not be emitted anyway. `.cfi_*` is rejected.
- **M4. The alignment of memory-space commons is dropped.** The final link ignores it, and
  `ld -r` rewrites st_value to 1 (`.icomm iv,4,2` has st_value 2 in the .o and 1 after `ld -r`).
  `elf32-i51.c:1048-1061` admits this in a comment, but it is not documented for users.
- **M5. `.pcode` error recovery consumes the following lines.** `tc-i51.c:2569-2578`:
  `ignore_rest_of_line()` and then `return` lets the next `pcodeOperand()` and
  `demand_empty_rest_of_line()` run on the following line(s). Stale `op_expr3/op_expr4/p*mode`
  (file-scope globals) are reused. It also tests `\r`, `\n` and `;` instead of
  `is_end_of_stmt`, so a `$` separator is not recognised.
- **M6. User errors are reported as "internal error: out of range error".**
  `elf32-i51.c:626-627`. This happens for an R_I51_8_B2B on a non-bit-addressable byte, or a
  `.pcode` target below 0x100, which is easy to reach (`.pcode ext` with ext=0x00).
- **M7. `srel == 0` is treated as an unresolved COMMON.** `elf32-i51.c:420, 446`. B2B and
  13_PCODE skip the transformation and silently leave the in-place offset for an undefweak
  symbol or one resolved to 0. During a final link a common is already defined, so this
  heuristic is not needed.
- **M8. `include/elf/i51.h:97-103`: SHF_* "codes" are a 3-bit enumeration but are tested as bits.**
  `SHF_IDATA` == `SHF_EXCLUDE` (bit 31). `i51_section_flags()` (`tc-i51.c:2072`) treats
  SHF_BDATA, SHF_XDATA and SHF_CDATA as SHF_REGBANK because they share bit 29.
  `i51_elf_section_from_shdr` turns any contentless section with bit 31 set (a generic
  `"e"`/SHF_EXCLUDE section) into SEC_IS_COMMON. The names lack an `I51_` prefix and pollute
  readelf's namespace.
- **M9. A register name in parentheses becomes a symbol.** `mov a,(r3)` assembles as direct
  0x00 with R_I51_8_DIR against an undefined symbol `R3`, and there is no diagnostic in gas.
- **M10. `ELF_MAXPAGESIZE 1` (backend) disagrees with `MAXPAGESIZE=0x0800` (emulparams).**
  `cpu-i51.c` has `section_align_power 1` for an 8-bit machine.
- **M11. The linker script injects a `RET` byte** (`__I51_RET`) at the end of `.text` in every
  link. All RAM spaces are `(INFO)`, so the initial contents of `.data`, `.xdata` and `.eeprom`
  never reach a loadable image. That is outside this review's lane; it is noted for the
  address-space reviewer.

---

## Build, sanitizer, and `--enable-targets=all` results

- I rebuilt a copy of the tree with `-O2 -g -Wall -Wextra -Wmissing-prototypes -Wshadow
  -Wimplicit-fallthrough -Wformat=2 -Wcast-qual -Wwrite-strings -Wsign-compare
  -fsanitize=address,undefined`. The port files produced **zero warnings**. Adding
  `-Wc++-compat -fanalyzer` also gave nothing in the port files.
- I ran a corpus of about 70 malformed and edge-case lines, an all-instructions file, the
  `ld`, `ld -r` and `--gc-sections` links, `objdump -D` on 5 KB of random bytes, and a crafted
  object with a local symbol in SHN_I51_RDATA_C / an out-of-range index. **No ASAN or UBSAN
  reports.** (Directories: `review/b-asan`, `review/t`.)
- `--enable-targets=all` (bfd, opcodes, binutils, ld) builds cleanly with no i51 warnings.
  objdump and ld from that build handle i51 objects, and the result is byte-identical to the
  single-target link. Nothing in modifications.patch disturbs other targets. The config.sub
  canonicalisation is `i51-elf` → `i51-unknown-elf`; `mcs51`/`8051` aliases are not accepted.

---

## LOW (dead code, misleading comments, style)

- **Dead code:**
  - `BFD_RELOC_I51_R1`, `_R3`, `_8` and `_16` are declared in reloc.c, bfd-in2.h and libbfd.h
    but never generated. Gas uses `BFD_RELOC_8`/`16`.
  - The R_I51_R1/R3 howtos have `dst_mask 0`, so applying them writes nothing.
  - `i51_elf_*_symbol_ptr` (7) are written but never read.
  - `p1mode` is unused.
  - `elf32_i51_object_p` and `i51_elf_fake_sections` are no-ops; the comment "Set the right
    machine number" is wrong.
  - `MD_APPLY_FIX3` and `md_after_pass_hook` are hooks that no longer exist (`tc-i51.h:98, 176`).
  - There are `ASMDBG` fprintf blocks and commented-out `#define`s.
  - In i51-dis.c, `#include <assert.h>` and `opintl.h` are unused.
- **Misleading comments:**
  - `tc-i51.h:100-102` says direct addresses reach "only the first 0x80 bytes", while the
    R_I51_8_DIR howto says 0x00..0xff.
  - `tc-i51.c:1712` claims "a constant never reaches this", but the check is on symbols.
  - The md_apply_fix pcrel comment contradicts the code (see C2).
- **Global namespace pollution:**
  - gas has non-static globals `line`, `op`, `opcode`, `oper`, `regno`, `regbank`,
    `i51_directop`, `op_expr1..4`, and the functions `pcodeOperand`, `writePcodeOperand`,
    `decodePcodeOperand`, `i51_build_ins` and `i51_parse_operand*`.
  - In libbfd, `elf32_i51_symbol_processing` and `elf32_i51_section_from_bfd_section` are
    exported and should be static.
- **Diagnostics and misc:**
  - `md_show_usage` prints "A51 options: NONE".
  - `line_separator_chars = "$"` makes `$` unusable in operands.
  - `i51_info_to_howto_rela` prints an unsigned value with `%d` and returns `0`/`1` for `bool`.
  - Mixed `return 0/1` and `true/false` throughout elf32-i51.c.
  - `md_apply_fix` HIGH range check is -65536..65535.
  - Right shifts of negative `offsetT` values (`>> 8`) are implementation-defined.
- **readelf integration:** there is no `EM_8051` case for symbol section indices (shows
  `PRC[0xff01]`), and no e_flags decoding.

---

## What blocks submission to binutils@sourceware.org

1. **Licence:**
   - tc-i51.c/.h, elf32-i51.c, i51-dis.c and include/elf/i51.h are **GPLv2-or-later with the
     old 59 Temple Place address**; upstream requires GPLv3+.
   - include/opcode/i51.h has **no header at all**.
   - cpu-i51.c and the ld script claim "Copyright (C) 1999/2014-2025 FSF" for new code by a
     different contributor (Dmitry Teytelman), which is inconsistent with the 2001
     Radek Benedikt files.
2. **Copyright assignment or DCO:** FSF copyright assignments (or DCO sign-offs, under current
   binutils policy) are needed from every author: Radek Benedikt (2001), Dmitry Teytelman, and
   later contributors. The FSF-copyright lines are not valid without them.
3. **config.sub** must first go upstream through config-patches@gnu.org (config.git). Binutils
   only imports it.
4. **No testsuite:**
   - nothing under `gas/testsuite/gas/i51/`, `ld/testsuite/ld-i51/`, or
     `binutils/testsuite` (objdump);
   - the `tb/` Python harness is out-of-tree and does not run under DejaGnu;
   - the generic `ld-elf`/`gas` suites have never been run (`make check` not wired).
5. **GNU coding style:**
   - `//` comments throughout tc-i51.[ch];
   - CamelCase function names;
   - the 7-fold copy-pasted section and common code in both gas and bfd;
   - K&R-style `switch (...) {` braces;
   - tabs and spaces mixed;
   - long lines.
6. **Missing NEWS entries** (gas/NEWS, ld/NEWS, binutils/NEWS) and no ld documentation of the
   emulation. The c-i51.texi build could not be checked here because makeinfo is not installed.
7. **Missing standard features:** no DWARF line info, no CFI, and no 32-bit data reloc. The
   reloc enum has 4 unused entries.
8. **The `.local` name conflict (H1)** would be rejected on review because it changes the
   semantics of a documented generic directive.

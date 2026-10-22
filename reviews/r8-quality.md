# r8-quality: C correctness review of the MCS-51 port (binutils 2.47)

The review covered the source tree `work/modern/binutils-2.47`, read only and never modified. Repros use the
official build, `work/modern/build` (`as-new`, `ld-new -L build/ld`, `objdump`, `nm-new`,
`readelf`). Fuzzing used a private sanitizer build,
`review8/quality/asan` (`-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all`).
The scripts are in `review8/quality/scripts` and the saved cases in `review8/quality/t/{crash2,lcrash,lcrash2}`.

## Findings, ranked

### HIGH-1: gas segfaults on a relative branch to `X - undefined`
`tc-i51.c:1416-1417` (md_apply_fix, not-done path) evaluates `S_GET_SEGMENT (fixp->fx_addsy)` for every
`BFD_RELOC_I51_7_PCREL`. The code assumes that write.c always leaves an add symbol on such a fixup.
It does not when the branch target is `sym - undefined` and `sym` is in the same section as the branch. In that case
fixup_segment folds `sym` into the pc-relative value, sets `fx_addsy = NULL` and keeps `fx_subsy`. The
abs_section_sym substitution only happens when `fx_subsy` is NULL.

    $ printf ' sjmp .-y\n' > seg.s;  as-new seg.s -o seg.o
    seg.s:1: Error: can't resolve .text - Y
    seg.s:1: Error: can't resolve 0 - Y
    seg.s: Internal error (Segmentation fault).
The same happens for `l: nop` / `jb 0x20.1,l-y`, `djnz r0,l-y` and `jnc fwd-bits` (found by fuzzing).
Expected: the two "can't resolve" errors and no crash. UBSAN reports
`symbols.c:2499 member access within null pointer`, called from `tc-i51.c:1417`.

### HIGH-2: `ld --gc-sections` drops `__RB__`, so data is allocated on top of the selected register bank
`i51_finish` (tc-i51.c:1629) emits `__RB__` as an unreferenced common. The linker collects it into the fake
`.regbank` common section that `i51_elf_common_section` (elf32-i51.c:908-923) makes. Nothing keeps that section, so
section GC sweeps it.

    START: .using 1 / mov ar0,#5 / mov RV,#7 / sjmp START / .rcomm RV,2   (START .global)
    ld -e START            -> __RB__ 0x00 size 0x10, RV = 0x10;  75 08 05 / 75 10 07
    ld --gc-sections -e START -> no __RB__,  RV = 0x08;            75 08 05 / 75 08 07
In the second link, R0 of bank 1 and the variable RV share address 0x08. There is no diagnostic. The script only
reserves bank 0 (`. = MAX (., 0x08)`). Expected: the register-bank reservation survives GC. For example, the
section could get SEC_KEEP, or the script could use `KEEP (*(.regbank))`.

### HIGH-3: R_I51_8_DIR and R_I51_8_BIT wrap modulo 0x10000 at link time
Both howtos (elf32-i51.c:91, :206) use `complain_overflow_unsigned` and go through
`_bfd_final_link_relocate` (:562). `bfd_check_overflow` first cuts the value to the 16 address
bits of `bfd_i51_arch` (cpu-i51.c, bits per address = 16), so any value from 0x10000 up passes when its low 16
bits fit. The comment at :554-556 describes exactly this problem for R_I51_16_CODE, but the fix was applied
to that one relocation only.

    printf ' mov K,a\n setb K\n mov K+1,#1\n jb K+0x10,.\n' > dm.s
    as-new dm.s -o dm.o && ld-new -e 0 --defsym K=0x10030 -o dm.elf dm.o   -> rc 0
    f5 30 / d2 30 / 75 31 01 / 20 40 fd      (gas refuses each of these for an in-file K)
`K` defined as `.global K / .equ K,0x10030` in another object gives the same result. R_I51_7_PCREL
(`complain_overflow_signed`) is masked in the same way: `sjmp K` with K=0x10030 links as `80 2e`, a branch to 0x30.
Within the 64K space this masking matches how the 8051 PC wraps, but it is wrong for a target above 0xFFFF.

### HIGH-4: an ordinary `.comm` in one object silently pulls an `.xcomm` of another object into internal RAM
`elf32_i51_check_common_space` (elf32-i51.c:955-960) exempts every ordinary common. The generic
common merge then keeps the section of the larger declaration.

    o1.s: .comm X,10 / mov X,a          o2.s: .xcomm X,4 / mov dptr,#X / movx a,@dptr
    ld-new -e 0 -o oo.elf o1.o o2.o   -> rc 0, X = 0x20 (internal RAM, size 10)
    f5 20 / 90 00 20 / e0     (the movx reads xdata 0x20, which nothing reserved)
If the `.xcomm` is the larger one, the link fails, but only because R_I51_8_DIR catches it. The R_I51_16 user is
never checked. In a single file gas refuses this pair ("already a common of another memory space").
The manual says a common in two spaces "cannot be arbitrated by size ... and the link is refused".

### MEDIUM-1: `.lcomm` or `.tls_common` after `.xcomm` of the same name still moves the symbol out of its space (r7 #4 residue)
The fix for r7 #4 only covers `i51_common_parse`. `.lcomm` and `.tls_common` are still obj-elf's
(`obj_elf_lcomm`/`obj_elf_tls_common` → s_comm_internal with `s_lcomm_internal`/`elf_common_parse`).

    ' .xcomm buf,8\n .lcomm buf,8\n'      -> rc 0, BUF GLOBAL in .bss (internal RAM)
    ' .xcomm buf,8\n .tls_common buf,8\n' -> rc 0, BUF TLS COM (ordinary common)
Expected: the "already a common of another memory space" error.

### MEDIUM-2: a negative absolute symbol from another object is refused by the linker
`i51_final_link_relocate` (elf32-i51.c:491) computes `srel = relocation + r_addend` from the
zero-extended 32-bit `st_value`. So `.equ K,-1` arrives as 0xffffffff, and even `K+1` (= 0) overflows.

    k.s: .global K / .equ K,-1        u.s: mov a,#K / add a,#K+1 / .byte K / .word K / mov a,#HIGH(K)
    ld-new -e 0 u.o k.o  -> "relocation truncated to fit" for all five (R_I51_8_IMM x2, R_I51_8, R_I51_16, R_I51_H)
The same source with K defined in the same file assembles. `ld --defsym K=-1` links. Expected: the value is
sign-extended from 32 bits, which is the ELF32 symbol value width, before the range checks.

### MEDIUM-3: `.pcode ADDR -1` silently becomes address ADDR-1 with no operand
`i51_pcode` (tc-i51.c:1990) reads the address with `expression()`, which takes `0x200 -1` as one
expression. The manual says the address "is separated from its first operand by white space".

    ' .pcode 0x200 -1\n'  -> rc 0, bytes 01 ff 00   (address 0x1FF, no operand)
    ' .pcode 0x200 +X\n'  -> rc 0, R_I51_13_PCODE X+0x200, no operand
Expected: operand -1, or at least a diagnostic.

### LOW
1. The pcode keyword `SHL8` has no word-boundary check. `pcode_keyword` (tc-i51.c:1780) only checks
   keywords that end in a letter. `.equ SHL8X,0x1234` / `.pcode 0x200 SHL8X` assembles as `SHL8 X`
   (`02 00 80 55`).
2. The constant and symbolic forms of a swapped second pcode operand disagree (tc-i51.c:1944). The constant
   `.pcode 0x200 1,#SWAP 0x1234,2` is accepted and comes out identical to `#WORD 0x3412`, with no swap flag. The constant
   `@SWAP 0x12` comes out identical to `@WORD 0x12`. The symbolic `#SWAP X` is refused ("cannot be swapped").
3. `@BYTE` range: the constant `.pcode 0x200 @BYTE 0x100` is refused ("out of range: 256"). The same value
   through a forward `.equ K,0x100` is accepted and stored as `ff` (tc-i51.c:1942 compared with pcode_byte).
4. A numeric `.N` suffix binds to the whole preceding expression (i51_fold_bit_suffix runs after
   `i51_read_expression`, tc-i51.c:1026). The symbolic NAME.N binds to the name.
   With `.equ X,0x20`, `setb 1+X.1` gives `d2 02` but `setb 1+0x20.1` gives `d2 09`. `setb 0x20.1+1` is a junk
   error, and `setb 0x20 .1` (with white space) is accepted.
5. Wrong diagnostic: `setb 0x20.8` says "0x20.8: 0x20 is not bit addressable"
   (tc-i51.c:944-948). The byte is bit addressable; the bit number is out of range. The B2B path words this correctly.
6. Misleading diagnostic: i51_check_direct (tc-i51.c:1351) reports any symbol at or above 0x80 as RAM in the SFR
   page. For a code label (`.space 0x90` / `L1: mov L1,a`) or an xdata symbol it says "RAM there is reachable
   only through @R0/@R1". The same symbol below 0x80 passes gas, and ld then refuses it with the right reason.
7. A user common `__RB__` is silently hijacked. `.using 1` / `.xcomm __RB__,40` gives rc 0, and `__RB__` becomes a
   `.regbank` common of size 16 (tc-i51.c:1636 refuses only non-common definitions). The size, the space and
   the alignment the program gave are lost.
8. Ordinary `.comm` gets the generic ELF default alignment min(size,16) (elf.c), and so does `__RB__`
   (st_value 16). `.comm A1,1 / .comm B1,20 / .comm C1,3` puts B1 at 0x40 and leaves 0x25..0x55 for 24 bytes
   of data in the 128-byte direct RAM. Memory-space commons default to 1.
9. `i51_elf_section_from_shdr` (elf32-i51.c:736) turns any NOBITS section whose sh_flags carry one of the
   top three bits into a common section. That includes bit 31, which is also SHF_EXCLUDE (SHF_I51_IDATA == 0x80000000). Symbols
   defined in such a section disappear. With `.xbss` patched to sh_flags 0xa0000003, the result is
   `undefined reference to XB`. Nothing in the tree writes SHF_I51_*.
10. The output depends on the path: a direct link makes the RAM output sections PROGBITS and fills them with zeros (nm `D`). `ld -r`
    then `ld` makes them NOBITS (nm `B`). This is cosmetic. Each memory space adds its full size of zeros to the ELF file.
11. Still present from r7 #7: `ld ... -b binary blob` is refused ("initialized data in internal RAM").
12. Upstream, not the port. These are still present and hit 52 of 12,000 mutated objects:
    UBSAN `linker.c:3172` (shift exponent 32) and `elflink.c:10942` (1<<31) for a huge common alignment.
    The i51 SHN_I51_* commons reach them the same way that SHN_COMMON does.

## Verification of r7-quality findings
| r7 | Status |
|---|---|
| 1 `HIGH(sym)±c` and similar silently wrong | Fixed. Every form is refused ("have to be the whole operand"). `+0`/`-1+1` are accepted with correct values. Constant-operand folding is unchanged. |
| 2 `.org HIGH(fwd)` → 0 | Fixed. The operator is refused outside instruction and datum contexts. |
| 3 internal error (abort) | Fixed. Nested operators, `mov dptr,#HIGH`, `.pcode`, `.equ`, `.sleb128`, `.fill`, `.reloc`, `.if` and `HIGH-HIGH` now give clean errors. In 37.5k gas cases, no abort came from operators. |
| 4 `.xcomm` then `.comm` | Fixed for `.comm` in both orders. Residue: MEDIUM-1 (`.lcomm`, `.tls_common`) and HIGH-4 (across objects). |
| 5 per-file `__RB__` | Fixed. `as m1.s m2.s` and `as m2.s m1.s` both give size 0x20. |
| 6 `__RB__:` label assert | Fixed. Gives a clean error, but without a line number. A common `__RB__` is still accepted (LOW 7). |
| 7 `flags.10` | Fixed: "bit number 10 is not 0..7". |
| 7 R_I51_8 header comment | Fixed. |
| 7 huge `.rcomm` alignment | Fixed: "alignment too large", for local and global. |
| 7 `-b binary` | Not fixed (LOW 11). |
| 7 upstream UBSAN | Still present (LOW 12). |

## Checked clean
- Generic changes. `s_comm_internal` now skips `demand_empty_rest_of_line` after a failed parser. Every
  `comm_parse_extra` that returns NULL (elf, coff, mach-o, pe, arc, msp430, i51) has already ignored the line
  through `parse_align` or its own error path. The line after the error is now kept, as six probe lines showed.
  `bss_alloc` still does the MIPS/Alpha `.sbss` choice, then `bss_alloc_section`, and restores the subsection.
  `.symver`: `save_symbol_name` is applied to the version name only, `ver` still points into the
  original, and `@@@` duplicate detection works with folded names. Listing dummy frags: objects built with
  `-alsmgn` are byte-identical to those built without, over 12.5k gas fuzz cases plus 7.5k valid-program cases. The only
  diagnostic differences are the generic "same address redefinition" quirk under listings. `set_zero_frag` keeps
  the rs_dummy frag. readelf's EM_8051 predicates (NONE/8/16/32, RELA) are correct.
- The operator machinery: the `i51_read_expression` whole-operand test, `pending--` on nested operators, `nextcharP`
  restore in i51_parse_name (including quoted names), and the NAME.N strtol path.
- The ISA model check: 2,999 random instructions over all 113 table rows matched an independent Python encoder
  byte for byte after link.
- Constant, forward-equate and extern differential: 1,600 random (context × operator × value) triples
  covering imm, direct, bit, data, dptr, ljmp, cjne, jb and every `.pcode` mode. Apart from the documented
  "constant zero byte left out" pcode encoding, the only mismatches are the ones reported above.
- Disassembler: all 256 opcodes × lengths 1-3 and 200 random blobs up to 4 KB, through `objdump -b binary -m i51 -D
  --visualize-jumps=extended-color`, gave 0 sanitizer reports. `--adjust-vma` page and wrap handling was checked.
- Mutated ld locals with reserved and out-of-range `st_shndx` (0xff00-0xff3f, 0xfff1/2, 0xffff): handled.
- `.reloc` with every R_I51_* name, `-mmcu` errors, `-g/--gdwarf-5/--gstabs` with readelf `-wilrL`, objcopy and
  `--strip-unneeded` round trip of memory-space commons, and `ld -r` / `ld -d -r` then ld (same .text).

## Statistics
- gas grammar fuzz (garbage-heavy; `-mmcu`, `-g` variants; each case also run with `-alsmgn`): 15,000
  cases. 1 crash (HIGH-1), 0 sanitizer reports otherwise, 0 listing-induced object differences.
- gas valid-program fuzz: 7,500 cases, 3,272 of which assembled. Each went through `objdump -dr`, `objdump -D --visualize-jumps`, nm,
  `readelf -a -wi`, `ld -r`, `ld`, `ld --gc-sections`, and `ld -r`→`ld`, with the .text compared against a direct link.
  0 reports.
- ld structure-aware mutation (relocs, symbols, st_shndx, sh_flags/sizes, e_flags, byte flips; ld, ld -r,
  ld -r→ld, --gc-sections, objdump -dxr, nm, readelf, objcopy): 12,000 objects. 0 port findings. Only the
  upstream UBSAN cases in LOW 12 appeared.
- Disassembler: 968 inputs, 0 findings.

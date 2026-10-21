# MCS-51 (i51) port: binutils idioms, reuse, redundancy

This review covers conformance to binutils' own style and infrastructure. It does not cover UB or paperwork.
Paths are relative to the patched tree `work/modern/binutils-2.47`. Line numbers refer to that tree.
Sibling targets used for comparison: avr, msp430, z80, pru, mips (elfxx-mips scommon), obj-elf.

Findings are ranked by value, meaning bug-risk reduction plus size reduction. "−N" is the estimated number of lines removed.

---

## 1. bfd `elf32_i51_relocate_section` hand-rolls symbol resolution (HIGH; −60)
`bfd/elf32-i51.c:491-656`
- The relocatable-link branch (524-542) adjusts section-symbol addends by hand. Stock ELF targets set `#define elf_backend_rela_normal 1` and write `if (bfd_link_relocatable (info)) continue;` after resolution.
- The local-symbol path (557-568) computes `vma+output_offset+st_value` and so skips `_bfd_elf_rela_local_sym`. That makes SEC_MERGE and section-symbol addends wrong.
- The global path (569-603) open-codes the indirect/warning walk and treats undefined and common symbols as `relocation = 0`. Use `RELOC_FOR_GLOBAL_SYMBOL` instead (elf-bfd.h).
- `RELOC_AGAINST_DISCARDED_SECTION` is missing, yet `elf_backend_can_gc_sections 1` is set (1153). With `--gc-sections` (or COMDAT), relocs against discarded sections are applied against garbage instead of being zeroed.
- The same function body exists in `elf32-avr.c:1400-1460` and `elf32-msp430.c:1440-1490`; copy it.
- Range errors from R_I51_8_B2B and R_I51_13_PCODE are returned as `bfd_reloc_outofrange` (426-449). The user then sees "internal error: out of range error" (626). Use `bfd_reloc_dangerous` or `bfd_reloc_overflow` (or `_bfd_error_handler` with a real message), as avr does for its alignment errors.

## 2. The memory-space table is encoded 7 times in bfd and gas (HIGH; −250)
The same {space name, SHN_I51_*, fake common section} triple is spelled out separately in each of these places:
- `bfd/elf32-i51.c:735-770`: `section_from_bfd_section`, a strcmp chain.
- `bfd/elf32-i51.c:774-933`: `symbol_processing`, 7 static section/symbol/ptr triples plus 7 copy-pasted 17-line init blocks. The `*_symbol_ptr` variables are written and never read.
- `bfd/elf32-i51.c:969-983`: `i51_elf_space_name`, a switch.
- `bfd/elf32-i51.c:1109-1122`: `link_output_symbol_hook`, a strcmp chain again.
- `gas/config/tc-i51.c:384-417`: 7 groups of statics.
- `gas/config/tc-i51.c:577-639`: 7 copy-pasted 8-line fake-common inits in `md_begin`.
- `gas/config/tc-i51.c:2378-2400`: a switch.

**Fix:** keep one `static const struct { const char *name; unsigned shndx; } i51_spaces[]` per side, plus arrays `asection i51_com_sec[N]; asymbol i51_com_sym[N];`. Init them in a loop.

**Reference:** `elfxx-mips.c` (`mips_elf_scom_section`, `_bfd_mips_elf_symbol_processing`, `_bfd_mips_elf_section_from_bfd_section`) handles the one-space case. Generalize it with a table instead of copy-pasting it 7 times. This also removes the risk of the 4 bfd mappings drifting apart.

## 3. gas `i51_common` reimplements `s_comm_internal` and `bss_alloc` (HIGH; −150)
`gas/config/tc-i51.c:2167-2407`
- Lines 2176-2246 hand-parse name, size, redefinition and alignment. `read.c:s_comm_internal (param, parse_extra)` (`read.h:168`) does exactly that and calls back with the symbol and size. obj-elf's `elf_common_parse` is the model callback.
- Lines 2257-2369 are 7 byte-identical 16-line cases that differ only in the section variable. Each is a copy of `read.c:bss_alloc` (2611) with `bss_section` replaced. Replace them with one `i51_space_alloc (segT, sym, size, align)` helper taken from `bss_alloc`, or generalize `bss_alloc` to take a segment.
- The power-of-2 loop (2237) duplicates `exact_log2`/`log2` from read.c.

## 4. Overriding the standard obj-elf/read.c pseudo-ops changes their meaning (HIGH; small diff)
`gas/config/tc-i51.c:72-109`
- `.local` (75) replaces `obj_elf_local` (obj-elf.c:86, ELF "make symbol STB_LOCAL") with "delete a built-in register name from the operand hash". Any producer that emits ELF `.local` gets silently different behaviour. Rename it (for example `.unreg`/`.noreg`).
- `.comm` and `.common` (83-84) shadow obj-elf `elf_common` and lose its ELF semantics. `.common` also normally means `s_mri_common`.
- `.bss` (93) shadows `obj_elf_bss`.
- `.equ` and `.set` (76-77) map to `s_set`, which read.c potable (403, 482) already does. They are redundant entries.

## 5. Global mutable parse state and duplicated operand parsers (HIGH; −200)
`gas/config/tc-i51.c:355-381`
- 20+ non-static globals are exported from `tc-i51.o` (verified with `nm`). They include generic names that can collide with gas symbols: `line`, `op`, `opcode`, `oper`, `regno`, `op_expr1..4`, `op1mode`, `op2mode`, `op1hlmode`, `b2b_offset`, `regbank`, `p1..p4mode` (p1mode is never used).
- `md_undefined_symbol` (1106-1108) carries a comment warning that re-entrancy through `expression()` would clobber them.
- `i51_parse_operand1` (1178-1321) and `i51_parse_operand2` (1323-1512) are about 80% the same code. The B2B(...) argument parser appears twice verbatim (1255-1280 and 1412-1437). HIGH/LOW prefix scanning appears 5 times (1201, 1218, 1349, 1378, 2016).
- Opcode selection walks `opcode++` from inside the operand parsers and stops on an in-band "last row of this mnemonic" flag, 0x80 in `insn_size` (`include/opcode/i51.h`). The disassembler has to mask this flag off again (`i51-dis.c:162`, `& 0x03`).

**Idiom to follow** (tc-avr.c `md_assemble` → `avr_operands`; tc-msp430.c): parse each operand once into a local `struct i51_operand { kind; reg; expressionS exp; int prefix; int b2b; }`. Then iterate the rows that share the mnemonic (`strcmp (opc->name, name) == 0`) and match their arg letters. The 0x80 flag and the order-dependent table walk both go away.

## 6. Range checking bypasses gas's fixup-overflow machinery (MED-HIGH; −60)
`gas/config/tc-i51.c`
- `md_apply_fix` (846-851) sets `fx_no_overflow = 1` on every fixup through a one-case `switch`. That disables `write.c:fixup_segment`'s generic `fx_size`/`fx_signed` overflow check.
- The checks are then re-implemented per reloc (866-886), again in `check_range` (1676-1706, where JUMP_INPAGE and IMM16 are identical cases), and again in fixup8/11/16 and `decodePcodeOperand` (3 copies of the same message).
- Constants go through a custom path in `fixup8` instead of `fix_new_exp` plus `md_apply_fix` (the avr and msp430 pattern; in avr's case `avr_operand`→`fix_new_exp`, with the range applied in `md_apply_fix`).
- Simplification: create fixups with `fx_signed` set correctly and let write.c complain. Keep explicit checks only for -128..255 (IMM) and the 2K page.
- Dead code: the empty `switch` at 958-962.

## 7. bfd relocations that the howto machinery already handles (MED; −25)
`bfd/elf32-i51.c:382-394, 460-465`
- R_I51_7_PCREL is the stock signed 8-bit PC-relative case. Use HOWTO bitsize 8, `complain_overflow_signed`, `pcrel_offset true`, dst 0xff, and send it to `_bfd_final_link_relocate` as avr/msp430 do for their pcrel relocs. Today the howto says `complain_overflow_bitfield` and the code ignores it.
- R_I51_16 is exactly what the generic path writes (big-endian bfd, 16-bit, mask 0xffff). Delete its case.
- Once those two go, the custom `bfd_reloc_offset_in_range` prologue (365-378) only has to cover 11/B2B/PCODE.

## 8. Bit-address, 11-bit-page and pcode encodings duplicated across gas and bfd (MED; −40)
- The bit-address fold (0x20-0x2f → n·8+b, and SFR 0x80-0xf8 with `&7==0`) is written 4 times: `tc-i51.c:465-470`, `:1816-1829`, `:929-936` and `elf32-i51.c:423-438`. Comments on each say "Mirrors ...".
- AJMP/ACALL insertion appears at `tc-i51.c:896-914` and `elf32-i51.c:396-412`. The 13-bit pcode field appears at `tc-i51.c:940-948` and `elf32-i51.c:441-458`.
- Put `static inline` encoders in `include/opcode/i51.h` or `include/elf/i51.h`, as `include/opcode/avr.h` does with its `AVR_DISP0_P` etc. helpers, and share them. All the magic constants become named.

## 9. Directive boilerplate: 13 identical section-switch functions (MED; −110)
`gas/config/tc-i51.c:2409-2545` and the 13 prototypes at 40-53
- `i51_rbss` … `i51_eeprom` differ only in name, static and flags.
- Replace them with one `i51_space (int idx)` that takes `md_pseudo_table` arg = index into the table from #2. obj-elf.c (`obj_elf_section` and its siblings) and tc-msp430.c (`msp430_section`) parametrize the same way.
- Several of these are declared `static` and then defined without `static`.

## 10. Disassembler ignores branch-target plumbing and repeats itself (MED; −80)
`opcodes/i51-dis.c`
- Relative branch targets ('J', three copies at 200-216, 286-302 and 328-344) are printed only as a `; 0x0000` comment string. They should go through `info->print_address_func`, as avr-dis.c:484-489 does for its comment addresses, so objdump shows `<label>`.
- `info->insn_type` and `info->target` are never set. avr-dis.c:183-212 sets them, and they feed `objdump --visualize-jumps`. Only '1' and '6' use print_address_func (366).
- The 1-byte fetch-and-check pattern appears 9 times; one `fetch` helper with an early `return -1` would cover it.
- The MOV dir,dir swap is done with strcpy temp buffers (272-278).
- Fixed register strings are built with `sprintf` (168-183, 240-260). Use a table, or print directly with `dis_style_register`.
- Upper-case hex (`0x%02X`) is used where binutils disassemblers use lower case.
- `#include <assert.h>` is unused. `comment2` is never set.

## 11. `md_atof` hand-rolled (LOW-MED; −45)
`gas/config/tc-i51.c:972-1019`. Replace with `return ieee_md_atof (type, litp, sizep, true);` (atof-ieee.c:744), as tc-avr.c, tc-pru.c and most targets do.

## 12. Chip-specific SFR/bit table compiled into the assembler (MED, design; −190)
`gas/config/tc-i51.c:157-348`
- The table includes AT89S8252-only registers (DP1L, SPDR, WMCON, SPCR, SPSR). It is materialised lazily through `md_undefined_symbol` (1103-1128), which re-parses and upper-cases the name, and it is made removable through the `.local` hack (#4).
- Binutils targets keep only architectural register names in gas. Per-chip I/O names belong in include files (avr: avr-libc `ioXXX.h`; msp430: `msp430*.h`/linker `.ld` symbols).
- Suggestion: keep A, AB, Rn, @Ri, C, DPTR and the 8051 core SFRs, and move the rest to an `.inc` file that `.include` pulls in. The `'U'` ARn mode stays. If predefined absolute symbols are still wanted, create them once in `md_begin` with `symbol_new` instead of on the miss path.

## 13. Dead or vestigial code and relocation types (LOW-MED; −80)
- **Relocations never produced:** R_I51_R1 and R_I51_R3 (`elf32-i51.c:54-82`, map 269-270), plus `BFD_RELOC_I51_R1`, `_R3`, `BFD_RELOC_I51_8` and `BFD_RELOC_I51_16` in `bfd/reloc.c:4488-4520`. The last two are parallel to the BFD_RELOC_8/16 that gas actually uses. Keep the ELF numbers reserved (`EMPTY_HOWTO`) and drop the four unused BFD_RELOC enums.
- **No-op backend hooks:** `elf32_i51_object_p` (660), `i51_elf_fake_sections` (707, a 12-line comment around `return 1`) and `elf32_i51_check_relocs` (339). The defaults do the same, so delete them. Also delete the forward-declaration block (28-36); every definition already precedes its use.
- **tc-i51.h macros:**
  - `MD_APPLY_FIX3` (98) is obsolete and nothing reads it.
  - `md_after_pass_hook` (176) is not referenced anywhere in gas. Only `md_cleanup` is called (read.c:1442).
  - `#define md_operand(x)` is empty.
  - `TARGET_MACH 0` is the default.
  - There are 7 commented-out `//#define` lines (51-52, 112, 114, 127, 162, 165).
  - About 90 lines of comments are copied verbatim from the gas internals manual.
- **tc-i51.c:**
  - 8 `#ifdef ASMDBG` stderr blocks plus the `//#define ASMDBG`.
  - The VTABLE branch in `tc_gen_reloc` (1166-1168); the port has no VTABLE relocs.
  - Unused `opmode` params on fixup11/fixup16, and fixup11's `mode` switch with a single case.
  - `#include <stdio.h>` (as.h already includes it).
  - The `p1mode` global.
  - `md_show_usage` printing "A51 options: NONE".
- **Opcode table:** the "OPCODE" bit-pattern string column in `include/opcode/i51.h` is consumed by nobody (both I51_INS expansions drop it). The 'i' mreloc is documented but unused.

## 14. Special sections declared in gas instead of bfd (LOW-MED)
- `tc-i51.h:131-155` uses `ELF_TC_SPECIAL_SECTIONS`, which only gas sees. The binutils-wide mechanism is `elf_backend_special_sections` (a `bfd_elf_special_section[]` in elf32-i51.c), which gas, ld, objcopy and readelf all share. See elf32-avr.c and elf32-m68hc1x.c.
- `.bitdata` and `.eeprom` are created by gas directives, but `.bitdata`/`.bitbss` are missing from the table.

## 15. ld side (LOW-MED)
- **`ld/scripttempl/elf32i51.sc:21`:** `test -z "${RELOCATING}" && exit 0` generates an empty `-r`/`-Ur` script (`elf32i51.xr` is 20 bytes, verified). `ld -r` therefore runs with no script at all: no /DISCARD/, and orphan placement for the debug sections. Every other template wraps the address parts in `${RELOCATING+...}` and still emits the section list.
- **Same script, lines 226-255:** the DWARF and stabs lists are hand-copied, and they lack DWARF5 sections (.debug_addr, .debug_rnglists, .debug_loclists, .debug_str_offsets, .debug_line_str). Use `source_sh $srcdir/scripttempl/DWARF.sc` plus `${STACKNOTE}`, as elf32msp430.sc, avr.sc and elf32cr16.sc do.
- **Page size:** `ELF_MAXPAGESIZE 1` (`elf32-i51.c:1129`) contradicts `MAXPAGESIZE=0x0800` (`emulparams/elf32i51.sh`). `TEXT_START_ADDR` is unused by the custom script.
- **`bfd/cpu-i51.c`:** section alignment power 1 on a byte machine. avr, z80 and msp430 use 0 or 1 according to their code alignment, and the 8051 has no alignment, so it should be 0.
- **Template choice:** `TEMPLATE_NAME=generic` with `EXTRA_EM_FILE=genelf` is conventional for ELF MCUs without a custom em (moxiebox, ft32, msp430elf use it), so this is fine. There is no custom em, which is good.

## 16. Header naming and magic letters (LOW)
- **`include/elf/i51.h`:** `SHF_CDATA`, `SHF_REGBANK`, `SHF_RDATA` etc. lack the arch prefix. Every other target uses `SHF_<ARCH>_*` (SHF_MIPS_GPREL, SHF_ARM_PURECODE). `SHF_RDATA` in particular is generic enough to collide. `EF_I51_ABI_MASK` is defined but never used.
- **`include/opcode/i51.h`:** has no license header. Args letters ('A','R','#','J','1','6',...) and mreloc letters are bare chars compared in three files (tc-i51.c, i51-dis.c, tb). Named enums or `#define`s with the struct defined in the header would follow `include/opcode/avr.h`, which defines the constraint letters' meaning next to its `AVR_INSN` X-macro.
- **pcode flag bits** (`tc-i51.c:2735-2857`: 0x40, 0x80, 0xC0, 0x02, 0x8000 and the shifts) are unnamed.

## 17. Style nits (grouped; LOW)
- About 48 C++ `//` comments in tc-i51.c and 7 in tc-i51.h.
- 10 `switch (...) {` same-line braces in tc-i51.c and 3 in i51-dis.c. Single-line `if (...) stmt;` forms, e.g. tc-i51.c:1113, 1291, 2104.
- Missing space before `(` in roughly 30 places: `if(`, `fixup11(`, `read_memory_func(`, `bfd_getb16(`.
- 9 lines with trailing whitespace in tc-i51.c and 2 in i51-dis.c. About 30 lines over 79 columns.
- Broken indentation in `i51_cleanup` (2117-2124).
- camelCase names: `pcodeOperand`, `writePcodeOperand`, `decodePcodeOperand`, `enum PADRMODE`.
- Functions and data that should be `static` but are not: `i51_build_ins`, `i51_parse_operand*`, `i51_common`, `i51_directop`.
- `return 0`/`return 1` from `bool` functions (`elf32-i51.c:329-332, 663, 676, 691, 712, 729-770, 1072-1082`).
- Needless casts: `(char *) opc` into `str_hash_insert`, `(struct ... *) str_hash_find`, `(symbolS *) NULL`. `xmalloc (sizeof (arelent))` should be `XNEW (arelent)`; the same applies to `sym_ptr_ptr`.
- The ASCII line-end test `'\x0D'`/`'\x0A'` (2569) should be `is_end_of_stmt`/`is_it_end_of_statement ()`. `skip_space` duplicates `SKIP_WHITESPACE`/`skip_whitespace`.
- `number_to_chars_bigendian (f, x, 1)` is used about 20 times for single bytes. `*f = x` or `md_number_to_chars` is enough, and the opcode byte emit repeats in 10 cases of `i51_build_ins` (1604-1672); hoist it above the switch.
- Comments that narrate history rather than state rules: "The old test asked…" (1683), "used to take the second arm" (1810), "turned one bad bit address into three diagnostics" (461), the R_I51_8 paragraph in include/elf/i51.h, and the `add_symbol_hook` essay (`elf32-i51.c:1046-1061`). Binutils style keeps history in ChangeLog or commit messages.

---

## Totals
About 1,300 removable lines out of about 5,200 in the port. In order of size:
- 250 for the space tables (#2)
- 200 for the operand parser and globals (#5)
- 190 for the SFR table (#12)
- 150 for common/bss_alloc (#3)
- 110 for directive boilerplate (#9)
- 80 dead code (#13)
- 80 disassembler (#10)
- 60 relocate_section (#1)
- 60 range checks (#6)
- the rest from smaller items

The highest bug-risk reductions are #1 (gc-sections / merge-section correctness), #4 (pseudo-op semantics) and #2 and #8 (drift between copies).

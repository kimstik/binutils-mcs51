# MCS-51 (i51) port, review 7: idioms, reuse, redundancy

Lane: whether the code follows binutils idioms, reuses existing infrastructure, avoids redundancy and anti-patterns, and keeps to GNU style. This review covers the current code on `claude/r6-fixes`.

- Paths are relative to `work/modern/binutils-2.47` (the tree patched to HEAD). Line numbers refer to that tree.
- Siblings used for comparison: avr, msp430, z80, pru, rl78, mips, obj-elf.
- "−N" is the estimated number of lines removed.
- r6-status.md was not trusted. Every claim below was checked in the code. Where a test was needed, the built `as-new` was run.

## Part A: the 17 items of r6-idioms-reuse.md

| # | item | status | evidence (current code) |
|---|------|--------|-------------------------|
| 1 | relocate_section hand-rolls symbol resolution | **done** | elf32-i51.c:613-642: `_bfd_elf_rela_local_sym`, `RELOC_FOR_GLOBAL_SYMBOL`, `RELOC_AGAINST_DISCARDED_SECTION`, `if (bfd_link_relocatable) continue`. `elf_backend_rela_normal 1` is at :1109. `bfd_reloc_outofrange` now only means "outside section" (:663). |
| 2 | space table written 7 times | **partial** | One table per side: gas `i51_spaces[]` tc-i51.c:400-420; bfd `i51_common_spaces[]` elf32-i51.c:824-837. Fake commons are built in a loop (tc-i51.c:584; elf32-i51.c:902-912). Left over: (a) a **third** list of the same names, `i51_section_spaces[]` elf32-i51.c:373-399; (b) gas `.regbank` is still a separate pair of statics (tc-i51.c:432-433, 582); (c) `link_output_symbol_hook` (:1075-1077) repeats `i51_common_by_section`'s strcmp loop; (d) nothing is shared through include/elf/i51.h. |
| 3 | `i51_common` reimplements s_comm_internal/bss_alloc | **partial** | `s_comm_internal` is used (tc-i51.c:2018). Still present: the power-of-2 loop at :1972-1982, which duplicates `parse_align()` (read.h:167, used by `elf_common_parse`), and `i51_alloc_local` :1922-1945, a line-for-line copy of `bss_alloc` (read.c:2611) with a segment substituted. |
| 4 | standard pseudo-ops overridden | **mostly done** | `.local`, `.bss`, `.equ` and `.set` are no longer overridden. `.comm` and `.common` (:69-70) still are, and both reach `elf_common_parse` through the special case `I51_BSS` (:1969-1970). That is obj-elf's `obj_elf_common` (obj-elf.c:82-83, 311) minus its MRI branch, so it is redundant and slightly lossy. |
| 5 | global parse state, duplicated operand parsers, 0x80 flag | **mostly done** | No exported data (verified with `nm -g`). There is one `struct i51_operand` parser (:861) and row matching by name (:1016). Left over: the in-band 0x80 "last row" flag is still in every `insn_size` of include/opcode/i51.h (e.g. :64, `0x82`). It is now read by nobody, and both consumers still mask it off (tc-i51.c:1139; i51-dis.c:135, 137, 154). There is also a static side channel, `i51_operator_class` (:363), which `i51_apply_operator` writes and `i51_parse_operand` reads. |
| 6 | range checks bypass the fixup machinery | **not done** | `fx_no_overflow = 1` is unconditional (:1200). Constants still skip fixups in `fixup8`/`fixup16` (:1676-1687, :1758-1764) and go through `check_range` (:1561-1585). That gives **two range tables for the same fields**, and they already disagree (see B1). |
| 7 | relocs the howto machinery handles | **done** | R_I51_7_PCREL goes to `_bfd_final_link_relocate` with `complain_overflow_signed` (:58-70, :570-573). The custom R_I51_16 and R_I51_16_CODE cases are justified: with `bits_per_address` 16, `bfd_check_overflow` masks a 16-bit field to nothing (comment :562-564 is correct). |
| 8 | bit-address/AJMP/pcode encoders duplicated gas↔bfd | **partial** | Within gas they are folded into `i51_bit_address` (tc-i51.c:451). bfd still re-derives it (elf32-i51.c:519-522). The AJMP field is written twice (tc-i51.c:1746-1747; elf32-i51.c:511-512), and the 13-bit pcode field 3 times (tc-i51.c:1299-1308, 2281-2288; elf32-i51.c:529-532). Nothing is in include/. |
| 9 | 13 section-switch functions | **done** | One `i51_space (int)` (:1907), table-driven (:83-95). |
| 10 | disassembler | **partial** | Done: `insn_type`/`target` set (i51-dis.c:142-144, 324-332); one fetch (:134-138); `assert.h` dropped. Not done: 'J' targets are still `"0x%04lX"` comment strings (:202, 280, 318), copied 3 times, and not passed to `print_address_func`; there are 28 `sprintf (opN,"<fixed>")` calls; the strcpy swap remains (:256-259); hex is upper case; `comment2` is never set (:150, 341, 379). |
| 11 | `md_atof` | **done** | `ieee_md_atof` (:1326). |
| 12 | chip SFR table compiled in | **not done** | Table at :150-342, still with the AT89S8252-only registers DP1L/DP1H/SPDR/WMCON/SPSR/SPCR (:186-212). Only the lookup changed, to `md_parse_name`. |
| 13 | dead code | **partial** | Removed: object_p, fake_sections, check_relocs, the forward-decl block in bfd, `BFD_RELOC_I51_R1/R3/8/16`, MD_APPLY_FIX3, md_after_pass_hook, ASMDBG, stdio.h, p1mode. Still present: R_I51_R1 and R_I51_R3 as full HOWTOs instead of `EMPTY_HOWTO` (elf32-i51.c:46-52); VTABLE branch in `tc_gen_reloc` (:1416-1418); `md_show_usage` "A51 options: NONE" (:521-523); `TARGET_MACH 0` (tc-i51.h:26); the OPCODE bit-string column in the opcode table, read by nobody; mreloc `'i'` (no table row uses it, yet `i51_build_ins` has cases for it at :1468 and :1492); manual-copied comments (:1161-1165, :1386-1391). |
| 14 | special sections in gas | **done (by removal)** | ELF_TC_SPECIAL_SECTIONS was dead upstream. Commit e9b821f explains why nothing was added to bfd. Acceptable. |
| 15 | ld side | **partial** | Done: DWARF.sc is sourced (elf32i51.sc:252); emulparams no longer sets a page size. Not done: `test -z "${RELOCATING}" && exit 0` (:21) still produces a 20-byte `.xr`/`.xu` (verified in build/ld/ldscripts); `TEXT_START_ADDR` is unused (elf32i51.sh:5); cpu-i51.c:35 still has alignment power 1. |
| 16 | header naming, magic letters | **partial** | `SHF_I51_*` done; opcode header has a licence. `EF_I51_ABI_MASK` is still unused and now carries a 14-line essay (include/elf/i51.h:95-110). Arg and mreloc letters are still bare chars. pcode flag bits (0x40, 0x80, 0x02, 0x8000, 0xe000, shifts at tc-i51.c:2204-2275) are unnamed. |
| 17 | style | **partial** | Done: `//` comments gone; trailing whitespace down to 1 line; every non-hook function is static. Left: `i51_cleanup` indentation (:1849-1862); `return 0/1` from bool functions (elf32-i51.c:737, 752; `check_range` returns int used as bool); 8 casts on str_hash/xmalloc/NULL (:576, 580, 603, 1021, 1170, 1401, 1403, 1408), with `xmalloc` where `XNEW` belongs; `skip_space` duplicates `is_whitespace`/`SKIP_WHITESPACE` (:438); the opcode byte emit is repeated 9 times in `i51_build_ins`; `enum PADRMODE` with unprefixed enumerators; the opcode tables are non-const (tc-i51.c:144, i51-dis.c:41), although commit e314f63 says otherwise; history-narrating comments **grew** (see B6). |

**Tally: done 5 (1, 7, 9, 11, 14) · mostly done 2 (4, 5) · partial 8 (2, 3, 8, 10, 13, 15, 16, 17) · not done 2 (6, 12).**

## Part B: new findings in the current code, ranked by value

### B1. Two range tables for one operand already disagree (HIGH: bug; −45)
Constants are checked by `check_range` (tc-i51.c:1561). Symbols are checked by `md_apply_fix`/`i51_fix_range` (:1239-1309). The two do not agree:

- `fixup16` checks every 16-bit constant as IMM16 (-32768..65535, :1760).
- `md_apply_fix` checks BFD_RELOC_I51_16_CODE as 0..65535 (:1273).

Verified with the built `as-new`:
- `ljmp -1` and `lcall -2` assemble silently, to `ljmp 0xffff`.
- `.equ X,-1` followed by `ljmp X` is rejected ("operand out of range: -1").

There are more copies of the same rules:
- HIGH's 16-bit check: 3 copies (:698, :1246, bfd :550).
- The B2B diagnostics: 3 copies (:706-711, :1285-1293, bfd :515-524 plus :671-684).
- The pcode exec range: 3 copies (:1299-1306, :2281-2286, bfd :529).

**Facility:** follow the avr/pru pattern and always `fix_new_exp`, even for constants. `md_apply_fix` already finalises a fixup with no symbol (`fx_done`, :1209-1211), so it becomes the single gas range check. This deletes `check_range`, `i51_arg_kind`, `I51_OP_*`, and the constant branches of `fixup8`/`fixup16`. `I51_OP_JUMP_INPAGE` (:105) is already dead.

### B2. `i51_build_ins` re-derives what the parser already knew (MED; −35)
`i51_assemble` flattens `ops[]` into `exprs[2]` plus `regno` (:1119-1136). `i51_build_ins` then rebuilds each operand's kind from `opc->args` through `i51_arg_kind` and the kind1/kind2 swap (:1452-1462).

**Fix:** pass `ops`/`nops` and index `opc->args[i]` directly. Also:
- Emit the opcode byte once above the switch (9 copies, :1487-1549).
- Drop the dead `'i'` cases.

### B3. Space knowledge lives in three name lists across two programs (MED; −30)
- gas `i51_spaces` (:400).
- bfd `i51_common_spaces` (:824).
- bfd `i51_section_spaces` (:373).
- `.regbank` is special-cased in both gas (:432, :582) and bfd (:379, :830).

**Fix:** one X-macro list in include/elf/i51.h holding {name, SHN_I51_*, space kind, bss/data}, expanded on each side. Make `.regbank` an ordinary table entry in gas, and have `link_output_symbol_hook` call a by-name helper.

### B4. bss_alloc and parse_align copied instead of called (MED; −25)
- `i51_common_parse` alignment (:1972-1982) is `parse_align (symbol_get_obj (sym)->local)`.
- `i51_alloc_local` (:1922-1945) is `bss_alloc` with the segment swapped. Upstream route: give `bss_alloc` a segment-taking sibling.
- Deleting the `.comm`/`.common` entries (:69-70) and the I51_BSS special case (:1969, :1883-1884, :406) lets obj-elf handle plain commons, MRI branch included.
- `i51_common_error` (:1955-1961) exists only because the hand-rolled parser cannot use `parse_align`'s own error path.

### B5. Bit-address, AJMP and pcode encoders belong in a shared header (MED; −20)
This is item 8's remainder. include/opcode/i51.h is a bare X-macro table with no include guard, so it cannot hold helpers. Move the table into an `i51-opc.h`-style guarded header that has `static inline i51_bit_address()`, `i51_put_ajmp()` and `I51_PCODE_*` masks (avr.h is the model). bfd then uses the same `i51_bit_address` (elf32-i51.c:519-522).

### B6. Comments narrate history (LOW-MED; −80 comment lines)
Binutils keeps history in ChangeLog and commit messages. Examples:
- elf32-i51.c:106-110 ("as this entry's src_mask once made…"), :156-158, :535-541 ("Objects of that age…"), :961-965 ("this port's lineage… work today"), :1016-1031 (the add_symbol_hook essay, still there), :1089-1099 (an 11-line justification).
- include/elf/i51.h:27-51 (a byte-order essay citing "the 2001 original"), :53-75 ("before 14 existed"), :95-108, :140-151.
- tc-i51.c:2022-2025 ("a plain prefix match took the BYTE out of…").

State the rule and drop the story.

### B7. Redundant backend and gas macros (LOW; −20)
- `elf_backend_may_use_rel_p`, `_may_use_rela_p`, `_default_use_rela_p` and `elf_info_to_howto_rel NULL` (elf32-i51.c:1100-1105) are exactly the elfxx-target.h defaults when USE_REL is 0 (elfxx-target.h:351, 719-727). Delete them with their comment.
- tc-i51.h:84-85: `#undef`/`#define LOCAL_LABELS_DOLLAR 0` is the as.h:681 default.
- tc-i51.h:26: `TARGET_MACH 0` is the default.

### B8. Disassembler (LOW-MED; −60)
- `print_insn_i51` is 285 lines.
- Make 'J' one helper that calls `print_address_func` (this also fixes objdump `<label>` for sjmp/jz/djnz/cjne).
- The `print_address_func != NULL` guard and its "older callers" comment (:351-357) are dead, because the hook is always set.
- The `insn_type` test `opcode->name[1] == 'c'` (:331) is a magic letter.
- Use a register-name table instead of 28 sprintf calls.
- 8 same-line braces (`switch (...) {`, `if(...) {`, `} else {`) and 1 trailing-whitespace line (:145).

### B9. Trivial nits (counts)
- 2 lines over 79 columns in tc-i51.c (:512, :1381).
- `pseudo_table` spacing is mixed (`{ "bitcommon",i51_common,` at :82).
- `char name[11]` magic size (:1053).
- The `regbank` sentinel `0xFF` and `regused+8` (:356, :1854) are unnamed.
- The `/* forward declaration */` block (tc-i51.c:27-38) could shrink by ordering definitions before use. Only `fixup8`, `fixup11`, `fixup16`, `i51_check_direct` and the pseudo-op handlers need it.
- The alias special case `strcasecmp (name, "call")` (:1112) duplicates `i51_aliases`.

## Size
About −300 code lines and −80 comment lines are available.

Highest value:
- **B1**, a real gas bug (`ljmp -1` accepted) caused by duplicated range logic.
- **B3** and **B5**, which remove the risk of gas and bfd drifting apart.
- **Item 15's `-r` script**: an empty `ld -r` script.

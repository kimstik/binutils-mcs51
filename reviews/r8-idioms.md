# MCS-51 (i51) port, review 8: idioms, reuse, redundancy

- Lane: is the code organic to binutils (idioms, reuse, no redundancy, GNU style, comments that state rules)?
- Paths are relative to `work/modern/binutils-2.47`. Line numbers refer to the current tree (`git diff HEAD`).
- "−N" is the estimated number of lines removed.
- Every status below was checked in the code. Where a check needed it, the built `as-new`, `objdump` or `readelf` was run.

## Part A: r7 items, re-checked

### A.1 r7 Part A (the 17 items)

| # | item | status | evidence |
|---|------|--------|----------|
| 1 | relocate_section symbol resolution | **done** | elf32-i51.c:605-634 uses `_bfd_elf_rela_local_sym`, `RELOC_FOR_GLOBAL_SYMBOL`, `RELOC_AGAINST_DISCARDED_SECTION` and `bfd_link_relocatable … continue`. `rela_normal` is at :1080. |
| 2 | space table written several times | **mostly done** | The common spaces are one X-macro, `I51_COMMON_SPACES` (include/elf/i51.h:93-100), expanded in gas (tc-i51.c:476-483) and in bfd (elf32-i51.c:813-822). `.regbank` is an ordinary entry, and `link_output_symbol_hook` calls `i51_common_by_section` (:1025). **Left:** bfd's `i51_section_spaces[]` (elf32-i51.c:371-397) is a second name→space list beside gas's `i51_spaces[]` (tc-i51.c:449-469). See B5. |
| 3 | `bss_alloc`/`parse_align` copied | **done** | Uses `parse_align (1)` (tc-i51.c:1711) and the new `bss_alloc_section` (tc-i51.c:1724; read.c:2643). |
| 4 | standard pseudo-ops overridden | **done (justified)** | Only `.comm` and `.common` are still overridden (tc-i51.c:98-99). The plain case goes to `elf_common_parse` (:1706-1707). The override exists so that one name cannot be a common of two spaces (:1699-1705, comment :1738). The MRI branch of `obj_elf_common` is lost, which does not matter for i51. |
| 5 | parse state, 0x80 flag | **mostly done** | The 0x80 "last row" flag is gone (include/opcode/i51.h:50-160 holds plain sizes). **Left:** the side channel `i51_operator_class` (tc-i51.c:392). `i51_apply_operator` writes it (:718), `i51_parse_operand` reads it (:1027, :1034), and `i51_read_expression` resets it (:904). |
| 6 | range checks bypass fixups | **done** | Every operand field goes through `fix_new_exp` (tc-i51.c:1110-1158), and `md_apply_fix` makes the one range check (`i51_check_range` :1361, table :428-442). Verified: `ljmp -1`, `lcall -2` and `.equ X,-1; ljmp X` are now all rejected with "code address out of range". **Left:** the constant `.pcode` address (B4). |
| 7 | relocs the howto machinery handles | **done** | Unchanged. The custom R_I51_16_CODE case keeps its correct comment (elf32-i51.c:553-560). |
| 8 | encoders duplicated between gas and bfd | **done** | `i51_bit_address`, `i51_addr11_insn` and the `I51_PCODE_*` masks are in include/elf/i51.h:102-131. gas uses them (tc-i51.c:742, 944, 1150, 1451, 1464-1473) and so does bfd (elf32-i51.c:509, 515, 522-525). |
| 9 | 13 section-switch functions | **done** | One table-driven `i51_space` (tc-i51.c:1680). |
| 10 | disassembler | **done** | i51-dis.c was rewritten (251 lines). It uses styled output and `print_address_func` for J/1/6 targets (:163-174), has no sprintf and no strcpy swap, uses lower-case hex, sets `insn_type` without magic letters (:180-191), and prints `.byte` for an unknown opcode (:216-225). |
| 11 | `md_atof` | **done** | `ieee_md_atof` (tc-i51.c:1554). |
| 12 | chip SFR table compiled in | **done (different fix)** | The table remains, but each entry carries an MCU mask and `-mmcu` selects the set (tc-i51.c:59-75, 509-523, 573). This is documented in NEWS and the manual. Acceptable. |
| 13 | dead code | **done** | R_I51_R1 and R_I51_R3 are `EMPTY_HOWTO` (elf32-i51.c:50-51). Gone: the VTABLE branch, `TARGET_MACH`, the OPCODE bit-string column and the mreloc `'i'`. `md_show_usage` is real (:499-506). **New dead definitions:** see B3. |
| 14 | special sections | **done** | Unchanged. |
| 15 | ld side | **mostly done** | `TEXT_START_ADDR` is gone (emulparams/elf32i51.sh). cpu-i51.c:37 has alignment power 0. The `-r` script is no longer empty (build/ld/ldscripts/elf32i51.xr is 2450 bytes). **Left:** the `-r` script is a separate 30-line heredoc (elf32i51.sc:17-46) that repeats the section list. Other scripttempls use the `${RELOCATING+…}`/`${RELOCATING-0}` idiom inside one script. `MACHINE=` (elf32i51.sh:7) is a no-op. |
| 16 | header naming, magic letters | **mostly done** | `EF_I51_ABI_MASK` is now used (elf32-i51.c:999, 1053), and its essay is down to 5 lines (i51.h:56-60). The pcode flag bits are named (tc-i51.c:1752-1755). Operand letters are still bare chars, but they are documented once (include/opcode/i51.h:28-45). Acceptable. |
| 17 | style | **mostly done** | No casts on hash results. `XNEW` is used. The opcode tables are `const` (tc-i51.c:142, i51-dis.c:40). No line in the C files is over 79 columns, and there is no trailing whitespace. `return 0/1` remains only in int functions. **Left:** `enum pcode_mode` enumerators are unprefixed (`DIRECTWORD`…, tc-i51.c:1757-1766). i51-dis.c:21-22 has a double blank line. elf32-i51.c:1076-1080 mixes spaces and tabs before the macro values. |

**Tally: done 12 (1, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14) · mostly done 5 (2, 5, 15, 16, 17) · not done 0.**

### A.2 r7 Part B

| r7 | status | evidence |
|----|--------|----------|
| B1 two range tables (`ljmp -1` accepted) | **fixed** | The single table is `i51_ranges` (tc-i51.c:428). Verified with `as-new`. The constant `.pcode` address is the one remaining duplicate (B4). |
| B2 `i51_build_ins` re-derives operands | **fixed** | `i51_emit` (tc-i51.c:1164-1212) takes `ops` and indexes `opc->args[i]`. The opcode byte is emitted once (:1182). |
| B3 three space name lists | **partial** | The common list is shared through the X-macro. The section→space list is still separate (B5). |
| B4 `bss_alloc`/`parse_align` | **fixed** | See A3. |
| B5 shared encoders | **fixed** | They are in include/elf/i51.h, not in include/opcode/. That is acceptable: include/elf/ppc64.h also has inline helpers. |
| B6 history comments | **mostly fixed** | No history narration is left in the C code. What remains is in the doc and the generation-0 ABI text (B3, B6). |
| B7 redundant macros | **fixed / retracted** | The `elf_backend_may_use_*` macros and `TARGET_MACH` are gone. r7 was wrong about `LOCAL_LABELS_DOLLAR` (tc-i51.h:79-80): te-generic.h:29 sets it to 1, so the `#undef` is needed, and dlx and i386 do the same. |
| B8 disassembler | **fixed** | See A10. |
| B9 nits | **fixed** | `I51_MNEMONIC_MAX`/`I51_NAME_MAX` replace `char name[11]` (tc-i51.c:149-150). Only 5 forward declarations remain (:88-92). The alias is a function (:1100). |

## Part B: new findings, ranked by value

### B1. Folding symbol names to upper case causes about 205 testsuite markings and two generic changes (HIGH; about −450)

`tc_canonicalize_symbol_name` folds every symbol to upper case (tc-i51.h:97-99; tc-i51.c:525-542). Several things follow from that one choice:

- **Testsuite markings.** 216 generic testsuite files are touched (+1691 lines). In about 205 of them the stated reason is the folding: "# The i51 assembler folds symbol names to upper case." (101×) and "# i51 folds symbol names …" (99×), plus variants. The examples include the whole ld-archive set (archive.exp:41-44), objdump.exp (7 places), readelf.exp:369-372, ld-elf/elf.exp:126 and gas/all line-comment (gas.exp:538-540). These markings do not hide back-end bugs, but they switch off most of the generic coverage of gas and ld for this target. An upstream reviewer would not accept about 200 `xfail` lines whose cause is a design choice.
- **Generic change in obj-elf.c:1800-1801.** `save_symbol_name` had to be made public (symbols.c:344, symbols.h:63) only so that version names get folded the same way.
- **Linker script.** It has to PROVIDE every startup hook in both spellings, with a 7-line explanation (elf32i51.sc:95-111). The manual repeats the explanation in 13 lines (c-i51.texi:112-128).
- **Exceptions in the folding function.** It must leave alone `.startof.`/`.sizeof.` names and any name that `bfd_get_section_by_name` already knows (tc-i51.c:535-538). That lookup runs on every symbol created.

**Fix:** keep symbols case-sensitive by default, as every other ELF port does. Built-in names are already looked up case-insensitively (`i51_lookup_name`, tc-i51.c:597-609), and mnemonics are lowered (:1239-1240), so `mov A,#10` and `MOV a,#10` still work. If Keil-style folding is wanted, add an opt-in option. The existing global `symbols_case_sensitive` (symbols.c; m68k sets it with `.opt case`, tc-m68k.c:5669) is the infrastructure for that.

**Result:** about 205 markings (about 420 testsuite lines), the obj-elf.c, symbols.c and symbols.h changes, the canonicalize function (18 lines), the duplicate PROVIDEs and their comments, and the manual paragraph can all go.

### B2. The generic changes are correct but should be separate, tested patches (HIGH for upstreaming; ±0)

- **read.c:1868-1874 (`s_comm_internal`).** It skips `demand_empty_rest_of_line` when the `comm_parse_extra` hook fails. That is a real generic fix: after `parse_align` fails it has already called `ignore_rest_of_line`, so the old code consumed the *next* line. Every existing hook returns NULL only after `parse_align` (obj-coff.c:179-181, obj-macho.c:900-902, tc-arc.c:972-974, read.c:2742-2744, tc-bpf), so the change is safe for all of them. obj-elf.c:278 adds the missing `ignore_rest_of_line` that the new rule needs. **Missing:** a generic gas test (gas/all or gas/elf) where `.comm x,4,3` followed by a second line shows that the second line survives.
- **read.c:2615-2664 (`bss_alloc_section`).** This is an upstream-style split.
  - It saves and restores `now_seg` in both `bss_alloc` (:2618-2619, 2638) and `bss_alloc_section` (:2648-2649 and its tail). Only the callee needs to.
  - The new comment ("subsection 1 of BSS_SEG") is fine.
- **read.c:3389-3409 (`assign_symbol` listing).** The listing dummy frag is now attached to any undefined, unequated symbol that has no frag, and no longer only to a symbol just created. That changes the `-als` output on every target for a symbol referenced before its `.set`/`=` (an improvement). The change depends on `rs_dummy == 0` (from `notes_calloc`) to survive `set_zero_frag` (read.c:4161). **Missing:** a generic listing test. The comment clause "also for one a directive such as .local made before it was given a value" is awkward; "including a symbol that already exists" would do.
- **obj-elf.c:1800-1801.** Goes away with B1. If it stays, the later `notes_strdup (version_name)` at the bottom of the function becomes a second copy and should be dropped.
- **readelf.c.** `case EM_8051:` in `guess_is_rela` is placed between `EM_ARC_COMPACT3_64` and `EM_AVR` (:1286). The list is alphabetical, with numerics first, so the case belongs after `EM_860` (:1276). `get_machine_flags` does not decode the e_flags generation. That is optional, but `readelf -h` shows a bare flag value.
- **config.sub:1320.** config.sub is imported from the GNU config project. The `i51` entry must be sent to config-patches@gnu.org first. It cannot be patched in binutils.
- **ld/configure.tgt:323.** `i51-*-*` sits between `h8300-*-linux*` and `hppa*`, which breaks the alphabetical order.

### B3. Compatibility code for objects no tool in the tree writes (MED; about −45)

- **SHF_I51_* section flags.**
  - include/elf/i51.h:66-75 defines seven SHF_I51_* values. Only `SHF_I51_SPACE` is read (elf32-i51.c:736), and nothing sets any of them.
  - The `section_from_shdr` hook (elf32-i51.c:719-742, :1082) gives SEC_IS_COMMON to a section that carries such a code. Only hand-written numeric `.section` flags reach it (ld-i51/shf.s).
  - The field overlaps `SHF_EXCLUDE`: `SHF_I51_IDATA` is `0x80000000`, so `_bfd_elf_make_section_from_shdr` (elf.c:943) marks such a section SEC_EXCLUDE.
  - **Fix:** delete the hook, the 7 macros and the shf test (−30), or document that this is an import path for a named foreign toolchain.
- **ABI "generation 0".**
  - `EF_I51_ABI_*` (i51.h:56-64), the `st_value = 1` fallback (elf32-i51.c:999-1001), the refusal in `merge_private_bfd_data` (:1040-1066) and the manual text (c-i51.texi:522-531) all exist for objects from before this port had an ABI.
  - A new upstream port has no previous ABI.
  - The manual sentence "a linker that predates the field" is history.
  - **Fix:** keep `e_flags = 0` and treat `st_value` as the alignment, as SHN_COMMON does (−15). Alternatively, say in one sentence which external objects need this.
- **R_I51_8 adds the byte already in the section** (elf32-i51.c:105-107, 528-533; c-i51.texi:813-816). With RELA and `partial_inplace false`, gas writes 0 there. Verified: `.byte sym+5` gives contents `00` and addend 5. Adding the byte is REL behaviour inside a RELA target. Drop it and let the howto range check handle the value (−3).

### B4. The `.pcode` address still has a second range check (LOW-MED; −10)

tc-i51.c:2019-2029 checks a constant `.pcode` address and encodes it inline. `md_apply_fix` already does the same check for the fixup (:1463-1474). Always call `fix_new_exp` with BFD_RELOC_I51_13_PCODE, as `i51_emit_field` does for every operand. `md_apply_fix` then finalises the constant (`fx_done`, :1395-1397).

### B5. The space a section belongs to is known in two places (LOW-MED; −15)

- gas `i51_spaces[]` (tc-i51.c:449-469) lists the 14 space sections and whether each one is bss or data.
- bfd `i51_section_spaces[]` (elf32-i51.c:371-397) lists the same names plus `.data`, `.bss`, `COMMON`, `.gnu.linkonce.d.` and `.bit`, mapped to an `enum i51_space`.

**Fix:** one more X-macro in include/elf/i51.h, `I51_SPACE_SECTIONS(X)` giving {name, space, bss/data}, expanded on both sides, as `I51_COMMON_SPACES` already is.

### B6. Documentation and comments (MED; about −60)

- **Dangling doctruth markers.** c-i51.texi:5-10 and 10 `@c doctruth:` markers refer to `tb/doctruth.py` and a "gate stage". Neither exists in the tree. Remove them (−16).
- **Manual length.** c-i51.texi is 883 lines, against 600 for avr and 161 for pru.
  - The hook paragraph (:112-128) goes with B1.
  - The ABI-generation paragraph (:522-531) goes with B3.
  - The relocation table (:802-883) restates the howto comments, which is acceptable.
- **`TC_FIX_TYPE` comment** (tc-i51.h:56-64, 9 lines). It argues its case. Suggested replacement: "The symbol of a direct operand, for i51_check_direct (); the fixup's own symbol may by then be a section symbol." (−6)
- **Linker script comments.**
  - elf32i51.sc:9-15 (the Harvard essay) can be cut to 2 lines.
  - :58-60 goes with B1.
  - :172 is 93 columns wide and should be wrapped.
  - The copyright on the new .sc file says "2014-2025" (:1, 49), copied from avr.sc. It should be 2026.
- **Cosmetic in-place writes.** The PC-relative branch to an absolute target written in place "for the disassembly of the object" (tc-i51.c:1410-1419) and the constant ACALL/AJMP target written in place (:1147-1151) are values that the linker overwrites. Other RELA ports leave the field zero. Optional, −8.

### B7. Testsuite markings: proportion and comments (MED; see B1)

- With B1 done, about 11 markings remain, and each is a real target property:
  - Initialised data is refused in RAM that nothing loads: ld-elf ×6, checks.exp:31-33, archive.
  - `.dc.a` is 16 bits (readelf.exp:722).
  - There is nowhere to put orphan writable sections.
  - There is no stack-size property in a 16-bit address space.
  - `uses_genelf` (ld-lib.exp:1217).
  - Page size 1.
  - Macro handling with ONLY_STANDARD_ESCAPES (macros.exp:57).

  None of them hides a back-end bug.
- Most upstream xfail lists carry no per-target comment. Writing the same one-line comment in 200 files adds 200 lines. If any markings remain, one comment per .exp file is enough.
- readelf.exp:372 (`readelf -r`) has an `xfail` without a reason. With B1 it should pass, and the marking should go.

### B8. Small idiom points (LOW; about −15)

- **gas fake common sections** (tc-i51.c:473-483, 576-588). gas builds its own `asection`/`asymbol` copies of `*bfd_com_section_ptr`. tc-v850.c:187-195 shows the gas idiom: real sections made with `SEC_IS_COMMON`, which `bfd_is_com_section` recognises. That would remove the static arrays and the copy loop (−12). bfd's own static fake sections for `symbol_processing` (elf32-i51.c:872-900) follow the mips scom pattern and are fine.
- **`i51_user_symbol`** (tc-i51.c:615-623) duplicates the name with `xmemdup0` on every lookup. From `i51_parse_name` (:833) the name is already NUL-terminated, so it can call `symbol_find (name)` directly. A copy is needed only for the `.N` base and in `i51_parse_operand`.
- **`md_apply_fix` default case** (tc-i51.c:1476-1478) is `as_fatal (_("line %d: …"), fixp->fx_line, …)`. Siblings use `as_bad_where (fixp->fx_file, fixp->fx_line, …)` or `abort ()`.
- **Opcode struct defined twice.** `struct i51_opcode` exists in both tc-i51.c:132-138 and i51-dis.c:29-36. Define it once, with `mask`, in include/opcode/i51.h behind an include guard, and keep the X-macro rows in the same header. avr.h and pru.h do this.
- **Unprefixed enumerators** in `enum pcode_mode` (tc-i51.c:1757-1766): use `PCODE_DIRECT_WORD` and so on.

## Size

- Available: about −450 lines from B1 (mostly testsuite), and about −150 lines of code, comments and documentation from B3-B8.
- Highest value:
  1. **B1**: one design choice is behind most generic-testsuite xfails and the obj-elf/symbols changes.
  2. **B2**: the generic read.c fixes are correct but need their own generic tests, and the config.sub change must go through the GNU config project.
  3. **B3**: SHF_I51/ABI-generation compatibility code that no in-tree tool needs, with the SHF_EXCLUDE overlap.

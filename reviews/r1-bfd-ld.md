# BFD + linker review — binutils-mcs51 (i51/8051)

Scope: `bfd/cpu-i51.c`, `bfd/elf32-i51.c`, `include/elf/i51.h`,
`ld/emulparams/elf32i51.sh`, `ld/scripttempl/elf32i51.sc`, and the bfd/ld hooks in
`mcs51/modifications.patch`.

Method: patches applied to a pristine binutils-2.47 tree, configured `--target=i51-elf`,
built, and driven with real input. Line numbers are lines in `mcs51/*.patch`
(post-fix where a fix was applied).

Legend: **[FIXED]** = applied to the patch file in this branch. **[OPEN]** = reported only.

---

## S1 — Critical

### 1. Every howto `size` field is in the pre-2.36 encoding → 8-bit relocs write nothing, 16-bit relocs write one byte **[FIXED]**
- `struct reloc_howto_struct.size` has been **bytes**, not a log2 code, since binutils 2.36
  (`bfd/bfd-in2.h:3228` "The size of the item to be relocated in bytes"; `HOWTO_RSIZE`,
  `bfd_get_reloc_size` at `bfd-in2.h:3310-3322`). The table still said
  `0 = byte, 1 = short, 2 = long`.
- Consequence: `read_reloc`/`write_reloc` (`bfd/reloc.c:540-604`) hit `case 0:` and do
  **nothing** for `R_I51_R1/R3/7_PCREL/8_BIT/8/L/H/8_B2B`, and write only one byte for
  `R_I51_11/16/13_PCODE`. Everything routed through `_bfd_final_link_relocate`
  (the `default:` arm of `i51_final_link_relocate`) was silently dropped.
- Evidence (unfixed build, `MOV A,#LOW(t)` / `#HIGH(t)` / `#t`, `t` resolving to 0x09):

  ```
  pre-link : 74 00 74 00 74 00
  linked   : 74 00 74 00 74 00     <- expected 74 09 74 00 74 09
  ```
  Real project: `diag`, `RESET_CONT+0xc`: `mov 0x81,#0x00` — that is `mov SP,#0`.
  Correct is `mov SP,#0x6A`.
- Fix: sizes set to real byte counts — `additions.patch:100,115,130,145,160,175,190,205,220,235,250,265`.
  `R_I51_NONE` additionally made a true no-op (size 0 / bitsize 0 / `complain_overflow_dont`).

### 2. Linker applies 16-bit in-instruction fields little-endian; the 8051 (and gas) use big-endian **[FIXED]**
- gas writes every 16-bit instruction field big-endian: `number_to_chars_bigendian`
  (`gas/config/tc-i51.h:73`), `bfd_putb16`/`bfd_getb16` in `md_apply_fix`
  (`additions.patch:1855,1889,1895`). The BFD target, however, is
  `TARGET_LITTLE_SYM bfd_elf32_i51_vec` (`additions.patch:1001`), so `bfd_get_16`/
  `bfd_put_16` in `i51_final_link_relocate` byte-swap the field.
- MCS-51 `LJMP addr16` is `02 A15-A8 A7-A0`; `AJMP` is `a10a9a8 00001 / a7-a0`. There is no
  little-endian reading of these encodings.
- Evidence (unfixed build):

  | site | pre-link | unfixed link | correct |
  |---|---|---|---|
  | `LJMP tgt` (tgt=8) | `02 00 00` | `02 08 00` | `02 00 08` |
  | `ACALL tgt` (tgt=8) | `11 00` | `08 00` | `11 08` |

  The `ACALL` case overwrites the opcode byte itself.
- Real project `diag`, unfixed, disassembled with the port's own objdump:

  ```
  00000000 <RESET>:      0:  32           reti          <- should be: 01 32  ajmp 0x0032
  0000000b <I_TF0>:      b:  21 00        ajmp 0x0100   <- should be: 01 21  ajmp 0x0021
  ```
  A reset vector of `RETI` is not a working image.
- Fix: `bfd_getb16`/`bfd_putb16` for `R_I51_11` and `R_I51_13_PCODE`
  (`additions.patch:437,439,477,479`) and an explicit big-endian `R_I51_16` case
  (`additions.patch:482-488`) so it no longer goes through the endian-neutral generic path.
- After the fix the same image disassembles as `ajmp 0x0032` / `ajmp 0x0021` /
  `mov SP,#0x6A`, i.e. coherent 8051.

### 3. The testbench reference ROMs encode bugs 1 and 2 — `make check` cannot catch either **[OPEN]**
- `tb/base.7z` `projekt/*/www8051.rom` are all dated Nov 17 2025 (not 2001) and match the
  **unfixed** 2.47 build byte for byte. They contain the corruption above:
  `diag` reset vector = `32` (RETI), `led1` reset vector = `02 26 00` (LJMP 0x2600 in a
  5173-byte ROM — the byte-swap of `02 00 26`).
- So a green `make check` currently certifies broken output, and the correct build *fails*
  the check (`diag` reference `66cb26…` vs fixed `ade88d…`, 134 bytes differ, every one at
  a relocation site).
- Fix: regenerate `base.7z`'s reference ROMs from a build with fixes 1+2, or (better)
  regenerate them from `make frozen` (the real 2.11.2/big-endian port) and keep them.
  Until then the reference is not a reference.
- Aside, same file: `tb/Makefile:136` runs `make clean … || true` and then only checks
  `-f www8051.rom`; if `clean` fails the stale reference survives and every project
  reports PASS without building. Guard the clean, or hash into a scratch dir.

---

## S2 — High

### 4. `relocate_section` indexes the howto table with an unchecked reloc type **[FIXED]**
- `howto = elf_i51_howto_table + ELF32_R_TYPE (rel->r_info);` with no bound test, while
  `i51_info_to_howto_rela` (`additions.patch:336-351`) does check. A crafted object with
  `r_type >= R_I51_max` gave an out-of-bounds read plus a `switch (howto->type)` on
  garbage — reachable from `ld`, `objdump`, `nm` on an untrusted `.o`.
- Fix: bounds check + `bfd_error_bad_value`, `additions.patch:553-560`.

### 5. The shipped linker script does not know the port's section names **[OPEN]**
- gas emits `.rdata`, `.bitdata`, `.idata`, `.eeprom`, `.data`, `.bss`, `.text`
  (verified on `tb` objects), and `bfd/elf32-i51.c` additionally invents `.regbank`,
  `.rbss`, `.bbss`, `.ibss`, `.xbss`, `.ebss`, `.bitbss`, `.rbbs`, `.bbbs`, `.ibbs`,
  `.xbbs`, `.ebbs` (`additions.patch:696-720,738-790`).
- `ld/scripttempl/elf32i51.sc` places only `.vectors .init .text .rodata .fini .bit
  .data .bss .idata .xdata .eeprom` (`additions.patch:4085-4171`). Not one of
  `.rdata/.bitdata/.rbss/.bbss/.bitbss/.regbank/.xbss/.ebss` appears — they all become
  orphans at whatever address the orphan placer picks.
- The real script the testbench uses (`tb/base.7z lib/www51.sc`) places all of them and is
  the de-facto spec. Port that section list into the template.

### 6. Default link fails outright: overlapping allocated sections **[OPEN]**
- `rom`, `xdata` and `eeprom` all start at ORIGIN 0 (`additions.patch:4064,4076,4079`) in
  one flat VMA space. `ld` checks allocated-section overlap
  (`ld/ldlang.c:5893 IGNORE_SECTION`, `lang_check_section_addresses`) and errors:

  ```
  ld: section .xdata LMA [00000000,00000000] overlaps section .text LMA [00000000,00000004]
  ld: section .eeprom LMA [00000000,00000000] overlaps section .xdata …
  (exit 1)
  ```
- The testbench never sees this: every project links with `--script …/www51.sc
  --no-check-sections`. The built-in emulation is untested and, as shipped, unusable.
- Fix: give the non-CODE spaces distinct load addresses (the usual trick: high fake LMAs),
  or mark them `NOLOAD`/non-alloc, or ship `--no-check-sections` behaviour via the
  emulation. Do not just tell users to pass the flag.

### 7. `bits`, `data`, `idata` regions do not describe an 8051 **[OPEN]**
- `bits (rw!x) : ORIGIN = 0x0020, LENGTH = 0x10` (`additions.patch:4067`). Bit space is a
  *separate* address space of 128 bit-addresses; `www51.sc` correctly declares
  `bit : ORIGIN = 0, LENGTH = 0x80` and computes `.bit` at `(byte_addr-0x20)*8`.
  As written only 16 bit variables fit and their addresses are byte addresses.
- `data (rw!x) : ORIGIN = 0x0030, LENGTH = 0x50` (`:4070`) — comment says "128 bytes",
  value is 80. It also excludes 0x00-0x1F, so `.regbank`/`.rdata` (register banks) have
  nowhere to go, and 0x20-0x2F (the bit-addressable bytes that `.bdata`/`.bbss` need).
- `idata (rw!x) : ORIGIN = 0x0080, LENGTH = 0x80` (`:4073`) is modelled as a disjoint
  region; on the 8051 indirect addressing covers the whole 0x00-0xFF and the upper half is
  merely indirect-only. `www51.sc` keeps one `data : 0..0xFF` region for exactly this reason.
- `xdata … LENGTH = 0x10000` (`:4076`) hard-codes a full 64K external bus.

### 8. The three "compiler-independent weak symbols" can never bind **[OPEN]**
- `PROVIDE_HIDDEN (__gsinit_startup = 0)` etc. (`additions.patch:4173-4175`).
- gas for this target upper-cases symbol names. A source reference produces
  `__GSINIT_STARTUP`, so the lowercase PROVIDE never matches:

  ```
  ld: e.o: in function `_START':
  (.text+0x1): undefined reference to `__GSINIT_STARTUP'
  ```
- Two further problems even if the names matched: `PROVIDE` is not weak — it creates an
  absolute definition; and defining a *hook* to address 0 means `LCALL __gsinit_startup`
  jumps to the reset vector instead of being a no-op. A `RET` stub in `.text`, or
  `PROVIDE`ing them to a `_RETI_`-style stub (which is what `www51.sc:100-110` does for the
  interrupt hooks), is the working pattern.
- `__stack = ORIGIN(idata) + LENGTH(idata)` (`:4178`) evaluates to 0x100 — one past the top
  of internal RAM; SP must be *below* the first stack byte, and the region model is wrong
  anyway (see 7).

---

## S3 — Medium

### 9. Everything silently truncates: no overflow checking anywhere **[OPEN]**
- Nine of twelve howtos use `complain_overflow_dont`
  (`additions.patch:164,179,194,209,224,239,254,269` + NONE). `R_I51_8`/`R_I51_L` against a
  symbol at 0x0109 now writes 0x09 with no diagnostic; `R_I51_16` cannot overflow, but
  `R_I51_8`, `R_I51_8_BIT` and `R_I51_R1`/`R3` all can and should be
  `complain_overflow_unsigned`. (`R_I51_R1`/`R3` are marked `complain_overflow_bitfield`
  with `bitsize 8` — a 1-bit and a 3-bit field respectively, so the check is meaningless.)
- Not applied here because tightening it may reject sources that currently rely on the
  truncation; it needs a decision, not a patch.

### 10. `bfd_reloc_outofrange` is used as a domain check, and the link still succeeds **[OPEN]**
- `R_I51_8_B2B` and `R_I51_13_PCODE` return `bfd_reloc_outofrange` for legitimate
  application errors (`additions.patch:454,456,472`), which `elf32_i51_relocate_section`
  turns into `"internal error: out of range error"` *warnings*
  (`additions.patch:633-635`) and then leaves the field unrelocated. `diag` alone emits 11
  of these and links "successfully".
- Use `reloc_overflow`/`einfo`-level errors so a bad image fails the link.

### 11. `R_I51_11` page check is off by the instruction length **[OPEN]**
- `additions.patch:426`: `(srel ^ (rel->r_offset + out_sec->vma + out_offset)) & 0xF800`.
  `r_offset` points at the AJMP/ACALL *opcode*; the 8051 resolves the page from the PC of
  the following instruction, i.e. `r_offset + 2`. At a 2 KiB boundary this both accepts
  out-of-page targets and rejects legal ones.
- `R_I51_7_PCREL` gets this right only by accident: the linker computes the displacement
  against `r_offset` (`additions.patch:411`) and gas compensates with
  `if (fixp->fx_pcrel) reloc->addend -= 1;` (`gas/config/tc-i51.c` `tc_gen_reloc`).
  Verified correct (`SJMP` to a symbol 1 byte past the next insn emitted `80 01`), but it
  is a hidden coupling — document it or move the bias into the linker.

### 12. `ld -r` and `ld -Ur` get an empty script **[OPEN]**
- `additions.patch:4048`: `test -z "${RELOCATING}" && exit 0`. `genscripts.sh:316-331`
  sources the template inside a subshell for `LD_FLAG=r` and `LD_FLAG=u`, so
  `ldscripts/elf32i51.xr` is literally:

  ```
  /* Script for -r */
  ```
  No `OUTPUT_FORMAT`, no `OUTPUT_ARCH`, no section list. No upstream `scripttempl` does
  this. As a side effect every `${RELOCATING-0}` / `${RELOCATING+…}` guard in the file is
  dead text.

### 13. Half the SHN/SHF machinery in `elf32-i51.c` is dead **[OPEN]**
- ~320 lines (`additions.patch:696-960`) implement `SHN_I51_REGBANK/RDATA_C/BDATA_C/…`
  commons and `SHF_RDATA/BDATA/IDATA/XDATA/EDATA` section flags.
- `elf_backend_section_from_bfd_section` — the only hook that would ever *emit* those
  indices — is commented out with "Temporarily disabled - causes crashes with standard
  sections" (`additions.patch:1016-1017`). Confirmed: no object produced by this toolchain
  carries an `SHN_I51_*` index (`readelf -s` on the testbench objects shows only
  `ABS/COM/UND`). The reader side is therefore unreachable, and the disabled writer is a
  known-crashing code path shipped in the tree.
- Either fix the hook (it returns 0 for `bfd_abs/und/com/ind` but not for `.text`, which is
  probably the crash) and gate it on the i51 section names, or delete the whole block.
- The `static asection i51_elf_*com_section` singletons (`additions.patch:790-816`) are also
  process-global, never registered with any BFD, and have `owner == NULL`; if they ever do
  get reached, generic ELF code that dereferences `sec->owner` will fault.

### 14. `elf_backend_final_write_processing` does not chain **[OPEN]**
- `bfd_elf_i51_final_write_processing` (`additions.patch:663-668`) sets `e_machine` and
  returns, never calling `_bfd_elf_final_write_processing` (`bfd/elf.c:13500`), so
  `EI_OSABI` / GNU-osabi handling is skipped. Also redundant: `ELF_MACHINE_CODE EM_I51`
  already sets `e_machine`, and forcing it unconditionally mislabels any foreign BFD copied
  through this vector.

---

## S4 — Low / hygiene

- **`EM_I51 0x1051`** (`additions.patch:3823`) is unregistered. It collides with nothing in
  2.47's `include/elf/common.h`, but 0x1051 sits in the low numeric range that the ELF
  registry allocates from; other unofficial ports deliberately pick 0x7676/0x9026/0xFEBA/
  0xbeef. Move it high, or register it.
- **`readelf` decodes nothing i51-specific beyond reloc names.** `guess_is_rela`
  (`modifications.patch:384`, correct — RELA) and `get_machine_name`
  (`modifications.patch:402`) are wired, but there is no `get_i51_section_type_name`,
  no `SHF_RDATA/BDATA/…` flag decoding and no `SHN_I51_*` symbol-index names, so those
  print as raw `PRC[0xff01]` / unknown flags. `case EM_I51:` is also inserted between
  `EM_ARC_COMPACT3_64` and `EM_AVR` in an otherwise alphabetical list.
- **`bfd_arch_i51` is inserted mid-enum** (`modifications.patch:29,57`), inside the i386
  `bfd_mach_*` define block and before `bfd_arch_romp`, renumbering every later
  `bfd_arch_*`. Harmless for a self-contained build, gratuitous churn otherwise; append
  instead.
- **`bfd_elf32_i51_vec`** (`modifications.patch:110,124,136,226,234`) uses the pre-2.16
  naming. Every other vector in 2.47 is `<arch>_elf32_<endian>_vec` — here that would be
  `i51_elf32_vec`.
- **`bfd/Makefile.am` and `opcodes/Makefile.am` are patched but their `Makefile.in` are
  not**, while `ld/Makefile.in` *is* (`modifications.patch:263-274,288-299,324-334`).
  The build only works because automake's `.c.lo:` suffix rule picks the file up; there is
  no dependency tracking for `elf32-i51.lo` and `make dist` will not ship it. Patch the
  `.in` files too, or none of them.
- **`ld/configure.tgt` hunk applies with fuzz 2** against a clean 2.47 (it is anchored on
  the h8300 block). Re-cut it with `make -C tb refresh` so it does not drift into the wrong
  case arm.
- **`cpu-i51.c`**: `section_align_power = 1` (`additions.patch:41`) means default 2-byte
  section alignment on a byte-addressed machine; the field is only consulted by a.out/pdp11
  so it is inert here, but 0 is the honest value. No `bfd_mach_i51*` variants are defined,
  so there is no way to distinguish 8051/8052/DS80C390 later.
- **`ELF_MAXPAGESIZE 1`** (`additions.patch:999`) vs `MAXPAGESIZE=0x0800` in
  `ld/emulparams/elf32i51.sh` (`additions.patch:4028`) — pick one. `TEXT_START_ADDR` in the
  same file is unused because the custom script hard-codes `> rom`.
- **`elf_backend_can_gc_sections 1`** (`additions.patch:1008`) with `TEMPLATE_NAME=generic`:
  `generic.em` has no `--gc-sections` plumbing, so this never fires.
  (`TEMPLATE_NAME=generic` + `EXTRA_EM_FILE=genelf` is itself a supported upstream pairing —
  `pjelf`, `elf32ft32`, `xgateelf`, `moxiebox` all use it — so the README's "migrated from
  'elf' to 'generic' template" is accurate and not a defect. Note it describes the *ld*
  template only; `bfd/elf32-i51.c` still `#include "elf32-target.h"`.)
- **`elf32_i51_check_relocs`** (`additions.patch:357-388`) walks the relocs and computes
  `h`, then discards it — the whole function body is dead. Together with the unused
  `r_type`, unused `abfd`/`info`/`namep` parameters it produces five warnings and makes
  `--disable-werror` mandatory.
- **`elf32_i51_object_p`** (`additions.patch:672-676`) is `return 1;` — it accepts anything
  and could simply be dropped.
- **Reloc numbering/naming is consistent** across `include/elf/i51.h:3826-3839`,
  `bfd/reloc.c` (`modifications.patch:166-215`), `bfd/libbfd.h`
  (`modifications.patch:144-160`) and `bfd/bfd-in2.h` (`modifications.patch:61-99`): same
  eleven names, same order, and `elf_i51_howto_table` is indexed by `R_I51_*` value in the
  same order. No mismatch found. Two of the declared codes are unreachable, though:
  `BFD_RELOC_I51_8` and `BFD_RELOC_I51_16` are never mapped in `i51_reloc_map`
  (`additions.patch:288-300` maps `BFD_RELOC_8`/`BFD_RELOC_16` instead), so
  `bfd_reloc_type_lookup` returns NULL for them. Delete them or use them.

---

## Verification performed

- binutils 2.47 + both patches, `--target=i51-elf`, native build: clean (5 warnings in
  `elf32-i51.c`, `--disable-werror` required).
- Hand-written cases for `R_I51_16`, `R_I51_11`, `R_I51_L`, `R_I51_H`, `R_I51_8`,
  `R_I51_7_PCREL`, before and after the fixes.
- Full `tb` testbench run against both builds. `diag` is the only project that builds in
  this sandbox (the other nine need `cgi/*.obj`, which `base.7z` does not ship and no rule
  builds — `make[1]: *** No rule to make target '../../cgi/testP3.obj'`; worth checking
  whether CI really exercises them). `diag` links, and the fixed build's image is the one
  that disassembles as valid 8051 — see S1.3.

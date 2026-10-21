# R6: full review of main @ 70a8b20 — consolidated findings

Seven reviewers, one lane each, run in parallel against a build of `main` @ 70a8b20
(binutils 2.47 + `mcs51/*.patch`, `make -C tb build OPTFLAGS=-O1`). Every finding
below was reproduced with the built tools; the ones marked ✔ were re-run a second time
independently while this summary was written. Duplicates across lanes are merged;
the lanes that found each item are given in brackets.

| lane | report |
|------|--------|
| enc  | `r6-gas-encoding.md` — instruction matching and encoding (17.6k-line matrix, 60k fuzz files) |
| ld   | `r6-ld-relocs.md` — relocations, overflow, address spaces, linker script |
| tools| `r6-tools.md` — disassembler, objdump/objcopy/strip/nm/size, malformed-input fuzzing |
| dd   | `r6-directives-docs.md` — directives, memory model, documentation truth, sdas/ASEM idioms |
| tb   | `r6-testbench-ci.md` — gate, CI, release, mutation |
| cq   | `r6-code-quality.md` — C code, sanitizers, `--enable-targets=all`, upstream blockers |
| id   | `r6-idioms-reuse.md` — binutils idioms, reinvented wheels, redundancy |

Repro sources (text only) are under `r6-repro/<lane>/`. The reports cite them by the
scratchpad paths they were written at; map `…/scratchpad/review/<dir>/` and
`…/scratchpad/dd/` to `r6-repro/<dir>/`.

Status of R5-OPENITEMS on this head: 1 deliberate (case folding), port items 2,3,4,5,6,7,8,9,10
fixed, testbench items 11–18 fixed, docs 19–20 fixed. What follows is new or still open.

---

## What is right

- All valid instruction forms encode correctly: 255 defined opcodes against an
  independent Intel-map encoder, ~17.6k mnemonic × operand lines, 0 mismatches. [enc]
- Disassembler: 4669 instructions incl. 0x85 operand swap, cjne/djnz/jbc, ajmp page
  edges — 0 mismatches; printed text reassembles byte-identical. [tools]
- No crash, sanitizer report or hang: ~70 malformed inputs + 1000 mutation-fuzz runs under
  ASAN/UBSAN. Zero warnings under `-Wall -Wextra -fanalyzer`. `--enable-targets=all`
  builds and links byte-identically. [tools, cq]
- Gate: all 15 stages pass end to end (~15 s) once `s51` and `7z` are installed. [tb]
- Release publishes only from the tested commit; BUILD-INFO and SHA256SUMS checked. [tb]

## CRITICAL — wrong bytes or a wrong image, exit 0, no diagnostic

Grouped by root cause; fixing the cause closes the group.

### RC1 — operand matcher falls back to the last table row
`i51_parse_operand1` (tc-i51.c ~1238) / `i51_parse_operand2` (~1397) take the mode of the
last group entry when nothing matches.
1. ✔ `jmp lbl`, `jmp 0x1234` → `73` (jmp @A+DPTR); `swap x`, `da x`, `mul x`, `rl 5`,
   `movc a,lbl` → bare form. [enc, tb, R5]
2. ✔ `add 0x45,#0x5a` → `24 45` (add A,#0x45); ✔ `anl/orl/xrl 0x45,0x46` → `53 45 46`
   (#imm); ✔ `movx 0x45,a` → `f0`; `xch`, `cjne d,d`, `xchd`, `movc`, `div`, `rlc`, `rr`,
   `rrc` likewise. [enc]

### RC2 — fixups finished in gas, overflow checking switched off
Every fixup sets `fx_no_overflow`; range checks are re-implemented in 4 places and skipped
for forward references; absolute targets get no reloc. [id #6]
3. ✔ Absolute / `.equ` branch targets resolved against the section start, no reloc:
   `sjmp 0` linked at 0x100 → `80 fe` (`sjmp .`); `ajmp 0x10` after 0x7fe bytes links
   to 0x810 with no page error. [enc C1, cq C3]
4. `sjmp`/`jcc` to a weak or global symbol in the same section resolved in gas; a strong
   definition elsewhere is ignored while `ljmp` follows it. [ld C6, cq C2]
5. Forward-referenced constants skip range checks: `ljmp fw` (fw=-70000) → `02 ee 90`;
   `mov dptr,#fw` (0x12345) → `90 23 45`; `.pcode M` (M=0x2345 later) → 0x0345. [enc C6, cq C6]
6. ✔ `#high(0x1234)+1` → `74 12`; `#high(0x1234)&0x0f` → `74 00` — HIGH()/LOW() swallow the
   rest of the expression (`i51_prefix_keyword` ~1978). [enc C2]
7. HIGH()/LOW() on a symbolic bit operand silently dropped (`setb high(EXT)` → `d2 12`). [enc C3, cq H2]
8. ✔ Text after `cjne`'s third operand assembled as a new instruction:
   `cjne a,#1,l,nop` → extra `00`. Error paths leave `input_line_pointer` mid-line. [enc C5, cq C1]
9. `#arN` / `arN+k` keep the bank of the first `.using` (`md_undefined_symbol` ~1104). [enc C4, cq C5]
10. `.pcode` symbolic vs constant differ: `@BYTE SYM` not decremented under RELA,
    `#SWAP SYM` byte order reversed vs `#SWAP const`. [ld C5, cq C7]

### RC3 — `elf32_i51_relocate_section` resolves symbols by hand
Instead of `RELOC_FOR_GLOBAL_SYMBOL` / `_bfd_elf_rela_local_sym` /
`RELOC_AGAINST_DISCARDED_SECTION` (as avr, msp430). [id #1]
11. ✔ Merged strings (`.rodata.str*`, "aMS") addressed by their pre-merge offset:
    S3 at 0x1C loaded as `#0x0020`, S4 (=S2 at 0x16) as `#0x0024` past the image. [ld C1, cq C4]
12. `srel == 0` treated as "unresolved common": `B2B(sym@0,3)` → `d2 03`, `.pcode` to 0 and
    undefined weak accepted. [ld C4, tb M2]
13. ✔ `R_I51_8_BIT` has no overflow check: bit 0x100 → `c2 00`. `R_I51_16` masks:
    `ljmp lbl+0x10000` → `02 00 03`. HIGH of a 17-bit value truncated. ajmp/acall page check
    ignores bit 16 (`acall 0x10000` → `11 00`). [ld C3/C10, tb H2, cq C8]

### RC4 — relocations carry no address space
14. ✔ `setb B2B(xdata_var,1)` → `d2 29`; `mov a,xdata_var` → `e5 25`; `B2B(idata@0xB0,0)` →
    `setb P3.0`; `ljmp`/`acall` to `.xdata`, `sjmp` to `.data`, `setb` on a code label or a
    byte symbol — all link clean. [R5, ld C7, enc M6, tools]
15. ✔ Direct RAM past 0x7F across files: a second file's `.bss` var lands at 0x90 and
    `mov a,v2` → `e5 90` (P1). The gas check sees only one file; ld accepts 0..0xFF. A
    `.idata` symbol used directly is never diagnosed. [dd C2, ld C2]
16. Space commons silently bound to a definition in another space (`.xcomm BUF` + `.idata BUF`
    → `mov dptr,#0x23`); `.xcomm buf,4` then `.icomm buf,8` silently switches to idata. [ld C9, dd H2]

### RC5 — default linker script / memory model
17. ✔ Initialised RAM data is discarded: `.data`/`.xdata`/`.idata`/`.rdata`/`.bdata`/`.bit`/
    `.eeprom` are `(INFO)` with no LMA in ROM and `__INIT_DATA` is a bare `ret`.
    `.data; v: .byte 5,6,7` never reaches the ihex. [dd C1, ld M4]
18. Without `.using`, `.regbank` is empty and `.rdata`/`.rbss`/`.rcomm` start at 0x00 on top
    of R0–R7. [dd C3, ld C8, tools]
19. No stack reserved or checked: RAM can fill to 0xFF with `STACK=0xFF`; `STACK` undocumented,
    0x100 limit not adjustable for 128-byte parts. [dd C4, ld M3]
20. `.eeprom` unbounded (128 KB links; EEV at 0x1000F → `#0x000f`). [dd M5, ld C10]

### RC6 — all spaces are ALLOC+LOAD at LMA 0 in one ELF address space (project script `lib/www51.sc`)
21. `objcopy -O binary|ihex|srec` without `-j` writes `.eeprom` over code incl. the reset vector
    (351 bytes differ from the reference ROM; two conflicting ihex records at 0). [tools 1]
22. `strip` / `objcopy` ELF→ELF moves `.text` LMA 0 → 0x172 (`rewrite_elf_program_header`
    resolving overlapping PT_LOADs); later ihex/srec put code at 0x0172. [tools 2]

### Directives
23. `.local x; .comm x,4` gives a GLOBAL common merged across files: the port's `.local`
    replaces ELF `.local` (and deletes register names); ~125 lines of `i51_common` unreachable;
    no way to make a file-local space common. Upstream would not accept the override. [dd C5, cq H1, id #4]
24. `.ds n` reserves 2n bytes (generic gas `.ds` = `.ds.w`); sdas/ASEM reserve n. [dd H1]

## HIGH / MEDIUM

- `--emit-relocs` writes wrong addends for section-symbol relocs (`elf_backend_rela_normal`). [ld M1]
- User range errors printed as "internal error: out of range error". [ld M2, dd M2, cq]
- No DWARF: `as -g` / `--gdwarf-N` exit 0 with no `.debug_*`; `.loc`/`--gstabs` fail
  ("cannot relocate 4 bytes"); `addr2line` → `??:?`. [tools 4, cq]
- `print_insn_i51` returns -1 on a short read: opcode dropped, false "out of bounds". [tools 3]
- `nm` prints `?` for data/bit/xdata/eeprom symbols, `i` for idata; `size` sums spaces. [tools 5–6]
- Operand parsing accepts nonsense: `B2B()` on byte operands; numeric `.N` folded on any operand
  (`ljmp 0x20.3` → `02 00 03`); negative direct/bit addresses; register names in expressions
  become external symbols; `sym.N` only for constants; `(r3)` becomes a symbol. [enc M1–M5, cq H2–H3]
- `PSW.n`, `IE.n`, `IP.n`, `TCON.n`, `SCON.n`, `F1` missing from the name table → link-time
  undefined. Labels named like SFRs/bits accepted, then misbind. [enc M4, M7, dd]
- `.pcode`: missing comma swallows following lines; `.pcode 0x200,1` → bogus zero word;
  keywords case-sensitive contrary to the texi. [dd M3]
- Alignment of space commons dropped (and rewritten by `ld -r`); `objcopy -R .ibss` deletes the
  space-common symbols. [dd M1, cq, tools 7]
- `SHF_I51_*` codes overlap `SHF_EXCLUDE` and are tested as bits; page size disagrees between
  backend (`ELF_MAXPAGESIZE 1`) and script (`MAXPAGESIZE=0x800`). [cq, id #15]
- Generated `ld -r` script `elf32i51.xr` is empty; DWARF section list hand-copied, missing DWARF5. [id #15]

## Testbench / CI

- **Gate never asserts rejection** — only listed correct encodings; no must-reject table, no
  generic `jmp`/`call` case. That is why RC1 survived five rounds. [tb H1]
- **Every link test defines targets with `--defsym`** (absolute) — no test involves an address
  space, so RC4 is invisible. [tb H3]
- Linker range-checks only 4 of 9 emitted reloc types are tested. [tb H2]
- **Released binaries are not the gated ones**: release.yml's gate builds its own toolchain;
  archives come from separate build.yml jobs with no hash link. arm64/macOS get `check`+`isa`
  only; Windows gets `--version` + one probe that passes even if relocation is never applied. [tb H4]
- x86_64 release built with `-march=haswell`. [tb M5]
- `check` compares against hashes produced by the port itself; `oracle` pins only per-class counts. [tb M1]
- Mutation: 59.4 % killed (41/69); scope excludes the operand parser, space/common directives,
  ELF section handling and the ld emulation — where the bugs are. [tb M4]
- `doctruth` compares name lists only; counts as a release stage. [tb M6, dd M4]
- Actions pinned by tag; no `permissions:`; archives not reproducible; ucsim/runner/gcc unpinned. [tb]

## Idioms and size (≈1,300 of ≈5,200 lines removable) [id, cq]

1. Hand-rolled symbol resolution in `relocate_section` (RC3) — −60.
2. Space name ↔ SHN_I51_* ↔ fake-common mapping written 7× in bfd, 7× in gas — one table (elfxx-mips scom pattern), −250.
3. `i51_common` re-parses what `read.c:s_comm_internal` does; 7 copies of bss_alloc — −150.
4. Overrides of obj-elf `.local`/`.comm`/`.common`/`.bss`; `.equ`/`.set` duplicate read.c.
5. ~20 exported mutable globals; `parse_operand1/2` ~80 % identical; table-order matching with in-band 0x80 flag (root of RC1) — −200.
6. `fx_no_overflow` everywhere + 4 hand range checks (root of RC2) — −60.
7. R_I51_7_PCREL / R_I51_16 should go through HOWTO + `_bfd_final_link_relocate` — −25.
8. Bit folding ×4, 11-bit page and 13-bit pcode encodings ×2 — shared helpers, −40.
9. 13 identical section-switch directives → one table-driven — −110.
10. Disassembler bypasses `print_address_func` for rel targets, no `insn_type`/`target`, byte read ×9 — −80.
11. AT89S8252 SFR table compiled into gas via `md_undefined_symbol` — −190.
12. `md_atof` → `ieee_md_atof` — −45. Dead code (R_I51_R1/R3, unused BFD_RELOC_I51_*, no-op hooks, ASMDBG) — −80.
13. Style: ~55 `//` comments, CamelCase, missing `static`, history-narrating comments.

## Upstream blockers [cq]

GPLv2 headers with the old FSF address (`include/opcode/i51.h` has none); copyright
assignment or DCO from every author; `config.sub` via config-patches@gnu.org first; **no
gas/ld/binutils DejaGnu tests**; no NEWS entries; the `.local` override; `//` comments,
CamelCase, 7× copy-paste.

## Suggested order

1. Regression tests first, one per CRITICAL item, marked xfail (DejaGnu `gas/testsuite/gas/i51`,
   `ld/testsuite/ld-i51`), plus a must-reject table and space-aware link tests in the gate.
2. RC1 (matcher) and RC2 (let fixups reach the linker, drop `fx_no_overflow`) — closes items 1–10.
3. RC3 (standard symbol resolution) — closes 11–13 and `--emit-relocs`.
4. RC5/RC6 (script: data init image, bank 0, stack, eeprom bound, distinct LMAs) — closes 17–22.
5. RC4 (address space in relocs) — an ABI decision (`e_flags` generation 1?), do last.

# Review: assembler + disassembler (i51)

Scope: `gas/config/tc-i51.c`, `gas/config/tc-i51.h`, `opcodes/i51-dis.c`,
`include/opcode/i51.h` (all in `mcs51/additions.patch`), plus the
`opcodes/disassemble.c/.h` and `gas/configure.tgt` hooks in
`mcs51/modifications.patch`.

Line numbers are lines **within the added file** as it appears in
`mcs51/additions.patch`, counted **before** the fixes in this branch.
Items marked **[FIXED]** are applied to `mcs51/additions.patch` here; the
rest are reported only.

Verified good, no findings: the opcode table in `include/opcode/i51.h` is
complete and correct. All 256 encodings were machine-checked against the
Intel MCS-51 map: every real opcode has exactly one matching entry, the
reserved `0xA5` has none, no opcode matches two entries, every
`bin_opcode`/`bin_mask` agrees with the bit-pattern string, every
instruction length matches, and the `0x80` "last variant of this mnemonic"
sentinel is set on the last entry of every mnemonic (the operand-scan
loops in `i51_parse_operand1/2` walk on that bit and would run off the
array if it were wrong). `@Ri`/`@DPTR`/`@A+DPTR`/`@A+PC`/`AB`/`DPTR` forms
are all present and encoded correctly. `gas/configure.tgt`,
`opcodes/disassemble.c` and `opcodes/disassemble.h` hooks are correct and
idiomatic.

---

## Critical

* **`anl C,/bit` and `orl C,/bit` disassemble to a fixed `/C` and never
  consume the operand byte.** `opcodes/i51-dis.c:176-178` prints the
  literal string `"/C"` for `args[1] == '/'`. `0xA0`/`0xB0` are two-byte
  instructions whose second byte is the bit address; the byte is skipped
  and the printed operand is wrong for *every* `/bit` instruction.
  Fix: read the byte and print `/0x%02X`. **[FIXED]**

* **`mov direct,direct` (`0x85`) disassembles with its operands
  reversed.** `0x85` is the one MCS-51 instruction that encodes the
  *source* byte first. `opcodes/i51-dis.c:125-131` puts the first operand
  byte in `op1` (printed as the destination) and `:182-188` puts the
  second in `op2`. The assembler gets this right
  (`tc-i51.c` mreloc `'d'`: `fixup8 (op_expr2)` then `fixup8 (op_expr1)`),
  so `as` and `objdump` disagree: `mov 0x30,0x40` assembles to `85 40 30`
  and disassembles as `mov 0x40, 0x30`.
  Fix: swap the operand strings when `args[0] == 'D'` (only `"DDN"`
  reaches that code). **[FIXED]**

* **Largest forward relative branches disassemble as backward branches.**
  `opcodes/i51-dis.c:77` declares `unsigned char rel_addr`; `:141`, `:198`
  and `:231` compute `rel_addr = opdata + 2 (+ offset)` and then test
  `rel_addr & 0x80` to pick the sign. The addition wraps, so a
  displacement of `0x7E`/`0x7F` on a two-byte branch tests as negative:
  `80 7f` printed `sjmp .-0x7F ; <addr-0x81>` instead of
  `sjmp .+0x81 ; <addr+0x7F>`. The target in the comment is wrong too,
  because it is computed as `addr + opdata - 0x100` using the wrapped
  sign decision.
  Fix: sign-extend `opdata` into an `int` first and decide the sign on the
  real displacement. **[FIXED]** (also masks the printed target to 16 bits;
  the old code printed a 64-bit wrapped value for backward branches near 0).

* **ACALL/AJMP 11-bit page semantics are not implemented in gas.**
  `check_range (I51_OP_JUMP_INPAGE)` at `tc-i51.c:1535` is
  `((num & 0xFFFFF800) == 0)` — it only accepts target addresses
  `0x0000..0x07FF`, regardless of where the instruction is. The ISA rule
  is different: only A10..A0 are encoded, A15..A11 come from the address
  of the *next* instruction, so the target must lie in the same 2K page as
  `PC+2` and may be anywhere in 0..0xFFFF. Consequences:
  a legal `ajmp 0x1234` from page 2 was rejected, and `md_apply_fix`'s
  `BFD_RELOC_I51_11` case (`tc-i51.c:866`) silently truncated A15..A11 with
  no page check at all. (`bfd/elf32-i51.c` `R_I51_11` does check the page,
  so only locally-resolved and constant operands were affected.)
  Fix: widen `check_range` to a 16-bit test, route the constant case
  through the fixup so the final instruction address is known, and do the
  `(target ^ (PC+2)) & 0xF800` test in `md_apply_fix`. **[FIXED]**

* **A constant target for a relative branch was emitted as a raw
  displacement.** `fixup8` at `tc-i51.c:1560` takes the `O_constant` path
  for `I51_OP_JUMP_REL` and falls into `default:`, which range-checks the
  *absolute address* against -128..127 and then stores `value & 0xFF` as
  the displacement. So `sjmp 0x0006` emitted `80 06` (jumping to
  `PC+2+6`) and `sjmp 0x0100` failed with "Operand out of 8-bit range",
  while the same branch to a *symbol* was computed correctly. Every 8051
  assembler treats the operand of `sjmp`/`jc`/`djnz`/`cjne` as an absolute
  target.
  Fix: always take the `fix_new_exp (..., pcrel=true, BFD_RELOC_I51_7_PCREL)`
  path; `gas/write.c:1117` subtracts `MD_PCREL_FROM_SECTION` for
  symbol-less pcrel fixups, so the displacement and the -128..127 check
  both come out right. **[FIXED]**
  **This is the one fix that changes bytes for input that assembles
  today** (`sjmp <literal>`). `tb/` could not be run here to confirm the
  golden ROMs are unaffected — `7z` is not installed in this environment.
  Run `make -C tb check` before merging.

## High

* **`md_apply_fix` reads two bytes for every one-byte fixup.**
  `tc-i51.c:830` does `insn = bfd_getb16 (where);` unconditionally, before
  the switch. Only the `BFD_RELOC_I51_11` case uses `insn`; for
  `BFD_RELOC_8`, `_8_LOW`, `_8_HIGH`, `_8_BIT` and `_7_PCREL` the fixup
  covers one byte and the second byte can be past the end of the frag
  buffer — an out-of-bounds read on a one-byte fixup at the end of a
  fragment.
  Fix: move the read into the cases that need it. **[FIXED]**

* **`BFD_RELOC_I51_8_B2B` and `BFD_RELOC_I51_13_PCODE` hit
  `default: as_fatal` in `md_apply_fix`.** Both are generated by this file
  (`fixup8` with `I51_OP_B2B`, and `i51_pcode`) and both become `fx_done`
  whenever the symbol is absolute or resolves in-section, at which point
  gas dies with "unknown relocation type: 0x..". `tc-i51.c:920`.
  Fix: add both cases, mirroring `R_I51_8_B2B` / `R_I51_13_PCODE` in
  `bfd/elf32-i51.c:388,410`. **[FIXED]**

* **`#imm` and `/bit` as the second operand break when a blank follows the
  comma.** `md_assemble` steps over the `,` with a bare `line++` and no
  `skip_space`; `i51_parse_operand2` then sets
  `input_line_pointer = line` (`tc-i51.c:1226`, still pointing at the
  blank) and the `#`/`/` branches do `input_line_pointer++` intending to
  drop the sigil — they drop the blank instead, leaving `expression()`
  looking at `#5` / `/P1.0`, which yields "missing operand 2". `mov a,#5`
  worked, `mov a, #5` did not. The same off-by-one silently defeats the
  `HIGH(` / `LOW(` prefix scan after `", "`.
  Fix: `line = skip_space (line)` before recording the operand start.
  **[FIXED]**

* **`fixup11` declares a one-byte fixup for a two-byte field.**
  `tc-i51.c:1667`: `fix_new_exp (frag_now, ..., 1, oper, false,
  BFD_RELOC_I51_11)` while `md_apply_fix` writes the field with
  `bfd_putb16` and `R_I51_11`'s howto is 16-bit. `fx_size` disagrees with
  both.
  Fix: size 2. **[FIXED]**

## Medium

* **The disassembler ignores memory-read failures.**
  `i51dis_opcode` returns `unsigned char` and `i51dis_op16` returns
  `unsigned short`; both `return -1` on error (`i51-dis.c:53,67`), which
  becomes `0xFF`/`0xFFFF` and is indistinguishable from real data. A
  truncated instruction at the end of a section was printed as if the
  missing bytes were `0xFF`, and `print_insn_i51` still returned the full
  length. Every other binutils disassembler returns -1 after calling
  `memory_error_func`.
  Fix: return `int`, propagate -1 out of `print_insn_i51`. **[FIXED]**

* **`bfd_vma` printed with `%lX`.** `i51-dis.c:144,147,153,201,204,234,237`.
  `bfd_vma` is `uint64_t`, which is `unsigned long long` on mingw-w64 —
  one of the five hosts this port is built for. Wrong output and
  `-Wformat`.
  Fix: cast to `unsigned long`. **[FIXED]**

* **The disassembler never calls `info->print_address_func`.** Branch,
  call and `ajmp` targets are printed as bare hex inside a `;` comment
  (`i51-dis.c:144,153,201,234`), so `objdump -d` shows no
  `<symbol+0x..>` annotation for any control transfer and
  `--disassemble=<func>` cross-referencing does not work. Standard
  binutils practice is `(*info->print_address_func) (target, info)` for
  anything that is an address. Not fixed — it changes output format.

* **No styled output.** The whole file prints through `info->fprintf_func`
  only. Since 2.38 disassemblers emit through `info->fprintf_styled_func`
  with `dis_style_mnemonic` / `dis_style_register` /
  `dis_style_immediate` / `dis_style_address`, which is what
  `objdump --disassembler-color=on` and the libopcodes ANSI styling hook
  drive. i51 output is unstyled and stays uncoloured. Not fixed — it is a
  rewrite of every print site.

* **`.using 1` was rejected.** `i51_using` at `tc-i51.c:1726` does
  `switch (*input_line_pointer++)` with no whitespace skip, so only
  `.using1` (no blank) was accepted; anything else produced
  "unsupported register bank". It also never calls
  `demand_empty_rest_of_line`, so `.using 0 garbage` is accepted silently.
  Fix: `SKIP_WHITESPACE ()` first. **[FIXED]** (the trailing-garbage check
  is not added.)

* **`get_symbol_name` is called with the wrong pointer type.**
  `tc-i51.c:995` (`i51_local`) and `:1785` (`i51_common`) declare
  `const char *name;` and pass `&name` to `get_symbol_name (char **)`.
  GCC reports `-Wincompatible-pointer-types`; this is a constraint
  violation that a stricter C2x compiler will reject outright. `i51_local`
  then passes the `const char *` to `extract_op (char *, ...)`
  (`-Wdiscarded-qualifiers`). The build only survives because
  `tb/Makefile:111` passes `--disable-werror`. Not fixed — `name` should
  be `char *` and `i51_common`'s `*p = 0; ... *p = c;` dance reworked
  with `restore_line_pointer` properly.

* **File-scope globals with generic names, one of which collides with
  libopcodes.** `tc-i51.c` defines non-static `i51_opcodes` (`:155`),
  `opcode`, `oper`, `op`, `line`, `regno`, `op_expr1..4`, `op1mode`,
  `op2mode`, `b2b_offset` (`:359-370`); `i51-dis.c` defines its own
  non-static `i51_opcodes` with a *different* struct layout. gas links
  `libopcodes.a`, so the two only fail to clash today because nothing in
  gas references `print_insn_i51` and the archive member is never pulled
  in. With `-fno-common` (GCC 10+ default) these are definitions, not
  tentative ones. The compiler already reports 11
  `-Wshadow` "declaration of 'oper'/'opcode'/'op_expr1' shadows a global"
  warnings from this. Fix: `static` on both `i51_opcodes` arrays
  **[FIXED]**; the rest should be made `static` and given an `i51_` prefix.

* **`md_undefined_symbol` clobbers the parser's globals.**
  `tc-i51.c:1018` writes the shared `op[11]` buffer and the shared `oper`
  pointer. It is called from `expression()`, which
  `i51_parse_operand1/2` call while holding both. Currently benign only
  because neither is re-read after `expression()` outside `#ifdef ASMDBG`.
  It also truncates symbol names to 10 characters before the operand-table
  lookup (`sizeof (op)`), which is harmless only because every table name
  is 7 characters or fewer. Fix: use a local buffer.

## Low

* **`{"/C", '/', 0}` in `i51_directop` (`tc-i51.c:179`) is broken.**
  `anl C,/C` takes the hash-hit path in `i51_parse_operand2`, which sets
  `op2mode = '/'` and then falls through none of the `D`/`B`/`U` branches,
  so no expression is ever produced: `op_expr1` stays `O_max` and `fixup8`
  builds a fixup over an uninitialised expression. `/CY` and `/P1.0` work
  because they take the miss path. Fix: drop the entry, or give it
  `'B', 0xD7`.

* **`md_section_align` shifts a negative `int`.** `tc-i51.c:752`:
  `(addr + (1 << align) - 1) & (-1 << align)`. Left-shifting a negative
  value is undefined (C11 6.5.7p4) and the mask is `int`-typed against a
  `valueT`. Fix: `& -((valueT) 1 << align)`. **[FIXED]**

* **`md_assemble` checks the wrong expression for a missing operand 3.**
  `tc-i51.c:699`: after `expression (&op_expr2)` for the `cjne` relative
  operand it tests `op_expr1.X_op == O_absent`. A missing third operand is
  not diagnosed. Fix: test `op_expr2`. **[FIXED]**

* **`.pcode` range diagnostics print the wrong operand.** `tc-i51.c:2562`
  and `:2567` check `op_expr1.X_add_number` but print
  `op_expr4.X_add_number`; the second message also reads
  "Pcode exec addrss uderflow". **[FIXED]**

* **`toupper` on a plain `char`.** `tc-i51.c:517`:
  `to[size++] = toupper(*op_end++)` — undefined for bytes >= 0x80 on
  signed-char hosts. binutils uses `safe-ctype.h`'s `TOUPPER` everywhere
  for exactly this. Fix: cast to `unsigned char`. **[FIXED]**

* **`unsigned char *where = fixp->fx_frag->fr_literal + ...`**
  (`tc-i51.c:777,829`) assigns a `char *` to an `unsigned char *` without
  a cast, and every use then casts back to `(bfd_byte *)`. Fix: declare it
  `bfd_byte *` and cast once. **[FIXED]**

* **`struct hash_control` no longer exists.** `tc-i51.c:355,357` declare
  `static struct hash_control *i51_hash;` and assign `str_htab_create ()`
  to it. `hash_control` was removed from gas in 2.36; the declaration only
  compiles because it is an incomplete type behind a pointer, and every
  `str_hash_insert`/`str_hash_find` call passes an incompatible pointer.
  Fix: `static htab_t`. **[FIXED]**

* **`print_insn_i51` had no prototype in scope.** `i51-dis.c` did not
  include `disassemble.h`, so `-Wmissing-prototypes` fired and the
  definition was never checked against the declaration.
  Fix: `#include "disassemble.h"`. **[FIXED]**

* **Disassembler operand buffers are tight.** `char op1[10], op2[10],
  op3[10]` (`i51-dis.c:83`) with `sprintf`. No overflow was reachable with
  the original narrow types, but the buffers leave no headroom
  (`"@A+DPTR"` is 8 bytes, `"#0x1234"` is 8) and GCC's
  `-Wformat-overflow` flags them as soon as the value types widen.
  Fix: 16 bytes. **[FIXED]** Better still: print through
  `info->fprintf_func` directly and drop the buffers.

* **`case '6'` advanced `addr` by 1 after a 16-bit read.**
  `i51-dis.c:156-158`. Latent only — `ljmp`/`lcall` have no further
  operands. **[FIXED]**

* **`i51_fold_bit_suffix` has no upper bound on the SFR case.**
  `tc-i51.c:466`: `else if (addr >= 0x80 && (addr & 7) == 0)` accepts
  `0x100.0` and folds it to `0x100`; only the generic 8-bit check
  downstream catches it. Fix: `addr >= 0x80 && addr <= 0xF8`.

* **`MD_APPLY_FIX3` (`tc-i51.h:95`) is dead.** Removed from gas long ago.
  `tc-i51.h` also carries a large amount of commented-out AVR-derived
  boilerplate (`:51-52`, `:60-71`, `:97-103`, `:112`, `:147-157`) that
  should not be in a file submitted against a 2.47 tree.

* **`R_I51_7_PCREL`'s name says 7, the field is 8 bits.** `md_apply_fix`
  checks -128..127 (`tc-i51.c:854`) and `bfd/elf32-i51.c` checks the same.
  Cosmetic, but the name misleads.

* **`tc_gen_reloc`'s `reloc->addend -= 1` for pcrel fixups
  (`tc-i51.c:1082`) is undocumented magic.** It compensates for
  `i51_final_link_relocate`'s `R_I51_7_PCREL` case, which subtracts
  `r_offset` (the address of the displacement byte) rather than the
  address of the next instruction. The two agree, but neither says so.
  Add a comment on both sides.

* **`bfd/elf32-i51.c`'s `R_I51_11` page test uses the wrong PC.**
  Out of scope for this review but it is the link-time half of the
  ACALL/AJMP finding above: it tests
  `srel ^ (r_offset + section vma)`, i.e. the address of the *opcode*
  byte, where the ISA uses the address of the *next* instruction. An
  `ajmp` at `0x07FE` targeting `0x0802` is legal and is rejected; one at
  `0x07FE` targeting `0x0002` is illegal and is accepted.

* **Bit-addressable SFR name coverage is uneven.** `i51_directop` has
  `P0.x`-`P3.x`, `ACC.x`, `B.x` and `T2CON.x` in dotted form but no
  `TCON.x`, `SCON.x`, `IE.x`, `IP.x` or `PSW.x`; `PSW.1` is spelled `FL`
  where Intel and most assemblers use `F1`; `IE.6`, `IP.6` and `IP.7` are
  absent. Numeric `0xB8.2`-style operands do work via
  `i51_fold_bit_suffix`.

* **No target options at all.** `md_shortopts` is `""`, `md_longopts` holds
  only the terminator, `md_parse_option` always returns 0 and
  `md_show_usage` prints "A51 options: NONE" (`tc-i51.c:528-546`). The
  device-specific SFRs hard-coded in `i51_directop` (AT89S8252 `DP1L`,
  `SPDR`, `WMCON`, `SPSR`, `SPCR`; 8052 `T2CON`/`RCAP2*`/`TH2`/`TL2`)
  are therefore always defined, with no way to select a plain 8051.
  A `-mcpu=` option would be the binutils-idiomatic answer.

* **`symbols_case_sensitive = 0` is set from inside `md_begin`'s body**
  via a function-local `extern` declaration (`tc-i51.c:551`). It is
  declared in `symbols.h`; the local `extern` is redundant. Note that this
  uppercases *every* symbol in the assembly, which is why
  `tb/i51elf_sym_uc.py` exists — but the *mnemonic* lookup in
  `md_assemble` (`str_hash_find (i51_hash, op)`) is still case-sensitive
  against a lowercase table, so `MOV A,R0` is rejected as
  "unknown opcode" while `mov a,r0` is accepted. Operands are uppercased
  (`extract_op`), mnemonics are not. Inconsistent; most MCS-51 source in
  the wild is uppercase.

* **Build system: `tc-i51.c` and `i51-dis.c` are in no `Makefile.am`
  source list.** `mcs51/modifications.patch` adds `i51-dis.c` to
  `opcodes/Makefile.am:TARGET32_LIBOPCODES_CFILES` but not to
  `opcodes/Makefile.in`, and never touches `gas/Makefile.am` or
  `gas/Makefile.in` at all. Both files build today only through
  automake's generic `.c.o` rule; `make dist` and dependency tracking miss
  them, and a tree that regenerates `Makefile.in` will drop `i51-dis.c`
  from `libopcodes`.

* **Licence headers are wrong for a 2.47 tree.** Both files say
  "Copyright (C) 2001" with the GPL **v2**-or-later notice and the old
  "59 Temple Place" FSF address. New binutils files must carry GPLv3+ and
  the current boilerplate. `tc-i51.c` also uses `//` comments throughout
  and includes `<stdio.h>`/`<ctype.h>` after `as.h` (which already
  provides both).

* **Dead locals.** `op_start` in `extract_word`/`extract_op`
  (`tc-i51.c:481,506`), `fixp` in `fixup16` (`:1749`) and in three
  `writePcodeOperand` branches (`:2328,2349,2626`) are set and never used;
  `i51_pcode`'s `pflags`/`temppflags`/`f` warn as well.

---

## Verification performed

* Applied the patched `mcs51/*.patch` to a clean `binutils-2.47` tree;
  both apply without fuzz. `gas/as-new`, `libopcodes` and `objdump` build
  with no errors and no new warnings in `i51-dis.c`.
* Machine-checked all 256 opcodes against a reference MCS-51 map for
  entry coverage, first-match ambiguity, instruction length and
  `bin_opcode`/`bin_mask`/bit-pattern agreement: zero discrepancies.
* Assembled and disassembled a probe covering `mov a, #5` (blank after
  comma), `anl c, /p1.0`, `mov 0x30,0x40`, `mov dptr,#0x1234`,
  `mov 0x90.3,c`, `cjne`, `djnz`, `jb acc.7`, `orl c,/0xd7`, `sjmp`,
  `ajmp 0x0123`, `ajmp 0x1234` (rejected, correct page diagnostic) and
  raw `.byte` sequences for displacement `0x7E`/`0x7F`/`0x80`.
* **Not** run: `make -C tb check` against the golden ROMs — `7z` is not
  installed in this environment. Do this before merging, specifically
  because of the `sjmp <literal>` change.

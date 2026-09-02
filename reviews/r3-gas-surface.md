# gas surface audit — everything except instruction encoding

Scope: the layer a programmer actually types. Directives, symbol case folding, expressions and
operands, standard gas machinery, diagnostic quality. Instruction encoding, the opcode table,
ACALL/AJMP paging, branch displacements, bit-address folding boundaries, howto/reloc internals,
the ld script and the testbench were audited in earlier rounds and are not re-covered here.

Toolchain under test: `make -C tb build` → binutils 2.47 + `mcs51/*.patch`, target `i51-elf`.
All command output below is verbatim. `AS` = `work/modern/build/gas/as-new`.

Seven defects were fixed in this branch (marked **FIXED**); the rest are reported.
After the fixes the full gate still passes: `isa roundtrip branch bits reloc commons
defaultlink sim oracle` all PASS and all 10 projects reproduce their reference ROM byte for byte.

---

## Findings, worst first

### S1. `mov a,AR0` without `.using` killed gas with an internal error — **FIXED**

Before:

```
$ printf '.text\nmov a,ar0\n' > z.s ; AS -o z.o z.s
z.s: Assembler messages:
z.s:2: Error: missing .using
z.s: Fatal error: Case value 63 unexpected at line 1382 of file "../../binutils-2.47/gas/symbols.c"
```

Not one instruction — the whole `AR0..AR7` family, 8/8 forms tested:

```
  mov a,ar0      Fatal error: Case value 63 unexpected ...
  mov ar0,a      Fatal error: Case value 63 unexpected ...
  mov ar0,#1     Fatal error: Case value 63 unexpected ...
  xch a,ar3      Fatal error: Case value 63 unexpected ...
  inc ar2        Fatal error: Case value 63 unexpected ...
  add a,ar5      Fatal error: Case value 63 unexpected ...
  mov ar1,ar2    Fatal error: Case value 63 unexpected ...
  mov ar0,ar1    Fatal error: Case value 63 unexpected ...
```

Root cause is general, not specific to `.using`. `md_assemble` presets
`op_expr1.X_op = op_expr2.X_op = O_max` as an "unset" marker. `i51_parse_operand1/2` are `void`:
on an error they call `as_bad` and `return`, leaving the marker in place — but `md_assemble` then
still runs `i51_build_ins`, which hands the `O_max` expression to `fix_new_exp`, and gas aborts
in `make_expr_symbol`. Any future `as_bad` added to either operand parser inherits the same crash.

Fix: `md_assemble` snapshots `had_errors()` and emits nothing if the count moved.
After:

```
$ printf '.text\nmov a,ar0\n' > z.s ; AS -o z.o z.s ; echo exit=$?
z.s: Assembler messages:
z.s:2: Error: missing .using
exit=1
```

`.using 1` / `mov a,ar0` still assembles to `e5 08`, `mov ar7,a` to `f5 0f` — unchanged.

### S2. `--defsym name=value` never bound, because case folding starts too late — **FIXED**

Before:

```
$ printf '.text\nljmp foo\n' > ds.s
$ AS --defsym foo=0x40 -o ds.o ds.s ; objdump -dr ds.o
   0:	02 00 00    	ljmp	0x0000
			1: R_I51_16	FOO         <-- unresolved
$ AS --defsym FOO=0x40 -o ds.o ds.s ; objdump -dr ds.o
   0:	02 00 40    	ljmp	0x0040       <-- only the shouted spelling worked
```

`tc-i51.c` set `symbols_case_sensitive = 0` inside `md_begin`. gas defines the `--defsym`
symbols in `gas_init()`, which runs *before* `perform_an_assembly_pass()` calls `md_begin`
(`gas/as.c:1426` vs `gas/as.c:1293`). So `--defsym` names were the only symbols in the whole
assembler that stayed as written, and therefore could never match a reference from the source.

Fix: moved to a `tc_init_after_args()` hook, which `gas_init()` calls immediately before the
defsym loop. After: all three spellings resolve to `02 00 40`.

### S3. Everything after `.using <n>` was assembled as an instruction — **FIXED**

`i51_using` never called `demand_empty_rest_of_line`, so the reader picked up the rest of the
line as a fresh statement:

```
$ printf '.using 1 nop\n' > z.s ; AS -o z.o z.s ; echo exit=$? ; objdump -s -j .text z.o
exit=0
Contents of section .text:
 0000 00                                   .            <-- a nop nobody wrote
```

It also stepped over the character it rejected, so `.using` at end of line consumed the newline
and shifted every following line number, and the message named the wrong problem
("unsupported register bank" for a missing argument).

Fix: accurate message, `ignore_rest_of_line` on the bad path, `demand_empty_rest_of_line` on the
good one. After:

```
$ printf '.using 1 nop\n' > z.s ; AS -o z.o z.s ; echo exit=$?
z.s:1: Error: junk at end of line, first unrecognized character is `n'
exit=1
$ printf '.using\n' > z.s ; AS -o z.o z.s
z.s:1: Error: expected a register bank number 0, 1, 2 or 3
```

### S4. `.pcode` keyword matching ate the front of symbol names — **FIXED**

`pcodeOperand` matched its mode keywords with bare `strncmp`, no word boundary:

```
$ printf '.equ BYTECOUNT,5\n.text\n.pcode 0x100 BYTECOUNT\n' > z.s ; AS -o z.o z.s ; echo exit=$?
exit=0
$ objdump -sr -j .text z.o
00000003 R_I51_8           COUNT                     <-- "BYTE" eaten, "COUNT" relocated
 0000 01004000                             ..@.
$ printf '.equ WORDS,5\n.text\n.pcode 0x100 WORDS\n' | ...
00000003 R_I51_16          S                          <-- "WORD" eaten, "S" relocated
```

Silent. Exit 0. A wrong object referencing a symbol the source never mentions.

Fix: `pcode_keyword()` requires the keyword not to be followed by a name character. After, both
assemble as plain operands (`01 00 40 05`), while the real project syntax
`.pcode 0x100 #BYTE SZ` (`work/base/projekt/diag/www8051.asm:178`) is unchanged (`01 00 40 07`).

### S5. `mov a,#-129` … `#-256` were silently truncated — **FIXED**

`check_range(I51_OP_IMM8/I51_OP_BIT)` only asked that the top 24 bits were all-0 or all-1:

```
  #-128  exit=0 bytes=7480
  #-129  exit=0 bytes=747f     <-- wrong value, no diagnostic
  #-255  exit=0 bytes=7401
  #-256  exit=0 bytes=7400
  #-257  exit=1 Error: Operand out of 8-bit range
```

Fix: the range is `-128..255`. After, `#-129` and below are rejected; `#-128`, `#-60`, `#-'1'`
and `#255` still assemble to the same bytes as before, and all 10 project ROMs are unchanged.

### S6. `.comm sym,size,align` recorded the wrong alignment — **FIXED**

`i51_common` converts the byte alignment to a power of two with a loop that destroys `temp`,
then passes the wreckage to `S_SET_ALIGN` — which for ELF *is* the common symbol's alignment:

```
$ printf '.comm av,4,4\n.comm bv,4,16\n' > al.s ; AS -o al.o al.s ; readelf -s al.o
   4: 00000001     4 OBJECT  GLOBAL DEFAULT  COM AV     <-- asked for 4, recorded 1
   5: 00000001     4 OBJECT  GLOBAL DEFAULT  COM BV     <-- asked for 16, recorded 1
```

Every explicitly aligned common in the whole memory-space family came out unaligned. Fix: keep
the requested value. After:

```
   4: 00000004     4 OBJECT  GLOBAL DEFAULT  COM AV
   5: 00000010     4 OBJECT  GLOBAL DEFAULT  COM BV
   7: 00000008     4 OBJECT  GLOBAL DEFAULT PRC[0xff01] DV   (.rcomm dv,4,8)
```

### S7. One bad bit address produced three errors, one on a line that does not exist — **FIXED**

```
$ printf '.text\nsetb 0x31.2\nnop\n' > bs.s ; AS -o bs.o bs.s
bs.s:2: Error: 0x31 is not bit addressable
bs.s:2: Error: garbage at end of line
bs.s:3: Error: junk at end of line, first unrecognized character is `2'   <-- line 3 is "nop"
```

`i51_fold_bit_suffix` returned without stepping over `.2`, so the leftovers were re-read.
Fix: consume the suffix on both paths. After: one error, correct line, exit 1.

### S8. `-g` is a silent no-op — **REPORTED, structural**

```
$ printf '.text\n.global _start\n_start: nop\nnop\n' > dbg.s
$ AS -g        -o dbg.o dbg.s ; echo exit=$? ; readelf -S dbg.o | grep -c debug
exit=0
0
$ AS -gdwarf-5 -o dbg.o dbg.s ; readelf -S dbg.o | grep -c debug
0
$ printf '.text\n.file 1 "a.s"\n.loc 1 2 0\nnop\n' > v.s ; AS -o v.o v.s ; readelf -S v.o | grep -c debug
0
```

No `.debug_line`, no `.debug_info`, no warning, exit 0. Cause: `md_assemble` never calls
`dwarf2_emit_insn()`, which is what makes gas record a line entry per instruction, and
`tc-i51.c` contains no reference to dwarf2 at all. `.file`/`.loc` are accepted and discarded.
`-gstabs` at least fails, though the message is about a relocation number:

```
$ AS -gstabs -o dbgs.o dbg.s ; echo exit=$?
dbg.s: Error: reloc 2 not supported by object file format
dbg.s:3: Error: reloc 2 not supported by object file format
exit=1
```

Fixing this is a feature (add `dwarf2_emit_insn` to `md_assemble`, add `BFD_RELOC_32` to the
howto table for stabs) and was left out of this branch. At minimum `-g` should say it does
nothing on this target rather than exit 0 with an empty object.

### S9. `.local` is not gas's `.local`, and the local-common code it gates is dead — **REPORTED, structural**

The port binds `.local` to `i51_local`, which only deletes names from the built-in operand hash
so `wr:` or `.equ ACC,…` become usable. `md_pseudo_table` is inserted first in `pobegin()`
(`gas/read.c:597`), so ELF's `obj_elf_local` is skipped entirely. `symbol_get_obj(sym)->local`
is set nowhere else in gas except section-group signature symbols
(`gas/config/obj-elf.c:366`, `:2820`) — so the ~120-line "allocate in `.rbss`/`.bbss`/…"
branch of `i51_common` can never run, and every common is global:

```
$ printf '.local sv\n.comm sv,4\n' > lc.s ; AS -o lc.o lc.s ; echo exit=$? ; nm lc.o
exit=0
00000004 C SV                              <-- still a global common
```

`.local sv` on a name that is not a built-in operand is a silent no-op. There is no way to get a
file-scope private object in any memory space.

Useful side of `.local` (this does work, and the projects use it —
`work/base/projekt/serial/ipsetup.asm:1` is `.local WMCON, F0`):

```
$ printf '.local ACC\n.equ ACC,0x55\n.text\nmov a,ACC\n' > v.s ; AS -o v.o v.s
   0:	e5 55       	mov	A, 0x55
$ printf '.equ ACC,0x55\n.text\nmov a,ACC\n' > v.s ; AS -o v.o v.s
v.s:1: Error: symbol `ACC' is already defined
```

### S10. ~130 identifiers are reserved words with no diagnostic that says so — **REPORTED, structural**

The operand hash is consulted on the raw operand text before any symbol lookup, and the text is
upper-cased first, so a label whose folded name collides with an SFR, bit or register name is
unusable — even when it is defined in the same file:

```
$ for id in a b c p ps ie es ea rd wr t0 t1 t2 sp ov cy ac fl acc dptr ; do
    printf '.text\n%s: nop\nljmp %s\n' $id $id > rw.s ; AS -o rw.o rw.s ; done
  a      exit=1 rw.s:3: Error: unknown instruction operand 1: `A'
  b      exit=1 rw.s:3: Error: unknown instruction operand 1: `B'
  ...
  dptr   exit=1 rw.s:3: Error: unknown instruction operand 1: `DPTR'
```

20/20 tested names fail. The full list is `i51_directop[]` in `tc-i51.c` — every SFR, every
named bit and every alias, ~130 entries including `B`, `C`, `P`, `PS`, `IE`, `ES`, `EA`, `RD`,
`WR`, `T0`, `T1`, `T2`, `FL`, `OV`, `AC`, `CY`. Not silent — but the message blames the
instruction, not the name, and the escape hatch (`.local`) is undocumented and non-obvious.

### S11. `sym.N` bit addressing on a `.equ` base silently produces a garbage symbol — **REPORTED, structural**

```
$ printf '.equ BASE,0x20\n.text\nsetb BASE.3\n' > v.s ; AS -o v.o v.s ; echo exit=$?
exit=0
$ objdump -dr v.o
   0:	d2 00       	setb	0x00
			1: R_I51_8_BIT	BASE.3          <-- a symbol named "BASE.3"
```

`.` is a symbol character in gas, so `expression()` swallows the suffix and
`i51_fold_bit_suffix` (which only handles `O_constant`) never sees it. The object links only if
something else happens to define `BASE.3`; otherwise the failure surfaces at link time as an
undefined symbol with a name the programmer never wrote. Workarounds that do work:

```
$ printf '.equ BASE,0x20\n.text\nsetb (BASE).3\n'  ->  d2 03    (parenthesised base folds)
$ printf '.text\nsetb 0x20.3\n'                    ->  d2 03
$ printf '.text\n.rcomm FLAGS,1\nsetb B2B(FLAGS,3)\n' -> d2 03 + R_I51_8_B2B FLAGS
```

### S12. Two symbols differing only in case collide; `.equ` collides silently — **REPORTED, by design**

`md_begin` (now `i51_init_after_args`) sets `symbols_case_sensitive = 0`, so
`gas/symbols.c:356` upper-cases every symbol name at creation. Consequences, all measured:

| situation | result |
|---|---|
| `Foo: nop` then `foo: nop` | `Error: symbol \`foo' is already defined`, exit 1 — caught |
| `.equ Val,1` then `.equ VAL,2`, `.byte Val,VAL` | `.data = 02 02` — **silent**, last wins |
| `.global MixedCase` + `MixedCase: nop` + `ljmp mixedcase` | one symbol, links |
| `nm` on the object | `00000000 T MIXEDCASE` — no round trip, the source spelling is gone |
| `.extern Thing` | `U THING` |
| foreign object whose symbol stayed lower case | `undefined reference to \`HELPER'`, ld exit 1 |
| linker script `PROVIDE(gsinit=…)` vs `PROVIDE(GSINIT=…)`, source `ljmp gsinit` | binds to **GSINIT** |
| `.section MySec,"a"` | section name **not** folded: `[ 4] MySec` |
| `.macro Two` invoked as `two 1,2` | works (gas folds macro names itself) |

**The rule:** every name that has to match across the gas boundary must be written in upper case
on the non-gas side — linker scripts, hand-written or foreign objects, `ar` scripts, `--wrap`,
`-u`, `--defsym`. Names that never leave gas may be written in any case. Section names are the
one exception: they are *not* folded, so `.section MySec` must be spelled `MySec` in the script
too. `ld/scripttempl/elf32i51.sc` already uses upper case throughout (`ENTRY(_START)`,
`PROVIDE (__GSINIT_STARTUP = __I51_RET)`), and `tb/i51elf_sym_uc.py` exists to fold foreign
libraries — this is the general rule those two artefacts are instances of.

### S13. `HIGH()`/`LOW()`/`B2B()` are upper-case-only and instruction-only — **REPORTED**

```
$ printf '.equ V,0x5678\n.text\nmov a,#HIGH(V)\n'  -> 74 56   ok
$ printf '.equ V,0x5678\n.text\nmov a,#HIGH (V)\n' -> 74 56   ok (gas squeezes the space out first)
$ printf '.equ V,0x5678\n.text\nmov a,#high(V)\n'
  x.s:3: Error: garbage at end of line
  x.s:4: Error: unknown opcode `v'                            <-- second error is noise
$ printf '.equ V,0x5678\n.text\nmov a,#HIGH V\n'
  x.s:3: Error: garbage at end of line
$ printf '.equ V,0x5678\n.data\n.byte LOW(V)\n'
  x.s:3: Error: junk at end of line, first unrecognized character is `('
```

Matched with `strncmp` against the raw line in `i51_parse_operand1/2`, so: lower case does not
work (in an assembler that is otherwise entirely case-insensitive), the parentheses are
mandatory, and the operators do not exist in `.byte`/`.word`. A `.equ HIGH,0x42` is shadowed
whenever it is followed by `(`. All of these produce an error rather than wrong code, but the
second error in the lower-case case is invented.

### S14. `$` cannot appear in a symbol name — **REPORTED**

`line_separator_chars[] = "$"`, so:

```
$ printf '.text\nmy$sym: nop\n' > v.s ; AS -o v.o v.s
v.s:2: Error: unknown opcode `my'
```

Matters for objects produced by C toolchains, which commonly emit `$` in local label names.
The diagnostic does not mention `$`.

### S15. `.pcode` takes no comma after its first operand, and says so badly — **REPORTED**

```
$ printf '.text\n.pcode 0x100,#1,#2,#3\n' > v.s ; AS -o v.o v.s
v.s:2: Error: junk at end of line, first unrecognized character is `,'
$ printf '.text\n.pcode 0x100 #1,#2,#3\n'   -> ok, 01 00 54 01 02 03
```

The exec address is separated by whitespace, the three operands by commas — as in
`work/base/projekt/diag/www8051.asm:178`. Nothing in the diagnostic hints at that.
`.pcode` with no argument at all reports `pcode exec address underflow: 0x0`, which is true but
unhelpful.

---

## Directive table

Verdict key: **ok** = correct behaviour and a real diagnostic on bad input; **fixed** = was
broken, fixed on this branch; **gap** = accepted but does something other than what its name
suggests; **broken** = wrong output or wrong diagnostic, still outstanding.

| directive | emits / does | section | binding | size | align | verdict |
|---|---|---|---|---|---|---|
| `.using N` | sets AR0..AR7 base to `N*8`; `__RB__` common at end of file | `.regbank` (fake common) | GLOBAL | — | — | **fixed** (S3); valid `N` still gives `mov a,ar0` = `e5 08` at bank 1 |
| `.comm`/`.common` | common symbol | `COM` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.rcomm`/`.rcommon` | common in register/direct RAM | `PRC[0xff01]` = `.rbss` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.bitcomm`/`.bitcommon` | common in bit space | `PRC[0xff02]` = `.bitbss` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.icomm`/`.icommon` | common in indirect RAM | `PRC[0xff03]` = `.ibss` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.xcomm`/`.xcommon` | common in external RAM | `PRC[0xff04]` = `.xbss` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.ecomm`/`.ecommon` | common in on-chip "external" RAM | `PRC[0xff05]` = `.ebss` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.bcomm`/`.bcommon` | common in bit-addressable RAM | `PRC[0xff06]` = `.bbss` | GLOBAL | arg 2 | arg 3 | **fixed** (S6) |
| `.local` | deletes a name from the built-in operand hash | — | — | — | — | **gap** (S9): is *not* ELF `.local`; silent no-op on any other name; the memory-space local-common code it was meant to gate is unreachable |
| `.bit v[,v…]` | one **byte** per bit, value 0 or 1 | current | — | 1 B/bit | 1 | **ok**; `.bit 2` / `.bit -1` / `.bit 0x100` → `bit value is not in range 0..1`; `.bit` alone is a no-op; `.bit sym` emits `R_I51_8` with no range check; `.bit` works in `.text` too (3 bits → 3 bytes) |
| `.pcode addr op,op,op` | 3-byte header + operands | current | — | var | 1 | **fixed** (S4); syntax quirk and weak diagnostics stand (S15) |
| `.equ` / `.set` | gas `s_set` | absolute | LOCAL unless `.global` | — | — | **ok**; redefinition allowed by design; case collision is silent (S12) |
| `.rdata` `.bdata` `.idata` `.xdata` `.edata` `.bitdata` `.eeprom` | switch to the space, `PROGBITS WA` | own | — | — | 1 | **ok**; optional subsection number accepted; junk → `bad or irreducible absolute expression` |
| `.rbss` `.bbss` `.ibss` `.xbss` `.ebss` `.bitbss` `.bss` | switch to the space, `NOBITS WA` | own | — | — | 1 | **ok**; `.byte 1` there → `attempt to store non-zero value in section '.rbss'`; `.align`/`.space` work |
| `.byte` `.word` `.short` `.2byte` `.ascii` `.asciz` `.string` `.skip` `.space` `.fill` `.float` `.double` | standard | current | — | — | — | **ok**, big-endian throughout (`.word 0x1234` → `12 34`, matching the instruction stream; `.float 1.0` → `3f800000`) |
| `.long` `.int` `.4byte` | 4 bytes big-endian | current | — | — | — | **ok** for constants; **broken** for a relocatable operand: `reloc 2 not supported by object file format` (no `BFD_RELOC_32` in the i51 howto table) — errors, but names a BFD number, not `.long` |
| `.org` `.align` `.p2align` | standard | — | — | — | — | **ok**; `.align 4` = 16-byte (ELF power-of-two convention); backwards `.org` → `attempt to move .org backwards`; neither reaches the `abort()` in `md_estimate_size_before_relax`/`md_convert_frag` |
| `.section` | standard | named | — | — | — | **ok**; section names are **not** case folded |
| `.global` `.globl` `.extern` `.weak` `.type` `.size` | standard | — | — | — | — | **ok**; names folded to upper case (S12) |
| `.macro` `.rept` `.irp` `.if` `.ifdef` `.else` `.endif` `.include` `.err` `.print` `.title` `.psize` | standard | — | — | — | — | **ok**; unterminated `.if` → `end of file inside conditional` + the opening line |

## Standard gas machinery — measured

| feature | result |
|---|---|
| `-a` listing | works, one byte per column (`LISTING_WORD_SIZE 1`): `2 0000 00 nop` / `3 0001 74 05 mov a,#5` |
| `--fatal-warnings` | works: `Error: 1 warning, treating warnings as errors`, exit 1, no object |
| `-g` / `-gdwarf-5` | **silent no-op**, exit 0, zero debug sections (S8) |
| `-gstabs` | fails with `reloc 2 not supported by object file format` (S8) |
| uppercase mnemonics `MOV A,#5` | work — gas core lower-cases the mnemonic before `md_assemble` |
| comment `;`, line comment `#`, C comment `/* */` | all work; `#` at line start is a comment while `#5` stays an immediate |
| `$` | statement separator, so unusable in symbol names (S14) |
| exit code after an error | 1, and **no object is written** — checked on every error path above |
| error recovery | gas continues reading the file (multiple errors reported per run) but never emits an object once `had_errors()` is non-zero |

## Diagnostic quality

Accurate, right line, right exit code: the `.comm` family, section-space directives, `.bit`
range, `.org` backwards, unterminated `.if`, unknown pseudo-op, unknown opcode, invalid operand
combinations, immediate out of range, redefinition, `.equ` shadowing an SFR.

Inaccurate but still an error (all reported above, none fixed):

- `#high(V)` → `garbage at end of line` **plus** an invented `unknown opcode \`v'` on the next line (S13).
- `my$sym:` → `unknown opcode \`my'` — never mentions `$` (S14).
- `.pcode 0x100,#1` → `junk at end of line, first unrecognized character is \`,'` (S15).
- `.pcode` with no argument → `pcode exec address underflow: 0x0` (S15).
- `.long target` → `reloc 2 not supported by object file format` — a BFD enum value, not a name.
- `ljmp b` where `b:` is a label in the same file → `unknown instruction operand 1: \`B'`,
  which blames the instruction rather than saying `B` is the accumulator-extension register (S10).
- The `.comm` size-mismatch warning always says `.comm` even for `.rcomm`/`.xcomm`/…:
  `Warning: Length of .comm "SYM" is already 4. Not changed to 8.`

gas on this target never reports columns; that is upstream behaviour, not a port defect.

Silent wrong behaviour found: S2, S3, S4, S5, S6, S9, S11, and the `.equ` case collision in S12.
S2–S6 are fixed; S9, S11 and S12 stand.

## Files touched

- `mcs51/additions.patch` — `gas/config/tc-i51.c` and `gas/config/tc-i51.h`
  (S1 `md_assemble` error guard, S2 `i51_init_after_args` + `tc_init_after_args`,
  S3 `i51_using`, S4 `pcode_keyword`, S5 `check_range`, S6 `i51_common` alignment,
  S7 `i51_fold_bit_suffix`).

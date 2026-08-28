# REVIEW-unfinished — what does nothing, what is half-built, what never fires

Head reviewed: `0f45319` (`origin/work/green`). Review only; nothing was changed.

## Method

Coverage, not grep. The two patches were applied to a pristine binutils 2.47 and
built with `-O0 -g -fprofile-arcs -ftest-coverage`:

```
$ patch --fuzz 0 -p1 -d /home/user/work-cov/binutils-2.47 < mcs51/additions.patch
$ patch --fuzz 0 -p1 -d /home/user/work-cov/binutils-2.47 < mcs51/modifications.patch   # no offsets, no fuzz
$ ../binutils-2.47/configure --target=i51-elf --disable-nls --disable-werror \
      --disable-gdb --disable-shared CFLAGS="-O0 -g -fprofile-arcs -ftest-coverage" \
      LDFLAGS="-fprofile-arcs"
$ make -j4 all-bfd all-opcodes all-gas all-ld all-binutils        # rc=0
```

Then the whole merge gate was run against that toolchain:

```
$ make -f tb/Makefile gate BUILD=/home/user/work-cov/build WORK=/home/user/work-cov/gatework
...
gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
gate rc=0
```

All ten stages green, all ten projects matching the reference ROM and the 2001
oracle. Coverage was then read straight off that run, before any probe of mine
touched the counters:

```
$ cd build/bfd     && gcov -f -b -t elf32-i51.c        # Runs: 2197
$ cd build/gas     && gcov -f -b -t config/tc-i51.c    # Runs:  788
$ cd build/opcodes && gcov -f -b -t i51-dis.c          # Runs:  587
```

File totals for the gate:

| file | lines executed | branches taken at least once |
|---|---|---|
| `bfd/elf32-i51.c` | 57.06% of 361 | 54.55% of 176 |
| `gas/config/tc-i51.c` | 68.61% of 1166 | 60.61% of 716 |
| `opcodes/i51-dis.c` | 85.34% of 232 | 64.35% of 115 |
| `bfd/cpu-i51.c` | — no functions, only `bfd_i51_arch`; no `.gcda` is produced | — |

Never-executed source lines: 143 in `elf32-i51.c`, 347 in `tc-i51.c`,
36 in `i51-dis.c`.

## Headline

**Seven functions in the port's own files were never executed once by the whole
gate** — ten stages, ten projects, ~2200 tool invocations:

| function | file | gate coverage |
|---|---|---|
| `i51_symbol_is_valid` | `opcodes/i51-dis.c` | 0.00% of 10 |
| `bfd_elf32_bfd_reloc_name_lookup` | `bfd/elf32-i51.c` | 0.00% of 8 |
| `i51_elf_section_from_shdr` | `bfd/elf32-i51.c` | 0.00% of 9 |
| `md_atof` | `gas/config/tc-i51.c` | 0.00% of 23 |
| `md_show_usage` | `gas/config/tc-i51.c` | 0.00% of 3 |
| `md_convert_frag` | `gas/config/tc-i51.c` | 0.00% of 2 |
| `md_estimate_size_before_relax` | `gas/config/tc-i51.c` | 0.00% of 2 |

Four more functions are *entered* on every run and do nothing at all:
`elf32_i51_check_relocs`, `elf32_i51_object_p`, `i51_elf_fake_sections`, and
`elf32_i51_link_output_symbol_hook` (which returns at the first `if` in every
gate stage).

---

# (c) Runs for a real user, never once for the gate

The dangerous category. Everything here works today; nothing in CI would notice
if it stopped.

## c1. `i51_symbol_is_valid` — the disassembler's symbol filter. WORST FINDING.

`opcodes/i51-dis.c:88`. Twelve lines of comment explain why it exists: without it
`objdump -d` names a subroutine after an SFR equate, because every MCS-51 address
space starts at zero and `ACC`, `P1`, `TCON` and thousands of data symbols all sit
below 0x100. It is hooked up for real (`opcodes/disassemble.c:638`).

Gate coverage: **0.00% of 10 lines.** Reason:

```
$ grep -n objdump tb/isa_check.py
136:        r = subprocess.run([self.objdump, '-D', '-z', '-b', 'binary', ...
```

`-b binary` has no symbol table, so `objdump.c:1384` never calls
`inf->symbol_is_valid`. Every `objdump` invocation in the gate is a raw-binary
decode. No stage ever disassembles an ELF object with a symtab.

Proof it fires the moment a user does:

```
$ as-new -o sym.o sym.s && objdump -d sym.o        # ordinary ELF, has .symtab
$ cd build/opcodes && gcov -f i51-dis.c | grep -A1 symbol_is_valid
Function 'i51_symbol_is_valid'
Lines executed:80.00% of 10
```

0% across the entire gate, 80% after one ordinary `objdump -d`. A regression here
— a mistake in the `SEC_CODE` test, an inverted return — would ship green.

**Where a test would go:** `tb/isa_check.py` or a new stage; assemble an object
with an absolute SFR equate at the same value as a code label, `objdump -d` it,
and assert the code label wins.

## c2. `elf32_i51_link_output_symbol_hook` — the `ld -r` common-space restorer

`bfd/elf32-i51.c:948`. Its comment: *"without it a relocatable link degrades every
such common to an ordinary one, and the next link allocates it in
byte-addressed .bss."*

Gate coverage: 14.29% of 21 — the signature, the early `if`, the early `return`.
Lines 959–978, the entire body that puts the `SHN_I51_*` index back, are `#####`.

It is not dead code. It is untested code. Isolated:

```
$ rm -f build/bfd/elf32-i51.gcda
$ ld-new -o z1.elf c1.o                 # final link
Function 'elf32_i51_link_output_symbol_hook'
Lines executed:14.29% of 21

$ rm -f build/bfd/elf32-i51.gcda
$ ld-new -r -o z2.o c1.o                # relocatable link
Function 'elf32_i51_link_output_symbol_hook'
Lines executed:76.19% of 21
```

`ld -r` reaches the body. The gate *does* run `ld -r` (`tb/sim/run-reloc.py`), but
never on an object holding memory-space commons; and `tb/sim/run-commons.sh`, the
stage written for memory-space commons, never runs `ld -r` at all — grep it, there
is no `-r` in the file.

What a real user gets, and what nothing checks:

```
$ as-new -o c1.o c1.s            # .xcomm XV,16,1  .rcomm RV,4,1  .bitcomm BV,1,1
$ readelf -s --wide c1.o  | tail -3
     5: 00000001    16 OBJECT  GLOBAL DEFAULT PRC[0xff04] XV
     6: 00000001     4 OBJECT  GLOBAL DEFAULT PRC[0xff01] RV
     7: 00000001     1 OBJECT  GLOBAL DEFAULT PRC[0xff06] BV
$ ld-new -r -o c1r.o c1.o && readelf -s --wide c1r.o | tail -3
     8: 00000001     4 OBJECT  GLOBAL DEFAULT PRC[0xff01] RV
     9: 00000001    16 OBJECT  GLOBAL DEFAULT PRC[0xff04] XV
    10: 00000001     1 OBJECT  GLOBAL DEFAULT PRC[0xff06] BV
```

Correct — and produced entirely by the 20 lines the gate never executes.

**Where a test would go:** `tb/sim/run-commons.sh`, right after the existing
object-level `expect_ndx` block: `ld -r` the same `commons.o`, re-run `expect_ndx`
on the result, then link that and re-run the `expect_size` block.

## c3. `bfd_elf32_bfd_reloc_name_lookup` — the `.reloc` directive

`bfd/elf32-i51.c:264`, 0.00% of 8. Reachable by any user writing `.reloc`:

```
$ printf '\t.text\n_START:\tret\n\t.byte 0,0\n\t.reloc 1, R_I51_16, _START\n' > rl.s
$ as-new -o rl.o rl.s && objdump -r rl.o | tail -2
OFFSET   TYPE              VALUE
00000001 R_I51_16          _START
```

Works. Untested. The name table it walks is `elf_i51_howto_table[i].name`, which
nothing else in the port ever reads, so a typo in any of the twelve `"R_I51_*"`
name strings is invisible to every gate stage.

## c4. `md_atof` — `.float`, `.double`, `.single`

`gas/config/tc-i51.c:961`, 0.00% of 23. Runs for anyone emitting a float:

```
$ printf '\t.data\n\t.float 1.0\n'  > f.s; as-new -o f.o f.s; objdump -s -j .data f.o
 0000 3f800000
$ printf '\t.data\n\t.double 1.0\n' > d.s; as-new -o d.o d.s; objdump -s -j .data d.o
 0000 3ff00000 00000000
$ printf '\t.data\n\t.single 2.5\n' > s.s; as-new -o s.o s.s; objdump -s -j .data s.o
 0000 40200000
```

Big-endian IEEE, correct for `TARGET_BYTES_BIG_ENDIAN 1`. Nothing asserts it.

## c5. Five of the seven `SHN_I51_*` arms of `elf32_i51_symbol_processing`

`bfd/elf32-i51.c:753`, 17.65% of 102. Gate-executed arms: `SHN_I51_RDATA_C` and
`SHN_I51_XDATA_C` only — the two spaces the ten projects use. Never executed:
`SHN_I51_REGBANK`, `SHN_I51_BDATA_C`, `SHN_I51_IDATA_C`, `SHN_I51_EDATA_C`,
`SHN_I51_BITDATA_C` (85 `#####` lines). This is the path `nm`, `objcopy`, `strip`
and `objdump` take when they canonicalise a symbol table.

All seven work when reached — one object with all seven common kinds plus `.using`:

```
$ nm-new all.o
00000002 C BCV     00000001 C BITV    00000003 C CV     00000004 C ECV
00000008 C ICV     00000004 C RCV     00000010 C XCV    00000008 C __RB__
$ objcopy all.o all2.o && readelf -s --wide all2.o | tail -8   # every PRC[0xff0n] preserved
$ strip-new all3.o; echo rc=$?                                  # rc=0
```

After that single `nm` the function goes to `100.00% of 102`. Each arm fills a
zero-initialised `static asection` by hand; five of the seven fill patterns are
never once executed by CI.

**Where a test would go:** `tb/sim/run-commons.sh` already builds exactly this
object. Add `nm`/`objcopy` round-trips over it.

## c6. Register-bank aliases `AR0..AR7` and `.using` banks 1/2/3

Never executed by the gate: `tc-i51.c:1274-1280` (operand 1 `'U'`),
`1453-1464` (operand 2 `'U'`), `1098-1107` (`md_undefined_symbol` `'U'`),
`1808-1822` (`.using 1`, `.using 2`, `.using 3`, and the bad-bank error).
`i51_using` is 40.91% of 22 — only `.using 0` is ever assembled.

```
$ printf '\t.text\n\t.using\t2\n\tmov\tA,AR3\n' > u.s
$ as-new -o u.o u.s && objdump -d u.o | tail -1
   0:	e5 13       	mov	A, 0x13          # 16+3, correct
$ printf '\t.text\n\t.using\t9\n' > u9.s; as-new -o u9.o u9.s
u9.s:2: Error: expected a register bank number 0, 1, 2 or 3
```

Correct, untested. Three quarters of the register-bank feature is dark.

## c7. Backward branch displacements in the disassembler

`i51-dis.c:211`, `:297`, `:339` — all three `sprintf (opN,".-0x%02X",-rel_addr)`
arms are `#####`. The gate decodes only isolated golden bytes from
`tb/isa/*.txt`, whose displacements are all forward.

The comment above each one records a *past bug* — *"Sign-extend the encoded
displacement before deciding its sign: testing bit 7 of (displacement + insn
length) turns the largest forward branches into backward ones"* — and the branch
that fix protects is never run by CI.

```
$ printf '\200\376\330\374\264\052\373\245' > back.bin
$ objdump -D -z -b binary -m i51 back.bin
   0:	80 fe       	sjmp	.+0x00		; 0x0000
   2:	d8 fc       	djnz	R0, .-0x02	; 0x0000
   4:	b4 2a fb    	cjne	A, #0x2A, .-0x02	; 0x0002
   7:	a5          	.byte	0xA5		; ????
```

Correct. The `????` unknown-opcode path (`i51-dis.c:351-354`) is also `#####` and
also correct.

**Where a test would go:** add a few negative-displacement rows to
`tb/isa/8051.txt` (or a `back.txt`), which the `roundtrip` stage already decodes
and re-assembles.

## c8. Half the `.pcode` operand modes

`decodePcodeOperand` 33.33% of 60, `writePcodeOperand` 42.22% of 45. Never
executed: `DIRECTSWAP`, `INDIRECTSWAP`, `INDIRECTBYTE`, `DIRECTSHL8` — i.e. the
`#SWAP`, `@SWAP`, `@BYTE`, `#SHL8` keywords `pcodeOperand` parses, and the
"Pcode operand 2 isn't swapable" diagnostic. `.pcode` itself is well covered
(`i51_pcode` 97.14%); only the plain byte/word modes are ever fed to it.

## c9. `md_show_usage`

0.00% of 3; reached by `as --help`. Trivially:

```
$ as-new --help | tail -3
A51 options:
                   NONE
```

Note "**A51**" — every other string in the port says i51/I51. One-word cosmetic
inconsistency in the only target-specific help text there is.

---

# (b) Genuinely half-implemented

## b1. `.byte LOW(sym)` / `.byte HIGH(sym)` — code-space pointer tables cannot be assembled

`gas/config/tc-i51.h:60-69`:

```c
//void i51_parse_cons_expression (expressionS *exp, int nbytes);
//#define TC_PARSE_CONS_EXPRESSION(EXPR,N) avr_parse_cons_expression (EXPR,N)
//void avr_cons_fix_new(fragS *frag,int where, int nbytes, expressionS *exp);
//#define TC_CONS_FIX_NEW(FRAG,WHERE,N,EXP) avr_cons_fix_new(FRAG,WHERE,N,EXP)
```

Confirmed effect:

```
$ cat tbl.s
	.text
_START:	ret
tgt:	nop
tab:	.byte	LOW(tgt)
	.byte	HIGH(tgt)
$ as-new -o tbl.o tbl.s
tbl.s:5: Error: junk at end of line, first unrecognized character is `('
tbl.s:6: Error: junk at end of line, first unrecognized character is `('
```

The instruction form works — `mov A,#LOW(tgt)` and `mov A,#HIGH(tgt)` emit
`R_I51_L` and `R_I51_H` correctly — and `.word tgt` emits `R_I51_16`. Only the
byte-at-a-time data form is missing, which is exactly the form a split
low-byte/high-byte jump table needs.

**What is missing to finish it:** the two AVR-shaped hooks, written for i51.
`TC_PARSE_CONS_EXPRESSION` must recognise `LOW(`/`HIGH(` at the head of a `.byte`
expression and record the mode; `TC_CONS_FIX_NEW` must then emit
`BFD_RELOC_I51_8_LOW` / `BFD_RELOC_I51_8_HIGH` instead of `BFD_RELOC_8`. Both
relocations already exist, are already mapped in
`bfd/elf32-i51.c:i51_reloc_map[]`, and are already handled in
`md_apply_fix`. Model: `avr_parse_cons_expression` / `avr_cons_fix_new` in
`gas/config/tc-avr.c`. Fix goes in `gas/config/tc-i51.h` plus a new pair of
functions in `gas/config/tc-i51.c`.

Related dead scaffolding: `tc-i51.c:56-70` copies AVR's
`BITFIELD_CONS_EXPRESSIONS` / `REPEAT_CONS_EXPRESSIONS` cascade, declaring
`parse_bitfield_cons` and `parse_repeat_cons`, which are never defined and never
called; neither macro is ever defined. The cascade's only surviving effect is a
local `#define TC_PARSE_CONS_EXPRESSION(EXP,N) expression(EXP)` used at
`tc-i51.c:1022` inside `.bit`, where `read.c` would have supplied the same
default.

## b2. `ELF_TC_SPECIAL_SECTIONS` — 24 lines of table gas 2.47 does not read

`gas/config/tc-i51.h:116-139` declares `.rdata .rbss .bdata .bbss .idata .ibss
.xdata .xbss .edata .ebss .eeprom` with types and flags. Nothing consumes the
macro:

```
$ grep -rn "ELF_TC_SPECIAL_SECTIONS" binutils-2.47/gas/ | grep -v ChangeLog
gas/config/tc-mep.h:112
gas/config/tc-i51.h:116
gas/config/tc-microblaze.h:92
$ grep -rn "special_sections" gas/config/obj-elf.c gas/config/obj-elf.h gas/read.c gas/write.c
(no output)
```

The mechanism moved into BFD years ago (`elf_backend_special_sections`, e.g.
`elf32-avr.c:710`). Observable consequence — the table says `.rbss` is
`SHT_NOBITS` with `SHF_ALLOC|SHF_WRITE`:

```
$ printf '\t.text\n_START:\tret\n\t.section .rbss\n\t.byte 1\n\t.section .xdata\n\t.byte 2\n\t.section .eeprom\n\t.byte 3\n' > spec.s
$ as-new -o spec.o spec.s && readelf -S --wide spec.o | grep -E 'rbss|xdata|eeprom'
  [ 4] .rbss     PROGBITS  00000000 000035 000001 00      0   0  1
  [ 5] .xdata    PROGBITS  00000000 000036 000001 00      0   0  1
  [ 6] .eeprom   PROGBITS  00000000 000037 000001 00      0   0  1
```

No `A`, no `W`, no `NOBITS`. A user reaching a space through `.section .rbss`
instead of the `.rbss` directive gets a non-allocated section the default script
still matches but the ELF flags disagree with.

**What is missing to finish it:** a
`static const struct bfd_elf_special_section elf_i51_special_sections[]` in
`bfd/elf32-i51.c` plus `#define elf_backend_special_sections
elf_i51_special_sections`, carrying the same eleven entries. The table in
`tc-i51.h` is then deletable.

## b3. `md_elf_section_flags` / SHF_REGBANK — the writer half was never built

`tc-i51.h:48` says *"Support for SHF_REGBANK"*, and `i51_section_flags`
(`tc-i51.c:1791`) is live and called (`obj-elf.c:755`) at 75.00% of 4 lines. The
one dead line is its entire body:

```c
  if (attr & SHF_REGBANK)          /* executed */
    flags |= SEC_IS_COMMON;        /* #####    */
```

`attr` is what `obj_elf_parse_section_letters` produced. `SHF_REGBANK` is
`0x20000000`; no standard section letter yields it, and the hook that would add
one is commented out two lines above the declaration:

```c
//#define md_elf_section_letter(LETTER, PTR_MSG)	i51_section_letter (LETTER, PTR_MSG)
//#define md_elf_section_word(STR, LEN)		i51_section_word (STR, LEN)
```

So `i51_section_flags` is an identity function that will stay one until
`md_elf_section_letter` is written. Note also that `i51_section_letter` and
`i51_section_word`, the functions those two lines name, do not exist anywhere in
the tree.

## b4. `SHF_RDATA` … `SHF_EDATA` — six constants nothing writes and nothing can read

```
$ grep -rn "SHF_REGBANK\|SHF_RDATA\|SHF_BDATA\|SHF_IDATA\|SHF_XDATA\|SHF_EDATA\|SHF_CDATA" bfd gas opcodes include ld binutils
bfd/elf32-i51.c:634:  if ((hdr->sh_flags & SHF_CDATA) != 0 && ...
bfd/elf32-i51.c:645:   of sh_flags - SHF_RDATA on .rbss, SHF_BDATA on .bbss and so on - so
gas/config/tc-i51.h:48:/* Support for SHF_REGBANK */
gas/config/tc-i51.c:1793:  if (attr & SHF_REGBANK)
include/elf/i51.h:47..53   (the seven #defines)
```

Writer side: `i51_elf_fake_sections` stamps nothing, and its comment says so and
says why. Honest. Reader side: see a1 below — the test is not merely unused, it
is unsatisfiable. Six of the seven constants have no reader and no writer at all.

---

# (a) Dead code that should be deleted

## a1. `i51_elf_section_from_shdr` — 0% executed, and its one branch is *unsatisfiable*

`bfd/elf32-i51.c:615-640`, 0.00% of 9 lines across the gate. Coverage alone would
only say "untested". The source proves it can never do its job.

The hook is reached from exactly one place:

```
$ grep -n "elf_backend_section_from_shdr" bfd/elf.c
2963:      if (bed->elf_backend_section_from_shdr (abfd, hdr, name, shindex))
```

which sits in the `default:` arm of `switch (hdr->sh_type)` at `elf.c:2530`.
`SHT_PROGBITS` and `SHT_NOBITS` are handled at `elf.c:2536-2537` and never reach
it. And `_bfd_elf_make_section_from_shdr` sets:

```
elf.c:920   flags = SEC_NO_FLAGS;
elf.c:921   if (hdr->sh_type != SHT_NOBITS)
elf.c:922     flags |= SEC_HAS_CONTENTS;
```

So inside this hook `sh_type != SHT_NOBITS` always holds, therefore
`SEC_HAS_CONTENTS` is always set, therefore

```c
  if ((hdr->sh_flags & SHF_CDATA) != 0 && (flags & SEC_HAS_CONTENTS) == 0)
    flags |= SEC_IS_COMMON;                       /* unreachable for any input */
```

can never be true. Not "untested" — impossible, for every ELF file that exists.

The hook body itself *is* reachable, but only for a section with a
processor-specific `sh_type`:

```
$ printf '\t.text\n_START:\tret\n\t.section .procsec,"a",@0x70000000\n\t.byte 1\n' > proc.s
$ as-new -o proc.o proc.s && readelf -S --wide proc.o | grep procsec
  [ 4] .procsec   LOPROC+0  00000000 000035 000001 00   A  0   0  1
$ nm-new proc.o >/dev/null; cd build/bfd && gcov -f elf32-i51.c | grep -A1 section_from_shdr
Function 'i51_elf_section_from_shdr'
Lines executed:77.78% of 9
```

77.78% — the 22.22% that stays dark is the `SHF_CDATA` line and its `flags |=`.

**Comment defect.** The comment above `i51_elf_fake_sections` (`elf32-i51.c:642-654`)
carefully explains that stamping a space code would "reach
`i51_elf_section_from_shdr ()` on the way back in and hand the linker a section of
real data to place as a common." It could not: the stamped section would be
`SHT_PROGBITS` or `SHT_NOBITS` and would never reach that function. The reasoning
is sound about *why not to stamp*, but the mechanism it names does not exist.

**Where the deletion goes:** `bfd/elf32-i51.c` — remove
`i51_elf_section_from_shdr` and `#define elf_backend_section_from_shdr`, or, if
the classification is to be finished, move it to a real reader (`add_symbol_hook`
already does the equivalent job through `SHN_I51_*`).

## a2. The `.local` path in `i51_common` — 126 lines, unreachable

`gas/config/tc-i51.c:1968-2093`, every line `#####`. `i51_common` overall is
29.44% of 180.

The gate reaches it never, and no user can. `symbol_get_obj(symbolP)->local` is
set in exactly two places in `obj-elf.c`: `obj_elf_local` (line 366) and the
section-group signature symbol (line 2820, irrelevant to `.comm`). And
`obj_elf_local` is unreachable, because the port's own `.local` shadows it:

```
$ sed -n '590,606p' gas/read.c
  pop_table_name = "md";   pop_override_ok = 0;  md_pop_insert ();
  pop_table_name = "obj";  pop_override_ok = 1;  obj_pop_insert ();
```

md table first; `obj_pseudo_table`'s `{"local", obj_elf_local, 0}`
(`obj-elf.c:86`) then loses the insert silently under `pop_override_ok = 1`.
`.local` is `i51_local` — a directive that deletes built-in operand names from
the operand hash so `.equ` can redefine them. Different feature, same name.

Observable:

```
$ cat loc.asm
	.text
	.local	myvar
	.comm	myvar,4
	.local	myx
	.xcomm	myx,4
$ as-new -o loc.o loc.asm && readelf -s loc.o | tail -2
     4: 00000004     4 OBJECT  GLOBAL DEFAULT  COM MYVAR
     5: 00000004     4 OBJECT  GLOBAL DEFAULT PRC[0xff04] MYX
```

Both still `GLOBAL`. Every common in this port is external, always. Confirms the
earlier sighting exactly.

Credit where due: `tb/sim/run-commons.sh` already documents this and pins it with
a `localcom.s` probe asserting `LCVAR` stays `PRC[0xff01]`. So the dead branch is
*known* dead and guarded against becoming live by accident. It is still 126 lines
of unreachable code, and the seven `case` arms inside it are the only reason
`frag_var` and `rs_org` appear in this file at all.

**Where the deletion goes:** `gas/config/tc-i51.c`, the whole
`if (symbol_get_obj (symbolP)->local) { ... }` arm; the `else` becomes the body.
`md_convert_frag` and `md_estimate_size_before_relax` (d4 below) become provably
dead in the same stroke.

## a3. `comment2` in the disassembler — a write-only 40-byte buffer

`opcodes/i51-dis.c`:

```
$ grep -n comment2 opcodes/i51-dis.c
136:  char op1[16], op2[16], op3[16], comment1[40], comment2[40];
158:  comment2[0] = 0;
353:      comment2[0] = 0;
391:  if (*comment2)
392:    (*prin) (stream, dis_style_comment_start, " %s", comment2);
```

The only two writes both store `'\0'`. `if (*comment2)` is therefore false on
every path, and line 392 is `#####` in the gate — as it must be, forever.
Not "untested": dead by construction.

## a4. The `VTABLE_INHERIT` / `VTABLE_ENTRY` arm of `tc_gen_reloc`

`tc-i51.c:1146-1148`, `#####`. Unreachable because `i51_reloc_map[]` has no entry
for either type, so `bfd_reloc_type_lookup` returns NULL and the function returns
at line 1143 first:

```
$ printf '\t.text\nf:\t.vtable_inherit f,f\n' > vt.s && as-new -o vt.o vt.s
vt.s:2: Warning: .vtable_inherit has been deprecated
vt.s:2: Error: reloc 1392 not supported by object file format
```

The `Error` is the NULL-howto path at 1140-1143. Line 1148 is behind it and can
never run. (`--gc-sections` still works without vtable relocs — verified: a
`.text.dead` section is dropped and `.text` shrinks from 0xc to 0x7 bytes.)

## a5. Dead range checks — confirms the mutation round's survivors

- `check_range` case `I51_OP_JUMP_REL` (`tc-i51.c:1610-1611`) — `#####`.
  Unreachable: the only site that could pass `I51_OP_JUMP_REL` is `fixup8`'s
  `default:` arm at 1680, and `fixup8` guards that whole block with
  `if (ex->X_op == O_constant && mode != I51_OP_JUMP_REL)` (line 1642).
  All eleven call sites verified by grep; no other passes that mode.
- `check_range` `default: return 0` (`1623-1624`) — `#####`. The seven modes
  that exist are all named in cases above it.
- `fixup8`'s `_("LOW Operand out of 8-bit range: ...")` at 1655-1657 — `#####`
  and unreachable, because `check_range` returns `1` unconditionally for
  `I51_OP_LOW_ADDR` (lines 1620-1621). The diagnostic string can never be printed:

```
$ printf '\t.text\n\tmov\tA,#LOW(0x123456)\n' > lo.s && as-new -o lo.o lo.s; echo rc=$?
rc=0
   0:	74 56       	mov	A, #0x56       # silently truncated, as intended
$ printf '\t.text\n\tmov\tA,#HIGH(0x123456)\n' > hi.s && as-new -o hi.o hi.s
hi.s:2: Error: HIGH Operand out of 8-bit range: `1193046'.
```

  HIGH complains, LOW cannot. That asymmetry is the intended semantics (LOW of
  anything is a valid byte) — the dead `if` and its message are the leftover.
- `fixup8`'s `_("HIGH Operand out of 8-bit range")` at 1647-1649 is also `#####`
  in the gate but *is* reachable, as the run above shows. That one is (c).

## a6. Two degenerate switches in `md_apply_fix`

`tc-i51.c:836-841`:

```c
  switch (fixp->fx_r_type)
    {
    default:
      fixp->fx_no_overflow = 1;
      break;
    }
```

and `tc-i51.c:945-949`, a `switch` whose only arm is `default: break;` — a
statement that does nothing at all. Both are template residue.

## a7. `#`-prefixed operand 1

`tc-i51.c:1175-1189`, `#####`. No MCS-51 instruction takes an immediate as its
first operand; the 111-row table in `include/opcode/i51.h` has no `args[0] == '#'`.
The `HIGH(`/`LOW(` scan duplicated inside that branch (lines 1181-1182) is a copy
of the live one at 1195-1196.

## a8. The `OPCODE` column of `include/opcode/i51.h`

`I51_INS(NAME, ARGS, SIZE, OPCODE, MRELOC, BIN, MASK)` — both expansions drop
`OPCODE`:

```
gas/config/tc-i51.c:152:  {NAME, ARGS, SIZE, MRELOC, BIN},
opcodes/i51-dis.c:36:     {NAME, ARGS, SIZE, BIN, MASK},
```

111 bit-pattern strings (`"aaa10001"`, `"00101rrr"`, …) that no consumer reads.
They cost nothing at runtime — a macro parameter never referenced never reaches
the object — so this is documentation living in a data column. Worth knowing
before someone "fixes" a mismatch between `"00100100"` and `0x24`: nothing checks
that they agree.

---

# (d) Intentionally inert, with the reason

## d1. `elf32_i51_check_relocs` — **the "entirely dead" sighting is refuted**

`bfd/elf32-i51.c:304`. Gate coverage **100.00% of 2 lines**. It is called on every
link. Its body is `return true;` and its comment says exactly that:
*"No GOT, no PLT, no garbage-collection bookkeeping: nothing to record here."*
Comment and code agree.

Registering it is redundant (a NULL `elf_backend_check_relocs` behaves the same),
and `--gc-sections` works without it — verified above. Category (d), not (a): a
future port change would put code here.

**But the block comment above the forward declarations still says:**
*"Look through the relocs for a section during the first phase. Since we don't do
.gots or .plts, we just need to consider the virtual table relocs for gc."*
The function considers no vtable relocs, and there are no vtable relocs to
consider (a4). Stale template text sitting directly above an honest comment.

## d2. `elf32_i51_object_p` — **the sighting is confirmed**

`bfd/elf32-i51.c:606-611`:

```c
/* Set the right machine number.  */

static bool
elf32_i51_object_p (bfd *abfd ATTRIBUTE_UNUSED)
{
  return 1;
}
```

100% executed, sets nothing. **Comment defect confirmed.** The comment describes
behaviour the code does not have.

It has nothing to do: `elfcode.h:624` already ran
`bfd_default_set_arch_mach (abfd, ebd->arch, 0)` before the backend hook is called
at `elfcode.h:889`, and `bfd_i51_arch` has exactly one machine number, 0
(`bfd/cpu-i51.c`). The hook is a no-op that could be `#undef`'d entirely. The
comment is a copy-paste from a multi-machine port.

## d3. `bfd_elf_i51_final_write_processing` — comment defect

```c
/* The final processing done just before writing out a I51 ELF object
   file.  This gets the I51 architecture right based on the machine
   number.  */
...
  elf_elfheader (abfd)->e_machine = EM_8051;
```

100% executed and load-bearing (it is what makes output carry EM_8051 even for
EM_I51_OLD input, as the README promises). But it reads no machine number; the
second sentence of the comment describes a lookup that is not there.

## d4. `md_convert_frag` and `md_estimate_size_before_relax`

Both `abort()`, both 0.00%. Unreachable: they fire only on `rs_machine_dependent`
frags, and the port creates none —

```
$ grep -n "rs_machine_dependent\|md_relax_table" gas/config/tc-i51.c gas/config/tc-i51.h
(no output; every frag_var in the file is rs_org, all seven inside the dead
 .local branch of a2)
```

Standard gas practice for a non-relaxing target. Leave them.

## d5. `.edata` / `.eeprom` — separate arenas at the same addresses

The sighting said "plain aliases of `.xdata`". Precisely: they are three distinct
output sections, each independently allocated, all based at 0x0000 —

```
$ readelf -S --wide sp.elf | grep -E 'xdata|edata|eeprom'
  [ 2] .xdata   PROGBITS 00000000 000056 000001 00  W  0 0 1
  [ 3] .edata   PROGBITS 00000000 000057 000001 00  W  0 0 1
  [ 4] .eeprom  PROGBITS 00000000 000058 000001 00  W  0 0 1
$ readelf -s --wide sp.elf | grep -E 'XDSYM|EDSYM|EESYM'
    XDSYM = 0x00000000   EDSYM = 0x00000000   EESYM = 0x00000000
```

Not aliases — three parallel allocation arenas that overlay one 16-bit address
range. That is what `ld/scripttempl/elf32i51.sc` says it does, and why
(*"Sections of different spaces may then share VMA ranges without tripping the
linker's overlap check"*). Comment and code agree.

The real limit, and it is not written down anywhere: **no relocation and no
instruction encoding distinguishes the three.** A `movx` at an `.edata` symbol and
a `movx` at the `.xdata` symbol of the same offset assemble to identical bytes.
The spaces exist for allocation only. Two smaller gaps in the same area:

- `.eeprom` has no overflow `ASSERT` in the script, while `.xdata` and `.edata`
  both do (`__XDATA_END <= 0x10000`, `__EDATA_END <= 0x10000`).
- There is no `.eeprom` common directive and no `SHN_I51_EEPROM_C`, though every
  other space has one. `.ecomm` is edata, not eeprom.

## d6. `MD_APPLY_FIX3`, `md_after_pass_hook` — defines with no consumer left

```
$ grep -rn "MD_APPLY_FIX3\|md_after_pass_hook" gas/ | grep -v ChangeLog | grep -v config/tc-
(no output)
```

Both survive only in `tc-i51.h` (lines 95 and 161). `MD_APPLY_FIX3` was removed
from gas in the 2003 era; `tc-microblaze.h` and `tc-msp430.h` carry the same
fossil. `md_cleanup` (line 160) *is* live (`read.c:1442`), so `i51_cleanup` runs;
`md_after_pass_hook` is the dead half of that pair.

## d7. Inert emulparams

`ld/emulparams/elf32i51.sh` sets `TEXT_START_ADDR=0x00000000`,
`MAXPAGESIZE=0x0800`, `EMBEDDED=yes`, `MACHINE=`. None reaches the port's own
script template:

```
$ grep -c "MAXPAGESIZE\|TEXT_START_ADDR\|EMBEDDED\|MACHINE" ld/scripttempl/elf32i51.sc
0
$ grep -n "MAXPAGESIZE\|TEXT_START_ADDR\|EMBEDDED\|MACHINE" ld/emultempl/generic.em ld/emultempl/genelf.em ld/genscripts.sh
ld/genscripts.sh:303:SEGMENT_SIZE=${SEGMENT_SIZE-${MAXPAGESIZE-${TARGET_PAGE_SIZE}}}
```

`SEGMENT_SIZE` only feeds `DATA_ALIGNMENT_`, which this template never uses. The
page size that actually matters is `ELF_MAXPAGESIZE 1` in `bfd/elf32-i51.c`.
Harmless, but `TEXT_START_ADDR` and `MAXPAGESIZE` read like layout controls and
are not. Related: the `-r`/`-u` scripts are empty by design
(`test -z "${RELOCATING}" && exit 0`) —

```
$ wc -c build/ld/ldscripts/elf32i51.xr build/ld/ldscripts/elf32i51.xu
20 elf32i51.xr
21 elf32i51.xu
```

so `ld -r` uses ld's orphan placement, which is what makes the c2 hook the only
thing preserving common spaces across `-r`.

## d8. No target options

`md_shortopts = ""`, `md_longopts` holds only the NULL terminator,
`md_parse_option` returns 0 unconditionally (100% executed, one line). The port
accepts no `-m` anything: no CPU variant, no memory model. `md_show_usage` says
`NONE`. Consistent; deliberate.

---

# Verdicts on the starting list

| sighting | verdict |
|---|---|
| `elf32_i51_check_relocs` entirely dead | **Refuted.** 100% of 2 lines, called on every link. Body is an honest no-op. Category (d). Its *outer* block comment is stale. |
| `elf32_i51_object_p` a no-op contradicting its comment | **Confirmed.** 100% executed, does nothing; comment says "Set the right machine number". |
| `.local` path in `i51_common`, ~120 lines, dead | **Confirmed.** Exactly 126 lines, all `#####`, unreachable because md's `.local` shadows `obj_elf_local` (`read.c:590-606`, `pop_override_ok = 1`). Every common is global — proved. |
| `SHN_I51_*` machinery ~320 lines partly unreachable, writer hook commented out as crashing | **Partly refuted.** The writer hook `elf32_i51_link_output_symbol_hook` is present, active, and correct — it just never runs in CI because no gate stage does `ld -r` on memory-space commons (c2). Genuinely unreachable in that machinery: only `i51_elf_section_from_shdr` (a1, 9 lines) and, gate-wise, 5 of 7 `symbol_processing` arms (c5, 85 lines). |
| AVR-shaped `.byte LOW()/HIGH()` hooks commented out; code-space pointer tables cannot be assembled | **Confirmed.** `.byte LOW(tgt)` → `Error: junk at end of line`. Category (b1) with a named fix site. |
| dead range checks that survived mutation | **Confirmed.** `check_range` `I51_OP_JUMP_REL` and `default`; the `LOW Operand out of 8-bit range` diagnostic (a5). |
| `.edata`/`.eeprom` are plain aliases of `.xdata` | **Refined.** Three distinct sections and three distinct allocation arenas, all based at 0x0000 — overlaid, not aliased. The real gap: nothing in the ISA or the relocations distinguishes them (d5). |
| known comment defect: `SHN_LORESERVE+n` describes a numerically no-op fix | **Refuted at this head.** `include/elf/internal.h:52` `#undef`s the external value and defines `SHN_LORESERVE (-0x100u)`. Compiled against the port's own include set: |

```
SHN_LORESERVE     = 0xffffff00
SHN_I51_REGBANK   = 0xffffff00
SHN_I51_BITDATA_C = 0xffffff06
SHN_COMMON        = 0xfffffff2
sizeof st_shndx in Elf_Internal_Sym = 4
```

A bare `0xff00` really would have been an ordinary section index inside bfd. The
comment in `include/elf/i51.h:55-61` is accurate.

---

# Comment-vs-code defects, collected

1. `bfd/elf32-i51.c:606` — *"Set the right machine number."* over
   `elf32_i51_object_p`, which sets nothing. (d2)
2. `bfd/elf32-i51.c:596` — *"This gets the I51 architecture right based on the
   machine number"* over a function that hardcodes `EM_8051` and reads no machine
   number. (d3)
3. `bfd/elf32-i51.c:298-301` — *"we just need to consider the virtual table relocs
   for gc"* over a function that considers nothing, for a target with no vtable
   relocs. (d1)
4. `bfd/elf32-i51.c:642-654` — the `i51_elf_fake_sections` comment names a
   round-trip through `i51_elf_section_from_shdr` that cannot happen: a
   `PROGBITS`/`NOBITS` section never reaches that hook. (a1)
5. `bfd/elf32-i51.c:628-633` — the `SHF_CDATA` comment describes marking a
   contentless section as a common; the condition is unsatisfiable. (a1)
6. `gas/config/tc-i51.h:48` — *"Support for SHF_REGBANK"* over a hook that cannot
   see `SHF_REGBANK` because `md_elf_section_letter` is commented out two lines
   below, and names two functions (`i51_section_letter`, `i51_section_word`) that
   do not exist in the tree. (b3)
7. `gas/config/tc-i51.h:114-139` — the `ELF_TC_SPECIAL_SECTIONS` table documents
   types and flags gas 2.47 never applies. (b2)
8. `gas/config/tc-i51.c:1655-1657` — the `LOW Operand out of 8-bit range`
   diagnostic promises a check `check_range` never performs. (a5)

No comment defect found in `opcodes/i51-dis.c`, `bfd/cpu-i51.c`, or
`include/elf/i51.h`.

---

# Where the gate's blind spots are, in one list

Every item below is code that runs for a user and never for CI. Ranked.

1. `objdump -d`/`-D` on an ELF with a symbol table — the gate only ever runs
   `objdump -b binary`. Kills `i51_symbol_is_valid` outright, and every
   symbol-naming path in `print_insn_i51`.
2. `ld -r` on an object holding memory-space commons — kills the body of
   `elf32_i51_link_output_symbol_hook`.
3. `nm` / `objcopy` / `strip` on `.regbank`, `.bcomm`, `.icomm`, `.ecomm`,
   `.bitcomm` commons — kills 5 of 7 arms of `elf32_i51_symbol_processing`.
4. Negative branch displacements in the disassembler.
5. `.using 1|2|3` and the `AR0..AR7` aliases.
6. `.float` / `.double` / `.single`.
7. `.reloc` with a relocation name.
8. `.pcode` with `#SWAP`, `@SWAP`, `@BYTE`, `#SHL8`.

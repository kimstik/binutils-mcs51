# Review: the 8051 memory model, end to end

Scope: the whole MCS-51 address-space model as this port implements it — the SFR page
vs upper internal RAM, register banks, the stack, XDATA and paging, CODE-space reads,
and the full space inventory (CODE, IDATA, DATA, XDATA, EDATA, EEPROM, BIT and the
`.rdata/.bdata/.idata/.xdata/.edata/.eeprom/.regbank/.bit*` sections).

Bit addressing, the `.bit`/B2B folding boundaries, the memory-space commons machinery,
the default script's section chaining, opcode encoding, relocations as such and the
testbench were reviewed elsewhere and are out of scope here.

Judged against the MCS-51/8052 architecture, not against the port's comments.

Method: toolchain built from `mcs51/additions.patch` + `mcs51/modifications.patch` on
binutils 2.47 (the `tb/Makefile` `make build` recipe). Every claim below is a command and
its output. `$AS`, `$LD`, `$NM`, `$OD`, `$RE` are `gas/as-new`, `ld/ld-new`,
`binutils/nm-new`, `binutils/objdump`, `binutils/readelf` from that build. Runtime checks
use ucsim (`s51 -t C52`). Nothing in the tree was modified.

Severity: **critical** = wrong code, silently, from ordinary input; **high** = no model at
all, the programmer carries it unaided; **medium** = tooling, diagnostics, crashes.

---

## S1. Directly addressed RAM has no 0x80 boundary. Data lands in the SFR page and the assembler emits SFR accesses for it. (Critical)

On an 8052 the addresses 0x80–0xFF name **two different memories**: direct addressing
(`mov a,addr`) reaches the SFR page, indirect addressing (`mov a,@Ri`) reaches upper RAM.
Directly addressed data must therefore stop at 0x7F. The port's own `gas/config/tc-i51.h`
says exactly this:

```
  /* 0x30..0x7F direct, indirect addresable */ \
  /* * *   standart section   * * */ \
  /* .data */ \
  /* .bss */ \
  /* 0x80..0xFF indirect addressable */ \
  { ".idata",	SHT_PROGBITS,	SHF_ALLOC + SHF_WRITE }, \
```

The linker script does not implement it. `ld/scripttempl/elf32i51.sc` chains
`.data`→`.bss`→`.idata`→`.ibss` into one arena and bounds only the total:

```
  ASSERT (__IDATA_END <= 0x100, "internal RAM overflow (past 0xFF)")
```

There is no `__DATA_END <= 0x80`. So:

```
$ cat big.s
	.text
	.global _START
_START:	mov	a,BIGEND
	mov	P1,a
	.data
	.global BIG
BIG:	.space 0x70
	.global BIGEND
BIGEND:	.byte 0

$ $AS -o big.o big.s && $LD -o big.elf big.o; echo "ld exit=$?"
ld exit=0
$ $NM -n big.elf | grep BIGEND
00000090 ? BIGEND
$ $OD -d big.elf | head -8
00000000 <_START>:
   0:	e5 90       	mov	A, 0x90
   2:	f5 90       	mov	0x90, A
```

`BIGEND` is a `.data` variable. It linked at 0x90. `mov a,BIGEND` assembled to `E5 90`,
byte-for-byte identical to `mov a,P1`. The link exited 0 with no diagnostic.

Confirmed as hardware behaviour, not a disassembly artefact:

```
$ cat alias.s          # excerpt
	mov	r0,#0x90
	mov	@r0,#0xAA	; upper RAM 0x90 <- 0xAA
	mov	a,BIGEND	; direct 0x90
	mov	B,a
	mov	a,@r0		; indirect 0x90
	mov	ACC,a
$ s51 -t C52 alias.hex < cmds
0xe0 ACC:                 0b10101010 0xaa '.' 170 (-86)
0xf0 B:                   0b11111111 0xff '.' 255 ( -1)
0x90                      aa .
```

B = 0xFF: the direct access the assembler emitted **for the variable** read the P1 latch.
ACC = 0xAA: the indirect access read the variable. Two memories, one symbol, no
diagnostic anywhere in the chain.

Found independently here from the symbol side and by another reviewer from the script side
(`__IDATA_END <= 0x100`, no bound at 0x80). Two independent confirmations — established.

Same root cause, opposite direction: `.idata` — indirect-only data — is allocated
immediately after `.bss`, so it normally sits **below** 0x80 and consumes the scarce
directly addressable region:

```
$ $OD -t sp.elf | grep -E '\.idata|\.data'
00000023 l       .data	00000000 DVAR
00000025 l       .idata	00000000 IVAR
```

`IVAR` is at 0x25. Nothing ever reaches 0x80–0xFF unless the program has more than 128
bytes of RAM — at which point S1 fires.

Fix would go in `ld/scripttempl/elf32i51.sc`: split the arena, bound `.data`/`.bss` with
`ASSERT (__DATA_END <= 0x80, ...)`, start `.idata` at `MAX (0x80, ...)`. That is a
behaviour change for programs that link today, so it is a decision, not a typo fix.

---

## S2. Relocations carry no address space. Cross-space nonsense assembles and links clean. (Critical)

`gas/config/tc-i51.c` `fixup8()` maps a direct memory operand, an immediate constant and
the low byte of a 16-bit address onto one relocation: `BFD_RELOC_8` → `R_I51_8`, whose
howto in `bfd/elf32-i51.c` is `complain_overflow_dont`. Nothing anywhere records which
space a symbol lives in.

```
$ $OD -dr t1.o
   7:	e5 00       	mov	A, 0x00
			8: R_I51_8	.idata+0x40
   9:	74 00       	mov	A, #0x00	; #0
			a: R_I51_8	.idata+0x40
```

A direct memory read and an immediate load of the same symbol produce the identical
relocation. The linker cannot tell them apart, so it cannot check either.

Consequences, all silent, all `ld exit=0`:

```
$ cat x.s           # excerpt; XV is at .xdata 0x1234, DV is internal RAM
	mov	r0,#XV
	mov	a,XV
	mov	dptr,#DV
$ $OD -d x.elf
   4:	78 34       	mov	R0, #0x34	; #52	#'4'
   d:	e5 34       	mov	A, 0x34
   f:	90 00 20    	mov	DPTR, #0x0020
```

- `mov a,XV` — direct-addressing an **XDATA** symbol — became `E5 34`, a read of internal
  RAM 0x34, which is `.data`/bit-addressable territory.
- `mov r0,#XV` truncated 0x1234 to 0x34. `complain_overflow_dont` means a 16→8-bit
  narrowing is never reported.
- `mov dptr,#DV` — an internal-RAM symbol as a 16-bit pointer — accepted.

The same for CODE. There is no code-pointer/data-pointer distinction anywhere in the port:

```
$ cat code.s        # excerpt; TAB is a .text label, XV is .xdata 0x40
	mov	dptr,#TAB
	movc	a,@a+dptr
	mov	dptr,#XV
	movc	a,@a+dptr
	movx	a,@dptr
	ljmp	XV
	mov	TAB,a
$ $OD -d code.elf
   0:	90 00 12    	mov	DPTR, #0x0012
   4:	93          	movc	A, @A+DPTR
   6:	90 00 40    	mov	DPTR, #0x0040
   9:	93          	movc	A, @A+DPTR
   a:	e0          	movx	A, @DPTR
   b:	02 00 40    	ljmp	0x0040
  10:	f5 12       	mov	0x12, A
```

One relocation, `R_I51_16`, for a code label and for an xdata object. The linked image
does `movc` on an xdata address, `movx` on the same pointer, `ljmp` to an xdata address,
and `mov 0x12,A` — a **code label used as an internal-RAM direct address**.

Root cause is structural: `bfd/cpu-i51.c` declares one flat 16-bit address space
(`16, /* Bits per address. */`) and the spaces exist only as section *names*. What is
missing is a space-tagged relocation set — at minimum a distinct "direct internal RAM
address" reloc, range-checked to < 0x80 in `bfd/elf32-i51.c`. That is a format change,
visible in every object the port has ever produced.

---

## S3. XDATA paging (`movx @Ri`, P2) is not modelled at all. (High)

`movx @dptr` is a 16-bit access. `movx @Ri` is an 8-bit access **within a 256-byte page
selected by P2**. The port has no page register, no page relocation, no page attribute on
a section, and no check.

```
$ cat pg.s          # PA at xdata 0x00F0, PB at xdata 0x01F0, PC_ at 0x02F1
	mov	r0,#LOW(PA)
	movx	a,@r0
	mov	r0,#LOW(PB)
	movx	a,@r0
	mov	r0,#PC_
	movx	a,@r0
$ $LD -o pg.elf pg.o; echo "ld exit=$?"
ld exit=0
$ $OD -d pg.elf | sed -n '5,12p'
   0:	78 f0       	mov	R0, #0xF0	; #240
   2:	e2          	movx	A, @R0
   3:	78 f0       	mov	R0, #0xF0	; #240
   5:	e2          	movx	A, @R0
   6:	78 f1       	mov	R0, #0xF1	; #241
   8:	e2          	movx	A, @R0
$ $OD -t pg.elf | grep -E 'PA|PB|PC_'
000000f0 l       .xdata	00000000 PA
000001f0 l       .xdata	00000000 PB
000002f1 l       .xdata	00000000 PC_
```

Two objects in different 256-byte pages compile to **identical instructions**. Which one
you touch depends on P2, which nothing in the toolchain tracks or emits. The third case,
`mov r0,#PC_` with no `LOW()` at all, silently discarded the page: 0x02F1 → 0xF1.

The only available route is hand-written:

```
$ $OD -d x.elf | sed -n '8,11p'
   7:	78 34       	mov	R0, #0x34	; #52	#'4'
   9:	75 a0 12    	mov	0xA0, #0x12	; #18
```

`LOW(XV)` into R0, `HIGH(XV)` into P2 (0xA0), by hand. Nothing verifies the two belong to
the same symbol, that P2 is still valid at the `movx`, or that a `.xdata` object does not
straddle a page boundary.

---

## S4. `.edata` and `.eeprom` are aliases of `.xdata`. Different "spaces", same address, same instruction. (High)

The script places all three at 0:

```
  .xdata 0x0000 (INFO) : ...
  .edata 0x0000 (INFO) : ...
  .eeprom 0x0000 (INFO) : ...
```

```
$ cat ov.s          # one byte in each of .xdata, .edata, .eeprom, each read via dptr
$ $LD -o ov.elf ov.o; echo "ld exit=$?"
ld exit=0
$ $OD -d ov.elf | sed -n '5,12p'
   0:	90 00 00    	mov	DPTR, #0x0000
   3:	e0          	movx	A, @DPTR
   4:	90 00 00    	mov	DPTR, #0x0000
   7:	e0          	movx	A, @DPTR
   8:	90 00 00    	mov	DPTR, #0x0000
   b:	e0          	movx	A, @DPTR
$ $OD -t ov.elf | grep -E 'XA|EA_|EEA'
00000000 l       .xdata	00000000 XA
00000000 l       .edata	00000000 EA_
00000000 l       .eeprom	00000000 EEA
```

Three variables in three "different" spaces at address 0x0000, reached by three identical
`movx a,@dptr`. On real parts a second external space or on-chip EEPROM is selected by a
chip-select line, a bank register, or (on the AT89S8252 whose SFRs this port hardcodes)
`WMCON`. The port emits nothing and checks nothing, so `.edata` and `.eeprom` are storage
that silently collides with `.xdata`. As a memory model they are decorative.

`.eeprom` also has no size bound — `.xdata` and `.edata` get an ASSERT, EEPROM does not:

```
$ printf '\t.text\n\t.global _START\n_START:\tnop\n\t.eeprom\n\t.space 0x10001\n' > eep.s
$ $AS -o eep.o eep.s && $LD -o eep.elf eep.o; echo "ld exit=$?"
ld exit=0
$ $NM eep.elf | grep -i eeprom
00010001 ? __EEPROM_END
00000000 ? __EEPROM_START
```

64 KB + 1 of EEPROM links clean. A bound would go beside the others in
`ld/scripttempl/elf32i51.sc`.

---

## S5. The stack is entirely the programmer's problem, and the tools will let RAM be 100% full. (High)

The whole of the port's stack support:

```
$ grep -n 'STACK' mcs51/*.patch
mcs51/additions.patch:4205:+  PROVIDE (STACK = __IDATA_END);
mcs51/additions.patch:4206:+  PROVIDE (__STACK = STACK);
```

No size reservation, no headroom ASSERT, no code that sets SP, nothing that stops the
stack growing into data. The one RAM ASSERT permits a zero-byte stack:

```
$ for n in 0xDF 0xE0 0xE1; do  ...  $LD -o f.elf f.o  ...  done
== .idata size 0xDF : link OK  __IDATA_END=0x000000ff
== .idata size 0xE0 : link OK  __IDATA_END=0x00000100
== .idata size 0xE1 : link FAILED: ld-new: internal RAM overflow (past 0xFF)
```

At 0xE0 internal RAM is completely full, `STACK` == 0x100, and the link succeeds. At 0xDF
the program gets exactly one byte of stack:

```
$ $NM -n stk.elf | grep -E 'STACK|IDATA_END'
000000ff I STACK
000000ff I __IDATA_END
$ $OD -d stk.elf | sed -n '5,8p'
00000000 <_START>:
   0:	75 81 fe    	mov	0x81, #0xFE	; #254
   3:	11 07       	acall	0x0007
```

`mov SP,#STACK-1` then `ACALL` pushes two bytes: SP 0xFE → 0xFF (the one free byte) →
0x00, which wraps and overwrites R0 of bank 0. Linked without a word.

Two further gaps on the same axis:

- Nothing sets SP. On reset SP = 0x07, so the stack starts at 0x08 — **inside register
  bank 1**. A program that does not move SP and uses `.using 1` corrupts itself. `STACK`
  is only `PROVIDE`d, so a program that never mentions it links fine with the reset value.
- `ld`'s region machinery cannot help, because internal RAM is not a region. There is
  exactly one:

```
$ $LD --verbose | sed -n '/MEMORY/,/^}/p'
MEMORY
{
  rom (rx) : ORIGIN = 0x0000, LENGTH = 0x10000
}
$ $LD --print-memory-usage -o stk.elf stk.o
Memory region         Used Size  Region Size  %age Used
             rom:           9 B        64 KB      0.01%
```

0xDF bytes of internal RAM are invisible to `--print-memory-usage`. Every RAM space is an
`(INFO)` non-alloc section whose address is arithmetic on the preceding section — which is
also precisely what disables `ld`'s overlap checking between spaces (see S8).

---

## S6. Register banks: `.using` is one global assembler variable with file scope. No bank is reserved by default, and `.rdata` then lands on bank 0. (Medium-high)

`tc-i51.c` keeps `static unsigned char regbank` for the whole assembly. `.using` writes it,
`AR0..AR7` read it. It is not scoped to a section, a function or a subsection, and it is
never saved or restored:

```
$ cat rb.s          # excerpt
	.using 2
_START:
f1:	push	AR0
	mov	PSW,#0x18	; hardware switches to bank 3
	push	AR0
	.using 1
f2:	push	AR0
	.data
	.using 3		; a .using written inside a DATA section
	.text
f3:	push	AR0
$ $OD -d rb.o | sed -n '5,15p'
   0:	c0 10       	push	0x10
   2:	75 d0 18    	mov	0xD0, #0x18
   5:	c0 10       	push	0x10
00000007 <F2>:
   7:	c0 08       	push	0x08
0000000a <F3>:
   a:	c0 18       	push	0x18
```

- A `.using 3` written inside `.data` changes `AR` encoding in a later `.text`. Space and
  bank state are unrelated in the hardware; here one directive leaks across both.
- `mov PSW,#0x18` selects bank 3 at run time; the assembler keeps encoding bank 2. (ASM51
  does not track PSW either, so this is defensible — but ASM51's `USING` is a
  procedure-level declaration, not one file-global variable.)
- Function boundaries mean nothing: `F3` inherits whatever the last `.using` in the file
  set, wherever it was written.

Bank reservation happens only if some `.using` was seen. `i51_cleanup()` then emits
`__RB__` as a `.regbank` common of `regused+8` bytes:

```
$ $RE -s rb.o | grep RB__
     9: 00000010    32 OBJECT  GLOBAL DEFAULT PRC[0xff00] __RB__
```

With no `.using` anywhere — the common case for code that simply uses R0–R7 — nothing is
reserved and `.rdata` starts at 0x00, on top of bank 0, which exists at reset regardless:

```
$ $LD -o rb3.elf rb2.o && $NM -n rb3.elf
00000000 ? RV
00000000 ? __RDATA_START
00000000 ? __REGBANK_START
```

`RV` is at 0x00 = R0. The default is wrong: bank 0 is always live.

At the other end, reserving all four banks pushes `.rdata` out of the register area:

```
$ $NM -n rb.elf | grep -E 'RV|RDATA|BDATA_START'
00000020 ? RV
00000020 ? __RDATA_START
00000021 ? __BDATA_START
```

`.rdata` is documented in `tc-i51.h` as `0x00..0x1F register, direct, indirect
addresable`. With 32 bytes of banks reserved there is no room left in 0x00–0x1F, so it
spills into 0x20–0x2F and silently eats bit-addressable bytes.

---

## S7. `push AR0` without `.using` crashes gas with an internal error. (Medium)

```
$ printf '\t.text\n\tpush\tAR0\n' > rb0.s
$ $AS -o rb0.o rb0.s; echo "exit=$?"
rb0.s: Assembler messages:
rb0.s:2: Error: missing .using
rb0.s: Fatal error: Case value 63 unexpected at line 1382 of file "../../binutils-2.47/gas/symbols.c"
exit=1
```

That is `BAD_CASE (op)` in `resolve_symbol_value()`. Root cause is in `tc-i51.c`:
`md_assemble()` presets `op_expr1.X_op = O_max` (63); `i51_parse_operand1()` hits the
`missing .using` path and does a bare `return`; `md_assemble()` never learns the operand
failed and calls `i51_build_ins()` → `fixup8()` → `fix_new_exp()` with `O_max`. Every
early `return` in `i51_parse_operand1/2` has this shape, so the crash is reachable from
the other operand errors too. A diagnosed error should not end in a fatal internal error.
Fix would go in `gas/config/tc-i51.c`: propagate operand-parse failure out to
`md_assemble()` and skip `i51_build_ins()`.

---

## S8. The address space is not recorded in the object format. `readelf` cannot tell the spaces apart and `nm` is useless. (Medium)

`include/elf/i51.h` defines `SHF_RDATA`, `SHF_BDATA`, `SHF_IDATA`, `SHF_XDATA`,
`SHF_EDATA`, `SHF_REGBANK`. Nothing stamps them. `bfd/elf32-i51.c` says so itself:

```
   Stamping a code onto one of them would reach i51_elf_section_from_shdr () on the
   way back in and hand the linker a section of real data to place as a common.
   The classification is unimplemented.  */

static bool
i51_elf_fake_sections (...)
{
  return 1;
}
```

Six spaces, identical flags, all at Addr 0 in the object:

```
$ $RE -S sp.o
  [ 4] .rdata            PROGBITS        00000000 000036 000001 00  WA  0   0  1
  [ 6] .idata            PROGBITS        00000000 000038 000001 00  WA  0   0  1
  [ 7] .xdata            PROGBITS        00000000 000039 000001 00  WA  0   0  1
  [ 8] .edata            PROGBITS        00000000 00003a 000001 00  WA  0   0  1
  [ 9] .eeprom           PROGBITS        00000000 00003b 000001 00  WA  0   0  1
```

`nm` is worse — the class letters are inconsistent noise:

```
$ $NM -n sp.elf | head -6
00000000 ? EEPVAR
00000000 e EVAR
00000000 ? RVAR
00000000 ? XVAR
00000000 T _START
00000000 E __EDATA_START
```

`XVAR` (xdata) prints `?`, `EVAR` (edata) prints `e`, `IVAR` (idata) prints `i`, `RVAR`
(register area) prints `?`. No consumer can classify a symbol from `nm`. Only
`objdump -t`, which prints the section **name**, works:

```
$ $OD -t sp.elf | grep -E 'XVAR|IVAR|DVAR'
00000023 l       .data	00000000 DVAR
00000025 l       .idata	00000000 IVAR
00000000 l       .xdata	00000000 XVAR
```

The address space of a symbol survives only as a naming convention. That is also why S2
cannot be fixed in the linker as things stand: by relocation time the space is gone.

Related: in a linked image the `(INFO)` treatment turns every bss space into PROGBITS
carrying real bytes in the file (`$RE -S sp.elf`: `.bss`, `.xbss`, `.ibss` all
`PROGBITS ... W`), where the objects correctly had them as `NOBITS`.

---

## S9. No part model. The tools assume an 8052 and cannot be told otherwise. (Medium)

```
$ $AS --target-help
A51 options:
                   NONE
```

`bfd/cpu-i51.c` declares a single machine (`0, /* Machine number - 0 for default. */`)
with no variants. There is no way to say 8031/8051 (128 bytes of internal RAM, no upper
RAM at all), 8052 (256), or to state ROM size, XDATA size, or a second DPTR. The script
hardcodes the 8052 assumption in `ASSERT (__IDATA_END <= 0x100, ...)`. On an 8051 half of
that RAM does not exist: a program that places data at 0x90 and reads it back through
`@Ri` links, runs on an 8052, and reads open bus on an 8051. Combined with S1, the address
0x90 has three possible meanings — SFR, upper RAM, nothing — and the port models none of
them.

---

## S10. `R_I51_13_PCODE` silently truncates code addresses above 0x1FFF. (Low)

`bfd/elf32-i51.c`:

```
      /* Use lower 13 bits for addresses > 0x1FFF */
      if (srel > 0x1FFF)
	srel = srel & 0x1FFF;
```

A relocation that cannot represent its target should return `bfd_reloc_overflow`, not
mask. `gas` diagnoses the underflow case (`pcode exec address underflow`) but not this
one. Low only because `.pcode` is a niche byte-code stream, not ordinary MCS-51 code.

---

## What the port gets right

Stated because the above is one-sided:

- `.rodata` is folded into `.text`, i.e. into code space, which is correct for a Harvard
  machine: constants are reachable only by `movc`, and `movc a,@a+dptr` / `movc a,@a+pc`
  encode correctly (`93` / `83` in `code.elf`).
- SFR names are reserved and collisions are caught rather than silently shadowed —
  `P1: .byte 0` gives `Error: symbol 'P1' is already defined`, whichever order it appears
  in. `.local P1` deliberately frees the name and the symbol then relocates as an ordinary
  `R_I51_8`: a clean, deliberate escape hatch.
- The total internal-RAM bound does fire (`internal RAM overflow (past 0xFF)`), and the
  xdata/edata 64 KB bounds exist.
- The B2B path in `bfd/elf32-i51.c` range-checks properly (`bfd_reloc_outofrange` below
  0x20, for 0x30–0x7F, for non-multiple-of-8 SFRs) — exactly the space-aware checking that
  every other 8-bit relocation lacks. It shows the shape a fix for S2 would take.

---

## Summary

| # | Finding | Severity |
|---|---------|----------|
| S1 | Direct RAM unbounded at 0x80; `.data` at 0x90 emits SFR accesses | Critical |
| S2 | Relocations carry no space; cross-space references assemble and link clean | Critical |
| S3 | XDATA paging (`movx @Ri` / P2) not modelled at all | High |
| S4 | `.edata`/`.eeprom` alias `.xdata`; `.eeprom` unbounded | High |
| S5 | Stack unreserved, unchecked, uninitialised; RAM may be 100% full | High |
| S6 | `.using` is one file-global variable; no bank reserved by default, `.rdata` on bank 0 | Medium-high |
| S7 | `push AR0` without `.using` → gas fatal internal error | Medium |
| S8 | Space unrecorded in ELF; `nm` cannot classify; six spaces look identical | Medium |
| S9 | No part model; 8052 assumed unconditionally | Medium |
| S10 | `R_I51_13_PCODE` masks addresses above 0x1FFF | Low |

The through-line: the port models the 8051's several address spaces as **section names in
one flat 16-bit BFD address space**. That is enough to lay data out and not enough to
check anything. Every finding above except S7 follows from it.

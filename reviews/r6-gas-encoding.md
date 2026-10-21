# gas i51: instruction matching & encoding review

Tools: `$BUILD/gas/as-new`, `ld-new`, `objdump`, `objcopy` from current main
(BUILD=/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/work/modern/build).
Source: `.../work/modern/binutils-2.47/gas/config/tc-i51.c`, `include/opcode/i51.h`.

Repro convention: `printf '<src>\n' > t.s && as-new -o t.o t.s && objcopy -O binary --only-section=.text t.o t.bin && xxd t.bin`
(`objdump -dr t.o` for relocs). Two-file repros use `ld-new -o x.elf a.o b.o`.

## Method

* `enc/ref.py` is a separate MCS-51 encoder written from the Intel opcode map. It covers all 111 forms.
* `enc/matrix.py` assembles every mnemonic (46) with 0, 1 and 2 operands drawn from 19 operand kinds, plus 3-operand cjne:
  A, R3, @R1, number, SFR name, ARn, #imm, #imm16, bit name, numeric bit 0x20.3, /bit, /0x20.3, C, DPTR, @DPTR, @A+DPTR, @A+PC, AB and a label.
  That is 17,641 lines. Each result is classified against the reference. Results are in `enc/matrix.tsv`.
  * 216 lines encode correctly. Every valid form is accepted with correct bytes.
  * A separate sweep of every Rn/@Ri gave 251/251 correct and covered 241 of 256 opcodes. The 15 not covered are A5 and the ajmp/acall page variants, which were checked by hand.
  * **0 valid forms are rejected and 0 valid forms get wrong bytes.**
  * **302 invalid lines are accepted silently.** They fall into finding 1 (operand drop) and finding 7 (bit suffix and code label taken as a byte).
* `enc/fuzz.py` ran 60,000 files of 40 random lines each, mixing tokens and expression edge cases. There were **no crashes, no internal errors and no as_fatal.**
* Ranges, branch boundaries, expressions and aliases were probed by hand. Each item below was reassembled and its bytes read back.

Results that came out clean:
* #imm range is -128..255 (-129 and 256 are rejected).
* sjmp/jc/jb/cjne/djnz boundaries of +127/-128 are exact.
* ajmp/acall page check is correct in the .o.
* Branch to a global or external symbol links correctly.
* `e-s` and `.`, LOW/HIGH of section symbols, `mov dptr,#sym` and undefined symbols (relocation kept) all behave.
* No crash anywhere.

---

## CRITICAL: valid source, wrong bytes, no diagnostic

### C1. Constant or `.equ` branch targets are resolved section-relative and lose their relocation (sjmp/jc/jnc/jz/jnz/jb/jnb/jbc/cjne/djnz/ajmp/acall)

```
a.s:  nop
      nop
      nop
      nop
b.s:  .equ tgt,0x10
      sjmp 0x10
      ajmp tgt
      jnb 0x20.0,tgt
ld-new -o e.elf a.o b.o ; objdump -d e.elf
   4: 80 0e   sjmp .+0x10  ; 0x0014   <- expected 80 0a (target 0x0010)
   6: 01 10   ajmp 0x10    (ok only because same page)
   8: 30 00 09 jnb ...     ; 0x0014   <- expected 30 00 05
```

The .o has no relocation, so after linking every branch points to target plus the section's load address.

ajmp/acall are affected the same way, including the page check:

```
p.s:  .space 0x7fe
q.s:  ajmp 0x10
      acall 0x20
ld-new p.o q.o
  7fe: 01 10  ajmp 0x810    <- expected an error (target in page 0, PC in page 1)
  800: 11 20  acall 0x820
```

Both assemble and link with rc=0.

Cause:
* `md_pcrel_from_section` (tc-i51.c:786) returns the section-relative `fr_address+where+1` when `fx_addsy==NULL`.
* `md_apply_fix` (tc-i51.c:821) sets `fx_done` for `s == absolute_section`.
* The BFD_RELOC_I51_11 case (~tc-i51.c:899) runs the page check against the section-relative PC and then writes the final bytes.

A relocation against `*ABS*` has to be kept for an absolute target in a relocatable section. `tb/isa/zeroops.txt` only checks this at address 0, where the error cancels out.

### C2. `HIGH(...)` / `LOW(...)` swallow the rest of the operand expression

| Source | Actual | Expected |
|---|---|---|
| `mov a,#high(0x1234)+1` | `74 12` | `74 13` |
| `mov a,#high(0x1234) & 0x0f` | `74 00` | `74 02` |
| `mov a,high(x)+1`, `cjne a,#high(x)+1,l`, `mov 0x30,#high(x)+1` | same pattern | |

With a symbol you get `R_I51_H x+1`, which is HIGH(x+1) rather than HIGH(x)+1.

Cause: `i51_prefix_keyword` (tc-i51.c:1978) leaves `input_line_pointer` on the `(`. `expression()` then parses `(0x1234)+1` as the operand of HIGH. Keil, ASEM-51 and the gas convention all treat HIGH as an operator on the parenthesised term only.

Related: `#1+high(x)` and `#(high(x))` are rejected, with cascading errors reported on "line 2".

### C3. HIGH()/LOW() on a bit operand is silently dropped when the operand is relocatable

```
setb high(EXT)
setb low(EXT2)
as -> d2 00  R_I51_8_BIT EXT   (no H/L)
ld-new --defsym EXT=0x0012 ... -> d2 12  (expected d2 00)
```

The constant case `setb high(0x1234)` gives `d2 12`, which honours the prefix, so the two paths disagree.

The same happens for `jb/jnb/jbc/mov c,/cpl/clr high(sym)`.

Cause: `fixup8` I51_OP_BIT case (tc-i51.c:1884) picks only between 8_B2B and 8_BIT and ignores HIGH/LOW. It should either emit H/L or reject the prefix.

### C4. `ARn` inside an expression is frozen at the first `.using`

```
.using 0
mov r0,#ar7
.using 2
mov r0,#ar7
push ar7
-> 78 07 78 07 c0 17      (second insn expected 78 17)

.using 0
mov a,ar1+0
.using 1
mov a,ar1+0
mov a,ar1
-> e5 01 e5 01 e5 09
```

Cause: `md_undefined_symbol` (tc-i51.c:1104-1127) creates a permanent absolute symbol `ARn = regbank+n` the first time ARn appears in an expression. That covers `#arN` and any arithmetic. After that, later `.using` directives are ignored. Bare `arN` goes through the operand table and is correct.

### C5. Text after the 3rd operand of `cjne` is assembled as another instruction

```
l: cjne a,#1,l xret          -> b4 01 fd 22        (an extra RET, no diagnostic)
l: cjne r0,#1,l xmov a,#7    -> b8 01 fd 74 07
l: cjne a,#1,l junk          -> "line 2: unknown opcode `unk'"
```

Cause: md_assemble (tc-i51.c:699-722) has no end-of-line check after operand 3 and sets `input_line_pointer = line` while it still points mid-line (tc-i51.c:728). read.c then writes the saved newline over the first remaining character, `*input_line_pointer++ = nul_char`, and resumes there.

The same mechanism, through the early `return` paths, produces the cascaded "line 2: unknown opcode / junk" errors on many bad lines (see L1).

### C6. Forward-referenced constants skip the range check

Backward references to the same values are rejected.

| Source | Actual |
|---|---|
| `ljmp fw` / `.equ fw,-70000` | `02 ee 90` |
| `mov dptr,#fw` / `.equ fw,0x12345` | `90 23 45` |
| `mov a,#fw` / `.equ fw,-200` | `74 38` |
| `mov a,fw` (fw=-200) | `e5 38` |
| `setb fw` (fw=-200) | `d2 38` |

Cause:
* md_apply_fix BFD_RELOC_16 (~tc-i51.c:895) has no range check.
* The 8-bit cases accept -256..255. `check_range` uses -128..255 for the immediate path.

---

## CRITICAL (invalid source accepted, operand silently dropped or retargeted)

This extends known item 1. It is the same root cause, but it is much wider than single-operand mnemonics.

### C7. Fallback to the last row of a mnemonic group for operand 1 and operand 2

Taken from the matrix. All of these produce no diagnostic:

| Source | Bytes | What the bytes actually do |
|---|---|---|
| `add 0x45,#0x5a` (also addc/subb) | `24 45` | add A,#0x45, and #0x5a is lost. `#0x1234` is not even range-checked. |
| `add 0x45,0x45` | `24 45` | |
| `anl 0x45,0x46` (also orl/xrl, and `anl p1,0x45`, `anl ar5,0x45`) | `53 45 46` | anl 0x45,**#**0x46 |
| `xch 0x45,0x46` | `c5 45` | xch A,0x45 |
| `cjne 0x45,0x46,l` | `b5 45 rel` | cjne A,0x45 |
| `xchd 0x45,@r1` | `d7` | |
| `xchd a,0x45` | `d6` | |
| `movx 0x45,a` | `f0` | movx @DPTR,A |
| `movx @dptr,0x45` | `f0` | |
| `movc 0x45,@a+pc` / `movc a,0x45` | `83` | |
| `div`, `mul`, `da`, `rl`, `rlc`, `rr`, `rrc`, `swap` or `jmp` with an address operand | 1-byte bare form | |

Cause:
* `i51_parse_operand1` (tc-i51.c:1238-1245): when the scan reaches the last row (`insn_size & 0x80`), `op1mode = opcode->args[0]` is set regardless of what was parsed.
* `i51_parse_operand2` (tc-i51.c:1397): `op2mode = opcode->args[1]` is set unconditionally after the scan.

As a result, md_assemble's final `op1mode==args[0] && op2mode==args[1]` test always passes for a generic expression.

The fix: give a generic expression its own kind ('D'/'B'/'J' and so on), and only accept a row whose arg letter is one of the expression-compatible kinds.

---

## MEDIUM: accepts invalid input or gives a bad diagnostic

* **M1. A numeric `.N` bit suffix is folded on every operand, not just bit operands.**
  * `mov a,0x20.3` gives `e5 03`.
  * `mov a,#0x20.3` gives `74 03`.
  * `ljmp 0x20.3` gives `02 00 03`.
  * `mov dptr,#0x80.1` gives `90 00 81`.
  * `mov a,#1.5` gives "0x1 is not bit addressable".

  Cause: `i51_fold_bit_suffix` is called unconditionally (tc-i51.c:1248, 1406, 1442).
* **M2. B2B() is accepted on byte operands.**
  * `mov a,b2b(0x20,3)` gives `e5 03`.
  * `push b2b(0x20,1)` gives `c0 01`.
  * `anl b2b(0x20,1),#3` gives `53 01 03`.
  * With a symbol, `mov a,b2b(v,3)` (v in .bdata) gives `e5 00` plus a plain `R_I51_8 .bdata`, so the `,3` is lost completely.

  B2B is rejected where it would be legal: `orl c,/b2b(..)` and `mov 0x30,b2b(..)` both give "garbage".

  Cause: tc-i51.c:1222-1227 and 1383-1387, then `fixup8` IMM8 with the B2B prefix.
* **M3. Negative direct or bit addresses are accepted.**
  * `mov a,-1` gives `e5 ff`.
  * `setb -1` gives `d2 ff`.
  * `push -5` gives `c0 fb`.
  * `jb -1,.` gives `20 ff fd`.
  * `ljmp -1` gives `02 ff ff`.
  * `mov dptr,#-65536` gives `90 00 00`.

  Cause: `check_range` treats IMM8 and BIT alike as -128..255, and IMM16/JUMP_INPAGE as -65536..65535.
* **M4. Standard bit names are missing.** `PSW.n`, `IE.n`, `IP.n`, `TCON.n`, `SCON.n` and `F1` are not in `i51_directop`. PSW.1 is spelled `FL`.

  `setb psw.3`, `jb ie.7,l`, `setb f1`, `setb acc.8` and `clr a.0` therefore assemble with rc=0 to `d2 00` plus a relocation against an undefined symbol `PSW.3`. The error only appears at ld time ("undefined reference to `PSW.3'").
* **M5. Register names inside expressions become external symbols.**
  * `mov a,r0+1` gives `e5 00` plus `R_I51_8_DIR R0+1`.
  * `mov a,#r0`, `mov a,#a` and `mov a,#dptr` give `R_I51_8_IMM R0/A/DPTR`.

  These only fail at link time. Cause: `md_undefined_symbol` returns 0 for 'R'/'A'/... refs.
* **M6. No memory-space check on direct operands.**
  * `mov a,xv` where `xv` is in `.xdata` gives `e5 00` plus `R_I51_8_DIR .xdata`. It links silently and reads R0, not XRAM.
  * `mov a,iv` where `iv` is in `.idata` is accepted as well. The comment in tc-i51.h says .idata is indirect-only.
  * `mov a,lbl` with a code label also passes.

  `i51_check_direct` only checks the in-section offset against 0x80.
* **M7. Labels named like an SFR or bit are accepted but cannot be used.**
  * `es: nop` / `ljmp es` gives "unknown instruction operand 1: `ES'".
  * Single-letter labels such as `b:`, `p:` or `c:` hit the same problem, with a misleading message.
  * `ljmp es+0` before `es:` silently binds to bit 0xAC, then fails with "already defined".

## LOW

* **L1. Error-path recovery.** Error returns in md_assemble leave `input_line_pointer` mid-line, so one bad line produces spurious follow-on errors attributed to "line N+1". Examples: `mov a,#high 0x1234` gives "unknown opcode `x1234'", and `cjne a,#1,.,.` gives "unknown pseudo-op `.'".
* **L2. Divergences from Keil/ASEM-51/sdas.** All of these error rather than silently misassembling, except the first two:
  * Generic `jmp` gives 0x73 (known). Generic `call` is "unknown opcode".
  * `11b` is a gas backward local label, not binary.
  * `$` is `line_separator_chars`, so `sjmp $` gives "missing operand".
  * `0FFh` is rejected.
  * sdas `#<x` / `#>x` are rejected.
  * `HIGH x` without parentheses is rejected.
  * `mov dptr,#high(x)` is rejected with "HI/LOW/B2B prefix not allowed".
* **L3. Misleading range messages.** `mov a,#1.5` says "0x1 is not bit addressable". "Operand out of 16-bit range" is printed for ajmp.

## Not found

* No crash or internal error from the operand matrix, the 2.4M-line fuzz, bignums, floats, `(1<<64)`, unbalanced parentheses or empty operands.
* No valid form is mis-encoded or rejected. All 255 defined opcodes match the Intel map.

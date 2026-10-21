# R7 regression lane: behaviour changes of `claude/r6-fixes` against origin/main

Tools: OLD = scratchpad/old/*, NEW = work/modern/build (HEAD 95ecb8d).
Work dir: scratchpad/review7/regress/ (probe harness `probe.sh`, assembly differ
`asmdiff.sh`, ISA differ `isadiff.py`, every probe's input/outputs under `p/<name>/`).

## What was compared, and what came out the same

| check | result |
|---|---|
| All 106 `.asm` in the tb tree (projekt/*, cgi/*, lib/*), each assembled in its own dir by OLD and NEW: section bytes (`objdump -s`), `nm -a`, relocations (`readelf -r`, R_I51_16_CODE folded to R_I51_16) | 100 identical; 4 differ in nm only (`cgi/rts`, `cgi/xon`, `lib/http`, `lib/serial`: OLD leaked a local absolute `ACC` symbol after `B2B(ACC,..)`, NEW does not — OK-INTENDED); `lib/case_aliases.asm` fails in both; **`lib/packet.asm` assembles with OLD, fails with NEW** (finding 2) |
| 10 projects built by their Makefiles (www51.sc, prebuilt OLD lib objects/archives) | ROM, EEPROM image, map and `nm` of `www8051.o` identical OLD vs NEW |
| Same, with `cgi/*.obj` rebuilt by each assembler | identical ROMs and maps |
| `make -C lib libw.a` from source | OLD ok, **NEW fails** (packet.asm) |
| tb/isa 8051.txt + extra.txt + zeroops.txt, every line assembled and linked (default script) by each toolchain | 0 differences, all match golden bytes |
| tb/isa/testall.asm through tb/dialect.py, linked with each toolchain's default script | identical .text |
| OLD objects linked by NEW ld (B2B at offset 0, .bdata/.data, acall/ajmp/sjmp, ljmp/lcall R_I51_16, HIGH/LOW, .word) | identical image to OLD ld |
| NEW objects linked by OLD ld | `invalid relocation type 14` (R_I51_16_CODE) — clean refusal, expected |
| Listings (`-a=`) of the projects | differ only in the symbol table (finding 7) |

## Findings (ranked)

### 1. WRONG (silent miscompile, claimed fix #6 incomplete): `HIGH(sym)+n` / `B2B(sym,b)+n` with a relocatable operand fold `n` *into* the operand

The manual says (Address Modifiers): "When their operand is not yet known, the
operator becomes a relocation, and has to be the whole operand." NEW instead
accepts the expression and folds the constant into the relocation addend:

```
 .text
 .ds.b 0x120
x: mov a,#high(x)+1      ; want 0x02  -> NEW emits R_I51_H .text+0x121 -> 74 01
   mov a,#high(x)-1      ; want 0x00  -> R_I51_H .text+0x11f            -> 0x01
   mov a,#1+high(x)      ; same as first
   .byte high(x)+1       ; same
   mov a,#high(EXT)+1    ; R_I51_H EXT+1
 .bdata
 .ds.b 1
f: .ds.b 1
   setb B2B(f,3)+1       ; want bit 0x0C -> R_I51_8_B2B .bdata+2 -> d2 13
```
(p/hl5, p/hl6, p/b2bplus). `LOW(x)+n` is harmless (mod 256). OLD rejected
the B2B form and also got HIGH wrong (so not a regression vs OLD), but the series
claims this fixed and the `high-low` test only uses constants. Cause:
`i51_strip_operator` (tc-i51.c ~1636) turns `O_i51_high` into `O_symbol` and
keeps `X_add_number`, which expr() already summed the outer `+n` into.
Should be: refuse a non-zero outer addend on O_i51_high/O_i51_b2b (or encode
it after the operator, which no reloc can).

### 2. REGRESSION: `#data16` range narrowed to -32768..65535; the shipped lib no longer builds

`lib/packet.asm:298  MOV DPTR,#-40982` (a count-up timeout = 0x5FEA). OLD: `90 5f ea`.
NEW: `Error: operand out of 16-bit range: -40982`, so `make -C lib` (libw.a) fails.
The gate never rebuilds lib/ (projects link prebuilt archives), so it stayed green.
Inconsistent with the same assembler's data directives: `.word -40982` is accepted
(5f ea) and `.byte -200` too (38), while `mov dptr,#-40982` / `mov a,#-200` are refused.
ASEM-51/A51 evaluate in 16-bit modulo arithmetic and accept it. OLD's own bound was
broken the other way (`#-65536` silently became 0). Suggest -65535..65535 for 16-bit
immediates (as `.word` does). From commit d1a1ab3 ("standard relocation"/range checks).

### 3. REGRESSION (minor): `.local R0` + `.equ R0,5` no longer shadows the register

```
 .local R0
 .equ R0, 5
 mov a,R0        ; OLD e5 05 (direct 5)   NEW e8 (register R0), no diagnostic
 mov a,#R0       ; both 74 05
```
SFR names, ARn (lib/pcmpwi.asm `.local AR5`) and bit names are shadowable, R0-R7/A/C
are not, and the definition is accepted silently, so one name means two things in one
file — exactly what the use-then-define rule exists to stop. Should be an error or warning.

### 4. WRONG-INTENT / DOC: zero-valued initializers in RAM are silently dropped

The new refusal of initialized RAM data exempts zero bytes ("a reservation"):
`.data; v: .byte 0` links clean and v is *not* zero at reset (RAM is undefined —
the very reason for the refusal). A user writing an explicit `0` almost always means
"initialised to 0". Same for `.xdata`/`.bitdata`. At least warn; `.ds`/`.space` are the
reservation spellings.
Related DOC conflict: c-i51.texi `.bit` says "This is how initialized data is written in
the bit space", but the default script now refuses `.bitdata` + `.bit 1` (p/bitdata).

### 5. OK-INTENDED but breaks formerly-fitting programs (documented): bank 0 + `__STACK_SIZE`

- `.rdata` moves from 0x00 to 0x08 without `.using`; everything above shifts. A program
  with 0x28 bytes of `.rdata` and a `.bdata` linked with OLD (bdata at 0x28) now fails
  `bit-addressable data overflow (past 0x2F)` (p/rdbig3). Intended (R6 #18), diagnosed.
- `.data 0x50` + `.idata 0x88` (OLD: STACK=0xF8, 8 bytes left) now fails
  `no room for __STACK_SIZE bytes of stack`; `--defsym __STACK_SIZE=0` restores it (p/stackfit).
  Message names the knob — fine. `__EEPROM_SIZE` defaults to 0x10000, so the eeprom
  bound checks nothing on the AT89S8252 (2 KB) this port targets.

### 6. OK-INTENDED: the other deliberate changes, verified
- `jmp lbl`: OLD `73` (jmp @a+dptr!), NEW `ljmp`; `call` was "unknown opcode" in OLD, now
  `lcall`. Always-long differs from ASEM-51/A51 (shortest form) but is safe and documented.
- SFR shadowing: `.equ P1,0x20` was "already defined" in OLD, now accepted; use-then-define
  is refused. OLD *accepted* `mov a,WMCON` before `.local WMCON / .equ WMCON,0x96` (p/shadow3);
  NEW refuses — documented. **The use-then-define error carries no line number**
  (`in.s: Error: ...`) — DOC/usability.
- `.global P1` with no definition now makes `mov a,P1` an external reference (OLD used 0x90).
- `.local` + `.comm` across two files: OLD one shared global common `BUF`; NEW two private
  4-byte objects (0x20, 0x24). Documented, but a silent cross-file semantic change; no
  corpus file uses `.local` with a common.
- `$`: OLD already split `a$b`; only `1$:` dollar local labels are lost (OLD assembled them).
  Documented; corpus has none.
- `NAME.N` for user symbols (`FLAGS.3`, `.bdata` label `.3`, `0x20.3`) works; OLD made it an
  undefined symbol `FLAGS.3`. `0x30.3` is refused. Labels `loop.1:` still work (`sjmp loop.1`).
- R_I51_8 now range-checked: `.byte TBL+0x210` (code address) was silently truncated by OLD ld
  (0x17), now an error for OLD and NEW objects alike. `-Ttext`/projects unaffected.
- acall/ajmp always relocated: OLD ld links them fine (R_I51_11); only R_I51_16_CODE and
  R_I51_32 (`-g`, `.long`) are unknown to OLD tools — clean error. `R_I51_16_CODE` doc
  mentions old objects; nothing says new objects need the new linker (DOC-MISSING, minor).
- `.byte B2B(f,2)`, `B2B(F , 2)`, `orl c, / acc.7`, `jb B2B(0x2f,7),y`, `@a + dptr`, `# 5`,
  `a , r0`, `@ r0`, `#-1`, `0b101`, `017`, `'A'`, `','`, `';'`, comments containing commas,
  macro-generated operands: NEW accepts all; bytes equal OLD wherever OLD accepted.
  `0FFH`/`1fh` refused by both (dialect.py rewrites them).

### 7. REGRESSION (cosmetic): listing symbol tables lose `file:line`
Every symbol declared with `.local` before its `.equ` (include/param.inc: P2, P3.2, ACC.n,
CPUCLOCK, BAUD, …) is listed without its source location, in `.local` order instead of
definition order (all 10 projects' `.lst`). Bytes unaffected. ELF `.local` creates the
symbol before the `.equ` gives it a location.

### 8. DOC/diagnostics (low)
`mov a,#high(x)*2` → `invalid operands (*GAS `expr' section* and *ABS* sections)` plus
`can't resolve value for symbol `L0'` (no line); `mov a,#-high(x)` → `can't resolve 0 - L0`
twice. Internal names leak; should be "HIGH() of a relocatable value must be the whole operand".

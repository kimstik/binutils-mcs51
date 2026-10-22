# R8 regression lane: current toolchain (NEW) against the pre-series toolchain (OLD)

Tools: OLD = scratchpad/old/*, NEW = work/modern/build/*. Work dir: scratchpad/review8/regress/
(`asmdiff.sh` per-file differ, `probe.sh name [as-flags] < src` prints OLD/NEW as/ld status + linked
.text hex, every probe under `p/<name>/`; `tb-old/`, `tb-new/` = corpus built by each toolchain;
`xl-old/`, `xl-new/` = cross links; `isadiff.py`, `testall/`, `libcmp/`, `dis/`, `lst/`).

## What was compared

| check | result |
|---|---|
| All 106 `.asm` of tb/base.7z (projekt/*, cgi/*, lib/*), each assembled in its own dir by OLD and NEW: `objdump -s`, `nm -a`, `readelf -r` (R_I51_16_CODE folded to R_I51_16) | 105 assemble with both; section bytes and relocations identical for all 105. `nm` differs in 5: `cgi/rts`, `cgi/xon`, `lib/http`, `lib/serial` (OLD leaked local abs `ACC` after `B2B(ACC,..)`), `lib/packet` (OLD leaked `AR2..AR7`). OK-INTENDED. `lib/case_aliases.asm` fails in both (definition loops, file not in any Makefile). |
| `lib/packet.asm` (`MOV DPTR,#-40982`) | now assembles, `90 5f ea` = OLD (R7 #2 fixed) |
| 10 projects built by their own Makefiles with wrappers in `tb-{old,new}/bin` | all 20 builds ok; `www8051.rom`, `.eep`, `map`, `nm www8051.o` identical OLD vs NEW; link warnings (WORKREG/CHKACC alignment discrepancies) identical in both |
| `make libw.a web51.obj` in lib/ from source | OLD ok, NEW ok; all 37 members byte-identical OLD vs NEW (prebuilt `libw.a` member `disp4.obj` differs from both - stale prebuilt archive, not a tool issue) |
| OLD-assembled project objects linked by NEW ld (via the Makefile, `LINKER=`) | 10/10 ROM and EEPROM identical to the OLD build |
| NEW-assembled project objects linked by OLD ld | 10/10 `invalid relocation type 14` (R_I51_16_CODE) - clean refusal, expected |
| tb/isa 8051.txt + extra.txt + zeroops.txt (302 lines), assembled+linked by each | 0 differences, all equal golden bytes |
| tb/isa/testall.asm through dialect.translate, linked with each default script | identical 3351-byte .text |
| Listings `-a=`: 10 projects + 37 lib listings + a HIGH/LOW/B2B/.pcode probe | bytes/lines identical; only the symbol table differs: NEW now gives `file:line` for `.global`/`.local`-before-`.equ` symbols and lists them in definition order; OLD's leaked ACC/ARn are gone. Better than OLD (R7 #7 fixed). |
| Multi-file `.using`/`__RB__`, `.local`+commons, space commons with alignment, OLD/NEW object mixes, gen-2 object, `ld -r` of gen-0 objects | see findings 4-6; gen-0 objects link identically with NEW and OLD ld; gen-2 refused by NEW ld; `ld -r` of gen-0 objects emits gen 1 with space-common st_value rewritten to 1 (semantics kept) |
| `-mmcu` 8051/8052/at89s8252/AT89S8252/foo | default = at89s8252 = OLD bytes; 8051 makes WMCON/T2CON/TR2/DP1L ordinary undefined symbols (link error); `foo` refused. OLD had no option. |
| Data directive ranges, constants (`.byte` +-255/256, `.word` +-65535/65536, -40982) | identical OLD/NEW incl. truncation warnings |
| Data/immediate ranges through relocations (`--defsym E=`) | `.byte E` -0xff..0xff, `.word E`/`mov dptr,#E` -0xffff..0xffff; outside now refused by NEW ld (OLD silently truncated). `#E` -0x80..0xff and direct 0..0xff: same in OLD and NEW |
| Immediate ranges in as | `mov a,#` -128..255 both; `mov dptr,#` now -65535..65535 (OLD -65535..65535 too, but -65536 silently became 0 in OLD; NEW refuses it) |
| Disassembler (`objdump -d`, linked image and .o with -r) | branch targets now `addr <sym+off>` instead of `.+0xNN ; 0xADDR`; hex lower case; decimal/char comments (`; #20`, `#'i'`) dropped; registers stay upper case; bit operands still numeric (`jb 0xe7, ...`). OK-INTENDED. |
| Case folding (tc_canonicalize_symbol_name) | symbols/`.equ`/`.set`/`--defsym`/quoted names fold to upper case (as OLD); section names keep case; `.startof.(.MyTab)` / `.sizeof.(.MyTab)` now resolve (OLD folded to `.STARTOF..MYTAB` = undefined); `.STARTOF.(.text)` spelled upper also works |

## Status of R7 findings against NEW

| R7 | status |
|---|---|
| 1 WRONG `HIGH(sym)+n`, `B2B(sym,b)+n` folded into addend | **FIXED**: all forms (`+n`, `n+`, `-n`, `*2`, unary `-`, `|0`, nested, EXT) refused with "HIGH(), LOW() and B2B() of a value not known here have to be the whole operand"; constants still compute (`#high(0x1234)+1`=0x13, `setb b2b(0x20,3)+1`=bit 4). Note `#LOW(x)+1` is now refused too (OLD accepted it, correct mod 256) - documented. |
| 2 REGRESSION `#data16` -32768.. | **FIXED**: -65535..65535; libw.a builds |
| 3 `.local R0`/`.equ R0,5` ignored | **FIXED**: `mov a,R0` = `e5 05` as OLD |
| 4 zero init in RAM silently a reservation | **DOC'd** (Memory Spaces: "A zero byte is accepted as a reservation; it does not make the RAM zero at reset"); `.bit` text now consistent. Still no warning (design choice). |
| 5 bank 0 / `__STACK_SIZE` | unchanged, OK-INTENDED, documented; `__EEPROM_SIZE` limit-nothing now documented |
| 6 use-then-define error had no line | **FIXED** (`in.s:2: Error: ...`); other items unchanged and OK |
| 6 doc: new objects need new linker | still not said explicitly (finding 7) |
| 7 listing lost file:line | **FIXED**, now better than OLD |
| 8 internal names in HIGH diagnostics | **FIXED** |

## Findings (ranked)

### 1. REGRESSION: a forward reference to a dotted name (`loop.1`, `cnt.1`) is split into `NAME.N`

Labels and `.equ` names containing `.digits` are still accepted and backward references work, but a
reference before the definition is now parsed as `B2B(NAME,N)` (tc-i51.c i51_parse_name ~850: any
not-yet-defined `X.N` falls into the `else` branch and creates symbol `X`).

```
 .text
 ljmp loop.1          ; OLD 02 00 09   NEW: Error: invalid instruction operands
 mov dptr,#tab.2      ; OLD 90 00 0a   NEW: Error: a bit address is not a number
 .byte cnt.1          ; OLD 05         NEW: assembles R_I51_8_B2B against CNT -> ld: undefined `CNT'
 djnz r0,loop.1       ; OLD d8 00      NEW: Error: invalid instruction operands
loop.1: nop
tab.2: nop
 .equ cnt.1, 5
```
(p/dotfwd5, p/dotfwd6, p/dotfwd8). Also `.global V.3` + `setb V.3` still references `V.3`, but a
plain `setb EXT.3` to a dotted name defined in another file now references `EXT` (p/dotglob,
p/dotn3). No corpus file has dotted labels, so no project is affected. The manual does not say that
dotted names are only usable after definition. Either refuse defining `X.N` names, or diagnose
"`X.N` used as bit N of X and defined later" like the built-in-name rule.

### 2. WRONG (silent, low likelihood): same, when the base name exists

```
 .bdata
W: .ds.b 1            ; W = 0x20
 .text
 setb W.3             ; OLD d2 50 (the .equ below)   NEW d2 03 = B2B(W,3), no diagnostic
 nop
 .equ W.3, 0x50
```
(p/dotfwd3). One name means two things in one file; the "used here as the built-in name and defined
later" check covers `ACC.3` (p/dotfwd4) but not program-symbol `NAME.N`.

### 3. DOC/REGRESSION (minor): space commons of exactly 0x10000 are dropped with a warning

Manual (Directives): "A memory-space common may ask for at most `0x10000`." NEW:
```
 .xcomm A6,0x10000     ; Warning: size (65536) out of range, ignored  -> A6 never created
 .rcomm A4,0x10001     ; same warning (OLD accepted both)
```
(p/bigcomm). Generic `s_comm_internal` masks size with `bits_per_address` = 16, so the real limit is
0xFFFF, and an out-of-range size is a *warning* that drops the declaration, leading to "undefined
reference" at link instead of an error at the line. Fix the doc to 0xFFFF and/or make it an error.

### 4. DOC (minor): `__RB__` defined in a file without `.using` is accepted and overrides the bank reservation

```
 .text
 .global __RB__
 .equ __RB__, 1        ; e.s: assembles clean
```
`ld e.o a.o b.o` (a/b use `.using 1/2`) links with only "alignment 16 of common symbol `__RB__` ... *ABS*"
warnings; `__RB__` = 1 absolute and the banks are no longer reserved. Manual says "a program that
defines `__RB__` itself is refused" - true only in a file that also uses `.using`, and that error
(`e2.s: Error: `__RB__' is the register-bank common ...`) has no line number. (p/multi/e.s, e2.s)

### 5. OK-INTENDED (documented), behavioural differences confirmed on probes
- `.local X` + `.comm X` in two files: OLD one global common (0x24); NEW two private copies (0x21, 0x25).
- Space-common alignment: NEW objects carry e_flags=1; NEW ld honours alignment (`.icomm IB,3,8` at
  0x30); OLD ld silently links NEW objects without R_I51_16_CODE and places IB at next free byte
  (0x29); NEW ld places OLD (gen 0) commons exactly like OLD ld; gen 2 refused ("unknown e_flags 0x2").
- `jmp lbl`/`call lbl` -> ljmp/lcall (OLD: `73` / unknown opcode).
- `.global P1` with no definition -> external `P1` (OLD 0x90).
- `PSW.3`, `FLAGS.3`, `Y.3` (Y=.equ 0x21), `0x90.5` now work (OLD: undefined symbols `PSW.3` etc.).
- `1$:` local labels refused (`$` is a separator); message "junk at end of line, first unrecognized
  character is `1'" twice - accurate but unhelpful.
- A label named like a register (`r1: mov a,r1`) shadows it: NEW assembles `mov a,direct R1` and ld
  refuses "a direct address cannot name code memory" (OLD: as error). With `.equ r1,0x30` it would
  be silent `e5 30` - per the documented shadowing rule.
- `.byte EXT+0x100` now refused at assembly ("value of 256 too large for field of 1 byte"), OLD
  deferred to ld which truncated; matches the documented +-255.
- Relocation range checks in ld for R_I51_8 (+-255) and R_I51_16 (+-65535): OLD truncated silently.
- RAM initialised data refused; `.data` + `.ds.b 0x50`/`.ibss 0x88` needs `--defsym __STACK_SIZE=0`;
  `.rdata` starts at 0x08.

### 6. DIAGNOSTICS (cosmetic)
Range errors for instruction operands and data now come from generic write.c and are less readable
than OLD's:
```
 mov dptr,#65536   ; NEW: value of 00010000 too large for field of 2 bytes at 0000000d
                   ; OLD: Operand out of 16-bit range: `65536'.
 .byte la-lb       ; NEW: value of fffffedc too large for field of 1 byte at 00000001 (hex for -292)
```
(p/r2, p/bytediff). `HIGH(HIGH(x))` gives "HIGH() of HIGH(), LOW() or B2B() of a value not known
here" (reads truncated). `.pcode 0x100 #WORD -65536` is accepted as 0 (OLD too), the one place left
with the -65536 bound (tc-i51.c pcode_flags ~1942) instead of -65535.

### 7. DOC-MISSING (minor, carried from R7)
Nothing says that NEW objects need the NEW linker: OLD ld refuses R_I51_16_CODE (every ljmp/lcall)
and R_I51_32 with "invalid relocation type 14", and links NEW objects without them while ignoring
common alignment. The ABI-generation paragraph covers only the common placement.

## Verdict
No regression on the real corpus: all 105 assemblable files, all 10 projects (ROM, EEPROM, map,
symbols), libw.a from source and OLD objects through NEW ld are byte-identical to OLD. All R7
correctness findings are fixed. New issues are edge cases around dotted names (1, 2) and two
doc/limit mismatches (3, 4).

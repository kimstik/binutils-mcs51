# Validation of the four fix branches merged into `work/green`

Review only. Nothing in `mcs51/`, `tb/` or `.github/` was touched. Every
throwaway build, mutated source and crafted input lives under `/tmp`.

Branch under review: `claude/validate-merged`, cut from `origin/work/green`
at `0f45319`.

```
0f45319 bfd: bounds-check r_offset before relocating          <- claude/robustness      e58a22a
b19c94e opcodes: teach the disassembler about symbols, ...    <- claude/binutils-tools  c6bab63
6c69255 gas: fix the assembler's user-facing surface          <- claude/gas-surface     d48b3fe
f109a44 tb: close the holes the gate could not see            <- claude/close-holes     91653a3
afee4a5 ci: build, gate and frozen workflows                  <- common merge-base of all four
```

---

## Verdict

| # | case | verdict | proof / what is missing |
|---|------|---------|-------------------------|
| 1 | `f109a44` ← `claude/close-holes` | **DONE** | `make -C tb gate` runs 11 stages and passes; `script` reports `146 covered, 319 checks`; `hexoracle.py` goes red on a byte moved between classes with size and residual unchanged; `romdiff.py` rejects a 2-column `frozen.expect`; `frozen.expect` re-derived from a fresh 2.11.2 build and every recorded value matches. Mutation: **111/198 killed (56.1%)**, one more absolute kill than the claimed 110, on a denominator that moved from 195 — **no regression**, see §6. |
| 2 | `6c69255` ← `claude/gas-surface` | **DONE** | All seven defects reproduced on a pre-fix build and gone on green. `push ar7` kills pre-fix gas with `Case value 63 unexpected`; green prints one diagnostic. 1206-input hostile corpus: 2 internal fatals pre-fix, 0 on green. |
| 3 | `b19c94e` ← `claude/binutils-tools` | **DONE** | `print_address_func`/`fprintf_styled_func` work (`ljmp 26 <RESET>`, ANSI escapes with `--disassembler-color=on`); pre-fix has neither. `i51_symbol_is_valid` removes every `*ABS*`/`.reg`/`.bss`/`.bitbss`/`.ibss`/`.bbss` misnaming; the remainder are all `.eeprom`. The exact figures 2342/239/76 are **not** reproducible with an independent counter — see §4. |
| 4 | `0f45319` ← `claude/robustness` | **DONE** | ASan pre-fix `ld` aborts on both crafted objects at `elf32-i51.c:407` (write) and `:358` (read); green ASan `ld` is clean. Guard sits before the `switch`, so it covers all five port-handled types and the default; per-reloc mangling: 7/16 ASan hits pre-fix, 0/16 on green. |

No case is UNTESTED: all four were reproduced on a pre-fix build and re-run on
green. Two numeric claims inside otherwise-verified cases could not be
reproduced and are flagged as such, not as failures: the `239 → 76` figures in
case 3 (§3) and the `56.4% (110/195)` kill rate in case 1 (§6).

Known gap, confirmed factually: **`tb/fuzz/` did not come across.** See §7 —
and note that deleting the guard `0f45319` added leaves the whole eleven-stage
gate green, so nothing in the repository can now tell whether that fix is
still there.

---

## 0. Method

Five toolchains were built from the same `binutils-2.47` tarball, plus the
frozen 2.11.2 tree for §1c.

| name | source | flags | purpose |
|------|--------|-------|---------|
| `greenbuild` | `work/green` patches (release recipe `make -C tb build`) | `-Os -flto -march=haswell` | the merged port |
| `gr-asan` | same tree | `-O1 -g -fsanitize=address` | memory-safety checks |
| `pre/b-plain`, `pre/b-asan` | `mcs51/*.patch` **as of `afee4a5`** | `-O2 -g` / `-O1 -g -fsanitize=address` | the pre-fix tree |
| `nosiv` | green tree with only the `case bfd_arch_i51: info->symbol_is_valid = …` block removed from `opcodes/disassemble.c` | `-O1` | isolates the `symbol_is_valid` half of case 3 |

The pre-fix trees were produced by extracting `mcs51/additions.patch` and
`mcs51/modifications.patch` at `afee4a5` and applying them to a pristine
tarball — not by reverting hunks.

### Did everything land in the merge?

All four branches share the merge-base `afee4a5`, and `work/green` is a linear
rebase of the four. Comparing the *final source content* (extracted from
`mcs51/additions.patch` at each revision) rather than the patch text:

```
$ cmp <branch>/gas/config/tc-i51.c <green>/gas/config/tc-i51.c   # etc.

claude/close-holes    : touches no port source (tb/ and .github/ only)
claude/gas-surface    : gas/config/tc-i51.c (105 lines), gas/config/tc-i51.h (6)   -> byte-identical in green
claude/binutils-tools : opcodes/i51-dis.c (96 lines), mcs51/modifications.patch    -> byte-identical in green
claude/robustness     : bfd/elf32-i51.c (15 lines)                                 -> byte-identical in green
```

Nothing was dropped or altered from the four branches' port changes. `f109a44`
carries *more* `tb/Makefile` change than `claude/close-holes` did (a
patch-offset guard in `build:` and a failing-project guard in `oracle:`); that
is addition, not loss. The one thing that did not come across is `tb/fuzz/`
(§7).

---

## 1. `f109a44` — the three gate holes

### 1a. `oracle` gates on all six byte-class counts

`tb/hexoracle.py` carries `CLASSES = ["addr16","acall11","word16","pcode13","zero8","residual"]`
and an `EXPECT` table with a six-tuple per project. Verified by execution, not
by reading: one byte of `ds1620`'s produced ROM was set equal to the oracle
byte at an offset that was previously counted as `zero8`, so **the ROM size
and the residual count are both unchanged** and only one non-residual bucket
moves.

```
before sabotage: {'addr16': 308, 'acall11': 1, 'word16': 137, 'pcode13': 25, 'zero8': 400} residual 25
zero8 byte at offset 0x0040: oracle=00 produced=6a
after  sabotage: {'addr16': 308, 'acall11': 1, 'word16': 137, 'pcode13': 25, 'zero8': 399} residual 25
size unchanged: True  residual unchanged: True

FAIL ds1620: zero8 399 (recorded 400)
1 of 10 projects deviate from the 2001 oracle
hexoracle.py exit = 1
```

A residual-only gate would have passed that. Claim verified.

**Caveat, factual:** only 8 of the 10 projects get byte-class gating. `diag`
and `serial` have `want_counts = None` in `EXPECT` and are gated on their size
delta alone — the gate run prints `explained +3` and `explained -1519` for
them and `classify()` is never called. That is documented in the file, but
"per project" in the commit message is 8/10, not 10/10.

### 1b. the `script` stage

```
$ make -C tb gate BUILD=…/work/modern/build
== script
== script arms: 146 covered, 319 checks, 38 unreachable
   unreachable  .hash .dynsym .dynstr .gnu.version .gnu.version_d .gnu.version_r
   unreachable  .rel.* .rela.*
run-script: PASS (every reachable *(...) arm of elf32i51.sc and lib/www51.sc placed its own input at its own address)
```

146 arms / 319 checks, exactly as claimed. `tb/sim/run-script.py` (679 lines)
is present in green and `script` is in both `$(TOOLGATE)` and the `gate.yml`
step list.

### 1c. `frozen.expect` and `romdiff.py`

`tb/frozen.expect` carries three data columns per project (outcome, differing
bytes, ROM size). `romdiff.py` refuses fewer. Fed a two-column file built by
stripping the size column off the real one:

```
FAIL …/two-col.expect:1: 'diag not-produced 0' gives 2 column(s) after the
project name, 3 required (outcome, differing bytes, ROM size) - this
expectation file predates the size column and cannot be trusted
rc=1
```

Against the real three-column file the same run reports per-project movement
and exits 1. Claim verified.

The recorded numbers are not just structurally three columns — they are
right. The whole frozen line was rebuilt from scratch here (`make -C tb
frozen` on binutils 2.11.2 with `gcc -m32`, then `make -C tb check-frozen`
with the `base2001.7z` overlay, then `romdiff.py --expect`):

```
identical 0, different 9, missing 1

## outcome against tb/frozen.expect
PASS diag     not-produced 0 0        PASS led2     differ 214 5010
PASS ds1620   differ 217 6284         PASS led3     differ 214 5200
PASS ds1822   differ 225 6078         PASS serial   differ 325 8128
PASS lcd      differ 214 5754         PASS welcome  differ 213 4812
PASS led1     differ 213 5173         PASS wjava    differ 213 4812
all 10 projects match the recorded frozen outcome.
romdiff.py exit = 0
```

`make -C tb check-frozen` itself ended nonzero (rc=2, "10 of 10 projects
failed"), which is the `failure` outcome `frozen.yml`'s Verdict step records
as expected. Both halves of that workflow's gate are satisfied by the file as
committed.

### 1d. `gate.yml` runs the list

`.github/workflows/gate.yml` runs `isa roundtrip branch bits reloc sim
defaultlink commons script check` + `check-canary` + `oracle` as separate
steps with `if: always()`, in `$(GATE)` order. `check` is there. Matches
`tb/Makefile`'s `GATE := $(TOOLGATE) check oracle`.

---

## 2. `6c69255` — the gas surface

Each defect reproduced on `pre/b-plain` and re-run on `greenbuild`. Same
input file, same command line.

| # | input | pre-fix (`afee4a5`) | green |
|---|-------|---------------------|-------|
| 1 | `push ar7` (no `.using`) | `Error: missing .using` **then** `Fatal error: Case value 63 unexpected at line 1382 of file "gas/symbols.c"` | `Error: missing .using`, rc=1 |
| 1b | `mov a,AR0` | same fatal | one diagnostic, rc=1 |
| 2 | `--defsym ext=0x123` + `ljmp ext` | `nm`: `U EXT` **and** `00000123 a ext` — two different symbols, the defsym never binds | `nm`: `00000123 a EXT`, bound |
| 3 | `.using 1 nop` | rc=0, assembles `00 22` — the `nop` is silently taken | `Error: junk at end of line, first unrecognized character is 'n'`, rc=1 |
| 4 | `.pcode 0x100 BYTECOUNT` | `objdump -r`: `R_I51_8  COUNT` — `BYTE` eaten as a keyword, relocating against a symbol the source never names | `R_I51_16  BYTECOUNT` |
| 5 | `mov a,#-129` | rc=0, emits `74 7f` = `mov A,#127` | `Error: Operand out of 8-bit range: '-129'`, rc=1 |
| 6 | `.comm cx,4,4` | `readelf -s`: alignment `00000001` | `00000004` |
| 7 | `mov c,0x33.1` as the last line of a 2-line file | three diagnostics, the last at **line 3 of a 2-line file** | one diagnostic at line 2 |

All seven land. Three follow-ups:

**Does the `O_max` guard cover every parser path, or only the tested ones?**
The guard is `if (had_errors () != errors_before) return;` placed immediately
before the *only* call site of `i51_build_ins` (line 751; the other match at
line 1487 is the definition). Every bare `return` inside the two operand
parsers is preceded by an `as_bad`, so every path that abandons an operand
also bumps the error count:

```
i51_parse_operand1: lines 1159-1291,  8 bare returns,  8 preceded by as_bad
i51_parse_operand2: lines 1294-1484, 11 bare returns, 11 preceded by as_bad
```

Verified empirically as well, with the hostile assembler
corpus recovered from `claude/robustness`'s `tb/fuzz/` (406 hand-written plus
800 random inputs):

```
pre/b-plain: 1206 inputs -> 2 internal/Case-value fatals, 0 signals
             (using_missing.s, r00554.s)
greenbuild:  1206 inputs -> 0 internal/Case-value fatals, 0 signals
```

**Regressions from the `.comm` alignment fix:** none found. Explicit
alignments are now recorded, implicit ones are unchanged, and the linker
places them:

```
                    pre-fix   green
.comm  a4,4,4          1        4
.comm  a1,4            4        4      (unchanged)
.comm  a8,8,8          1        8
.comm  a0,4,0          4        4      (unchanged)
.xcomm x4,4,4          1        4
.icomm i2,2,2          1        2

green link: X4@0x00  A0@0x20  A8@0x28  A4@0x30  A1@0x34  I2@0x38
```

**Regressions from `pcode_keyword()`:** none. Every valid operand keyword form
still assembles to byte-identical output on both builds:

```
                                              pre-fix          green
.pcode 0x100 #0x1234, @0x40, #BYTE 0x12   4100d412 344012  4100d412 344012
.pcode 0x100 BYTE 0x34, SWAP 0x56, SHL8 0x78  01006834 5678    01006834 5678
.pcode 0x100 WORD 0x9a, @BYTE 0x11, @WORD 0x33 6100549a 1033   6100549a 1033
```

Only names that merely *start* with a keyword change, which is the fix:

```
.pcode 0x100 BYTECOUNT, WORDY, SWAPPER

pre-fix objdump -r:  R_I51_8  COUNT   R_I51_16  Y    R_I51_16  PER
green   objdump -r:  R_I51_16 BYTECOUNT  R_I51_16 WORDY  R_I51_16 SWAPPER
```

`make -C tb commons` and `make -C tb reloc` also pass on green.

---

## 3. `b19c94e` — the disassembler

`print_address_func` and `fprintf_styled_func` both work, and neither exists
pre-fix:

```
green:    0:  02 00 26    ljmp    26 <RESET>
pre-fix:  0:  02 00 26    ljmp    0x0026

green   --disassembler-color=on:  ^[[33mljmp^[[0m ^[[35m26^[[0m <^[[32mRESET^[[0m>
pre-fix --disassembler-color=on:  ljmp  0x0026          (no escapes at all)
```

`i51_symbol_is_valid` is registered in `disassemble_init_for_target`
(`mcs51/modifications.patch`) together with `created_styled_output = true`.

### The 239 → 76 claim

**Not reproducible as stated, and it cannot be, from the pre-fix tree.** The
"before" figure was never measured on `afee4a5`: pre-fix `objdump` prints
`ljmp 0x0026` with no `<symbol>` at all, so the count of "annotated code
targets" there is 0. The 239 was measured on an intermediate tree — the
address hook in, the symbol filter not yet in. That tree was reconstructed
(`nosiv`, green minus only the registration block) and the measurement redone
with an independent counter over all ten `www8051.o` images:

```
counting <sym> and <sym±0xNN> annotations on ljmp/lcall/ajmp/acall:
  nosiv  : 2543 annotated code targets, 296 outside .text (11.6%)
             *ABS* 165  .eeprom 60  .reg 36  .bss 17  .bitbss 8  .ibss 7  .bbss 3
  green  : 2543 annotated code targets, 124 outside .text (4.9%)
             .eeprom 124

counting only exact <sym> hits:
  nosiv  : 1788 targets, 113 outside .text  (.reg 36  *ABS* 35  .eeprom 20  .bss 11  .bitbss 8  .bbss 3)
  green  : 1707 targets,  32 outside .text  (.eeprom 32)
```

The **substantive** claim holds in both countings and is what matters: every
`*ABS*` SFR misnaming and every `.reg`/`.bss`/`.bitbss`/`.ibss`/`.bbss`
misnaming is gone, and **every remaining wrong one is `.eeprom`** — 124 of 124,
or 32 of 32. That is consistent with the stated reason: `readelf -S` shows
`.eeprom … WAX`, i.e. `SEC_CODE` is genuinely set on it, so the filter cannot
tell it from `.text`.

The three *numbers* 2342 / 239 / 76 are not reproducible with an independent
counter; they depend on an unstated counting rule. Treat them as
unverified-but-directionally-correct, not as measurements.

What the change actually does, on `led1/www8051.o`:

```
nosiv (no filter)                       green (filter on)
 1c0: 01 e4     ajmp e4 <ACC.4>          1e9: 61 10   ajmp 310 <RESETRQ+0x2>
 1c2: 02 4c 02  ljmp 4c02 <IP_MAGIC1+…>  251: 61 10   ajmp 310 <RESETRQ+0x2>
 1d0: 02 b4 03  ljmp b403 <IP_MAGIC2+…>  36e: 02 04 31 ljmp 431 <__eeprom_end+0x8f>
 222: d1 60     acall 660 <GIANT+0x76>   371: 02 04 42 ljmp 442 <__eeprom_end+0xa0>
```

`ajmp e4 <ACC.4>` is a subroutine named after an SFR bit equate. Those are
gone. What is left is `.eeprom` symbols reached because that section really
carries the code flag.

**No regression:** the `info->section` half of the filter works. `objdump -D`
on a data section still prints its own labels, identically to `nosiv`:

```
Disassembly of section .reg:
00000000 <__RB__>:      00000008 <DATA_ADDR>:      0000000a <DATA_LEN>:      0000000c <UNWRITED>:
```

---

## 4. `0f45319` — the `r_offset` bounds check

The guard sits at the entry of `i51_final_link_relocate`, **before the
`switch`**, so it covers all five port-handled types *and* the `default:` arm.
The `howto` sizes match the accesses each arm makes, so
`bfd_reloc_offset_in_range` checks the right width in each case:

```
R_I51_7_PCREL  size 1  <- bfd_put_8
R_I51_11       size 2  <- bfd_getb16 / bfd_putb16
R_I51_8_B2B    size 1  <- bfd_get_8  / bfd_put_8
R_I51_13_PCODE size 2  <- bfd_getb16 / bfd_putb16
R_I51_16       size 2  <- bfd_putb16
```

Reproduced with the crafted objects recovered from `claude/robustness`'s
`tb/fuzz/repro/` (they are not in green — §7):

```
$ ASAN_OPTIONS=detect_leaks=0 pre/b-asan/ld/ld-new -e 0 \
    --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 --defsym EXTBIT=0x20 \
    -o /dev/null oob-write-r_offset.o

==15569==ERROR: AddressSanitizer: SEGV on unknown address 0x50400001000f
==15569==The signal is caused by a WRITE memory access.
    #0 bfd_putb16 bfd/libbfd.c:773
    #1 i51_final_link_relocate bfd/elf32-i51.c:407
    #2 elf32_i51_relocate_section bfd/elf32-i51.c:534

$ … oob-read-sh_size.o
==15612==ERROR: AddressSanitizer: heap-buffer-overflow … READ of size 1
    #0 bfd_getb16 bfd/libbfd.c:745
    #1 i51_final_link_relocate bfd/elf32-i51.c:358

$ ASAN_OPTIONS=detect_leaks=0 gr-asan/ld/ld-new … oob-write-r_offset.o
(.text+0xffff): warning: internal error: out of range error       <- no ASan report
$ ASAN_OPTIONS=detect_leaks=0 gr-asan/ld/ld-new … oob-read-sh_size.o
(.text+0x4): warning: internal error: out of range error          <- no ASan report
```

**Does it cover all five?** Beyond the structural argument: every relocation
in `tb/fuzz/seed.s` (which carries one of every type the port defines) was
taken in turn and its `r_offset` set to `0xffff`, then linked under ASan.

```
pre-fix linker: ASan/signal on 7 of 16 mangled relocations
   R_I51_11       2/2 <- port-handled     R_I51_8      0/3
   R_I51_16       4/4 <- port-handled     R_I51_8_BIT  0/2
   R_I51_8_B2B    1/1 <- port-handled     R_I51_H      0/1
   R_I51_7_PCREL  0/1 <- port-handled     R_I51_L      0/1
   R_I51_13_PCODE 0/1 <- port-handled

green linker:   ASan/signal on 0 of 16 mangled relocations
```

Every one of the pre-fix hits is a port-handled type, and every one is gone.
(`R_I51_7_PCREL` and `R_I51_13_PCODE` do not trip on *this* input because both
return early — overflow and `srel < 0x100` respectively — before touching
`contents`; that is a limit of the crafted input, not of the guard, which runs
before either.)

**Residual weakness, pre-existing, not a regression:** the port reports every
non-`ok` status through `info->callbacks->warning`, so
`bfd_reloc_outofrange` prints `warning: internal error: out of range error`
and does not fail the link — `ld` exited **0** on `oob-read-sh_size.o` on both
the pre-fix and the green build. Memory safety is fixed; the "malformed object
still links" part is untouched and was untouched before. Where a fix would go:
`elf32_i51_relocate_section`'s status switch in `bfd/elf32-i51.c` (the block
ending `(*info->callbacks->warning) (…)`) would have to route
`bfd_reloc_outofrange` through `->einfo`/a failure return rather than
`->warning`. **Not made here.**

---

## 5. Full gate

`make -C tb gate BUILD=…/work/modern/build` — **PASS**, 11 stages, in order:

```
== isa           table 280 + 3 instructions, program testall.asm   PASS
== roundtrip     280/280, 3/3, 18/18                               PASS
== branch        24 cases                                          PASS
== bits          50 cases                                          PASS
== reloc         36 checks                                         PASS
== sim           testall ran to completion, P1=127                 PASS
== defaultlink   default emulation links and lays out all spaces   PASS
== commons       commons keep their space, name and neighbours     PASS
== script        146 arms covered, 319 checks, 38 unreachable      PASS
== check         10/10 projects match the reference ROMs           PASS
== oracle        10/10 agree with the 2001 .hex                    PASS

gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
```

`make -C tb check` standalone — **PASS**:

```
PASS diag 1267 …  PASS ds1620 6284 …  PASS ds1822 6078 …  PASS lcd 5754 …
PASS led1 5173 …  PASS led2 5010 …    PASS led3 5200 …    PASS serial 8128 …
PASS welcome 4812 …  PASS wjava 4812 …
all 10 projects match the reference
```

`make -C tb check-canary` (in `gate.yml` but not in `$(GATE)`) — **PASS**:

```
CANARY PASS: check exited nonzero, 10 project(s) reported FAIL
```

### 5a. The gate cannot see any of the three code fixes

Run the same 11-stage gate against the **pre-fix** build (`afee4a5`, the tree
that still has all seven gas defects, the unfiltered disassembler and the
unguarded relocation):

```
$ make -C tb gate BUILD=…/pre/b-plain WORK=…/pwork
gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
```

Every stage passes, `check` matches all ten reference md5s, `oracle` agrees on
all six byte classes. So the merge gate — including the `script` stage
`f109a44` added — is blind to every defect `6c69255`, `b19c94e` and `0f45319`
fixed. That is not an argument against those fixes; it is the measurement of
what §7 costs.

---

## 6. `make -C tb mutants`

```
198 mutants -> work/mutants/mutants.json
--stages isa,roundtrip,branch,bits,reloc,sim,defaultlink,commons,script,check
baseline: isa roundtrip branch bits reloc sim defaultlink commons script check all pass

== 198 mutants in 6559s
   killed    111
   survived   87
   no-build    0
   KILL RATE 56.1% (111/198)
```

### Read this number carefully

**The denominator moved.** The claimed baseline was 110/195 = 56.4%. That 195
is the population `gen.py` produces on the `afee4a5` tree, reproduced here
exactly:

```
$ python3 tb/mutation/gen.py --tree <afee4a5 tree> --cap 12 --out /tmp/mut-pre.json
195 mutants -> /tmp/mut-pre.json

$ python3 tb/mutation/gen.py --tree work/modern/binutils-2.47 --cap 12 ...
198 mutants
```

`work/green` gained code, so `gen.py` found three more sites. **In absolute
terms the suite kills one more mutant than the baseline claimed: 111 against
110.** The percentage fell 0.3 points only because the denominator grew. A raw
percentage comparison is misleading in either direction and no conclusion is
drawn from it here.

Three rates, all of the same 111 kills:

| population | rate |
|---|---|
| all 198 mutants | **56.1% (111/198)** |
| killable population, 198 minus the 9 comment-only mutants that cannot be killed by construction | **58.7% (111/189)** |
| baseline as claimed, for reference only — different population | 56.4% (110/195) |

**It is a floor, not the suite's power.** Three known reasons, all from §8:
9 of the 198 mutants change only comment text and are unkillable; `gen.py`
silently drops mutants on id collision (4 of 202, per the parallel review), so
four faults were never tested at all; and `hexoracle.py` gates `diag` and
`serial` on ROM length alone.

### Where the kills came from

```
file                            killed  survived      operator   killed  survived
bfd/elf32-i51.c                     36        40      relop          22        11
gas/config/tc-i51.c                 31        19      constpm1       19        16
opcodes/i51-dis.c                   19        17      opctab         19         5
include/opcode/i51.h                19         5      guard0         15         7
ld/scripttempl/elf32i51.sc           6         6      endian         10        10
                                                      howto           7        23
first stage to catch the mutant:                      retstatus       7         1
   reloc 29   bits 28   isa 25   roundtrip 19         ldnum           6         6
   check 4    branch 3  defaultlink 2  script 1       cond0           4         8
   sim 0      commons 0                               oporder         2         0
```

Two things fall out of that. `sim` and `commons` caught nothing that an
earlier stage had not already caught. And 77 of the 111 kills were first
caught by `roundtrip`, `bits`, `reloc` or `script` — precisely the four
stages missing from `run.py`'s stale `STAGES` default (§8 item 5). Since the
harness stops at the first failing stage, it cannot be said how many of those
77 a six-stage run would still catch later; 77 is the exposure, not the loss.

### Did the merged fixes bring their own coverage?

Seven of the 198 mutants sit on lines the three code commits added (by
`difflib` against the `afee4a5` sources: 79 changed lines in `tc-i51.c`, 15 in
`elf32-i51.c`, 86 in `i51-dis.c`).

| mutant | on which fix | verdict |
|---|---|---|
| `dis-constpm1-222` `(insn>>5)&0x07) << 8` → `<< 9` | `b19c94e`, the `code_target` arithmetic behind `print_address_func` | **killed by `roundtrip`** |
| `gas-relop-1608` `num >= -128` → `num > -128` | `6c69255`, the `mov a,#-129` range fix | **survived** |
| `bfd-retstatus-342` `return bfd_reloc_outofrange` → `bfd_reloc_ok` | `0f45319`, the guard's failure return | **survived** |
| `bfd-endian-335`, `bfd-endian-337` | comment text the guard added | survived — unkillable |
| `dis-relop-139`, `dis-constpm1-139` | comment text the address hook added | survived — unkillable |

So: **the disassembler fix arrived with coverage** — `roundtrip` catches a
one-bit error in its new address computation. **The gas immediate-range fix
did not**: moving its lower bound from -128 to -127 is invisible to all ten
stages. **The bfd guard did not, and could not**: `bfd-retstatus-342` is an
equivalent mutant for well-formed input, and §7 shows that deleting the guard
outright is invisible to the whole gate.

### Control: did anything that used to be killed now survive?

The full 195-mutant control was not run — it would have cost another three
hours for a comparison that changes no verdict. It was narrowed instead: only
a **survivor** of the green run can have regressed, so only the afee4a5
counterparts of green's 87 survivors were run, on the pre-fix tree with the
same ten stages.

```
$ run.py --tree <afee4a5 tree> --build <afee4a5 -O2 build> --only <81 ids> \
         --stages isa,roundtrip,branch,bits,reloc,sim,defaultlink,commons,script,check
== 81 mutants in 731s
   killed 5   survived 76
```

Matching the two populations on `(file, operator, note)` — `note` names the
exact entry and change, e.g. `R_I51_8 pc_relative false -> true`; a
`(file, op, old, new)` key cannot, because many HOWTO entries carry
byte-identical source lines:

```
green: 198 mutants, 112 distinct keys      afee4a5: 195 mutants, 110 distinct keys
unambiguous keys common to both: 80        of those, control-tested: 47

  killed on afee4a5 -> SURVIVES on green (regression) : 0
  survived on both                                    : 40
  killed on both                                      : 5
  survived on afee4a5 -> KILLED on green              : 2
     bfd-howto-91   R_I51_7_PCREL size 1 -> 2
     bfd-howto-181  R_I51_16      size 2 -> 3
```

**No regression.** Nothing the suite killed before survives now. The five
control kills (`bfd-howto-120/138/150/155/168`) are killed on green as well —
they entered the control set only through the ambiguous text key.

The two gains are the robustness fix paying for itself: `bfd_reloc_offset_in_range`
reads `howto->size`, and `size` is the one HOWTO field the new guard consults,
so a wrong size is now observable where it was not before. Both are `size`
mutations, and they are the only two.

**What was not control-tested, and why.** 13 of green's 87 survivors have no
afee4a5 counterpart at all — they are new mutation sites (`gas-relop-919`,
`gas-relop-1608`, `gas-relop-1663`, `gas-constpm1-934`, `gas-constpm1-1582`,
`bfd-retstatus-342`, `bfd-endian-335`, `bfd-endian-337`, `dis-relop-139`,
`dis-constpm1-139`, and three more), so there is nothing to compare them
against; they are covered by the new-site table above. A further 33 of the 80
unambiguous common keys were not run because their green counterpart was
*killed* — a killed mutant cannot have regressed. Mutants whose `(file, op,
note)` key is ambiguous within either population (24 in green, 25 in afee4a5)
are excluded from the comparison entirely.

---

## 7. The known gap: `tb/fuzz/` did not come across

Confirmed factually.

```
$ git ls-tree -r --name-only origin/work/green | grep -i fuzz
(nothing)

$ git ls-tree -r --name-only claude/robustness | grep -i fuzz
tb/fuzz/armangle.py            tb/fuzz/gen_dis.sh    tb/fuzz/repro/oob-write-r_offset.o
tb/fuzz/elfmangle.py           tb/fuzz/probe.sh      tb/fuzz/repro/repro.sh
tb/fuzz/gen_asm.sh             tb/fuzz/run.sh        tb/fuzz/repro/upstream-gas-deep-parens.s
tb/fuzz/gen_asm_rand.py        tb/fuzz/seed.s        tb/fuzz/repro/oob-read-sh_size.o
tb/fuzz/repro/.gitignore
```

`grep -n fuzz tb/Makefile .github/workflows/*.yml` finds only `patch --fuzz`.
There is no `fuzz` stage, nothing references the directory, and 793 lines of
harness plus two crafted objects are gone.

### What is lost

1. **The only regression test for the fix in `0f45319`.** `tb/fuzz/repro/`
   holds the two objects that reproduce the OOB write and the OOB read, and
   `repro.sh` runs them. Green ships the guard with nothing that exercises it.
   The `mutants` harness reaches that line and cannot judge it:

   ```
    82/198 bfd-retstatus-342            survived     bfd_reloc_outofrange -> ok
   ```

   Stated precisely: that mutant does not delete the guard, it makes the
   guard report success instead of failure, so for well-formed input it is an
   equivalent mutant and no test built from valid objects could ever kill it.
   That is the point — the gate never presents an object whose `r_offset` is
   out of range, so nothing about the guard is observable to it.

   Demonstrated directly. A copy of the green tree with **only** the guard
   deleted (`diff` against green is exactly those six lines and nothing
   else), built with ASan:

   ```
   $ ld-new -e 0 --defsym EXTFUNC=0x100 ... -o /dev/null oob-write-r_offset.o
   ==20288==ERROR: AddressSanitizer: SEGV on unknown address 0x50400001000f
   ==20288==The signal is caused by a WRITE memory access.
       #0 bfd_putb16 bfd/libbfd.c:773
       #1 i51_final_link_relocate bfd/elf32-i51.c:416

   $ make -C tb gate BUILD=<that build> WORK=<scratch>
   gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
   ```

   The wild write is back and the whole eleven-stage gate still passes — all
   36 reloc checks, all ten reference ROMs, all six byte classes of the
   oracle. Nothing in green can tell that this fix was removed.

   (Method note: the first attempt at this experiment copied its source out
   of `work/modern/binutils-2.47` while the mutation run was mutating that
   very tree, and picked up a live `bfd-retstatus-355` mutant; its `reloc`
   failure was that mutant, not the missing guard. The run above is from a
   source rebuilt from green's own file content, verified by `diff` to differ
   only in the guard.)

2. **The only negative-input test for gas.** Every gate stage feeds gas valid
   assembly. `tb/fuzz/gen_asm.sh` + `gen_asm_rand.py` produce 1206 inputs gas
   must *diagnose* rather than assemble, and they are what finds the `O_max`
   fatal that `6c69255` fixed (2 hits on the pre-fix build, §2). Without them
   the class of bug `6c69255` is about — a diagnostic path that kills the
   assembler — has no coverage in green at all.

3. **All ELF/archive robustness coverage.** `elfmangle.py` (253 lines) mutates
   the seed object every way it knows and feeds each mutant to `nm`,
   `objdump -x`, `objdump -D`, `readelf`, `objcopy`, `strip` and `ld`;
   `armangle.py` does the same for archives. No stage in green feeds any tool
   a malformed object.

4. **The disassembler byte-stream corpus** (`gen_dis.sh`) — adversarial
   instruction streams through `print_insn_i51`. `roundtrip` only feeds the
   disassembler bytes gas itself produced.

5. **The recorded upstream finding.** `repro/upstream-gas-deep-parens.s` is a
   40 KB nest of parentheses that blows gas's recursive-descent
   `expression()`. Reproduced here on both the pre-fix and the green ASan
   builds (`rc=139`), and it is upstream, not the port. With the file gone the
   next person to hit it has to rediscover that.

Running the recovered harness's assembler class against the green ASan build
found nothing new — 1206 inputs, 2 findings, both the known upstream
deep-parens crash:

```
findings: 2
      2 SIGNAL 11
as-new  as/expr_deep_parens       SIGNAL 11
as-new  as/expr_deep_unbalanced   SIGNAL 11
```

So restoring `tb/fuzz/` would not turn the gate red today. What it costs is
that four of the classes of bug these four commits were about have no
regression test in green.

Where the fix would go: `tb/fuzz/` restored from `claude/robustness`
(`e58a22a`), plus a `fuzz:` target in `tb/Makefile` and a step in
`.github/workflows/gate.yml`. **Not made here.**

---

## 8. Defects found, not fixed

Recorded per the review-only rule. None of these were touched.

1. **`tb/mutation/gen.py` mutates comment text.** It matches its operators
   line-by-line without a comment mask, so a comment that contains
   `bfd_getb16`, `<=`, `0x1a` or a number becomes a "mutant" that is a
   semantic no-op and can never be killed. On `afee4a5` 4 of 195 mutants were
   comment-only; on `work/green` **9 of 198** are, because `0f45319` and
   `b19c94e` added comments naming `bfd_getb16 ()`, `bfd_putb16 ()` and
   `lcall 0x1a <helper>`. That is five extra guaranteed survivors introduced
   as a side effect of documenting the fixes, and it lowers the ceiling on the
   kill rate from 191/195 (97.9%) to 189/198 (95.5%). All nine did in fact
   survive the run. (The parallel review counts 7 rather than 9 under a
   stricter rule; the two extra here are `case 'W':` and `case 'Z':` lines
   where the mutated text lies in the trailing `//` comment, so they are
   unkillable too. Nothing turns on which count is used.)
   Fix would go in `tb/mutation/gen.py`: strip `/* … */` and `// …` before
   matching, or record a comment mask per file and skip those lines.

2. **The mutant population is not stable across source edits**, so before/after
   kill rates are not comparable. `gen.py --cap 12` samples evenly across the
   matches of each `(file, operator)` pair; when the number of matches changes
   the *sample* changes, not just its size. Matching by
   `(file, operator, old text, new text)`:

   ```
   afee4a5 population: 195  (160 distinct keys)
   green   population: 198  (162 distinct keys)
   common: 140      only in afee4a5: 20      only in green: 22
   ```

   So 20 of 160 mutation sites — 12.5% — were *replaced*, not just added to,
   by what is a net gain of three mutants.
   Fix would go in `tb/mutation/gen.py`: make the sample a deterministic
   function of the matched text (e.g. hash-ordered) rather than of the index,
   so unrelated edits do not reshuffle it.

3. **`oracle` byte-class gating covers 8 of 10 projects**, not 10 (§1a).
   `diag` and `serial` carry `want_counts = None` in `tb/hexoracle.py`'s
   `EXPECT` and are gated on size delta only. Fix would go in
   `tb/hexoracle.py`: record six-tuples for those two as well, against their
   own explained baselines.

4. **`bfd_reloc_outofrange` is reported as a warning and does not fail the
   link** (§4). Pre-existing, not introduced by any of the four.

5. **The gate stage list exists in three copies and one has already
   drifted.** `tb/mutation/run.py:33`'s `STAGES` default is
   `['isa','branch','sim','defaultlink','commons','check']` — six of the ten
   in `tb/Makefile:90`'s `MUTGATE`. It does not affect the number in §6:
   `tb/Makefile:463` passes `--stages` explicitly and this run's log line 11
   reads `--stages isa,roundtrip,branch,bits,reloc,sim,defaultlink,commons,script,check`,
   with the baseline line confirming all ten. It is a maintenance hazard —
   a direct `run.py` invocation, or a stage added to the Makefile and not to
   the third copy, gets a quietly weaker run. Fix would go in
   `tb/mutation/run.py`: require `--stages` instead of defaulting.

6. Also established by the parallel review (`claude/review-testcode`,
   `1792ce5`, `REVIEW-testcode.md`) and not re-derived here: `gen.py`
   silently drops mutants on id collision — 4 of 202, one of them half the
   PCREL range check; zeroing every byte of `diag`'s and `serial`'s ROMs
   still makes `hexoracle.py` exit 0 and print that all six byte classes
   agree, which is the concrete form of item 3 above; and `isa_check.py`
   prints PASS and exits 0 with `--stages ''` or with neither `--table` nor
   `--program`.

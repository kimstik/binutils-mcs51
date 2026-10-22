# Review 9, lane r9-tests: do the tests, manual and CI back the claims?

Scope: branch `claude/r6-fixes` at HEAD `b47a487`. The review copy is `review9/tests/src`, and it equals `mcs51/*.patch` hunk for hunk. Two builds:
- `review9/tests/build` is mutated.
- `review9/tests/bc` is a clean second copy, used for the manual checks.

Nothing outside `review9/` was touched.

The clean gate passes in 29 s with all 16 stages green. The dejagnu stage now runs the full suites, all with 0 FAIL, XPASS, ERROR or UNRESOLVED:

| suite | PASS | of which the port's own | XFAIL |
|---|---|---|---|
| gas | 275 | 42 | 84 |
| ld | 267 | 46 | 234 |
| binutils | 170 | – | 66 |

Harness, in `review9/tests/`:
- `mutants9.py` holds the faults and `mutate9.py` runs them. Each fault is applied once, then the tree is rebuilt. Every gate stage except doctruth then runs on its own, so every stage that kills a mutant is recorded.
- `results9.json` and `logs/` hold the results.
- `probe9.py` and `probes9.py` show the clean and mutant behaviour of each survivor. Their output is in `probes9.out` and `probes9b.out`.

## 1. Mutation results (112 mutants)

### 1a. r8 survivors re-run on the current code (38)

**Now killed (24), all by `dejagnu`, through the new tests or the generic suites:**
- high-const, bitsuffix-imm, rng-rel, rng-11, direct-0x80;
- canon-section, canon-startof;
- rb-max, rb-defined;
- mmcu-8052, mmcu-unknown;
- secname-dot, init-bitspace, init-xdata, r16-range;
- sc-bdata, sc-bitspace, sc-xdata, sc-lchook;
- re-32, re-16, oe-symver;
- pcode-oprange, pcode-swap1.

r8 finding §2.1 (the generic suites ran nowhere) is fixed.

**Still survive, and the behaviour differs (4):**

| mutant | clean / mutant |
|---|---|
| using-cleanup | `as a.s b.s` with `.using 1` in a.s and `mov a,ar1` in b.s: "missing .using" / accepted |
| space-dir-indirect | a global `.idata` byte below 0x80 used as a direct operand: links / "a direct address cannot name indirectly addressed internal RAM" |
| **dis-page** | `.org 0x7fe` then `ajmp 0x850`: `ajmp 850` / `ajmp 50`. 907bdd9 claims "ACALL/AJMP disassembly in another page", but ld-i51/page2 puts both instructions at 0x1000, where the start of the instruction and the next instruction are in the same page. |
| **ordcomm-space** | `.xcomm buf` in b.o and `.comm buf` in a.o, linked `b.o a.o`: refused / links, with BUF at xdata 0 (see §2.1) |

**Still survive, but are equivalent or I could not show a difference (10):**
- b2b-fix-bitnum: dead code; the bit number is refused earlier.
- dis-abs, dis-sjmp-type: identical objdump output.
- sc-r-misc, sc-r-eeprom: same section order from orphan placement.
- re-none, re-rela: readelf output is identical.
- oe-commonrest: the same "junk" error.
- dollar-lex: `$` is a line separator first.
- shdr-common: needs a producer of generation-0 objects.

### 1b. r8 "tb only" kills: are they in DejaGnu now? (8)

| mutant | r8 | now |
|---|---|---|
| comm-local-sec | commons only | commons + dejagnu |
| rd-bssalloc | commons only | commons + dejagnu |
| rb-size | commons/libsrc | commons + dejagnu + libsrc |
| dis-ddswap | roundtrip only | roundtrip + dejagnu |
| sc-misc | script only | script + dejagnu |
| highlow-msg (r7) | reloc only | reloc + dejagnu |
| r8imm-range | reloc only | **still reloc only** |
| b2b-bitnum | bits only | **still bits only** |

### 1c. New faults over the code changed since ee28858 (66)

**Killed (45)**, 33 of them by dejagnu alone:
- `.pcode`:
  - address scanning: pc-scan-sign, -hash, -at, -ws, -paren; pc-comma;
  - address range: pc-addr-max, pc-addr-min;
  - operand bytes, flags and ranges: pc-byte-present, pc-flags-present, pc-stored, pc-word-lo, pc-byte-hi;
  - keywords and swap: pc-kw-boundary, pc-swap-const.
- NAME.N: nameN-note, nameN-bitflag, nameN-nocanon.
- `__RB__`: rb-label, rb-align, rb-userdef-skip.
- Commons: comm-decl-check, comm-decl-local, comm-default-align.
- `.N` suffix: bitsuf-alnum, bitsuf-n7, bitsuf-onedigit.
- iram-idata, canon-sectsym, pcrel-noguard (the r8 `sjmp .-y` segfault guard).
- bfd:
  - sign extension and the DIR/BIT relocations: b-sext, b-dir-hi, b-dir-case, b-bit-case, b-pcrel-case;
  - ordinary commons: b-ordcomm-indirect, b-ordcomm-COMMON;
  - b-seckeep;
  - fake_sections: b-fake-off, b-fake-any, b-fake-contents.
- Scripts and readelf: sc-dwarf, sc-eeprom-assert, re-reloc-type.

Two of these are killed only by a tb stage:
- **b-dir-neg** (R_I51_8_DIR/BIT accepts -1): `reloc` only.
- **sc-dwarf**: `script` only.

**Survivors whose behaviour differs (17).** Each row has its repro in `probes9.py`.

| mutant | the claim it guards | clean / mutant |
|---|---|---|
| **b-pcrel-hi** | f681863: "relative-branch values past 0xFFFF are overflows" | `.org 0xfffe` / `sjmp y` with `--defsym Y=0x10000`: "relocation truncated to fit: R_I51_7_PCREL" / no such error |
| **b-pcrel-lo** | same | `sjmp y` with `--defsym Y=-1`: truncated / **links** |
| **b-ordcomm-xdata** | f681863: "an ordinary common meets ... never one of external RAM" | `.comm buf` (a.o) and `.xcomm buf` (b.o), linked `b.o a.o`: refused / links. The `a.o b.o` order is still refused, so only one order is pinned. |
| **b-align-zero / b-align-max / b-align-pow2** | 907bdd9: "a malformed common alignment in an object is refused" | The only test patches in 0xfffffffe, which breaks both the cap and the power-of-2 rule, so lifting either one alone is not seen. st_value 0, 0x20000 or 3: refused / links. |
| **iram-suffix** | f681863: the direct check covers internal RAM | `.section .data.foo` then `.ds.b 0x90` / `buf:` / `mov a,buf`: gas error at 0x90 / assembles silently |
| **iram-any** | f681863: "symbols outside internal RAM are left to the linker, which names their space" | `.xdata` buf at 0x90, `mov a,buf`: the linker says "a direct address cannot name external RAM" / gas says "at 0x90 ... reachable only through @R0/@R1", a misleading message |
| **at-fits** | the `@` operand is a fixed name | `jmp @a+dptrx`: "invalid indirect operand" / **accepted** as `@A+DPTR`, because the name is cut at 7 characters |
| pc-junk | `.pcode` address is one term | `.pcode 0x200) 1`: "junk in pcode address" / accepted, operand dropped |
| pc-scan-close | same | `.pcode (0x100)*2 1`: error / accepted, address 0x200 |
| pc-word-hi | `.pcode` constant ranges are the fixup's | `.pcode 0x200 WORD 65536`: error / accepted |
| pc-byte-lo | same | `.pcode 0x200 BYTE -256`: error / accepted |
| pc-shl8-hi | a zero `SHL8` sets no flag | `.pcode 0x200 SHL8 0`: `02 00 00` / `02 00 80` |
| comm-aligned-flag | f681863: an ordinary `.comm` is aligned to a byte unless told | `.comm x,4,4`: st_value 4 / 1 |
| using-cleanup, space-dir-indirect, dis-page, ordcomm-space | see 1a | |
| sc-edata | README: "ASSERTs bound ... the two external ones" | `.ebss` 0x10001 bytes: "edata overflow" / links |
| sc-r-dwarf | the -r script places DWARF | `ld -r -g`: `.rela.debug_line` / `.rela.debug_aranges` at the same index; the debug sections are reordered as orphans |

**Survivors I could not tell apart from the clean tools (4):**
- **rb-comm:** for a common, S_IS_DEFINED is already true, so `.comm __RB__` is refused either way.
- **at-space:** app.c's scrubber removes the blanks in `@ R0` and `@A + DPTR` before tc-i51 sees them, so the white-space skip in the `@` loop is redundant.
- **pcrel-nullsym:** this mutant was ill-formed, because it short-circuits on NULL. The correct form, pcrel-noguard, is killed.
- **b-gen0-shdr:** I found no generation-1 object that the legacy reader changes.

**Totals over 112 mutants:**
- 77 killed.
- 21 survive with a behaviour difference: 4 from r8 and 17 new.
- 14 are equivalent or not shown.

## 2. Findings, ranked

1. **MEDIUM: the manual contradicts f681863 on ordinary commons, and no test holds the new rule.**
   - The manual says two things:
     - in Memory Spaces: "A plain `.comm` names no space and is never compared this way";
     - in the `.comm` entry: "It names no memory space".
   - The code (`i51_common_space`) treats an ordinary common as internal RAM, and refuses it against `.xcomm` and `.bitcomm`:

     ```
     printf ' .comm buf,4\n' > a.s; printf ' .xcomm buf,4\n' > b.s; as a.s -o a.o; as b.s -o b.o
     ld a.o b.o   ->  b.o: symbol `BUF' is in external RAM (.xbss) here and in internal RAM (COMMON) in a.o
     ```
   - The mutants ordcomm-space and b-ordcomm-xdata survive in the `b.o a.o` order, so the rule could revert unseen in either direction.
2. **MEDIUM: three claims in commits f681863 and 907bdd9 have no discriminating test.**
   - R_I51_7_PCREL code-space bounds (b-pcrel-hi, b-pcrel-lo). With `--defsym Y=-1`, `sjmp Y` links silently in the mutant.
   - The malformed-alignment check. The single 0xfffffffe probe cannot tell the three conditions apart. Add st_value 0, 3 and 0x20000.
   - The direct check limited to internal RAM, including `.data.foo` (iram-suffix, iram-any).
3. **MEDIUM: dis-page.** 907bdd9 says it tests ACALL/AJMP "in another page", but page2.d cannot see whether the page comes from the start of the instruction or from the next instruction. An `ajmp` at 0x7fe would.
4. **MEDIUM: `.pcode` has gaps.**
   - Untested: `junk in pcode address`, the closing-parenthesis rule, the WORD upper bound (65535) and the BYTE lower bound (-255), and a zero SHL8.
   - Accepted by a one-line fault (at-fits): an over-long indirect name, `@a+dptrx`.
5. **LOW: remaining untested rules.**
   - `.using` does not carry into the next file (using-cleanup, open since r8).
   - The `.idata` direct case (space-dir-indirect).
   - The edata ASSERT (sc-edata), despite README.
   - `.comm` with an explicit alignment (comm-aligned-flag).
   - Two rules still pinned only by tb stages, not DejaGnu: b-dir-neg and r8imm-range (reloc), and b2b-bitnum (bits).
6. **LOW: the manual's `.pcode` text, "A byte that would be zero is left out", is inexact.** It is the operand that has to be zero:
   - `.pcode 0x200 #BYTE 1, @BYTE 1, @BYTE 0x100` gives `62 00 54 01 00 ff`: the `@BYTE 1` byte is stored as 00 and kept;
   - `@BYTE 0` stores nothing, where its byte would be 0xff.
7. **LOW: stale counts and claims in the harness.**
   - tb/Makefile:624 says the coverage run "runs twelve" stages; `$(MUTGATE)` has 13.
   - The tb/mutation/run.py docstring:
     - its example `--stages` includes doctruth, which MUTGATE excludes;
     - `gate(every=True)` claims that only check and oracle use `$(WORK)`, but dejagnu (and libsrc) use it too, and dejagnu deletes and rewrites `*.sum` in `$(BUILD)`.
   - gen.py and REBUILD_MARK cover neither `binutils/readelf.c` nor `include/elf/i51.h`, so the readelf predicates, which the gate now does kill (re-32, re-16, re-reloc-type), are outside `make mutants`.
8. **LOW: oversize commons are dropped quietly.** The manual says "A common is at most 0xFFFF units long", but `.comm c,0x10000` and `.xcomm c,0x10000` give only the generic warning "size (65536) out of range, ignored". gas exits 0, and C is then an undefined symbol.
9. **Info: macOS.** The macOS `build.yml` job now runs the full generic suites through the dejagnu stage. Whether they are clean on a darwin host is unverified offline.

## 3. c-i51.texi against the tools

Everything I checked holds, apart from §2.1 and §2.6.

**Every doctruth diagnostic:**
- r0;
- `ES`;
- the whole-operand rule;
- "allowed only as an instruction operand", both in `.equ` and on a `.pcode` address;
- the commons message: the manual's text appears for the `a.o b.o` link order;
- BUF at 0x90, in `.idata` and in `.data`;
- `.quad`.

**Operand values:**
- `.byte ACC,CY` → e0 d7;
- PSW.3, IE.7, TCON.4 → d3, af, 8c;
- 0x20.3 → 03 and 0x90.5 → 95;
- `#HIGH(0x1234)+1` → 0x13.

**Bit addresses:**
- `setb 1+0x20.1` and `mov a,0x20.3` are refused;
- `0x20.8` gives "bit number 8 is not 0..7";
- `LOOP.1` used before its definition is refused with the documented message.

**Directives:**
- `.bit` refuses HIGH() of an unknown value, and `.bit 1` in `.bitdata` is refused at link;
- `.word 0x1234` → 12 34;
- `.float 1.0` → 3f800000;
- `.ds 3` = 6 bytes.

**`.pcode`:**
- the address range is 0x100..0x1fff, and 0xff and 0x2000 are refused with the documented messages;
- the address is one term: `0x200 -1` has an operand and `(0x100 + 0x100) 1` works;
- a comma after the address gives its message;
- SWAP on the second operand is refused;
- the manual's example assembles to `03 00 74 04 12 34 05`.

**`.using` and `__RB__`:**
- `.using 4` is refused and `.using 1+1` works;
- `__RB__` is sized by the highest bank (0x18 after `.using 2` then `.using 0`);
- a label `__RB__`, `.equ`, `=`, `.set` and `.comm` of it are all refused. Only the label is reported at its line; the other forms carry no line number.

**`-mmcu`:**
- an unknown part is an error;
- 8051 and 8052 turn T2CON and WMCON into plain symbols.

**Commons and alignment:**
- a common with no alignment gets st_value 1;
- `.comm x,4,4` gets 4;
- `.xcomm ..,0x10000` is accepted and 0x20000 is refused;
- 3 gives "not a power of 2";
- a second space within one file is refused;
- ABI generation: objects are written as 1, `ld -r` writes 1, and 2 and 0x10 are refused with "knows ABI generations 0 to 1".

**Linker limits and the RAM spaces:**
- `__STACK_SIZE`: 0xd0 bytes of `.idata` link, 0xd1 do not, and `--defsym __STACK_SIZE=0` lifts the limit;
- `__IRAM_SIZE=0x80` holds;
- `__EEPROM_SIZE`: no limit unless set, and set to 0x800 it refuses 0x801;
- direct RAM ends at 0x7F: 0x60 bytes of `.bss` link and 0x61 do not;
- initialized data is refused in .bitdata, .xdata, .data, .idata and .edata, and a zero byte is accepted;
- the EEPROM objcopy line gives `:03000000010203F7`, and plain `-j .eeprom` gives an empty hex;
- nm classes: d/D, b/B in NOBITS spaces, i/I for `.idata`;
- `size` counts the code only.

**Ranges.** The linker bounds match the manual exactly (accepted / refused):

| relocation | accepted | refused |
|---|---|---|
| R_I51_8 | ±255 | ±256 |
| R_I51_8_DIR / BIT | 0..255 | -1 and 256 |
| R_I51_8_IMM | -128..255 | -129 and 256 |
| R_I51_16 | ±65535 | ±65536 |
| R_I51_16_CODE | 0..0xffff | -1 and 0x10000 |
| R_I51_7_PCREL | displacement up to +127 | +128, and targets below 0 or past 0xffff |
| R_I51_H (HIGH) | -32768..65535 | -32769 and 65536 |

The gas range messages agree with the table.

**`-g` and generated code:**
- `-g` emits R_I51_32 DWARF relocations;
- addr2line maps an address to `g.s:2`;
- `jmp`/`call` assemble to ljmp/lcall;
- acall always leaves an R_I51_11.

## 4. README, workflows and tb/Makefile

| claim | what it is checked against | verdict |
|---|---|---|
| `gate-list` has 17 words | release.yml's `want` (identical string) and its "seventeen" | holds |
| `ci-list` has the canary after `check` | $(GATE) plus canary, as a set | holds |
| README: "sixteen" stages | $(GATE): its list matches word for word | holds |
| gate.yml: "seventeen stages" | the same list | holds |
| release.yml: "the thirteen toolchain stages, then check, libsrc and oracle" | $(TOOLGATE) | holds |
| tb/Makefile:752: "seventeen" | the release body | holds |
| MUTGATE = TOOLGATE minus doctruth, plus check (13) | `make -n mutants` passes `--stages isa,…,disasm,dejagnu,check` | holds |

- **README dejagnu line.** `make -C tb dejagnu BUILD=<build tree>` "runs them with the generic gas, ld and binutils suites", which is now true (r8 LOW fixed).
- **The dejagnu stage itself.** It drops UNTESTED from "bad", as its comment says. It requires at least one `PASS: i51 ` in gas and in ld.
- **Stale items:** see §2.7.

## 5. Generic-suite markings: 15 sampled, none of them in r8's 22

Each stated reason was reproduced by hand with the clean tools. All 15 are true.

| test | stated reason | what I saw |
|---|---|---|
| ld-elf/endsym | folding, and no `_end` | `END`/`END2`; no `_end` symbol in the default script |
| ld-elf/pr14156a | folding, and RAM symbols share addresses with code | FOO… plus `__STACK_SIZE` (0x10, absolute) and `STACK` (0x20) interleaved with FOO2/FOO3 |
| ld-elf/pr25022 | genelf.em, as the listed targets use | "sh_link of section `.bar' points to discarded section"; fr30, iq2000, mn10200, mt and ft32 all have `EXTRA_EM_FILE=genelf` |
| ld-elf/pr26907 | page size of 1 | an empty `LOAD 0x000001 0x08 0x08 0 0` segment; `ELF_MAXPAGESIZE 1` |
| ld-elf/pr30791a | genelf.em, generic orphan merging | `ld -r` merges the four `__patchable_function_entries` into one, with sh_link to `.text.a` |
| gas/elf/size | folding | `FOO1` where `foo1` is expected |
| gas/all/sleb128-9 | folding | error text `.LUNDEF` vs `.Lundef` |
| gas/macros/irp | folding | `R_I51_32 FOO1` vs `foo1` |
| readelf `--demangle` mangled | folding breaks mangling | `_ZN4GOLD12OUTPUT_RELOCI…` |
| ld-scripts map with locals | `local_sym` is `LOCAL_SYM` | the map has `(local) LOCAL_SYM` |
| ld-gc/pr20882 | folding | `-e main` gives "cannot find entry symbol main" and gc drops `.debug_info`; `-e MAIN` keeps it |
| ld-gc/stop (`--gc-sections removing __stop_`) | folding | "cannot find entry symbol _start" |
| ld-checks/checks.exp (skipped) | initialized `.data` refused | `asm.s`: "initialized data in internal RAM" |
| ld-linkonce pr26103 (skipped) | initialized `.data` refused | ref1, sym1–3, ref2 `.data` and `.gnu.linkonce.d.foo` are all refused |
| ld-scripts/sysroot-prefix (skipped) | initialized `.data` refused | `x: .dc.a y` (a reloc-filled byte) is refused |

Also checked beyond the 15:
- gas/elf `line`, excluded for ONLY_STANDARD_ESCAPES: `tc-i51.h:28` defines it.
- ld-elf/sec-to-seg, page size 1: as above.

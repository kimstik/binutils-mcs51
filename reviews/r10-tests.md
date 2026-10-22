# Review 10, lane r10-tests: do the tests, manual, README and CI back the claims?

## Scope and setup

- **What was reviewed:** HEAD `e3c2b4e`. The workspace copy `review10/tests/src` reverse-applies both `mcs51/*.patch` cleanly.
- **The branch moved during the review.** It was rebased: e3c2b4e is now `0bb106b`. Four commits were added on top, up to `8efc2d0`, and `work/modern/binutils-2.47` was edited at 12:04. Some findings below may already be addressed there. They are marked "(see 59c71f3 / a320f83)", and I have not verified those commits.
- **Clean gate:** `make -C tb gate BUILD=review10/tests/build WORK=review10/tests/w0` passes all 16 stages in 44 s. The dejagnu stage gives:

| suite | PASS | of which the port's own | XFAIL |
|---|---|---|---|
| gas | 288 | 50 | 79 |
| ld | 286 | 64 | 233 |
| binutils | 170 | – | 66 |

- **Harness**, in `review10/tests/h/`:
  - `mutants10.py` holds the faults. `mutate10.py` runs them in two shards over src/build and src2/build2. Each mutant gets a rebuild, then every gate stage except doctruth, each run on its own.
  - `results10-{0,1}.json` and `logs/` hold the results.
  - `probe10.py <id> '<sh>'` applies one mutant to src3/build3 and runs a repro.
- Nothing in the repo or in `work/` was written.

## 1. Mutation results (74 mutants)

### 1a. The 21 behaviour-changing r9 survivors: all 21 are now killed

- **19 are killed by dejagnu as written:** using-cleanup, space-dir-indirect, dis-page, ordcomm-space, b-pcrel-hi/lo, b-ordcomm-xdata (respelled for the new code), b-align-zero/max/pow2, iram-suffix, pc-junk, pc-scan-close, pc-word-hi, pc-byte-lo, pc-shl8-hi, comm-aligned-flag, sc-edata, sc-r-dwarf.
- **2 no longer compile in their r9 spelling** (`-Werror`: unused `fits`, and an unused `i51_internal_ram`). Respelled as `at-fits2` and `iram-any2`, both are killed by dejagnu.

### 1b. New faults over the code changed since b47a487 (51)

**Killed (38).**
- Killed by dejagnu, unless another stage is named:
  - case-opt-noop, case-default-off (also defaultlink, check, libsrc, oracle), dot-fold, dot-old;
  - builtin-bitclass, global-ext, sfrN-nonote, nameN-nonote, at-noend;
  - datum-old, datum-none (also reloc), datum-8;
  - bit-nonconst, bit-hi (also bits), swap-wordrule;
  - comm-noalign1, rb-commparse;
  - pcscan-paren, pcscan-opname, opname-case, kw-user;
  - rodata-any, rodata-direct, regbank-nokeep, keep-all, pcode-anyspace, value-nosext;
  - spacecom-samesec, oldplain-COMMON and plain-direct-only (each also killed by commons), plain-filter-old;
  - re-16-code, re-32-code;
  - h-addr11 (7 stages), h-abi-current (13 stages).
- **Killed only by a tb stage, with no DejaGnu test:**

| mutant | killed by |
|---|---|
| bit-lo (`.bit -1` accepted) | bits |
| h-sfr-f8 (bit address of SFR 0xF8 refused) | bits |
| h-ram-2f (bit address of RAM 0x2F refused) | bits, reloc, guard |

**Survive, and the behaviour differs (7).** Repros use the `e3c2b4e` tools in `work/modern/b2`, or `probe10.py`.

| mutant | the claim it guards | clean / mutant |
|---|---|---|
| **global-weak** (frob_symbol drops `!S_IS_WEAK`) | bf7eb5c: "a built-in name made .global or .weak after its use" is refused | `setb ES` / `.weak ES` / `ljmp ES`: "`ES' is used here as the built-in name…" / accepted. builtin-global.s tests `.global` only. |
| **swap-lo** | bf7eb5c: "#SWAP takes the range of the HIGH()/LOW() pair" | `.pcode 0x200 #SWAP -32769`: "pcode operand out of range" / accepted |
| **swap-hi** | same | `.pcode 0x200 #SWAP 65536`: error / accepted |
| **linkonce-r-any** (`.gnu.linkonce.r.` row removed) | 1705e45: ".rodata and .gnu.linkonce.r.* are code" | `mov a,tbl` with tbl in `.gnu.linkonce.r.tbl`: "R_I51_8_DIR against `TBL': a direct address cannot name code memory" / links. Only `.rodata` is tested. |
| **plain-any** (the internal-RAM exemption applied to space commons) | manual: "Two memory-space commons … have to be of one directive"; a space common is not satisfied by another space | `.rcomm buf,1` in p1.o, a `.idata` global `buf` in p2.o: "symbol `BUF' is in indirectly addressed internal RAM (.idata) here and in internal RAM (.rbss)" / links, BUF=0x20 (see a320f83) |
| **re-8-dir** (readelf `is_8bit_abs_reloc` checks 12) | 787e1d6: readelf applies i51 relocations in DWARF | `.section .debug_foo` / `.byte sym+5`, then `readelf --relocated-dump=.debug_foo`: `05 0005` / `00 0005`. Only the 16- and 32-bit predicates are tested. |
| **opname-len** (operator name matched as a prefix) | the `.pcode` address scan | `H: nop` and `.pcode H(0x200)`: assembles / "junk in pcode address: `(0x200)'" |

**Survive, but equivalent or only the message differs (6):**
- **opname-b2b:** a B2B() value is at most 0xFF, so a B2B() address is always below the 0x100 minimum. Clean gives "pcode exec address underflow". The mutant gives "found ',', expected: ')'". Both are errors.
- **at-lead:** app.c's scrubber already removes the blank in `@ R0`.
- **comm-local:** a `.local` common goes through bss_alloc, so its alignment is unchanged.
- **rb-commparse-flag:** common_parse returns NULL, so frob_symbol never sees a common `__RB__`. There is no second message.
- **h-xdata-edata:** nothing reads `SHF_I51_XDATA`/`EDATA` (and the other single-space values). Only `SHF_I51_SPACE` is tested, in elf32-i51.c:775, so those `#define`s are dead.
- **checkspace-old:** on a 64-bit host, r_addend is sign-extended before the sum, so I found no input where the unextended sum and `i51_value` differ.

**Totals over 74 mutants:**
- 21 of 21 r9 survivors are now killed.
- Of the 51 new mutants, 38 are killed, 7 survive with a behaviour difference, and 6 are equivalent or differ only in the message.

## 2. Findings, ranked

1. **MEDIUM: `-mcase-sensitive` disables the "used as built-in, then defined" rule** (at e3c2b4e; see 59c71f3).
   - Uses are noted under `n->name` (upper case), but the symbol keeps the spelling it was written in. The same name then means two things in one file, silently:

     ```
     printf ' .text\n setb es\nes: nop\n setb es\n' > cs.s; as -mcase-sensitive cs.s -o cs.o
     objdump -d cs.o  ->  setb 0xac (built-in ES), then setb 0x00 (label es)
     ```
   - The same happens with `p1.1` used, then `p1.1:` defined, and with `.byte acc` followed by `acc:`.
   - The manual (i51-Regs) states the rule without exception. The only `-mcase-sensitive` test, case.d, has no built-in names in it.
2. **MEDIUM: four rules claimed in 1705e45/bf7eb5c have no discriminating test.** The repros are in the table in §1b:
   - `.weak` after a built-in use;
   - the `#SWAP` bounds -32768 and 65535;
   - `.gnu.linkonce.r.*` as code;
   - a space common against a definition in another part of internal RAM.

   Separately, readelf's R_I51_8 predicate is untested.
3. **MEDIUM: 269 generic XFAILs could be real PASSes now.**
   - I ran the dejagnu stage with as-new wrapped as `as-new.real -mcase-sensitive`, in build3, which I then restored. The result:

     | suite | XFAIL turned XPASS |
     |---|---|
     | gas | 77 of 79 |
     | ld | 128 of 233 |
     | binutils | 64 of 66 |

   - The only new FAILs are the port's own tests (gas 16, ld 27), which expect folding.
   - The folding xfails were the only option before `-mcase-sensitive`. Now a second pass of the generic suites with `-mcase-sensitive`, or a board `ASFLAGS`, would test about 270 generic behaviours that the gate now waives.
4. **LOW: the README is stale on case folding.**
   - README.md:84 says the folding is "(`symbols_case_sensitive = 0`, which 2001 never set)". The port never sets `symbols_case_sensitive`. It folds in `tc_canonicalize_symbol_name`, which is how the dot rule and `-mcase-sensitive` work.
   - The README does not mention `-mcase-sensitive`.
5. **LOW: the manual has range gaps.**
   - R_I51_8 says "The assembler and the linker accept −255 through 255". The linker does refuse 256 and -256, and gas refuses a resolved fixup ("value of 300 too large for field of 1 byte"). A constant datum, though, only warns (`.byte 256` → "Warning: value 0x100 truncated to 0x0"), and the object is still written. `.word` behaves the same way.
   - The R_I51_L/R_I51_H range (-32768..65535, checked by `mov a,#HIGH(y)` with Y=-32769 and 65536 refused) and the `#SWAP` constant range are not stated anywhere in the manual.
6. **LOW: gen.py's readelf mutant ids are off by 3 lines.**
   - `read()` uses `str.splitlines()`, which also splits on the three form feeds in readelf.c. gen.py names `relf-constpm1-16121`, `-16513` and `-16588`, but the lines are 16118, 16510 and 16585.
   - run.py uses the same split, so the mutants still apply. Only the ids and line numbers reported are wrong. Also, run.py's `'\n'.join` rewrites the form feeds as newlines in the mutated copy.
   - Otherwise gen.py does produce mutants for both files. At MUTCAP 12 that is 18 for include/elf/i51.h (relop 6, constpm1 12) and 3 for readelf.c (the line after each `case EM_8051:` with a literal). REBUILD_MARK knows both files.
7. **LOW: three bit-address rules are held only by tb stages** (`bits`): `.bit -1`, SFR 0xF8 and RAM 0x2F.
8. **INFO: `SHF_I51_REGBANK`…`SHF_I51_EDATA` in include/elf/i51.h are never read.** Only the mask is used, so a wrong value is undetectable (h-xdata-edata).

## 3. Manual (c-i51.texi) against the tools, at e3c2b4e

Every quoted diagnostic was reproduced verbatim:
- register `r0'
- `ES' … declare it with .local first
- the two HIGH() forms
- the `BUF' xbss/ibss link error
- `BUF' is at 0x90 … @R0/@R1
- `.quad`: cannot relocate 8 bytes

These stated values and behaviours hold:
- **Case and names:**
  - `-mcase-sensitive` keeps the case, and `--defsym` follows the mode in either option order.
  - A name starting with a dot keeps its case by default: `.foo` and `.Foo` are distinct, and `.FOO` is an undefined reference.
- **Built-in names and bit addresses:**
  - PSW.3=D3, IE.7=AF, TCON.4=8C, `.byte ACC`/`CY` = E0/D7.
  - 0x20.3=03 and 0x90.5=95; `setb 1+0x20.1` and `mov a,0x20.3` are refused.
  - `#HIGH (0x1234) + 1` = #0x13.
  - B2B is refused at a literal, an absolute symbol and the link.
  - LOOP.1 used before its definition is refused.
- **Directives:**
  - `.bit` takes the constant 0 or 1 only.
  - `.ds 3` reserves 6 bytes.
  - `.using` 0..3.
  - `.comm`/`.local`/`.xcomm __RB__` are all refused.
- **Commons:**
  - A common of 0x10000 draws "Warning: size … out of range, ignored".
  - Alignment of 0x10000 is accepted, 0x20000 and 3 are refused.
  - The default alignment is 1, including `,0` and `,"bss"`.
  - e_flags is 1, and generations 2 and 15 are refused by ld.
  - A plain `.comm` meets `.idata`, `.rdata`, `.data` and `.bcomm`, and is refused against `.xdata`, `.xcomm`, `.bitcomm`, `.text` and `.eeprom`, in both orders. `.bcomm` against `.rcomm` is refused.
- **Linker script values:** `__STACK_SIZE` 0x10, STACK is the first stack byte, `__IRAM_SIZE` 0x100, `__EEPROM_SIZE` 0x10000.
- **`.pcode`:** 0xFF is refused, 0x100..0x1FFF is accepted, and 0x2000 is refused. `0x200 -1` takes the sign as an operand. `@BYTE 1` stores 0x00. A bare keyword is a symbol where one exists.
- **Relocation bounds at the link** (each refused just past its bound):

  | relocation | accepted range |
  |---|---|
  | R_I51_8 | -255..255 |
  | R_I51_8_DIR | 0..255 |
  | R_I51_8_IMM | -128..255 |
  | R_I51_16 | ±65535 |
  | R_I51_16_CODE | 0..0xFFFF |
  | R_I51_13_PCODE | 0x100..0x1FFF |

- **Space errors:** a jump into `.data`, a direct address into xdata, bit or code, and a bit address into `.data` are refused, and `.data` at 0xA0 used direct is refused at the link.

doctruth does not check command-line options; the `-mmcu` values were checked by hand.

## 4. README, workflows and tb Makefile

- **Stage counts agree:**
  - README "sixteen stages (isa … oracle)" = `$(GATE)`, 16 names, and `make gate` prints the same list.
  - release.yml "seventeen" = `gate-list`, which is GATE plus check-canary, and is pinned literally there.
  - `ci-list` is CIGATE in CI order and passes its own set check.
  - gate.yml takes its stages from `ci-list`.
- **MUTGATE** = TOOLGATE minus doctruth, plus `check` (13 stages). The `mutants` target passes it, and `mutants-coverage` uses it through MUTSTAGES. The comments match.
- **Other workflows:** build.yml runs the full gate on Linux, and `check isa dejagnu` on macOS, where there is no ucsim. The comment says this.
- **Not true in the README:** see §2.4.

## 5. Generic-suite markings (10 sampled, checked by hand)

| test | stated reason | verified |
|---|---|---|
| ld-unique/unique.d | folding | default gives `A_VAL`; `-mcase-sensitive` gives `a_val`, and the test XPASSes |
| ld-undefined/entry-1.d | folding | "cannot find entry symbol foo"; XPASS case-sensitive |
| ld-scripts/provide-1.d | folding | XPASS case-sensitive |
| ld-selective/keepdot.d | folding | XPASS case-sensitive |
| ld-elfcomm `--sort-common` | folding | XPASS case-sensitive, both directions |
| gas/all redef2 | folding | XPASS case-sensitive |
| gas/symver symver2 | folding | XPASS case-sensitive |
| readelf `--demangle` | folding breaks mangling | XPASS case-sensitive |
| readelf RELR | `.dc.a` is 16-bit | `.dc.a 0x12345678` gives 2 bytes and a truncation warning; still XFAIL case-sensitive |
| ld-elf/retain1a.d | RAM data refused | ld: "initialized data in internal RAM, which nothing loads". The test also depends on folding (`_start`), which the comment does not say. |
| ld-elf/pr25022 | genelf.em, like fr30 etc. | "sh_link of section `.bar' points to discarded section"; `TEMPLATE_NAME=generic`, `EXTRA_EM_FILE=genelf` |
| gas/elf `line` (excluded) | ONLY_STANDARD_ESCAPES | defined in tc-i51.h:28 |

The commit's claim that 9e66673 "six generic tests pass and lose their xfail" holds: group0b, group0c, group1b, mbind 12 and mbind 16 PASS in gas, and merge5 PASSes in ld.

# VERIFY-green-2

Adversarial verification of `origin/work/green` @ `afee4a5` ("ci: build, gate and
frozen workflows"), by execution only. Every claim below is the output of a
command run in this tree. Nothing was taken from a report; the repository ships
none.

Host: Ubuntu 24.04.4, gcc 13.3.0, 4 cores, `s51` (sdcc-ucsim) present,
`7z`/`texinfo`/`py7zr` present - nothing had to be installed.

---

## 1. Build

### 1.1 `make -C tb build`

```
$ make -C tb build
...
-rwxr-xr-x 1 root root  690824 .../work/modern/build/gas/as-new
-rwxr-xr-x 1 root root 1031984 .../work/modern/build/ld/ld-new
EXIT=0
```

Downloads binutils-2.47.tar.xz, checks it against the pinned
`154ab23b...4cff` (matched), applies both patches at `--fuzz 0`, configures
`--target=i51-elf`, builds. Green.

### 1.2 Stock build, no `--disable-werror`

Independent tree, pristine 2.47 + both patches, `./configure --target=i51-elf`
with no warning-suppression flag of any kind:

```
CONFIGURE EXIT=0
MAKE EXIT=0
--- warning count total: 4
--- warnings in i51 port files: (none)
--- all distinct warning lines:
      3 warning: `-version-info/-version-number' is ignored for convenience libraries
      1 warning: ignoring multiple `-rpath's for a libtool library
```

`-Werror` was genuinely active - `gas/Makefile` line 462:

```
WARN_CFLAGS = -W -Wall -Wstrict-prototypes -Wmissing-prototypes -Wshadow \
              -Wstack-usage=262144 -Werror -Wwrite-strings
```

The four remaining lines are libtool notices, not compiler diagnostics. **Zero
compiler warnings, `-Werror` on, exit 0.** This claim holds.

(For contrast, `make -C tb build` uses `-Os -flto` and does emit
`-Wstack-usage` warnings from `libiberty` - stock binutils code, not the port,
and that build passes `--disable-werror`.)

---

## 2. Patches against a pristine 2.47 tarball

```
$ tar xf binutils-2.47.tar.xz          # sha256 154ab23b...4cff, verified
$ patch --fuzz 0 --no-backup-if-mismatch -p1 -d binutils-2.47 < mcs51/additions.patch
ADD EXIT=0
$ patch --fuzz 0 --no-backup-if-mismatch -p1 -d binutils-2.47 < mcs51/modifications.patch
MOD EXIT=0
--- lines that are not 'patching file': (none, both logs)
--- fuzz/offset/FAILED grep:             (none)
--- .rej / .orig files:                  (none)
--- counts: add.log:9  mod.log:28
```

9 new files, 28 modified files, **zero fuzz, zero offset, zero rejects**.

The vendored third-party corpora are byte-identical to the upstream sources
their PROVENANCE names - fetched and hashed here, not trusted:

```
a597813a...884c  tb/isa/8051.txt      == naken_asm@75b8b59 tests/comparison/8051.txt
7869c57e...c583  tb/isa/testall.asm   == freecores/8051@d264345 asm/testall.asm
```

So `isa`, `roundtrip` and `sim` are judged against bytes this toolchain did not
produce. That part is sound.

**Defect D1 (documentation vs. enforcement).** `tb/Makefile` claims the patches
"must apply with zero fuzz and zero offsets". `--fuzz 0` forbids fuzzy context
matching; it does **not** forbid offsets. Proven:

```
# one line inserted at the top of bfd/Makefile.am, then apply:
additions rc=0
modifications rc=0
Hunk #1 succeeded at 118 (offset 1 line).
Hunk #2 succeeded at 202 (offset 1 line).
...
```

`patch` exits 0, `make build` is green, the promise is not kept. Real context
drift *is* caught:

```
# one context line altered instead:
modifications rc=1
Hunk #1 FAILED at 117.
1 out of 4 hunks FAILED -- saving rejects to file bfd/Makefile.am.rej
```

Fix would be one line: pipe the `patch` output through
`grep -q 'offset' && exit 1`.

---

## 3. Stage inventory

`tb/Makefile` groups them itself:

```
TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons
GATE     := $(TOOLGATE) oracle
MUTGATE  := $(TOOLGATE) check
```

**14 stages exist that render a verdict.** Full list, with what runs each and the
result of running it on this tree:

| # | stage | run by | result here |
|---|-------|--------|-------------|
| 1 | `isa` | gate.yml, build.yml, `make gate`, mutants | PASS (280/280 + 3/3) |
| 2 | `roundtrip` | gate.yml, `make gate`, mutants | PASS (280 + 3 + 18) |
| 3 | `branch` | gate.yml, `make gate`, mutants | PASS (24/24) |
| 4 | `bits` | gate.yml, `make gate`, mutants | PASS (50/50) |
| 5 | `reloc` | gate.yml, `make gate`, mutants | PASS (36/36) |
| 6 | `sim` | gate.yml, `make gate`, mutants | PASS (P1=127) |
| 7 | `defaultlink` | gate.yml, `make gate`, mutants | PASS |
| 8 | `commons` | gate.yml, `make gate`, mutants | PASS |
| 9 | `oracle` | gate.yml, `make gate` | PASS (10/10 vs 2001 .hex) |
| 10 | `check` | build.yml, mutants | PASS (10/10 ROMs match) |
| 11 | `check-canary` | build.yml | PASS |
| 12 | `build` (tarball hash + fuzz-0 apply + compile) | gate.yml, build.yml | PASS |
| 13 | `frozen` (2.11.2 from ref.7z) + `check-frozen` | frozen.yml | built, check-frozen exits 2 as recorded |
| 14 | `romdiff.py --expect tb/frozen.expect` | frozen.yml | PASS, matches `tb/frozen.expect` exactly |

Aggregates: `make gate` (1-9, stops at first failure), `make mutants` (1-8 + 10).

Everything was run. Every stage is green on this tree.

---

## 4. Fault-injection matrix

Method: mutate one construct in `work/modern/binutils-2.47`, `make all-gas
all-ld all-binutils` incrementally, run the named stages, restore, rebuild.
Where a stage stayed green a behaviour probe was run under the same mutant to
separate "the suite is blind" from "the mutant is equivalent". The probe emits
the linked bytes of the relocation probe, the B2B forward-reference boundary,
and whether a `.rodata` input reaches the `objcopy -j .text` image.

| id | injected fault | file | stages run | red? |
|----|----------------|------|-----------|------|
| F1 | assembler encoding byte: `add A,dir` opcode `0x25`->`0x26` | `include/opcode/i51.h` | isa, roundtrip, sim, check | **RED** isa (`assemble 279/280`, `decode 279/280`), roundtrip, sim, check (1/10 projects) |
| F2 | disassembler operand: `R%c` register number +1 | `opcodes/i51-dis.c` | isa, roundtrip | **RED** roundtrip (`224/280`); isa green (decode only asks "is it one instruction") |
| F3 | branch displacement sign, assembler: `I51_7_PCREL` stores `-value` | `gas/config/tc-i51.c` | branch, sim, isa | **RED** branch, sim, isa |
| F4 | branch displacement sign, disassembler: sign-extension dropped | `opcodes/i51-dis.c` | roundtrip, isa | **RED** roundtrip; isa green (same reason as F2) |
| F5 / F5b | bit-address boundary, assembler: `md_apply_fix` RAM window `<0x30`->`<0x31` | `gas/config/tc-i51.c` | all 10 stages | **not red** - but the probe shows byte 0x30 is still *rejected*, only with a different message: the widened branch computes `(0x30-0x20)*8+b >= 0x80` and refuses anyway. **Semantically equivalent mutant, not a hole.** |
| F6 | bit-address boundary, linker: the non-multiple-of-8 SFR refusal deleted | `bfd/elf32-i51.c` | bits, reloc | **RED** bits |
| F7 / F7b | relocation size: howto `R_I51_H` size 1 -> 2 bytes | `bfd/elf32-i51.c` | reloc, check, isa (+probe) | **not red** - probe byte-for-byte identical to clean, so `R_I51_H` never reaches a size-dependent path. **Equivalent mutant, not a hole.** |
| F8 | relocation endianness: `R_I51_16` `bfd_putb16` -> `bfd_putl16` | `bfd/elf32-i51.c` | reloc, check, sim, oracle | **RED** reloc, check (10/10), sim - **oracle GREEN**, see §4.2 |
| F9 | linker range check: `R_I51_7_PCREL` overflow test disabled | `bfd/elf32-i51.c` | reloc, bits, check | **RED** reloc |
| F10 / F10b | section dropped from the image: `*(.rodata)` removed from `.text` | `ld/scripttempl/elf32i51.sc` | all 10 stages | **not red anywhere** - and the probe proves it is *not* equivalent, see §4.3 |
| F11 | ROM byte: `R_I51_8_B2B` SFR fold off by one | `bfd/elf32-i51.c` | check, oracle, bits, reloc, sim | **RED** bits (others green: the ten projects use only the RAM branch) |
| F12 | memory-space commons: external xdata common routed to `.ebss` | `bfd/elf32-i51.c` | commons, check, reloc, defaultlink | **RED** commons |
| F13 | `*(.xdata)`/`*(.xdata.*)` removed from the built-in script | `ld/scripttempl/elf32i51.sc` | defaultlink, check, reloc, commons | not red; probe identical to clean - ld's orphan placement lands `.xdata` at the same address, so no evidence of a hole |
| H1 | **ROM byte**: `objcopy` wrapper flips byte 0 of every `www8051.rom` | harness | check | **RED**, 10/10 FAIL with distinct produced hashes |
| H2 | pinned reference: one hex digit changed in `tb/reference.md5` | harness | check | **RED** - `reference ROMs in base.7z do not match the pinned tb/reference.md5` |
| H3 | `check`'s own failure verdict turned into `exit 0` | harness | check-canary | **RED** (exit 2) |
| H4 | one produced ROM byte flipped, `frozen.expect` unchanged | harness | `romdiff.py --expect` | **RED** (`FAIL lcd differ 1, recorded identical 0`) |
| H5 | one count in `tb/frozen.expect` changed 214 -> 215 | harness | `romdiff.py --expect` | **RED** (`FAIL lcd differ 214, recorded differ 215`) |
| H6 | one context line drifted in the 2.47 tree | harness | `build` (patch apply) | **RED** (hunk FAILED, `.rej` written) |
| H7 | `BUILD` pointed at a nonexistent tree | harness | `make gate` | **RED** (exit 2 at the first stage, aggregate exits 1) |

### Stages proven capable of going red

**11 of the 14 stages** (rows 1-6, 8, 10, 11, 12, 14): `isa`, `roundtrip`,
`branch`, `bits`, `reloc`, `sim`, `commons`, `check`, `check-canary`, `build`,
`romdiff --expect`. The `make gate` aggregate was separately shown to
propagate a stage failure and exit nonzero (H7).

**Not proven red: `defaultlink` (row 7), `oracle` (row 9), `check-frozen`
(row 13).**

- `defaultlink` - no fault I could construct made it fail. F10b and F13 both
  edit the very linker script it exercises and it stayed green in both. Its
  assertions are specific (seven exact symbol addresses, five section
  addresses and alloc flags, and the exact 18-byte ROM image) and would fail
  on a layout move, so this is a gap in my injections as much as in the stage
  - but it is not proven.
- `oracle` - **proven blind**, see §4.2. It is the only stage in `gate.yml`
  that touches the ten real projects, and it does not go red on a fault that
  makes all ten ROMs wrong.
- `check-frozen` - its verdict is inverted by design: `frozen.yml` records
  that it *must* fail, and it does (exit 2, matching `tb/frozen.expect`'s
  header). Making it pass would mean making a 2001 toolchain reproduce ROMs it
  cannot reproduce, which is not an injectable fault. Its byte-level gate is
  row 14, and that one was made red twice.

### 4.1 F7 - relocation size, resolved as equivalent

`R_I51_H` howto size 1 -> 2, rebuilt (`grep -c elf32-i51 rebuild-F7.log` = 1).
`reloc`, `check` and `isa` stayed green. The probe under F7b then came back
**byte-for-byte identical to the clean toolchain**:

```
clean : linked-text: 743574347412d27fd27980146145021234901234753511d20322
F7b   : linked-text: 743574347412d27fd27980146145021234901234753511d20322
```

`R_I51_H` never reaches a size-dependent code path, so the mutant has no
observable behaviour and its survival is not a coverage hole. Faults in the
same file that *do* change behaviour (F8, F9) turned `reloc` red.

Same conclusion for F5/F5b: the widened RAM window still refuses byte 0x30,
because `(0x30 - 0x20) * 8 + bit >= 0x80` for every bit, so only the
diagnostic text changes. And for F13: the probe under it was identical to
clean, so removing `*(.xdata)` from the script is absorbed by ld's orphan
placement at the same address.

### 4.1a The three historical failure modes, re-tested

Two earlier review rounds found this project certifying broken output three
ways. Each was retested by execution:

- *"a `decode: 280/280` line that was a printed constant."* Under F1 the same
  line reads `decode: 279/280` and names the entry
  (`line 45 add a, 25 bytes 2519 decoded as 2 instructions, want 1: .byte 0x25 / dec R1`).
  The counter is computed from the failure list. **Fixed.**
- *"reference ROMs compared against themselves."* H1 flips one byte of every
  produced ROM through an `objcopy` wrapper: 10/10 FAIL with ten distinct
  produced hashes. H2 changes one digit of `tb/reference.md5`: the run stops
  before building. `check-canary` sabotages the assembler: 10/10 FAIL.
  **Fixed.**
- *"probes that passed while the bug they targeted was live."* Eleven of the
  fourteen stages were made to fail by a fault in their own subject. One
  exception is structural (§4.2), one is an inverted-verdict stage that cannot
  be flipped, and one (`defaultlink`) resisted every fault I aimed at it
  without being shown to be fake.

### 4.2 F8 - `oracle` is blind to a byte-swapped 16-bit relocation

Same toolchain, same moment. `check` (build.yml) on the ten projects:

```
FAIL diag     reference=1267 84779b23... produced=1267 8895939a...
FAIL ds1620   reference=6284 5bd93daf... produced=6284 ac0e6271...
... (all ten)
10 of 10 projects failed
```

`oracle` (gate.yml) on the same ten ROMs:

```
all 10 projects agree with the 2001 oracle: recorded size delta,
every differing byte accounted for
EXIT=0
```

Its own per-project table shows it *saw* the corruption and filed it away:

```
          clean                              F8 (byte-swapped R_I51_16)
project addr16 acall11 word16 zero8 resid | addr16 acall11 word16 zero8 resid
ds1620     308       1    137   400    25 |     37       1    137   633    25
ds1822     357       1    141   427    28 |     36       1    141   722    28
lcd        321       2    137   422    27 |     36       2    137   669    27
led1       279       1    133   398    25 |     36       1    133   615    25
welcome    264       1    131   402    25 |     36       1    131   604    25
```

Root cause, `tb/hexoracle.py`:

- `classify()` buckets every differing byte into `addr16 / acall11 / word16 /
  pcode13 / zero8`, and its `word16` rule is literally *"these two bytes are
  each other's swap"* (`oracle[i+1] == produced[i]`), which is exactly what a
  `bfd_putl16` fault produces.
- `main()` gates on **only two numbers**: the size delta and
  `len(residual)`. The five bucket counts are printed and never compared to
  anything.

So any fault whose byte differences fall into a bucket is invisible, and a
16-bit endianness fault falls into a bucket by construction. `addr16` dropping
from 308 to 37 and `zero8` rising from 400 to 633 raise nothing.

**Fix is small and obviously correct**: pin the bucket counts in
`hexoracle.EXPECT` alongside `res`, the way `frozen.expect` pins its per-project
counts. Not applied here - this is verification, not development.

**Why this matters more than it looks.** `tb/reference.md5` says so itself:
the reference ROMs in `base.7z` were *"built by the ported toolchain"*. So
`check` compares this toolchain against an earlier version of this toolchain -
a strong regression test, but a circular one. The only ROM reference in the
repository that no run of this toolchain has ever written is
`projekt/*/www8051.hex`, the 2001 output - and `oracle`, the single stage that
uses it, is the stage whose byte comparison does not gate. The independent
anchor and the non-gating stage are the same stage. (`hexoracle.EXPECT` does
pin the decoded size of each 2001 `.hex`, so the oracle input itself cannot be
edited silently; it is the comparison against it that is loose.)

### 4.3 F10b - a dropped section survives the whole gate

`*(.rodata)` deleted from the `.text` output section of
`ld/scripttempl/elf32i51.sc`. Behaviour probe, clean vs. mutant, on the same
input (`.text: nop/ljmp` plus a 3-byte `.rodata`):

```
clean : rodata-in-text: 00020000abcdef22   ROTAG 0x00000004 T
F10b  : rodata-in-text: 0002000022         ROTAG 0x00000005 R
```

The three `.rodata` bytes are gone from the `objcopy -j .text` image and the
symbol has been re-homed into an orphan section. Then:

```
INJECT-F10b stage=isa         EXIT=0
INJECT-F10b stage=roundtrip   EXIT=0
INJECT-F10b stage=branch      EXIT=0
INJECT-F10b stage=bits        EXIT=0
INJECT-F10b stage=reloc       EXIT=0
INJECT-F10b stage=sim         EXIT=0
INJECT-F10b stage=defaultlink EXIT=0
INJECT-F10b stage=commons     EXIT=0
INJECT-F10b stage=check       EXIT=0
INJECT-F10b stage=oracle      EXIT=0
```

**Ten for ten green on a proven-observable fault.** This is precisely the bug
class `tb/Makefile` documents at length in the `oracle` comment - a section
orphaned out of `.text` and dropped by `objcopy -j .text`, which is how nine of
ten 2001 ROMs lost `LCALL network_init`. The suite would not catch that bug
recurring for `.rodata`.

Coverage, measured rather than guessed - every section name emitted by any
input in the tree (the ten projects' `.asm`, `lib/*.asm`, and all five probe
scripts) against the arms of the default script:

```
emitted somewhere:  .text .data .rdata .rbss .bdata .bbss .bitdata .bitbss
                    .idata .ibss .xdata .xbss .edata-commons .ebss .eeprom
                    .regbank COMMON            (run-commons.sh covers every
                                                bss space and .regbank)
emitted nowhere:    vectors  .vectors  .init  .rodata  .fini
                    .gnu.linkonce.t.*  .gnu.linkonce.r.*  .gnu.linkonce.d.*
                    .edata (initialised, as opposed to the .ecomm case)
```

**Defect D2.** Nine `*(...)` arms of the loadable part of the default script -
including both `KEEP (*(vectors))` lines, which hold the interrupt vector
table - have no input anywhere in the testbench. Deleting any of them is
invisible; F10b proves it for one of the nine.

---

## 5. Mutation score

`make -C tb mutants`, stages `isa roundtrip branch bits reloc sim defaultlink
commons check`:

```
== 195 mutants
   killed    109
   survived   86
   no-build     0
   BROKEN       0   (no stale, no norebuild)
   KILL RATE 55.9% (109/195)
```

**55.9% (109/195)** - identical to `claude/integrate-round2` (55.9%, 109/195)
and up from `claude/tests-mutation` (54.4%, 106/195). **No regression.**

The run was executed in two pieces (129 then the remaining 66) because the
first invocation was killed by the session harness at 129/195; `run.py`'s
signal handler restored the sources (`interrupted; sources restored`) and the
remainder was replayed with `--only` over the same `mutants.json`, same tree,
same stages. Neither piece reported a `stale` or `norebuild` mutant, so all 195
were really rebuilt and really tested:

```
first 129:   71 killed   58 survived
last   66:   38 killed   28 survived   (KILL RATE 57.6% (38/66))
combined:   109 killed   86 survived   ->  55.9% (109/195)
```

Which stage did the killing, over all 109:

```
reloc        28      roundtrip    18      defaultlink   2
isa          28      check         3      branch        2
bits         28      sim           0      commons       0
```

`sim` and `commons` killed nothing only because the harness stops at the first
red stage and they run last; `commons` was independently shown to be a live
gate by F12.

**The three mutants that only `check` caught** - i.e. that survived all eight
`TOOLGATE` stages, which is exactly the set `gate.yml` runs:

```
 91/195 bfd-endian-398   bfd_getb16 -> bfd_getl16
110/195 bfd-howto-138    R_I51_8 pc_relative false -> true
115/195 bfd-howto-168    R_I51_H pc_relative false -> true
```

This is W4 measured rather than argued: `gate.yml` would have passed all three.

Where the 86 survivors sit:

```
bfd-howto    25   dis-cond0     9   gas-endian    8   ldsc-ldnum   7
opc-opctab    5   gas-constpm1  5   dis-constpm1  5   bfd-relop    5
bfd-constpm1  5   bfd-guard0    4   gas-relop     3   gas-guard0   3
dis-relop     2
```

`bfd-howto` (25 of 86) dominates: perturbing a howto field of a relocation kind
that `i51_final_link_relocate` handles in its own `case` never reaches the
generic path that reads the field. F7/F7b is one of these, and its probe
confirmed it is behaviourally equivalent rather than merely undetected - so a
large part of the surviving 44% is unreachable-by-construction, not blind spot.
`ldsc-ldnum` (7) is the linker-script arm of §4.3.


`tb/mutation/gen.py --cap 12` emits **195** mutants - the same population as
`claude/tests-mutation` (54.4%, 106/195) and `claude/integrate-round2` (55.9%,
109/195), so the rates are directly comparable. Distribution:
`bfd/elf32-i51.c` 73, `gas/config/tc-i51.c` 50, `opcodes/i51-dis.c` 36,
`include/opcode/i51.h` 24, `ld/scripttempl/elf32i51.sc` 12.

The mutation harness itself was checked rather than trusted: `run.py` refuses
to score at all unless the clean tree passes every stage first
(`baseline: isa roundtrip branch bits reloc sim defaultlink commons check all
pass`), classifies a mutant whose incremental rebuild did not mention the
mutated object as `norebuild` rather than as a survivor, and re-runs the gate
on the restored tree at the end to prove nothing leaked between mutants. The
stage list it uses is `MUTGATE` from `tb/Makefile`, which - unlike `gate.yml` -
includes `check`.

---

## 6. Masking paths

Searched for `|| true`, missing `set -e`, unchecked exit codes, pipes without
`pipefail`, `continue-on-error`, `if-no-files-found: ignore`, self-comparison,
and stale outputs.

**Clean:**

- `|| true` appears exactly once, in `dist` (`strip ... || true`), which judges
  nothing. `frozen.yml`'s `objdump ... || true` is inside the "Disassemble the
  divergence" diagnostic step, which also judges nothing.
- `if-no-files-found: warn`, not `ignore`, and only on artifact upload.
- Every `sh` helper uses `set -u` and gates every command with `|| die` /
  `|| exit`; each takes a fresh `mktemp -d` with a cleanup trap. Every Python
  helper uses `tempfile.TemporaryDirectory()`.
- Stale outputs: `check`, `oracle`, `check-canary`, `build` and `frozen` all
  `rm -rf` their work directory first. `check` additionally deletes the shipped
  `www8051.rom/.hex/.o` from every project *after* hashing them, and a project
  that builds without producing a ROM is recorded `NO-ROM` and counted as a
  failure.
- **No comparison of a file against itself.** Proven three ways, not read:
  H1 (an `objcopy` wrapper that flips one ROM byte -> 10/10 FAIL with ten
  distinct produced hashes), `check-canary` (an assembler that cannot assemble
  -> 10/10 FAIL), and H2 (the pinned `tb/reference.md5` gate rejects a
  one-digit change to the reference before any build happens).
- `frozen.yml`'s `continue-on-error: true` on the testbench step is **not** a
  mask: the Verdict step requires `steps.check.outcome == 'failure'`, so the
  frozen line going *green* also fails the job, and the `romdiff --expect`
  comparison step carries no `continue-on-error` and its status is the job's.
  Reproduced end to end here (§3, stages 13-14).
- `if: always()` in `gate.yml` and `build.yml` does not swallow a failure - it
  only lets later steps run. `make gate` exits nonzero on the first red stage
  (H7).

**Masking found:**

- **M1 - `oracle`'s byte-level gate does not gate.** §4.2. Five of the seven
  numbers it computes are printed and never compared. This is the same failure
  mode as the historical `decode: 280/280` printed constant, one level up: the
  numbers are real, the comparison is missing.
- **M2 - `oracle` swallows a project build failure.**
  `( cd $$p && make clean && make ) > log || echo "$$p: build failed"`.
  Recovered only because `hexoracle.py` then reports "no produced ROM"; a
  project that builds a wrong-but-same-size ROM after a failing sub-step is
  compared as if it were fine.
- **M3 - `--fuzz 0` does not enforce zero offsets.** §2 (D1).
- **M4 - untested script arms.** §4.3 (D2).

---

## 7. Do the workflows gate?

| workflow | triggers | judged steps |
|----------|----------|--------------|
| `gate.yml` | `workflow_dispatch`, `push` on `branches-ignore: [main]` | build, isa, roundtrip, branch, bits, reloc, sim, defaultlink, commons, oracle |
| `build.yml` | `workflow_dispatch`, `push` filtered to `mcs51/**`, `tb/**`, `.github/workflows/build.yml` | build, check, check-canary, isa (native), wine smoke, dist, package, refresh |
| `frozen.yml` | `workflow_dispatch`, `push` on `branches-ignore: [main]`, weekly cron | frozen, check-frozen (continue-on-error, compensated), romdiff `--expect`, verdict |

No `continue-on-error` outside the one compensated case; no red stage can be
ignored inside a workflow that runs. The gaps are in *which* workflow runs
*when*:

- **W1 - no `pull_request` trigger anywhere.** `gate.yml` says "green here is
  the condition for merging into main", but it only fires on `push` to a branch
  of this repository. A pull request from a fork runs nothing.
- **W2 - `gate.yml` and `frozen.yml` never run on `main`.**
  `branches-ignore: [main]` excludes the branch being protected, so the merge
  commit is never gated. Whether a branch-protection rule requires these checks
  cannot be read from here.
- **W3 - `check` and `check-canary` live only in `build.yml`, which is
  path-filtered.** A push that touches `.github/workflows/gate.yml`,
  `frozen.yml`, or `README.md` and nothing else runs `gate.yml` (which does not
  include `check`) and skips `build.yml` entirely. The ten-project ROM
  comparison - the strongest stage in the tree, and the one that caught F1, F8,
  H1 and H2 - is then not run at all.
- **W4 - `gate.yml` omits `check`.** Combined with M1, `gate.yml` on its own
  cannot see a fault that corrupts every ROM (F8: `check` red, `oracle` green).
  The mutation run puts a number on it: three of the 109 killed mutants
  (`bfd-endian-398`, `bfd-howto-138`, `bfd-howto-168`) survived every stage
  `gate.yml` runs and were caught only by `check`. `MUTGATE` in `tb/Makefile`
  gets this right and includes `check`; `gate.yml` does not.
- Path-filter symmetry: `gate.yml` and `frozen.yml` have no `paths:` filter, so
  they run on every non-main push. Only `build.yml` is filtered.

---

## 8. Verdict

The port builds clean under `-Werror`, the patches apply to a pristine 2.47 at
fuzz 0 with no rejects, all 14 stages are green, and 11 of them were shown
capable of going red under a fault they are supposed to catch. The reference
comparison is genuine - it was made to fail by a single flipped ROM byte, by a
sabotaged assembler, and by a one-digit change to the pin file. The vendored
corpora are byte-identical to upstream. `check-canary` itself was made to fail.
This is a substantially stronger testbench than the two rounds that preceded it.

Two real holes remain:

1. **`oracle` does not gate on the bytes it compares** (M1). It is `gate.yml`'s
   only contact with the ten projects, and a linker endianness fault that makes
   all ten ROMs wrong leaves it green. Pin the bucket counts.
2. **A section dropped from the image is invisible** (D2/M4) - the exact bug
   class the repository documents as the reason `oracle` exists. Give every
   `*(...)` arm of the default script an input in `run-defaultlink.sh`.

Plus: `--fuzz 0` does not deliver the zero-offset promise (D1/M3), `oracle`
swallows sub-build failures (M2), and the workflows never run on
`pull_request` or on `main`, with the strongest stage (`check`) behind a path
filter and absent from `gate.yml` (W1-W4).

The mutation score did not regress: 55.9% (109/195), the same as
`claude/integrate-round2` and above `claude/tests-mutation`'s 54.4%.

Nothing in this tree was modified. Two temporary harness edits (`tb/Makefile`,
`tb/reference.md5`) were made for H2 and H3 and reverted; `git status` is clean.

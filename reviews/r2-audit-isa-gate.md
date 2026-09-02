# Audit: the instruction-level gate and the simulator oracle

Branch `claude/audit-isa-gate`, based on `origin/work/green` (5d02910).
Scope: `tb/isa/*`, `tb/isa_check.py`, `tb/dialect.py`, `tb/romdiff.py`,
`tb/fixhunks.py`, `tb/i51elf_ar.py`, `tb/sim/*`, and how `tb/Makefile` and the
workflows invoke them.

Everything below was run on this branch against a real
`make -C tb build` of binutils 2.47 + `mcs51/*.patch` (i51-elf), with
`sdcc-ucsim 4.2.0+dfsg-1` installed. Line references to `tb/` files are to
`origin/work/green`, before the fixes in §5. Line references to
`gas/config/tc-i51.c`, `opcodes/i51-dis.c`, `include/opcode/i51.h` and
`bfd/elf32-i51.c` are to the patched binutils 2.47 tree that `make -C tb build`
produces.

## Verdict

The gate is two-thirds real and one-third theatre.

* **Encoding is genuinely pinned.** All 255 defined MCS-51 opcodes are
  assembled and compared byte-for-byte against a golden column produced by a
  different assembler. That is a real independent oracle and it works.
* **Execution is genuinely pinned, for half the ISA.** 131 of 255 opcodes are
  executed inside ucsim, an independent simulator, and judged by a
  self-checking program. That is the strongest part of the gate.
* **Disassembly was not pinned at all.** The `decode` step asserted a condition
  that the i51 disassembler can never violate. It was a tautology. Three
  separate deliberately-broken disassemblers passed every gate, one of which
  printed `nop` for every instruction in the ISA. Fixed on this branch (§5);
  all three now go red.
* **The `program` step proves nothing.** `make isa` runs `testall.asm` through
  the assembler and checks only that the assembler exited 0. No bytes are
  compared. Its own docstring claims it "covers branches, fixups, tables"; it
  does not check any of them.
* **The linker's two overflow checks are untested.** `bfd/elf32-i51.c`
  independently re-implements the ACALL/AJMP 2K-page rule and the ±128
  relative-branch limit. Deleting either leaves all five gates green.
  `branch.py` covers the assembler's copies only.

Sixteen deliberate faults were injected into the port and every gate rerun for
each. Ten went red at the right gate with the right message. Six passed
unnoticed.

---

## 1. Coverage, computed

Method: the opcode→length table is derived from the *third-party* golden column
of `tb/isa/8051.txt` + `tb/isa/extra.txt`, not from our own disassembler. The
linked `testall` image is then walked linearly with that table, with the two
embedded `db` pairs (`DB_TBL`, and the two bytes before `FAIL71`) excluded as
data. The walk resyncs exactly; no unknown opcode and no data/instruction
overlap.

```
length table: 255 opcodes
opcodes absent from the table: a5          <- the one reserved MCS-51 opcode
testall linked .text: 3350 bytes
data bytes at: 0x987 0x988 0x99f 0x9a0
resync errors: []
distinct opcodes executed-path in testall: 131

SUMMARY
  defined MCS-51 opcodes (256 minus reserved a5): 255
  encoding checked vs third-party golden bytes  : 255
  executed/semantics checked by ucsim (testall) : 131
  encoding-only, never executed                 : 124
```

### The real end-to-end number

| what is proved | how many of 255 |
|---|---|
| source → bytes, vs an independent assembler's bytes | **255 (100%)** |
| bytes → linked image → executed → semantics checked by an independent simulator | **131 (51%)** |
| bytes → text, disassembly checked for correctness | **0 (0%)** as found; 255 after §5 |

"End-to-end" in the strong sense — the port's output is executed and the result
is judged by something that is not the port — is **131/255**.

`tb/isa/PROVENANCE` says testall covers "every instruction except MOVX and
RETI". That is testall's own header comment repeated, and as a coverage claim it
is wrong by a wide margin. 124 opcodes never appear on its executed path:

| family | opcodes executed | missing |
|---|---|---|
| `movx` | 0 / 6 | `e0 e2 e3 f0 f2 f3` |
| `reti` | 0 / 1 | `32` |
| `acall` page selects | 1 / 8 | `11 31 51 71 91 b1 f1` |
| `ajmp` page selects | 3 / 8 | `01 21 61 81 a1` |
| `xch a,Rn` | 1 / 8 | `c9 ca cb cc cd ce cf` |
| `xchd` | 1 / 2 | `d7` |
| `@Ri` operand forms (`x6`/`x7`) | 19 / 32 | `06 17 37 46 57 67 87 97 a7 b6 c7 d7 f7` |

Those 124 are still encoding-checked against the third-party bytes; they are
simply never run, so nothing tests what they *do*. `movx` and `reti` are
excluded on purpose. The rest is testall's own arbitrary sampling: it picks one
or two register numbers per instruction group and calls it done.

### Modes and forms never touched by any gate

Confirmed by grep over `8051.txt`, `extra.txt`, `testall.asm`, `branch.py`,
`run-defaultlink.sh`, `run-commons.sh`:

* **`HIGH(` and `LOW(` operand prefixes — zero occurrences anywhere.** These
  are the only syntax that produces `R_I51_H` / `R_I51_L`
  (`BFD_RELOC_I51_8_HIGH` / `_8_LOW`). Both relocations, and both branches of
  the `op1hlmode` / `op2hlmode` handling in `tc-i51.c`, are completely
  untested.
* **`R_I51_13_PCODE`, `R_I51_R1`, `R_I51_R3`** — no corpus reaches them.
* **Numeric SFR dotted bit addresses** (`0x90.1`, i.e. the
  `addr >= 0x80 && (addr & 7) == 0` arm of `i51_fold_bit_suffix`). The table
  has `0x20.3`, `0x23.5`, `0x24.7`, `0x2f.2` — all in the 0x20..0x2f RAM
  window — and named SFR bits (`ACC.7`, `P1.0`) which resolve through the hash
  table instead. Fault **F11** proves the gap: an off-by-one in that arm passes
  every gate.
* **The `…common` spellings of the common directives.** `tc-i51.c:92-105`
  registers both `rcomm`/`rcommon`, `bcomm`/`bcommon`, `bitcomm`/`bitcommon`
  and so on. `run-commons.sh` exercises only the short form of each.
* **Relocations in the table path at all.** Every `8051.txt` entry is a literal
  constant assembled at `.text` offset 0 and read back with
  `objcopy -O binary`. No symbol, no relocation. `branch.py` is the same — it
  uses numeric targets on purpose. So the only gates that ever link anything are
  `sim`, `defaultlink` and `commons`.

Relocation coverage, against the twelve types the port defines:

| reloc | exercised by | error path exercised |
|---|---|---|
| `R_I51_7_PCREL` | sim | **no** (F15) |
| `R_I51_11` | sim | **no** (F14) |
| `R_I51_16` | sim, defaultlink | n/a |
| `R_I51_8` | defaultlink | no |
| `R_I51_8_BIT` | defaultlink | no |
| `R_I51_8_B2B` | defaultlink | no |
| `R_I51_H` / `R_I51_L` | **nothing** | — |
| `R_I51_13_PCODE` | **nothing** | — |
| `R_I51_R1` / `R_I51_R3` | **nothing** | — |
| `R_I51_NONE` | n/a | — |

### The named regressions from last round

| bug | pinned? | by what | fault that proves it |
|---|---|---|---|
| `mov direct,direct` operand order | **yes** | `8051.txt:185` + sim | F1 → isa red, sim red |
| `/bit` negation (`anl c,/bit`) | **yes** | `extra.txt` + `8051.txt` (6 entries) + sim | F5b → isa red, sim red |
| ACALL/AJMP page boundary, assembler | **yes** | `branch.py` `ajmp-cross-ok` / `ajmp-back-cross` / `*-next-page` | F4 → branch red (isa, sim green) |
| ACALL/AJMP page boundary, **linker** | **NO** | nothing | F14 → all five gates green |
| relative-branch range, **linker** | **NO** | nothing | F15 → all five gates green |
| ACALL/AJMP page-bit placement | **yes** | `8051.txt` acall/ajmp ×16 + `branch.py` | F7 → isa red, branch red |
| relative branch ±127/−128 extremes | **yes** | `branch.py` `sjmp-fwd-max` / `sjmp-back-min` / `sjmp-plus128` / `sjmp-minus129` | F8 → branch red (isa, sim green) |
| relative branch base (PC+1 vs PC+2) | **yes** | table + branch + sim | F3 → isa, branch, sim red |
| DPTR / imm16 byte order, literal operand | **yes** | `8051.txt:148` `mov DPTR,#0x1234` | F6a → isa, branch, sim red |
| bit address, RAM window | **yes** | `8051.txt` `0x20.3` etc. | F10 → isa red |
| bit address, numeric SFR window | **NO** | nothing | F11 → all five gates green |

Each of the pinned ones is genuinely pinned — the fault injections below are
the proof, not an argument.

---

## 2. Soundness of the oracle

### What is independent

* **`8051.txt` golden bytes.** Vendored from naken_asm, produced by `c51asm`.
  Nothing in the port touches that column. Comparing our assembler's output
  against it is a real independent check. sha256 matches `tb/isa/PROVENANCE`:
  `a597813a…7884c`, 7374 bytes.
* **ucsim.** `run-testall.sh` drives our `as` → our `ld` → our `objcopy` → Intel
  HEX → `s51`, and the verdict comes from the program's own self-checks
  executed by a simulator that shares no code with the port. This is the one
  place where the port's *semantics* are judged by a third party.

### What is not

* **`branch.py`, `run-defaultlink.sh`, `run-commons.sh` expectations are
  hand-derived in-repo.** `run-defaultlink.sh` even carries a golden ROM image
  literal (`want=120011900001e0d208d20175812202000022`). These are regression
  pins written by the same people who wrote the port. They are useful — F4, F7,
  F8 prove they catch things — but they are not an oracle.
* **`make check` compares the port against itself.** `tb/frozen-report.md:7`:
  *"The reference ROMs are base.7z's own, produced by the current port on
  binutils 2.47."* So the ten-project ROM comparison is a byte-for-byte
  regression pin, not a correctness check. Nothing is wrong with that, but
  `tb/Makefile:19-22` describes it as "the reference … every project is
  supposed to produce", which reads as an external ground truth. It isn't one.
* **`naken_asm` and `c51asm` never run.** Only a frozen text file from 2020-era
  naken_asm is used. Nothing in CI installs either tool. The "independent
  assembler" is an artifact, not a live second opinion — so any syntax the port
  grows after the file was vendored has no golden column at all.

### Is anything a round-trip through the same tables?

Worth stating plainly: `gas/config/tc-i51.c` and `opcodes/i51-dis.c` **include
the same file**, `include/opcode/i51.h`:

```
gas/config/tc-i51.c:152  #define I51_INS(NAME,ARGS,SIZE,OPCODE,MRELOC,BIN,MASK) {NAME,ARGS,SIZE,MRELOC,BIN},
gas/config/tc-i51.c:157  #include "opcode/i51.h"
opcodes/i51-dis.c:36     #define I51_INS(NAME,ARGS,SIZE,OPCODE,MRELOC,BIN,MASK) {NAME,ARGS,SIZE,BIN,MASK},
opcodes/i51-dis.c:40     #include "opcode/i51.h"
```

So a round-trip through this port, **on its own**, would say nothing about the
opcode bytes: a wrong `BIN` field in `i51.h` is wrong identically in both
directions and the round-trip closes right over it. As found, the gate did not
do a round-trip — it did something weaker still (§3.1).

The fix in §5 does add one, and the reason it is worth adding is that it does
not stand on its own. The `assemble` half of the same gate compares those exact
opcode bytes against the third-party golden column first. The opcode table is
therefore already pinned by something outside the port, and the round-trip
answers the remaining question — whether the decoder agrees with the encoder
about mnemonic, operands, operand order and length. That is a real question
about the disassembler, and F2/F9/F12 confirm it is now being asked. What
neither half reaches is the *spelling* the disassembler chooses: if `i51.h`
named the `0x28` instruction `frobnicate`, both halves would still be happy.

---

## 3. Running the gate, and breaking it on purpose

### Baseline: all five green

```
$ make -C tb isa BUILD=…/work/modern/build
== table: 280 instructions
   assemble: 280/280
   decode:   280/280
== program: testall.asm
   assembled, 3350 bytes of text
PASS
== table: 3 instructions          (extra.txt)
   assemble: 3/3
   decode:   3/3
PASS

$ make -C tb branch …      == branch: 24 cases / checked: 24/24 / PASS
$ make -C tb sim …         PASS: testall ran to completion, all instruction tests passed (P1=127)
$ make -C tb defaultlink … run-defaultlink: PASS (default emulation links and lays out all spaces)
$ make -C tb commons …     run-commons: PASS (every external common keeps its address space)
```

### Fault injection

Method: one-line edit to the port source in `work/modern/binutils-2.47`,
`make -j4 all-gas all-binutils all-ld`, run all five gates, revert, rebuild,
confirm the baseline is green again. Harness:
`inject.sh NAME FILE OLD NEW`, aborts unless `OLD` occurs exactly once.

| # | injected fault | file | isa | branch | sim | defaultlink | commons |
|---|---|---|---|---|---|---|---|
| F1 | `mov direct,direct` operands emitted in the wrong order | tc-i51.c | **red** | green | **red** | green | green |
| F2 | disassembler prints the wrong register number (`R7`→`R0`) | i51-dis.c | green | green | green | green | green |
| F3 | relative-branch PC base `+1` → `+2` | tc-i51.c | **red** | **red** | **red** | green | green |
| F4 | ACALL/AJMP 2K-page check removed (assembler) | tc-i51.c | green | **red** | green | green | green |
| F5b | `anl c,/bit` loses its negation (`0xB0`→`0x82`) | i51.h | **red** | green | **red** | green | green |
| F6a | 16-bit literal operand emitted little-endian | tc-i51.c | **red** | **red** | **red** | green | green |
| F7 | ACALL/AJMP page bits shifted `<<5` → `<<4` | tc-i51.c | **red** | **red** | green | green | green |
| F8 | relative-displacement range check removed | tc-i51.c | green | **red** | green | green | green |
| F9 | disassembler prints `nop` for **every** instruction | i51-dis.c | green | green | green | green | green |
| F10 | dotted bit address off by one, RAM window | tc-i51.c | **red** | green | green | green | green |
| F11 | dotted bit address off by one, numeric SFR window | tc-i51.c | green | green | green | green | green |
| F12 | disassembler prints operand 1 twice instead of operand 2 | i51-dis.c | green | green | green | green | green |
| F13 | linker writes `R_I51_16` little-endian | elf32-i51.c | green | green | **red** | **red** | green |
| F14 | linker drops the ACALL/AJMP page overflow check | elf32-i51.c | green | green | green | green | green |
| F15 | linker drops the relative-branch overflow check | elf32-i51.c | green | green | green | green | green |
| F16 | linker `R_I51_8_B2B` off by one | elf32-i51.c | green | green | green | **red** | green |

F14 and F15 were run after the `isa_check.py` fix in §5 was already in the tree,
so their raw `isa` column showed one unrelated decode failure on the one-byte
`nop`; the logs show `assemble: 280/280` in both cases and the artefact is
recorded as green above. That defect is fixed (`objdump -z`) and F15 onwards
show `decode: 280/280` under the new check.

Representative failure text, showing the gate names the right thing:

```
F1   line 185  mov 177,100    want 8564b1   got 85b164
F5b  line 91   anl c,/OV      want b0d2     got 82d2
     line 92   anl c,/P2.5    want b0a5     got 82a5      (5 entries)
F4   ajmp-back-cross  ajmp 0x07fd   accepted, must be rejected
     ajmp-next-page   ajmp 0x0800   accepted, must be rejected
     acall-next-page  acall 0x0800  accepted, must be rejected
F8   sjmp-plus128     sjmp 0x0082   accepted, must be rejected
     sjmp-minus129    sjmp 0x0081   accepted, must be rejected
```

### Faults that slipped through every gate

| fault | what it breaks |
|---|---|
| **F2** | disassembler prints the wrong register in operand 2 |
| **F9** | disassembler prints `nop` as the mnemonic for **every** instruction |
| **F12** | disassembler prints operand 1 where operand 2 belongs |
| **F11** | assembler mis-encodes a dotted bit address on an SFR (`0x90.1`) |
| **F14** | **linker** stops rejecting an out-of-page `acall`/`ajmp` |
| **F15** | **linker** stops rejecting an out-of-range relative branch |

F2, F9 and F12 are one defect: the `decode` step could not fail (§3.1). Fixed.

F11 is a corpus hole: no entry anywhere uses a numeric SFR dotted bit
(`0x90.1`); the four dotted entries in `8051.txt` all land in the 0x20..0x2f RAM
window and the named ones (`ACC.7`) take a different code path.

F14 and F15 are the more interesting pair. `branch.py` pins the *assembler's*
range and page checks — F4 and F8 prove that — but nothing pins the **linker's
duplicates of the same two checks**. `bfd/elf32-i51.c` re-implements both
(`R_I51_11` returns `bfd_reloc_overflow` outside the 2K page, `R_I51_7_PCREL`
outside ±128) and both can be deleted with every gate staying green, because no
corpus ever links a branch that is out of range. Since the two implementations
are independent copies of the same rule — the comment in `elf32-i51.c` says
"Mirrors BFD_RELOC_I51_11 in gas/config/tc-i51.c" — they can drift apart
silently. F13 and F16 show the linker is otherwise reached: a byte-order or
bit-arithmetic fault in it does go red, via `sim` and `defaultlink`. It is only
the *error* paths that are untested.

Two further faults were injected and then discarded as harness artefacts rather
than results, and are not in the table above. Both are recorded because the
reasons are findings in their own right: the first attempt at F5 edited
`include/opcode/i51.h` and did not rebuild the assembler at all (§4, build
dependency), and F6 edited `md_apply_fix`'s `BFD_RELOC_16` arm, which turns out
to be unreachable in practice (§4). F5b and F6a are the corrected versions.

### 3.1 The `decode` step cannot fail

`tb/isa_check.py:60-66` as found on `origin/work/green`:

```python
def decodes(self, data, work):
    """True if our disassembler makes sense of these bytes."""
    ...
    return r.returncode == 0 and r.stdout.strip() and '(bad)' not in r.stdout
```

`print_insn_i51` never prints `(bad)`. On an unrecognised opcode it prints
`.byte 0x??` with a `; ????` comment (`opcodes/i51-dis.c:288-296`):

```c
if (!ok)
  {
    sprintf (op1, "0x%02X", insn);
    sprintf (comment1, "????");
    ...
  }
(*prin) (stream, "%s", ok ? opcode->name : ".byte");
```

Demonstrated on the one input that ought to be impossible to decode — `a5`, the
single reserved MCS-51 opcode, the one byte value `8051.txt` has no entry for:

```
$ printf '\245' > t.bin
$ objdump -D -z -b binary -m i51 t.bin
00000000 <.data>:
   0:	a5          	.byte	0xA5		; ????
```

No `(bad)` anywhere. The condition `'(bad)' not in r.stdout` is true for every
possible input to this disassembler. `decode: 280/280` was printed
unconditionally; it was not a measurement. That is exactly why F2, F9 and F12
passed.

This was the single largest gap in the gate: **the disassembler had no test at
all.** Not a weak test — none. The line in the module docstring, "feed the same
golden bytes to our disassembler; every one must decode", described a check that
was not implemented. §5 implements it.

### 3.2 The `program` step checks only "no error"

`tb/isa_check.py:109-119` assembles `testall.asm` and, on success, prints
`assembled, N bytes of text`. It compares nothing. The docstring
(`isa_check.py:8-9`) says it "Covers what a one-instruction-per-line table
cannot: branches, fixups, tables." It covers none of those — no branch
displacement, no fixup and no table byte is inspected. The real coverage of
those things comes from `make sim`, which is a different target and is **not
run by `build.yml`** (only `gate.yml` runs `sim`). On the `build` workflow, the
`testall.asm` step is a compile-only smoke test dressed as a semantic one.

---

## 4. Python and shell quality

Ranked by severity.

### S1 — `decodes()` asserts nothing (§3.1)
`tb/isa_check.py:66`. Fixed below.

### S1 — an empty or damaged corpus is a silent PASS
`read_table` (`tb/isa_check.py:28-35`) keeps only lines containing `|` and
drops everything else without a word. Nothing asserts a minimum entry count and
nothing verifies the corpus against the sha256 recorded in
`tb/isa/PROVENANCE` — no workflow re-hashes those files.

Feeding it a corpus whose `|` separators are gone — a bad merge, a whitespace
normaliser, a CRLF round trip:

```
full table entries: 280
separator lost -> entries: 0
empty file      -> entries: 0
```

and the gate is happy with the result:

```
$ python3 tb/isa_check.py --build …/work/modern/build --table /dev/null
== table: 0 instructions
   assemble: 0/0
   decode:   0/0
PASS
$ echo $?
0
```

A gate that reports PASS on an empty corpus is a gate that will go green the
day someone truncates the corpus. Fixed below.

### S2 — `hex_payload` validates nothing
`tb/isa_check.py:22-25` slices `raw[4:4+raw[0]]` with no record-type and no
checksum check. A type-01 (EOF) record parses as a zero-length payload, and a
golden byte edited without fixing the checksum quietly becomes the new expected
value:

```
as found, EOF record  :00000001FF -> b''
as found, one data byte corrupted, checksum left stale:
   :03000000B405FD47 (good) -> b405fd
   :03000000B405FE47 (bad)  -> b405fe
```

A zero-length expected value matches any instruction that assembles to nothing.
Fixed below; the same record now reports
`':03000000B405FE47' has a bad checksum`, and all 283 vendored records still
pass.

### S2 — `fixhunks.py` and `i51elf_ar.py` are dead in CI
Neither appears in `tb/Makefile` or in any workflow:

```
$ grep -rn "fixhunks\|i51elf_ar" --include='*.yml' --include=Makefile .
(no output)
```

`fixhunks.py`'s own docstring says *"CI applies the patch with --fuzz 0, so N
has to be brought back in line by counting"* — but no CI step runs
`fixhunks.py --check`. The failure mode is caught only indirectly, by
`make build`'s `patch --fuzz 0` refusing to apply. That is adequate but the
docstring overstates the arrangement.

### S2 — `include/opcode/i51.h` has no build dependency edge into gas
Not one of my files, but it bit this audit and it will bite anyone iterating
locally. `gas/Makefile` builds `config/tc-i51.o` via `TARG_CPU_O` and never
emits an `include config/$(DEPDIR)/tc-i51.Po` line, so the recorded dependency
is never read:

```
$ grep -n "tc-i51" work/modern/build/gas/Makefile
553:TARG_CPU_C = $(srcdir)/config/tc-i51.c
554:TARG_CPU_O = config/tc-i51.o
555:TARG_CPU_H = $(srcdir)/config/tc-i51.h
$ grep -o "[^ ]*include/opcode/i51.h" work/modern/build/gas/config/.deps/tc-i51.Po | sort -u
../../binutils-2.47/gas/../include/opcode/i51.h
$ touch work/modern/binutils-2.47/include/opcode/i51.h
$ make -C work/modern/build/gas as-new
make: Entering directory '…/build/gas'
make: Leaving directory '…/build/gas'          <- nothing rebuilt
```

Editing the shared opcode table — the single most load-bearing file in the port
— does not rebuild the assembler. `make -C tb build` does `rm -rf work/modern`
first, so CI is safe; an incremental local `make -C tb isa BUILD=…` is not. My
first attempt at fault F5 produced a false "slips through every gate" result
for exactly this reason.

### S3 — `md_apply_fix`'s `BFD_RELOC_16` arm is unreachable in practice
Confirmed by F6: little-endianising `bfd_putb16 ((bfd_vma) value, where)` in
`md_apply_fix` changed nothing anywhere, because literal 16-bit operands go
through `fixup16`'s constant path (`number_to_chars_bigendian`) and symbolic
ones stay as `R_I51_16` relocations for the linker
(`tb/sim/run-testall.sh:64-65` says so). Not a defect in the gate; worth
knowing when reading coverage numbers.

### S3 — `run-testall.sh` `patch` invocation can prompt
`tb/sim/run-testall.sh:54` runs `patch -s -d "$W" -p1 < patch` with no
`--batch`. GNU patch prompts on a mismatch; with the patch itself on stdin the
prompt reads from `/dev/tty`, which does not exist in a container. Behaviour is
then implementation-defined rather than a clean failure. Fixed below.

### S3 — external dependencies are unpinned and unrecorded
`gate.yml` installs `sdcc-ucsim` from Ubuntu with no version pin and never
records which version ran. The run's whole semantic verdict rests on that
binary. `frozen.yml` at least does `patch --version | head -1`; `gate.yml`
records nothing. `naken_asm` is never installed (correctly — only its vendored
data file is used). Verified locally: `sdcc-ucsim 4.2.0+dfsg-1`, `uCsim 0.6.4`,
and `run-testall.sh`'s `expr /u 100000+sfr[0x90]` marker path works with it.

### Clean

* No `shell=True`, no `os.system`, no `eval`, no bare `except` anywhere in
  scope. The only `try` is `try/finally` in `tb/i51elf_ar.py:41`.
* Exit codes propagate: every script returns nonzero on failure and `make`
  turns that into a red step. `run-testall.sh` uses distinct codes (1 test
  failed, 2 usage/toolchain, 3 simulator absent, 4 harness) and every one of
  them fails the CI step.
* `gate.yml` uses `if: always()` on every gate after the first, so one red gate
  does not hide the rest.
* `dialect.py` is honest: converting `testall.asm` leaves no unconverted `h`
  suffix, changes no instruction count (2473 lines in, 2472 out — the dropped
  line is the `end` directive), and the file uses only `h` suffixes (103 of
  them, zero `b`/`o`/`q`/`d`), so the single rule is sufficient. Its
  `([#, ])` prefix class would miss a tab-prefixed hex literal; there are zero
  of those in `testall.asm`.
* `romdiff.py` is a reporting tool only — it always returns 0 and is not a
  gate. `frozen.yml` handles that correctly with an explicit `Verdict` step
  that re-raises the `continue-on-error` outcome as an annotation.

---

## 5. What I changed

Small, clearly-correct defects only. No gate semantics were loosened and no
expected value was adjusted to make anything pass.

1. **`tb/isa_check.py` — make `decode` actually decode.** Replaced the
   unreachable `'(bad)' not in stdout` test. A golden byte string now has to
   come back from objdump as exactly one instruction, consuming exactly those
   bytes (which pins the decoded length), named rather than dumped as `.byte`,
   and re-assembling to the same bytes. Also passes `-z`, without which objdump
   elides an all-zero payload as `...` — that is every one-byte `nop`.

   The round trip is self-referential with respect to `include/opcode/i51.h`,
   and I say so in the docstring. It is still worth having, because the
   *assemble* half of the same gate has already pinned that table against a
   third-party golden column: given a correct encoder, agreement here is a real
   statement about the decoder's mnemonic, operands, operand order and length.

2. **`tb/isa_check.py` — refuse a degraded corpus.** `read_table` now raises on
   any non-blank, non-comment line it cannot parse instead of dropping it, and
   `main` fails when a `--table` yields zero entries.
3. **`tb/isa_check.py` — validate the Intel HEX records.** `hex_payload` now
   rejects a non-data record type, a length byte that disagrees with the
   record, and a bad checksum. All 283 vendored records pass.
4. **`tb/isa_check.py` — docstrings that match the code.** The `program` entry
   no longer claims to cover "branches, fixups, tables"; it says what it does,
   which is assemble and report size, and points at `make sim` for semantics.
5. **`tb/sim/run-testall.sh`** — `patch --batch` so a patch mismatch fails
   cleanly instead of trying to prompt on a `/dev/tty` that is not there.

### Verification

All five gates green on the current build after the changes:

```
== table: 280 instructions
   assemble: 280/280
   decode:   280/280
== program: testall.asm
   assembled, 3350 bytes of text (not compared; run `make -C tb sim' to execute it)
PASS
== table: 3 instructions          (extra.txt)
   assemble: 3/3
   decode:   3/3
PASS
== branch: 24 cases / checked: 24/24 / PASS
PASS: testall ran to completion, all instruction tests passed (P1=127)
run-defaultlink: PASS (default emulation links and lays out all spaces)
run-commons: PASS (every external common keeps its address space)
```

The three disassembler faults were then re-injected against the fixed gate.
All three now go red, and the message names the defect:

```
V2  (wrong register)   decode:  208/280
      line 48  add a, r0   bytes 28   decoded to `add A, R7', which assembles to 2f
V9  (mnemonic -> nop)  decode:    1/280
      line 1   cjne a,#5   bytes b405fd
                decoded to `nop A, #0x05, .+0x00', which does not assemble
V12 (operand swap)     decode:   80/280
      line 1   cjne a,#5   bytes b405fd
                decoded to `cjne A, A, .+0x00', which does not assemble
```

And the empty-corpus case now fails instead of passing:

```
$ python3 tb/isa_check.py --build …/work/modern/build --table /dev/null
== table: 0 instructions
   FAILED: no instructions in /dev/null
FAIL: 1
$ echo $?
1
```

Fault coverage before and after: 10 of 16 caught → **13 of 16**. The three that
moved are F2, F9, F12. The three still uncaught are F11 (corpus hole), F14 and
F15 (the linker's untested error paths) — all three need a new test case, not a
code fix, and are listed in §6.

## 6. What I did not fix, and would

* **Give the disassembler a genuinely independent corpus.** §5 fixed the
  tautology, but the check it replaces it with still leans on our own
  assembler. The clean version is a third column in the table —
  `source|hex|disassembly` — with the disassembly produced by a disassembler
  that is not ours. `naken_asm` ships one.
* **Close the numeric-SFR-dotted-bit hole (F11).** One line in `extra.txt`
  would do it, e.g. `setb 0x90.1` → `D2 91`. I did not add it because
  `extra.txt` sits next to a `PROVENANCE` that describes the corpora as
  third-party and vendored verbatim; a hand-written entry needs the maintainer
  to decide where it belongs.
* **Test the linker's overflow paths (F14, F15).** Two link-and-expect-failure
  cases: an `ajmp` whose target the linker places in another 2K page, and an
  `sjmp` to a label the linker puts more than 128 bytes away. `run-commons.sh`
  is the closest existing shape to copy. Without them the linker's copies of the
  two range rules can drift away from the assembler's, silently.
* **Cover `HIGH(` / `LOW(`.** Two `branch.py`-style directed cases would pin
  `R_I51_H` and `R_I51_L`, which today have no test.
* **Hash the corpora at gate time** against `tb/isa/PROVENANCE`.
* **Record the ucsim version** in `gate.yml`, the way `frozen.yml` records
  `patch --version`.
* **Add the missing `include config/$(DEPDIR)/tc-i51.Po`** to the gas Makefile
  fragment in `mcs51/modifications.patch`.
* **Run `make -C tb sim` in `build.yml`**, or stop describing the `isa`
  `--program` step as if it covered semantics.

# Mutation testing the MCS-51 port

Which tests are worth having, measured instead of guessed: inject one fault at a
time into the port's own source, rebuild, run the whole testbench against each,
and count how many faults it notices.

**Kill rate before: 22.6 % (44 of 195). After: 54.4 % (106 of 195).**

Same 195 mutants both times, same machine, same build. The only thing that
changed between the two numbers is the set of tests.

| suite | stages | killed | kill rate |
|---|---|---:|---:|
| before | isa branch sim defaultlink commons check | 44 / 195 | **22.6 %** |
| after | isa **roundtrip** branch **bits reloc** sim defaultlink commons check | 106 / 195 | **54.4 %** |

---

## 1. The harness

```
make -C tb build                 # once: the tree the mutants are cut into
make -C tb mutants               # generate, inject, rebuild, gate, report
```

`tb/mutation/gen.py` produces the mutants, `tb/mutation/run.py` runs them,
`tb/mutation/report.py` turns two runs into the tables below. About 7 s per
mutant on four cores: 195 mutants is 22 minutes.

### What gets mutated

Only the files the port itself adds - `mcs51/additions.patch` - and inside the C
files only the functions that encode, relocate or decode. Mutating binutils'
own generic code would measure binutils, not this port.

| file | what is mutated |
|---|---|
| `gas/config/tc-i51.c` | `md_apply_fix`, `fixup8/11/16`, `check_range`, `i51_fold_bit_suffix`, `i51_build_ins`, `md_pcrel_from_section`, `tc_gen_reloc`, `i51_bit`, `md_undefined_symbol` |
| `bfd/elf32-i51.c` | the HOWTO table, `i51_final_link_relocate`, `elf32_i51_relocate_section`, the reloc lookups, the common hooks |
| `opcodes/i51-dis.c` | `print_insn_i51` and its two readers |
| `include/opcode/i51.h` | the `I51_INS` opcode table |
| `ld/scripttempl/elf32i51.sc` | the default linker script |

### The operators

Nothing here is a hand-written list of bugs. Eleven operators are applied to
every site in scope where they match; each match is one mutant.

| operator | fault it stands for |
|---|---|
| `relop` | `<` ↔ `<=`, `>` ↔ `>=` — a range check off by one |
| `constpm1` | an integer literal incremented — wrong mask, wrong bound, wrong shift |
| `guard0` | the condition of a check that reports an error forced to 0 — the check is gone |
| `cond0` | any single-line `if` condition forced to 0 (disassembler) |
| `retstatus` | `return bfd_reloc_overflow/outofrange` → `return bfd_reloc_ok` — overflow detected and ignored |
| `endian` | `bfd_putb16` / `getb16` / `number_to_chars_bigendian` → the little-endian spelling |
| `oporder` | two adjacent statements differing only in an operand index, swapped |
| `boolarg` | the pc-relative flag of a `fix_new_exp` flipped |
| `howto` | one field of one HOWTO: size, bitsize, rightshift, dst_mask, pc_relative, overflow complaint |
| `opctab` | one `I51_INS` row: opcode byte, match mask, or size |
| `ldnum` | an integer literal in the default linker script incremented |

Matches are capped per (file, operator) and sampled evenly, so the population is
deterministic and a before/after comparison is on exactly the same mutants:
`--cap 12`, with 30 for `howto` and 24 for `opctab` because those two tables are
large and uniform. That is 195 mutants; none failed to compile.

### How a mutant is run

Patch the one line in `work/modern/binutils-2.47`, `make all-gas all-ld
all-binutils` in the existing build tree, run the gate, restore the line. The
first failing stage kills the mutant; a mutant that gets past every stage
survives, and is a hole.

Three things the harness has to get right, and does:

* **The clean tree must pass the gate**, checked before the loop and again after
  it, so a mutation that leaked out of the loop is reported rather than silently
  counted.
* **The restored file must look newer than the object built from the mutant**, or
  make skips it and the previous mutant stays in the binary for the rest of the
  run. This bit us: the first run reported every mutant killed by `isa`, because
  mutant #1 never left the assembler. `shutil.copyfile` + `os.utime`, not
  `copy2`.
* **The rebuild must actually contain the mutation**, verified per mutant against
  the build log. That check found a real defect in the build: **touching
  `include/opcode/i51.h` does not rebuild `gas`**, although `tc-i51.c` includes
  it. An incremental build leaves the assembler holding the old opcode table
  while the disassembler gets the new one. The harness forces `tc-i51.c` to
  rebuild, because a from-scratch `make -C tb build` has the fault in both
  halves, and that is the fault being measured.

---

## 2. What kills what

Stage order is the gate's order; a mutant is credited to the first stage that
notices it.

| stage | mutants it is first to kill |
|---|---:|
| isa | 21 |
| **roundtrip** (new) | **28** |
| branch | 2 |
| **bits** (new) | **21** |
| **reloc** (new) | **29** |
| sim | 0 |
| defaultlink | 2 |
| commons | 0 |
| check | 3 |

Before the new stages the same 44 kills read: isa 21, defaultlink 9, check 8,
sim 4, branch 2, commons 0. `sim`, `defaultlink` and `check` lose credit here
only because `bits` and `reloc` run earlier and catch the same faults first —
they are not redundant, they are late in the order. `commons` killed nothing in
either run.

---

## 3. The holes that were filled

Three new stages, wired into `tb/Makefile` and `.github/workflows/gate.yml`
next to the ones already there. `make -C tb gate` runs the whole list.

### `make -C tb roundtrip` — the disassembler against the assembler

`isa`'s `decode` step asked only whether `objdump` exited cleanly. The i51
disassembler never prints `(bad)`, so `decode: 280/280` was a printed constant:
**every mutation of `opcodes/i51-dis.c` survived the entire suite** — wrong
register, wrong operand order, wrong displacement sign, wrong instruction
length, all of it.

`roundtrip` disassembles the same golden bytes and feeds `objdump`'s output back
to `gas`, requiring the bytes to come back. It needs no new golden data: the
bytes are the ones c51asm produced. It also requires

* exactly one instruction decoded, spanning exactly the bytes given — so an
  instruction length taken from the opcode table cannot be wrong;
* the decode not to be `.byte`, which is what the disassembler prints for an
  opcode it does not recognise and which `gas` takes back happily, so the round
  trip would otherwise close over exactly the case that matters;
* the displacement a relative branch prints and the absolute target in its
  comment to agree — the displacement is the half the re-assembly throws away.

`tb/isa/zeroops.txt` adds 18 instructions whose operand byte, or displacement
byte, is `0x00`. No entry of `8051.txt` has one, and a disassembler that mistakes
a zero operand byte for a read error — `if (opdata < 0)` written as `<= 0` —
decodes all of them as nothing at all while every other gate stays green. Seven
mutants of that exact shape were surviving.

### `make -C tb bits` — bit addressing at its boundaries

The bit space is folded out of two disjoint byte ranges and the port holds four
copies of the rule: the `.3` suffix (`i51_fold_bit_suffix`), `B2B()` on a
constant (`fixup8`), `B2B()` on a symbol gas resolves itself (`md_apply_fix`),
and `R_I51_8_B2B` in the linker. The suite reached one of the four, at one
address.

50 cases (`tb/isa/bits.py`, runner `tb/sim/run-bits.py`) sitting on 0x20, 0x2F,
0x30, 0x80, 0xF8, on the SFR multiple-of-8 rule, on the first bit past the top of
the RAM window and on an address above the on-chip range, through all four paths,
plus the `.bit` directive's 0..1 range.

### `make -C tb reloc` — every relocation kind end to end

The instruction gate never links. `sim`, `defaultlink` and `commons` link, but
only what they happen to contain: `R_I51_H`, `R_I51_L` and `R_I51_13_PCODE` were
reached by nothing at all, and the linker's own copies of the ±128 branch limit
and the ACALL/AJMP 2K page rule by nothing at all — `branch.py` tests the
assembler's copies of those two rules, not BFD's.

36 checks in five steps (`tb/sim/run-reloc.py`):

* **emit** — one object carrying every relocation kind, against the exact list of
  (offset, type, symbol) it must hold;
* **resolve** — the same object linked, compared byte for byte;
* **range** — `R_I51_7_PCREL` and `R_I51_11` linked one unit inside and one unit
  outside their limit, on both sides;
* **fold** — the same relocations when gas resolves them itself, including
  `HIGH()`/`LOW()`, the 8- and 16-bit operand range checks, the refusal of a
  HIGH/LOW/B2B prefix on a branch target, and `.pcode`;
* **identity** — the same program linked straight, through `ld -r`, and out of an
  archive member: all three must produce the same image.

### Proof that the new tests can fail

Not asserted — measured. 62 mutants changed from `survived` to `killed`, each
named with the stage that killed it, in `tb/mutation/report.py` output. The
converse — that they pass on clean sources — is the baseline check the harness
runs before and after every batch. No new test is unfailable: every case in
`bits.py` and `run-reloc.py` that no mutant reaches is called out in section 5.

---

## 4. Surviving mutants

89 survive. They are not all holes. Grouped by site, with the reason nothing
sees them:

| group | n | what the fault would be | why nothing catches it | verdict |
|---|---:|---|---|---|
| HOWTO fields (`bfd-howto-*`, 25) | 25 | wrong size / bitsize / rightshift / dst_mask / pcrel / overflow complaint on one relocation | `i51_final_link_relocate` implements `R_I51_7_PCREL`, `_11`, `_8_B2B`, `_13_PCODE` and `_16` itself and never reads the howto; `_NONE`, `_R1`, `_R3` are never emitted by gas; and for the four kinds that do reach `_bfd_final_link_relocate` the ELF target is little-endian with `dst_mask 0x00ff`, so writing 1 byte or 2 puts the value in the same place | equivalent, except two named in §5 |
| B2B boundary arms (`bfd-*-394/398/401`, `gas-*-892/894/900/1641`) | 11 | the fold accepts or rejects one address more or less | at the exact value where each differs the port's behaviour is either byte-identical (0x100 folds to the same low byte) or is the quirk described in §6 — a test either way would pin a bug | equivalent / would pin a bug |
| `number_to_chars_bigendian (…, 1)` | 8 | byte order of a one-byte write | one byte has no byte order | equivalent |
| disassembler read-error guards (`dis-cond0-*`) | 8 | the check for a failed memory read is removed | `objdump` on a buffer never fails that read | equivalent |
| linker-script numbers | 7 | a space limit or a section origin off by one | five of them are the `ASSERT` limits — internal RAM, bit space, xdata, edata — and no test links a program that overflows any space; one is `.edata`'s origin and no test puts anything in `.edata`; one is comment text | **hole** (6) + inert (1) |
| `.pcode` relocation arms | 6 | wrong 13-bit underflow bound, wrong 13-bit mask, wrong flag mask | `reloc`'s `.pcode` cases use exec addresses 0x0FF / 0x123 / 0x2345 and no flag bits, which does not straddle 0x100, 0x1FFF or the 0xE000 flag field | **hole**, cheap to close (§5) |
| opcode-table mask/size (5) | 5 | a row matches one byte too many or claims the wrong length | the corpus is one instruction per buffer, so a length error runs off the end instead of desynchronising a stream, and a widened mask is absorbed by an earlier row winning the first-match scan | **hole**, needs a stream decode (§5) |
| comment text (`constpm1` on a number inside a comment) | 7 | nothing | nothing changed | inert |
| bad-reloc-type guards (`bfd-*-289/496`) | 3 | a corrupt object's reloc type is not rejected | no test feeds a corrupt object | hole, low value |
| disassembler cosmetics | 4 | the `; #65 #'A'` comment, the sign of a zero displacement, the ajmp page comment at a non-zero address | the round trip strips comments, `-0` and `+0` are the same number, and every corpus entry is disassembled at address 0 | cosmetic / **hole** for the page comment |
| the rest (`gas-relop-458`, `gas-constpm1-458`, `gas-guard0-838`, `gas-guard0-1624`, `gas-relop-1589`, `gas-guard0-1081`) | 5 | see §5 and §6 | | mixed |

Full per-mutant list: run `python3 tb/mutation/report.py --after <results.json>`.

---

## 5. Ranked: what to close next

Ranked by how bad the corresponding real bug would be, not by how easy the test
is. All six are small.

1. **The linker script's `ASSERT` limits are untested** (`ldsc-ldnum-206/207/210/211/212`).
   A wrong limit means a program that overruns internal RAM, the bit space or
   xdata links silently and fails on the chip. The test is one probe per space
   that is one byte too large, linked, and required to fail with that assert's
   message. This is the highest-value survivor group.
2. **`0x20.8` is not rejected** (`gas-relop-458`, `gas-constpm1-458`). The bit
   digit is checked against `'7'`; loosen it and `mov c,0x20.8` assembles as bit
   8, silently addressing the wrong byte. One case in `bits.py`.
3. **`.pcode` boundaries** (6 mutants). Add exec addresses 0x100, 0x1FFF and
   0x2000 to `PCODE_LINK` in `run-reloc.py`, and one `.pcode` with flag operands
   so the 0xE000 flag field is non-zero.
4. **Bit 7 of a relocated byte** (`bfd-howto-130`, `bfd-howto-175`). `dst_mask
   0x00ff → 0x007F` silently drops bit 7, and the probe's `BITSYM` is 0x7F and
   its `HIGH(0x1234)` is 0x12 — both with bit 7 clear. Change `BITSYM` to 0xD7
   and `XSYM` to 0xF234 in `run-reloc.py`.
5. **Decode a stream, not one instruction** (5 opcode-table mutants). Concatenate
   the golden encodings and disassemble the whole thing: a row that claims the
   wrong length then desynchronises everything after it, which a single-instruction
   buffer hides.
6. **`#HIGH()` on a constant out of range** (`gas-guard0-1624`).
   `mov a,#HIGH(0x12345)` — the existing case uses a symbol and so takes the
   `md_apply_fix` path instead.

Unkillable, and listed so nobody hunts them: `gas-relop-1589` (`check_range` is
never called with `I51_OP_JUMP_REL` — `fixup8` skips the constant path for it),
`gas-guard0-838` and `gas-constpm1-1634` (dead checks, see §6).

---

## 6. Bugs in the port that the mutants exposed

Defects in the port, not gaps in the tests. None is fixed here: this branch adds
tests, and a test that pins a quirk is worse than no test.

1. **`B2B()` does not apply the SFR alignment rule.** `i51_fold_bit_suffix`
   refuses `0x81.0` because 0x81 is not a multiple of 8. `B2B(0x81,0)` is
   accepted by all three other paths and assembles to `setb 0x81`, a bit that
   does not exist. The four copies of the rule do not agree.
2. **`B2B(0x2f,8)` is accepted** and yields bit 0x80 — the first SFR bit — where
   the RAM window's last bit is 0x7F. The bound is written `> 0x80` against the
   resulting bit address.
3. **An out-of-range `R_I51_8_B2B` is a warning, not an error.** The link
   succeeds with status 0 and a wrong byte in the image
   (`warning: internal error: out of range error`). Every other relocation
   overflow fails the link.
4. **A register-bank operand without `.using` aborts gas.** `mov a,AR0` with no
   `.using` in effect, and `.using 4`, both end in `Fatal error: Case value 63
   unexpected at line 1382 of file "symbols.c"`: `md_undefined_symbol` returns 0
   and leaves the expression unset instead of producing the intended
   `missing .using` diagnostic. The guard that would have produced it
   (`gas-guard0-1081`) is unreachable.
5. **`make` does not rebuild `gas` when the opcode table changes** (§1). An
   incremental build can ship an assembler and a disassembler that disagree about
   the ISA.
6. **Two dead checks in `md_apply_fix` / `fixup8`.** Any value that trips
   `value < -65536 || value > 65535` also trips the 8-bit check it falls through
   to; and `check_range` returns 1 unconditionally for `I51_OP_LOW_ADDR`, so the
   `LOW Operand out of 8-bit range` message can never be printed.

---

## 7. What this measurement does not cover

* One mutant per (line, operator): a line with two comparisons contributes only
  its first. Widening this raises the mutant count, not the honesty of the rate.
* `constpm1` and `ldnum` also hit numbers inside trailing comments; those seven
  mutants cannot be killed by anything and are listed as inert in §4.
* The population is capped and evenly sampled — a fixed, reproducible sample of
  the fault space, not the whole of it.
* A kill rate is not a percentage of bugs found. A surviving mutant is a hole, an
  equivalent mutant, or inert, and §4 says which for all 89.

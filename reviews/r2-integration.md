# Integration of the seven round-2 review branches

Branch `claude/integrate-round2`, cut from `origin/work/green` (5d02910).

Seven branches, all cut from the same base, merged one at a time, gate run after
each merge rather than at the end. Nothing was dropped. One behavioural conflict
between two branches had to be decided; everything else was textual.

## 1. Merge order and what happened

Order chosen to put the cheap merges first, the two `tb/isa_check.py` branches
adjacent so the dangerous one could be resolved with both versions in front of
me, and the two patch branches last so only one toolchain rebuild was needed
after them.

| # | branch | result |
|---|---|---|
| 1 | `claude/audit-provenance` (baceb8b) | fast-forward, report only |
| 2 | `claude/audit-green-honesty` (366b9e0) | clean |
| 3 | `claude/audit-isa-gate` (dd172cc) | clean |
| 4 | `claude/tests-mutation` (4566a0b) | **conflict** in `.gitignore`, `tb/isa_check.py` |
| 5 | `claude/rootcause-rom-delta` (fbd0ab9) | **conflict** in `tb/Makefile` |
| 6 | `claude/review-upstream` (e853c1b) | clean |
| 7 | `claude/review-newcode` (24fb1d4) | **conflict** in `mcs51/additions.patch`, twice |

Then two commits that are neither a merge nor a branch:

* `tb/isa/bits.py` — the one place two branches disagreed about *behaviour*
  rather than text. Found by running the gate after merge 7, not by reading.
* `mcs51/additions.patch` — three blob `index` lines refreshed, because the
  merge changed the content of the files they name.

## 2. The conflicts, and how each was resolved

### 2.1 `tb/isa_check.py` — the dangerous one

`claude/audit-isa-gate` replaced `decodes()`. The old one was a tautology:
`print_insn_i51` never prints `(bad)`, it prints `.byte 0xNN` with a `????`
comment, so `'(bad)' not in stdout` was a condition the disassembler could not
violate and `decode: 280/280` was a printed constant. The new one asserts
objdump succeeds, the payload comes back as **exactly one** instruction, that
instruction covers **exactly** those bytes, it is **named** rather than dumped as
data, and it **re-assembles** to the bytes it came from.

`claude/tests-mutation` had built a separate `roundtrip` stage on top of the
**old** `decodes()`: its own `disassemble()` parser, a `mismatch()` check that the
displacement a relative branch prints agrees with the absolute target in its
comment, `resyntax()` to turn the displacement back into something gas accepts,
and a re-assembly.

Git merged the *bodies* silently — both `decodes()` and `disassemble()` and the
whole roundtrip stage landed in one file — and conflicted only on the module
docstring. Taking that auto-merge would have left two overlapping checks: both
asserted one instruction, exact byte span, not `.byte`, and re-assembly, and
both counted every entry, so `make isa` and `make roundtrip` each disassembled
and re-assembled all 280 entries and the same failure would have been reported
twice.

Resolved by splitting the pass along the line the two names already imply:

* one parser, `Tools.disassemble()`, returning `(address, raw hex, text, comment)`
  per instruction. `INSN_LINE` is `audit-isa-gate`'s stricter regex.
* `Tools.decodes()` is the decode check and nothing else: one instruction,
  exact byte span, real mnemonic. It returns the parsed instruction, so the
  round trip does not have to disassemble again. The re-assembly moved out of
  it — re-assembly is what "roundtrip" means.
* the `roundtrip` stage takes that instruction, runs `mismatch()` (which
  `audit-isa-gate`'s version had thrown away with `.split(';')[0]`), then
  `resyntax()` and the re-assembly.
* stage selection moved from `--roundtrip` to `--stages`, default
  `assemble,decode`. `make isa` runs `assemble,decode`; `make roundtrip` runs
  `roundtrip`. Neither repeats the other's work.
* **no double counting**: an entry that fails `decode` is reported by `decode`
  and skipped by `roundtrip` when both stages run in the same invocation. When
  `roundtrip` runs alone — `tb/isa/zeroops.txt` is only ever reached that way —
  it decodes for itself and counts a decode failure once, as its own.

Everything both branches asserted survives. `audit-isa-gate`'s corpus checks
(`CorpusError`, Intel HEX record-type and checksum validation, no silently
dropped lines, empty table fails) are kept verbatim.

Proof the merged `decodes()` is still not a tautology:

```
a5    (None, 'not decoded to an instruction: .byte 0xA5')
0000  (None, 'decoded as 2 instructions, want 1: nop / nop')
0201  (None, 'nothing decoded')
```

### 2.2 `tb/Makefile` — two branches adding targets

`claude/tests-mutation` added `roundtrip bits reloc gate mutants` and introduced
`GATE`/`MUTGATE`; `claude/rootcause-rom-delta` added `oracle` and its own
`.PHONY` line. Only the `.PHONY` line and the `GATE` block conflicted; the target
bodies are in different parts of the file and merged clean.

Resolved to one `.PHONY` carrying every target of both, and the gate list split
three ways:

```make
TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons
GATE     := $(TOOLGATE) oracle
MUTGATE  := $(TOOLGATE) check
```

`GATE` is what `make -C tb gate` runs and matches `.github/workflows/gate.yml`
step for step, in the same order. `MUTGATE` is what a mutant has to survive; it
takes `check` rather than `oracle` because the two build the same ten projects
with the same tools and `oracle` does not fail a project that will not build, so
it can only be the weaker of the pair.

### 2.3 `.github/workflows/gate.yml`

Auto-merged. Verified by hand that every stage of both branches is present
exactly once: `isa, roundtrip, branch, bits, reloc, sim, defaultlink, commons,
oracle`.

### 2.4 `.gitignore`

Both branches added `__pycache__/`; kept `claude/tests-mutation`'s commented
form.

### 2.5 `mcs51/additions.patch` — two conflicts

**Hunk header for `bfd/elf32-i51.c`.** `review-upstream` cut 21 lines (the dead
body of `elf32_i51_check_relocs`), `review-newcode` added 43
(`elf32_i51_link_output_symbol_hook` plus its `elf_backend_` define).
961 − 21 + 43 = **983**. Verified mechanically for every hunk in the file:

```
OK  b/bfd/cpu-i51.c              header=42     actual=42
OK  b/bfd/elf32-i51.c            header=983    actual=983
OK  b/gas/config/tc-i51.c        header=2644   actual=2644
OK  b/gas/config/tc-i51.h        header=161    actual=161
OK  b/include/elf/i51.h          header=70     actual=70
OK  b/include/opcode/i51.h       header=153    actual=153
OK  b/ld/emulparams/elf32i51.sh  header=9      actual=9
OK  b/ld/scripttempl/elf32i51.sc header=249    actual=249
OK  b/opcodes/i51-dis.c          header=319    actual=319
```

**`fixup8`'s `I51_OP_B2B` range test.** `review-upstream` renamed the parameter
`oper` → `ex`; `review-newcode` changed the bounds in the same four lines
(`> 0x80` → `>= 0x80`, `> 0x100` → `> 0xFF`). Kept both: the new bounds written
against `ex`.

Both sets survive in full. From `review-upstream`: `EM_8051` /
`EM_I51_OLD` / `ELF_MACHINE_ALT1` / `i51_elf32_vec`, the `ATTRIBUTE_UNUSED`
and dead-variable warning fixes across the whole file. From `review-newcode`:
the B2B bounds in `md_apply_fix` *and* `fixup8` *and*
`elf32_i51_relocate_section`, the SFR multiple-of-8 rule
(`value <= 0xF8 && (value & 7) == 0`), `bfd_reloc_ok` → `bfd_reloc_outofrange`
past the SFR space, `elf32_i51_link_output_symbol_hook`, and the
`ADDR() + SIZEOF()` section chaining in `ld/scripttempl/elf32i51.sc`.

`git diff claude/review-upstream HEAD -- mcs51/additions.patch` is exactly
`review-newcode`'s delta, nothing more and nothing less.
`mcs51/modifications.patch` is byte-identical to `review-upstream`'s; no other
branch touched it.

Independent confirmation: `make -C tb refresh` regenerates the patches from the
tree `make build` patched. The regenerated `additions.patch` differed from the
committed one only in three blob `index` hashes — stale because the merge
changed the content of the three files they name — and `modifications.patch`
was byte-identical. The three hashes were then adopted from the refresh, so the
committed patches are now byte-identical to what `make refresh` produces. GNU
patch ignores `index` lines, so this changes nothing about applying.

### 2.6 `tb/isa/bits.py` — the one behavioural disagreement

Not a text conflict. It surfaced when the gate was run after merge 7:

```
== bits: 50 cases
   checked:  49/50
     link-offchip  setb B2B(BDVAR,1) BDVAR=0x100  linked, but complained:
                   (.text+0x1): warning: internal error: out of range error
```

`claude/tests-mutation` pinned the old behaviour:

```python
# Above the on-chip byte range the linker leaves the byte alone rather
# than folding it ... Pinned because it is the one arm with no diagnostic at all.
lcase('link-offchip', 0x100, 1, 0x01),
```

`claude/review-newcode` changed exactly that return, `bfd_reloc_ok` →
`bfd_reloc_outofrange`, on the grounds that a byte address past the SFR space is
not a byte address at all.

The fix wins. `bits.py`'s own header says "anything else — not bit addressable,
and must be refused", so the case was pinning the behaviour the other branch
fixed, and the new diagnostic is the same `out of range` that `link-below-ram`,
`link-above-ram` and `link-gap` already expect. Case updated to
`lcase('link-offchip', 0x100, 1, None, 'out of range')` with the history in the
comment. This is the only test expectation changed anywhere in the integration.

## 3. Which merge broke what

Only one merge broke anything: **merge 7, `claude/review-newcode`**, and only
`tb/bits` (`link-offchip`), for the reason in §2.6. Every other stage was green
after every merge.

Merges 1–5 were verified against a toolchain built from `origin/work/green`'s
patches (`isa`, `roundtrip`, `bits`, `reloc`, `oracle` all green as each landed).
Merges 6–7 change the toolchain, so the tree was rebuilt and the full gate rerun.

## 4. Acceptance

### 4.1 Patches apply to a pristine 2.47 at fuzz 0, offset 0 — PASS

Fresh extract of `binutils-2.47.tar.xz`
(sha256 `154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff`,
matching `PORT_SHA256`), then:

```
$ patch --fuzz 0 --no-backup-if-mismatch -p1 < mcs51/additions.patch      # rc 0
$ patch --fuzz 0 --no-backup-if-mismatch -p1 < mcs51/modifications.patch  # rc 0
$ grep -civ '^patching file ' apply.log
0
```

Every line of output is a `patching file` line: no `Hunk #N succeeded ... (offset
N lines)`, no fuzz (impossible at `--fuzz 0`), no rejects, both patches rc 0.
41 files.

### 4.2 Stock `./configure --target=i51-elf && make` — PASS

No `--disable-werror`, no `--disable-gdb`, no `CFLAGS`, out-of-tree:

```
$ ../binutils-2.47/configure --target=i51-elf     # rc 0
$ make -j4 MAKEINFO=true                          # rc 0
```

`-Werror` was in force — `gas/Makefile` line 462:

```
WARN_CFLAGS = -W -Wall -Wstrict-prototypes -Wmissing-prototypes -Wshadow \
              -Wstack-usage=262144 -Werror -Wwrite-strings
```

Zero compiler warnings in the whole build; the four `warning:` lines in the log
are all libtool's (`-version-info is ignored for convenience libraries`,
`multiple -rpath's`). `gas/as-new`, `ld/ld-new`, `binutils/objdump` all built.

### 4.3 `make -C tb build` then the full gate — PASS

`make -C tb build` rc 0. `make -C tb gate` rc 0:

```
gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons oracle)
```

Stage by stage, plus the two run outside `make gate`:

| stage | what it does | result |
|---|---|---|
| `check` | ten projects, ROMs against the reference base.7z ships | 10/10 PASS |
| `isa` — table `assemble` | 8051.txt + extra.txt against c51asm's golden bytes | 280/280, 3/3 |
| `isa` — table `decode` | one instruction, exact byte span, real mnemonic | 280/280, 3/3 |
| `isa` — `program` | testall.asm assembles | 3350 bytes of text |
| `branch` | literal branch encodings vs hand-derived bytes | 24/24 |
| `bits` | bit-address fold at its boundaries, gas and ld | 50/50 |
| `reloc` | every relocation kind end to end, `-r`, archives | 36/36 |
| `roundtrip` | 8051.txt, extra.txt, zeroops.txt back through gas | 280/280, 3/3, 18/18 |
| `commons` | one external common per memory space keeps its space | PASS |
| `defaultlink` | ld's built-in script lays out every space | PASS |
| `oracle` | ten ROMs against the 2001 `www8051.hex` | 10/10 explained |
| `frozen` | the 2001 toolchain against `tb/frozen.expect` | 10/10 PASS |
| `sim` | testall executed in ucsim, verdict from P1 | P1=127 PASS |

`sim`: `PASS: testall ran to completion, all instruction tests passed (P1=127)`.

`oracle`: `all 10 projects agree with the 2001 oracle: recorded size delta, every
differing byte accounted for` — `diag` `+3 bytes, explained`, `serial` `-1519
bytes, explained`, the other eight byte-exact in length with every differing byte
attributed to a recorded 2001 relocation defect.

`frozen` is the one stage with no `make` target of its own; it is what
`.github/workflows/frozen.yml` runs. Reproduced by hand:

```
$ make -C tb frozen        # rc 0, builds 2.11.2 + the 2001 patches, gcc -m32
$ make -C tb check-frozen  # rc 2 - the recorded outcome, see tb/frozen.expect
$ python3 tb/romdiff.py --reference work/refrom --produced work/tb \
      --projects "$PROJECTS" --expect tb/frozen.expect      # rc 0
PASS diag     not-produced 0
PASS ds1620   differ 217
PASS ds1822   differ 225
PASS lcd      differ 214
PASS led1     differ 213
PASS led2     differ 214
PASS led3     differ 214
PASS serial   differ 325
PASS welcome  differ 213
PASS wjava    differ 213

all 10 projects match the recorded frozen outcome.
```

Both halves the workflow gates on are as recorded: the testbench step ends
`failure`, and the comparison ends `success`.

### 4.4 `make -C tb mutants` — PASS, 55.9 % (109/195)

```
baseline: isa roundtrip branch bits reloc sim defaultlink commons check all pass
195 mutants -> work/mutants/mutants.json
...
== 195 mutants in 5860s
   killed    109
   survived  86
   no-build  0 (excluded: the fault cannot exist in that form)
   KILL RATE 55.9% (109/195)
```

**55.9 % (109/195), against the 54.4 % (106/195) `claude/tests-mutation`
measured alone. Nothing was lost in the merge; three more mutants die.**

The comparison is like for like: `gen.py` produced the same **195** mutants —
its per-`(file, operator)` cap and even sampling keep the population stable even
though the merge changed line counts in three of the five mutated files — and
`MUTGATE` is the same nine stages `tests-mutation` used
(`isa,roundtrip,branch,bits,reloc,sim,defaultlink,commons,check`). `no-build` is
0 both times, so the denominator is the same 195.

Which stage did the killing:

| stage | mutants killed |
|---|---:|
| `bits` | 28 |
| `isa` | 28 |
| `reloc` | 28 |
| `roundtrip` | 18 |
| `check` | 3 |
| `branch` | 2 |
| `defaultlink` | 2 |
| `sim`, `commons` | 0 |

`roundtrip` kills 18 on the merged tree, so the restructuring in §2.1 did not
weaken it: splitting the re-assembly out of `decodes()` and into the `roundtrip`
stage left the check that catches those 18 exactly where it was. `decode` (part
of `isa`) still kills its share — the stage is no longer the tautology it was on
`origin/work/green`.

The three extra kills are a consequence of the merge, not of anything new: they
are mutants that widen a bound the `claude/review-newcode` fixes tightened, so
the merged tree now has an observable difference where the pre-merge tree did
not, and `bits`/`reloc` see it. That is an inference from the operator/stage mix,
not a proof — `claude/tests-mutation` did not commit its `results.json`, so the
two runs cannot be diffed mutant by mutant. What is certain is the direction and
the size: 109 ≥ 106 on the same 195 with the same 9 stages.

The run finished cleanly: `run.py` restores the tree and re-runs the gate at the
end to prove nothing leaked out of the loop, and it printed no
`WARNING: the clean tree now fails ...`.

`make -C tb check-canary` also still passes — `CANARY PASS: check exited nonzero,
10 project(s) reported FAIL` — so the harness still goes red when it should.

A first attempt at this run was interrupted by the environment at 108/195.
`run.py` caught the signal and restored the sources, but the numbers above are
not from it: the tree was rebuilt from scratch with `make -C tb build` and the
whole 195 rerun end to end. `make -C tb gate` and `make -C tb check` were rerun
on that rebuilt tree too — `gate: PASS (isa roundtrip branch bits reloc sim
defaultlink commons oracle)`, `all 10 projects match the reference`, and the ten
ROM hashes are byte-identical to the ones in §4.5, which came from the first
build.

### 4.5 The ten reference ROMs — PASS, unchanged

```
PASS diag     1264 c3ba924a3c3b39f0818f0d6114e3c126
PASS ds1620   6281 87082cbd4c11b70f99b8144ce3986648
PASS ds1822   6075 e8ff5320cff95371eec5ea48b7a72662
PASS lcd      5720 52fc462c9ab1b3f8711a730456967d02
PASS led1     5170 61bb6a21acddeff991c8a1ab2fe0a9e5
PASS led2     5007 15b65478e586d7a77bd38407d2696436
PASS led3     5197 e94a53c5587266e22fc8701c9caf03d9
PASS serial   8125 63c123d76b07bd145af0112db96c883c
PASS welcome  4809 a2052d0f39802e5ccb9ccb49900446bc
PASS wjava    4809 eb2f09a9cab0b35740172a240bf1a9c0
all 10 projects match the reference
```

Not one ROM moved. Every merged fix is either off the path these ten projects
take (`link_output_symbol_hook` fires on `ld -r`, which none of them use; the
tightened B2B bounds only reject inputs none of them contain) or a no-op for
them (the `ADDR()+SIZEOF()` chaining makes explicit the layout the previous
script already produced for these inputs).

## 5. Dropped

Nothing. Every file from every branch is on this branch:

* `git diff <branch> HEAD -- <that branch's files>` is empty for
  `audit-provenance`, `audit-green-honesty`, `audit-isa-gate` (except
  `isa_check.py`), `tests-mutation` (except `isa_check.py`, `bits.py`,
  `Makefile`, `gate.yml`, `.gitignore`), `rootcause-rom-delta` (except
  `Makefile`, `gate.yml`), `review-upstream` (except `additions.patch`),
  `review-newcode` (except `additions.patch`).
* every difference in that list is accounted for in §2.

Three things changed shape rather than being dropped:

1. `isa_check.py`'s `--roundtrip` flag is now `--stages roundtrip`. The
   `make roundtrip` target was updated with it; no other caller exists.
2. The re-assembly `audit-isa-gate` put inside `decodes()` now lives in the
   `roundtrip` stage. It is still run, once, over the same corpus.
3. `bits.py`'s `link-offchip` expectation was inverted — §2.6.

## 6. Found while integrating, not fixed

Integration branch; these are reported, not touched.

1. **An out-of-range `R_I51_8_B2B` does not fail the link.**
   `bfd_reloc_outofrange` comes out as `(.text+0x1): warning: internal error: out
   of range error` and `ld` still exits 0 with the byte left as it was. That is
   what `link-offchip` ran into. `tb/sim/run-bits.py`'s failure arm only checks
   that the message appears in the log, never the exit status, so all four
   refusal cases (`link-below-ram`, `link-above-ram`, `link-gap`,
   `link-offchip`) would pass just as well if `ld` never failed on any of them.
   Worth deciding whether an out-of-range bit relocation should be an error, and
   if so, tightening the test to require a nonzero exit.

2. **`elf32_i51_link_output_symbol_hook` is not mutated.**
   `tb/mutation/gen.py` scopes `bfd` to a fixed list of function names, and the
   hook `claude/review-newcode` added is not on it. The new code is exercised by
   `make -C tb commons` but no mutant is cut into it, so the kill rate says
   nothing about how well it is tested.

3. **`elf32_i51_object_p` is a no-op.** Its comment says "Set the right machine
   number"; the body is `return 1;`. `claude/review-upstream` marked the argument
   `ATTRIBUTE_UNUSED` rather than deleting the hook, which is the warning-clean
   thing to do but leaves the comment lying. Pre-existing, in the 2001 lineage.

4. **`make gate` has no `check` and no `frozen`.** `GATE` is the nine stages
   `gate.yml` runs. `check` is `build.yml`'s and `frozen` is `frozen.yml`'s, so
   `make -C tb gate` on its own is not the whole repository gate. Both were run
   here by hand. If `make gate` is meant to be the single entry point, they
   belong in it.

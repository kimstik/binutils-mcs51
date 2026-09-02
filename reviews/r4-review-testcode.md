# REVIEW-testcode.md — the testbench read as code

Axis: `tb/` reviewed as software, not as a gate. Four rounds asked whether the gate
catches bugs in the port. This one asks whether the checkers are correct. A checker
with a bug is worse than no checker, because it certifies.

Base: `0f45319` (`origin/work/green`). Everything below was run against a real
`make -C tb build` of binutils 2.47 + `mcs51/*.patch` on this host. Every claim
carries the command and its output.

Bottom line: **no checker on the merge gate's critical path is dead.** The nine
`TOOLGATE` stages all do real work and all go red when sabotaged — I proved that for
`script`, `isa`, `oracle` and `check`. What is broken is narrower and specific:

1. `hexoracle.py` prints a verdict for ten projects and checks two of them on ROM
   *length alone*. Zeroing both ROMs end to end still exits 0. **Proven.**
2. `isa_check.py` prints `PASS` and exits 0 with `--stages ''`, or with no `--table`
   and no `--program`, against a toolchain of `exit 1` stubs. **Proven.**
3. `tb/mutation/run.py`'s stage list has already drifted from `tb/Makefile`'s
   `MUTGATE`, in the file whose Makefile comment says it cannot.
4. Two of `run-bits.py`'s 50 "checked" cases compare `b''` against `b''`. **Proven.**

---

## F1 — `oracle` certifies two of ten projects on length alone, then says otherwise

**Severity: high.** Critical path (`gate.yml` step "2001 .hex oracle", `$(GATE)`).
This is the repo's own historical failure mode — "an oracle computing seven metrics
and gating on two" — reproduced in the file rewritten to fix it.

`tb/hexoracle.py:237`

```python
        elif want_counts is None:
            verdict = "explained %+d" % delta
            notes.append(...)
```

`diag` and `serial` carry `want_counts = None` (`EXPECT`, lines 105 and 117). For
those two, `classify()` is never called, `counts` stays all zero, and the *only*
assertion is `delta == want_delta` — a length comparison. Then line 275 prints, for
all ten:

> `all 10 projects agree with the 2001 oracle: recorded size delta, and every one of
> addr16/acall11/word16/pcode13/zero8/residual at its recorded count`

Which is false for 20% of the corpus.

### Proof

`make -C tb check` confirms the produced ROMs are byte-identical to the ones
`base.7z` ships, so `base.7z`'s ROMs are exactly what `make oracle` feeds the
checker. Baseline first:

```
$ python3 tb/hexoracle.py --tree $S/otree --oracle $S/ohex
diag       1264   1267      3       0       0       0       0       0         0  explained +3
...
serial     9647   8128  -1519       0       0       0       0       0         0  explained -1519
all 10 projects agree with the 2001 oracle: ...
exit=0
```

Now replace every byte of `diag`'s and `serial`'s ROM with `0x00`, keeping the length:

```
$ python3 corrupt.py
diag: 1267 bytes replaced with 0x00
serial: 8128 bytes replaced with 0x00

$ python3 tb/hexoracle.py --tree $S/otree --oracle $S/ohex ; echo exit=$?
diag       1264   1267      3       0       0       0       0       0         0  explained +3
serial     9647   8128  -1519       0       0       0       0       0         0  explained -1519
all 10 projects agree with the 2001 oracle: recorded size delta, and every one of
addr16/acall11/word16/pcode13/zero8/residual at its recorded count
exit=0
```

Two ROMs, 9395 bytes, entirely destroyed. Green.

The other eight are sound — the six buckets really are all gated. One bit:

```
$ python3 corrupt2.py            # led1: flipped bit 0 of byte 0x400
$ python3 tb/hexoracle.py --tree $S/otree --oracle $S/ohex ; echo exit=$?
led1       5173   5173      0     279       1     132      25     398        27  word16 -1
FAIL led1: word16 132 (recorded 133), residual 27 (recorded 25)
1 of 10 projects deviate from the 2001 oracle
exit=1
```

**Mitigation, not a fix:** `make check` md5s all ten ROMs against `tb/reference.md5`,
so today diag and serial are pinned elsewhere. But `gate.yml` runs both stages with
`if: always()`, and the `oracle` line is the one that claims byte-level agreement.

**Where the fix goes:** `tb/hexoracle.py`. Either (a) classify diag and serial over
their common prefix — diag's delta is +3 bytes appended, serial's is a block of HTML,
both have a long identical region that `classify()` could walk with an offset — and
record those counts in `EXPECT`; or (b) at minimum, make the closing sentence say
what was actually checked, e.g. `all 10 projects agree (8 byte-classified, 2 by
recorded size only: diag serial)`. (b) is a three-line change and removes the false
certification immediately.

---

## F2 — `isa_check.py` prints PASS and exits 0 with nothing selected

**Severity: high (latent).** The direct sibling of the `--table /dev/null` bug this
repo already fixed. That fix landed on the empty-*table* path (`run_table`, line 241)
and missed the empty-*stage* and no-*input* paths.

`tb/isa_check.py:322`

```python
    stages = [s for s in args.stages.split(',') if s]
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        sys.exit('unknown stage(s): %s' % ','.join(unknown))
```

`''.split(',')` filtered by `if s` is `[]`. `unknown` is then also `[]`, so the guard
passes vacuously. `--table` and `--program` are both optional (`:331`, `:334`), so
omitting both runs nothing at all. Line 348 prints `PASS`, `main` returns 0.

### Proof

A "toolchain" that is five shell scripts containing `exit 1`:

```
$ for f in gas/as-new binutils/objcopy binutils/objdump ... ; do
      printf '#!/bin/sh\nexit 1\n' > $S/fake/$f; chmod +x $S/fake/$f; done

$ python3 tb/isa_check.py --build $S/fake ; echo exit=$?
PASS
exit=0

$ python3 tb/isa_check.py --build $S/fake --table tb/isa/8051.txt --stages '' ; echo exit=$?
== table: 280 instructions
PASS
exit=0
```

The second is the nastier one: it prints the corpus size — the same `280` the real run
prints — from `len(entries)` at line 239, and then runs zero checks. That reads
exactly like a passing run.

For contrast, the path that *was* fixed still holds:

```
$ python3 tb/isa_check.py --build $S/fake --table /dev/null ; echo exit=$?
== table: 0 instructions
   FAILED: no instructions in /dev/null
FAIL: 1
exit=1
```

`make isa` and `make roundtrip` pass explicit arguments, so the gate is not affected
today. The exposure is a future edit to the Makefile or a hand-run.

**Where the fix goes:** `tb/isa_check.py`, after line 323 — `if not stages:
sys.exit('no stages selected')` — and after `args = ap.parse_args()` — `if not
args.table and not args.program: sys.exit('nothing to check')`.

---

## F3 — the mutation harness's stage list has already drifted from the Makefile's

**Severity: high for the *number*, none for `make mutants`.** The mutation kill rate
is the figure used to argue the suite is strong. It is measured against a list that
no longer matches the gate.

`tb/Makefile:72-74` states the intent:

> `# The merge gate, in one list, so the workflow and the mutation harness cannot`
> `# drift apart from it.`

But there are **three** copies of that list, not one:

```
$ grep -n "^MUTGATE\|^TOOLGATE\|^GATE" tb/Makefile
88:TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons script
89:GATE     := $(TOOLGATE) check oracle
90:MUTGATE  := $(TOOLGATE) check

$ grep -n "^STAGES" tb/mutation/run.py
33:STAGES = ['isa', 'branch', 'sim', 'defaultlink', 'commons', 'check']
```

`run.py`'s default is missing `roundtrip`, `bits`, `reloc` and `script` — 4 of the 10
stages, including `script`, the one written to catch `*(reset_network)`, and `reloc`,
the only end-to-end relocation coverage. Its own docstring (`run.py:9-13`) says

> `The stages are the existing testbench targets, run through tb/Makefile, so
> whatever 'make -C tb <stage>' means today is what a mutant has to survive.`

and its usage line shows an invocation with no `--stages`. Anyone who follows the
docstring measures a kill rate against 60% of the gate and reports it as the gate's.

`make mutants` itself is fine — the Makefile overrides the default:

```
$ make -C tb -n mutants | grep -o -- '--stages [^ ]*'
--stages isa,roundtrip,branch,bits,reloc,sim,defaultlink,commons,script,check
```

The third copy is `.github/workflows/gate.yml:34-91`, which enumerates the `$(GATE)`
stages as separate steps instead of running `make -C tb gate`. It agrees with
`$(GATE)` today. Nothing checks that it still will.

**Where the fix goes:** delete `run.py:33`'s literal and make `--stages` required (or
read `MUTGATE` out of the Makefile with `make -C tb -s print-MUTGATE`). Separately,
either make `gate.yml` call `make -C tb gate`, or add a Makefile target that diffs
the workflow's step list against `$(GATE)`.

---

## F4 — two of `run-bits.py`'s counted cases are `b'' == b''`

**Severity: medium.** Proven assertions that cannot fail.

`tb/isa/bits.py:113-114`

```python
DIR_CASES = [
    dcase('bit-0',    '.bitdata\nBIT0:\t.bit 0', ''),
    dcase('bit-1',    '.bitdata\nBIT1:\t.bit 1', ''),
```

`run-bits.py:85-89` assembles the case, takes `objcopy --only-section=.text`, and
compares it with `bytes.fromhex('')`. The source's first directive is `.bitdata`, so
`.text` is empty by construction. What `.bit 0` actually reserved is never read.

### Proof

```
$ python3 bitprobe.py
bit-0   src='.bitdata\nBIT0:\t.bit 0'  want=''  .text=b''  .bit(where the byte went)=b''
bit-1   src='.bitdata\nBIT1:\t.bit 1'  want=''  .text=b''  .bit(where the byte went)=b''
```

Both sides of the comparison are `b''` regardless of what the assembler did. The only
thing these two cases assert is that `as-new` exits 0. They are counted in
`checked: 50/50`.

The two negative cases beside them (`bit-2`, `bit-neg`) are real — they require the
assembler to reject and to say `not in range 0..1`.

**Where the fix goes:** `tb/isa/bits.py`. Give `bit-0`/`bit-1` a companion assertion
in the space they actually write — check the `.bit`/`.bitdata` section's size and the
symbol's bit address, the way `LINK_CASES` already does — or drop the `want=''`
comparison and mark them explicitly as "assembles" cases so they stop inflating the
count.

---

## F5 — `run-reloc.py`'s "checked: N/M" is not a count of passes

**Severity: low (display).** `tb/sim/run-reloc.py:375`

```python
    print('   checked:  %d/%d' % (checks - len(bad), checks))
```

`checks` counts checks; `bad` counts *failure messages*. The `emit` step increments
`checks` by 1 and can append up to 11 messages (one per relocation, lines 249-254).
With enough mismatches the numerator goes negative.

### Proof — one wrong check, eleven subtracted

```
$ python3 relocprobe.py       # WANT_RELOCS types all replaced with R_I51_WRONG
== reloc: 36 checks
   checked:  25/36
FAIL: 11
exit=1
```

35 of 36 checks passed; the line says 25. Same shape in `run-branch.py:68`
(`len(CASES) - len(bad)`) and `run-bits.py:118` (`total - len(bad)`), though there
those two happen to stay 1:1 today. Exit status is correct in all three.

**Where the fix goes:** count successes, not `checks - len(bad)`. In `run-reloc.py`,
increment a `passed` counter in each non-failing branch.

---

## F6 — `mutation/gen.py` silently drops mutants and generates un-killable ones

**Severity: medium.** Both defects distort the kill rate, in opposite directions.

### 6a. id collision drops mutants

`gen.py:390` builds `'%s-%s-%d' % (key, name, line + 1)` — file, operator, line. But
`op_constpm1` and `op_relop` yield one mutant *per token on a line*, so two mutants on
one line share an id. `gen.py:400-405` then keeps the first and discards the rest,
with no message. `spread()` runs *before* the dedup, so the cap is spent on
duplicates.

```
$ python3 dedup.py                    # cap=12, sources reconstructed from additions.patch
mutants selected by spread(): 202
silently dropped by the id dedup: 4
   bfd/constpm1     1
   bfd/relop        2
   dis/relop        1

   dropped id=bfd-relop-354  note=< -> <=  if (srel > ((1 << 7) - 1) || (srel < - (1 << 7)))
   dropped id=bfd-relop-391  note=>= -> >  if ((srel < 0x30) && (((srel - 0x20) * 8 + x) >= 0x80)) ...
```

The first dropped one matters: that line is the `R_I51_7_PCREL` range check, and only
one of its two bounds is ever mutated. An off-by-one on the *other* bound — exactly
the fault class `relop` exists to model — is never generated.

### 6b. comment-only mutants can never be killed

`op_constpm1` and `op_ldnum` skip a line whose *own* first token is `/*`, `*`, `//` or
`#`. `op_relop` and `op_endian` have no comment guard at all, and none of them notice
a continuation line inside a multi-line comment.

```
$ python3 comments.py
mutants that only edit a comment: 7 of 198
   bfd-relop-409     relop     bfd/elf32-i51.c:409   /* Use lower 13 bits for addresses > 0x1FFF */
   bfd-endian-335    endian    bfd/elf32-i51.c:335   ... bfd_getb16 () past the ...
   bfd-endian-337    endian    bfd/elf32-i51.c:337   bfd_putb16 () past it for the rest.  */
   dis-relop-139     relop     opcodes/i51-dis.c:139
   dis-constpm1-139  constpm1  opcodes/i51-dis.c:139
   dis-constpm1-292  constpm1  opcodes/i51-dis.c:292
   ldsc-ldnum-116    ldnum     ld/scripttempl/elf32i51.sc:116
```

7 of 198 (3.5%) are semantic no-ops. Each rebuilds the whole toolchain, runs the whole
gate, survives by construction, and lands in the survivor list — where a reader is
meant to look for real holes. The reported kill rate is understated by ~3.5 points and
the survivor table is padded with noise.

**Where the fix goes:** `tb/mutation/gen.py`. Make the id include the match position
(`'%s-%s-%d-%d' % (key, name, line + 1, col)`), move the dedup before `spread()`, and
give every operator a shared "is this line inside a comment" filter rather than four
different half-guards.

---

## F7 — `mutation/run.py` discards the rebuild status and returns 0 after declaring
its own results suspect

`tb/mutation/run.py:192-196`

```python
    h.restore()
    rc, _ = h.rebuild()          # leave the tree as it was found
    killer, _, _ = h.gate()      # ... and prove nothing leaked out of the loop
    if killer:
        print('WARNING: the clean tree now fails %s - results are suspect' % killer)
```

`rc` is assigned and never read. If the restore-rebuild fails, `h.gate()` runs against
whatever binary the last mutant left, and the "nothing leaked" proof is worthless. And
when the proof *does* fail, the script prints a warning and falls through to `return 0`
at line 226 — a FAIL printed, exit 0. Documented as "Exit: 0 the run completed", but a
run whose own consistency check failed did not complete usefully.

**Where the fix goes:** `run.py:193` — check `rc` and exit 3; `run.py:196` — set an
exit code so the leak is a failure.

---

## F8 — `make libk80` masks a failing converter

`tb/Makefile:502-505`

```make
	@cd $(WORK)/tb/lib && for f in $(LIBK80_OBJS); do \
		python3 $(HERE)/i51elf_sym_uc.py $$f.obj $$f.upper.obj > /dev/null; \
		mv $$f.upper.obj $$f.obj; \
	done
```

No `||` between the two. A converter that exits nonzero after writing a partial
`.upper.obj` is followed by an `mv` that succeeds, the loop continues, and the loop's
status is the last `mv`. 27 objects go through this. Off the gate path (maintenance
only), so severity low — but it is the "shell stage whose last command masks an earlier
failure" pattern verbatim.

**Where the fix goes:** `tb/Makefile:502` — `python3 ... && mv ... || exit 1`.

---

## F9 — `zeroops.txt`'s golden bytes are never confronted with the assembler

`tb/Makefile:362-379`. `isa` runs `8051.txt` and `extra.txt` through
`assemble,decode`. `roundtrip` runs all three through `roundtrip` only. So
`tb/isa/zeroops.txt` — 18 entries, and unlike the other two tables **hand-derived**
(its own header: "the golden column is hand-derived, from the MCS-51 manual") — is
only ever checked by gas-vs-objdump round trip. Those two share
`include/opcode/i51.h`, which `isa_check.py`'s own docstring says means the round trip
"says nothing about the opcode bytes themselves".

The whole reason the corpus is an oracle — an independent assembler produced the
golden column — does not apply to `zeroops.txt`, and the one stage that would
cross-check it against the port's assembler is never run on it. It would pass today:

```
$ python3 tb/isa_check.py --build work/modern/build --table tb/isa/zeroops.txt --stages assemble,decode
== table: 18 instructions
   assemble: 18/18
   decode:   18/18
PASS
```

Free coverage, currently on the floor.

**Where the fix goes:** `tb/Makefile:367` — add
`isa_check.py --build $(BUILD) --table $(HERE)/isa/zeroops.txt` to the `isa` target.

Related, non-blocking: `decode` and `roundtrip` never read the table's *source* column.
Corrupting a golden operand byte is reported by `assemble` alone:

```
$ python3 tb/isa_check.py --build work/modern/build --table $S/8051-bad.txt \
      --stages assemble,decode,roundtrip
== table: 280 instructions
   assemble: 279/280
     line 1    main: cjne a,#5,main         want b404fd       got b405fd
   decode:   280/280
   roundtrip: 280/280
FAIL: 1
```

That is correct behaviour (`b4 04 fd` really is a valid instruction that round-trips),
and the docstring is honest about it — but it means dropping `assemble` from a table's
stage list removes the *only* cross-toolchain check on that table. Which is exactly
what F9 describes.

---

## F10 — vacuous-pass edges in the report scripts

Not on the critical path (both callers pass real arguments), listed for completeness.

```
$ python3 tb/hexoracle.py --tree /nonexistent --oracle /nonexistent --projects '' ; echo exit=$?
all 0 projects agree with the 2001 oracle: ...
exit=0

$ python3 tb/romdiff.py --reference /nonexistent --produced /nonexistent \
      --projects '' --expect /dev/null ; echo exit=$?
exit=0

$ python3 tb/romdiff.py --reference /nonexistent --produced /nonexistent \
      --projects 'diag led1' ; echo exit=$?      # no --expect: report mode, always 0
exit=0
```

`romdiff.py`'s `--expect` gate is otherwise solid: an empty expectation file against a
non-empty project list fails every project (`gate()`, `want is None` branch), and the
`len(line) < 4` guard at line 143 does reject a pre-size-column file. The failure is
only when *both* sides are empty.

**Where the fix goes:** `hexoracle.py:206` and `romdiff.py:46` — refuse an empty
project list.

---

## What is genuinely sound — verified, not assumed

I sabotaged the four stages that matter most and all four went red.

**`run-script.py` catches the bug it was written for.** Throwaway copy of `base.7z`
with `*(reset_network)` commented out again:

```
$ sh sabotage-script.sh
82:    *(reset_network)
82:    /* *(reset_network) */
== script arms: 146 covered, 319 checks, 38 unreachable
FAIL www51 .text image: 01020304050608090a0b0c0d0e0f1011121314151617,
                expected 0102030405060708090a0b0c0d0e0f1011121314151617
FAIL www51: _ETEXT/_etext: 0x16, expected 0x17
FAIL www51: unexpected output sections ['reset_network'] - an arm that no longer
     collects its input leaves the input as an orphan section
run-script: FAIL (3 of 319 checks)
EXIT=1
```

Three independent checks fire on one dropped arm. 319 real checks, not a printed
constant — `ck.n` is incremented per comparison.

The `audit()` cross-check is also real and complete, not a token gesture:

```
$ python3 auditprobe.py
arms found in www51.sc: 106  distinct: 106
declared in run-script.py: 68
unreachable: 38 (.hash/.dynsym/... and .rel.*/.rela.*)
audit failures: []
declared-but-not-in-script: []
```

68 + 38 = 106. Every `*(...)` in the script is accounted for.

**`check` and its canary work.**

```
$ make -C tb check BUILD=.../work/modern/build   # 10/10 PASS, exit 0
$ make -C tb check-canary                        # exit 0
CANARY PASS: check exited nonzero, 10 project(s) reported FAIL
```

**`isa`/`roundtrip`/`bits`/`branch`/`reloc`/`sim`/`defaultlink`/`commons` all pass on
the real build**, and none of their counts is a constant:

```
== table: 280 instructions   assemble: 280/280   decode: 280/280
   roundtrip: 280/280 (8051) / 3/3 (extra) / 18/18 (zeroops)
== bits: 50 cases     checked: 50/50
== branch: 24 cases   checked: 24/24
== reloc: 36 checks   checked: 36/36
PASS: testall ran to completion, all instruction tests passed (P1=127)
run-defaultlink: PASS / run-commons: PASS
```

**Clean on the things the brief asked me to hunt for:**

```
$ grep -rn "except:" tb/                     # nothing (one hit in testall.asm prose)
$ grep -rn "shell=True\|os.system\|os.popen" tb/    # nothing
$ grep -rn "/home/\|/Users/\|/tmp/[a-z]" tb/*.py tb/sim/* tb/mutation/*.py tb/Makefile
                                             # nothing
```

No comparison of a value against itself; no expected value derived from the thing under
test (`8051.txt`'s golden column is c51asm's, `www8051.hex` is the untouched 2001
output, `reference.md5` is hashed before the shipped ROMs are deleted); no `continue`
that counts a skipped case as passed except the one in F4; no off-by-one truncating a
case list. Temp trees are per-run `mktemp -d`/`TemporaryDirectory` with `trap` cleanup
— no collisions between stages. Exit codes propagate everywhere I checked except F7.

The two `except ValueError: continue` sites (`isa_check.py:64`, `run-script.py:435`)
are both self-defending: a parse that silently drops a `readelf` line leaves the
section missing, and the very next check reports it missing. Not the "mis-reads and
proceeds" pattern.

---

## The code as code

**Duplication.** Four near-identical tool wrappers:

```
$ grep -n "^class \(Tools\|Probe\)" tb/sim/*.py tb/*.py
tb/sim/run-bits.py:23:class Tools:
tb/sim/run-reloc.py:179:class Tools:
tb/sim/run-script.py:309:class Probe:
tb/isa_check.py:105:class Tools:
```

plus `run-branch.py`'s free-function `assemble()`. Five copies of "join `build/gas/as-new`,
check it exists, run it, then `objcopy -O binary --only-section=.text`". Five copies of
the missing-tool check with five different exit codes (`sys.exit('missing %s')`, exit 2,
`tools_ok()`). The two shell stages each re-implement `nm | awk` and
`readelf -S --wide | sed | awk` field extraction (`run-defaultlink.sh:94,119`,
`run-commons.sh:79,109,122,127`). A `tb/sim/toolkit.py` would absorb roughly 200 lines
across five files and give one place to fix a `readelf` output-format change.

**Three copies of the gate stage list** — `tb/Makefile:88-90`, `gate.yml:34-91`,
`run.py:33`. One has already drifted (F3). This is the highest-value consolidation in
the tree.

**`run-script.py` at 679 lines.** Justified. ~260 lines are the arm inventory — data
that *is* the test, one row per `*(...)` arm with its input section, marker byte,
symbol and expected address. ~420 lines of code produce 319 checks over two linker
scripts. The one avoidable piece is `DEF_DEBUG` (lines 143-174) vs `WWW_DEBUG` (lines
252-274): 20 of 27 rows are identical, ~25 lines that could be a shared base list plus
per-script extras.

**Small things.** `run-script.py:584` computes `covered` from `len()` of the tables and
prints it in the verdict line next to the real `ck.n` — a constant sitting where a
result goes; harmless because `audit()` independently forces the inventory to be
complete, but it reads like a claim. `run-script.py:481-483` prints ld's stderr and
continues; a link that warns is not a failure here, unlike `run-defaultlink.sh:79`
which fails on `overlap`. `fixhunks.py:85` `bad = 1 if check else 0` is dead in the
non-check branch. `run-reloc.py:270-275` re-runs `objcopy` up to three times for one
comparison. `run-script.py`'s `--keep` is undocumented in its own usage line (`:34`).

---

## Ranked

| # | Finding | Path | Proven |
|---|---------|------|--------|
| F1 | `oracle` gates diag + serial on ROM length, then claims byte-class agreement for all 10 | critical | yes |
| F2 | `isa_check.py` PASS/exit 0 with `--stages ''` or no input | latent, gate-adjacent | yes |
| F3 | `run.py` STAGES has drifted from `MUTGATE` (4 of 10 stages missing) | mutation score | yes (grep) |
| F6 | `gen.py` drops colliding mutants; emits 7 un-killable comment mutants | mutation score | yes |
| F4 | `run-bits.py` counts two `b'' == b''` comparisons as checks | gate, cosmetic effect | yes |
| F9 | `zeroops.txt` never assembled — no cross-toolchain check on that table | gate coverage | yes |
| F7 | `run.py` ignores rebuild status; prints "results are suspect", returns 0 | mutation harness | static |
| F5 | `checked: N/M` is `checks - len(messages)`, not a pass count | display | yes |
| F10 | empty project list → vacuous PASS in `hexoracle.py` / `romdiff.py` | off path | yes |
| F8 | `make libk80` masks a failing converter | maintenance | static |

No fix was made. Every "where the fix goes" above names a file and a line.

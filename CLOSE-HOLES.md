# Three holes in the gate, reproduced and closed

Branch `claude/close-holes`, cut from `work/green` @ afee4a5.

Each hole below was reproduced first, on this machine, with the command and
the output that shows it. Then it was fixed. Then the same fault was re-run
against the fix and the output that shows it going red is recorded. Nothing
here is a claim without a command behind it.

Every run used the port built by `make -C tb build` (binutils 2.47 +
`mcs51/*.patch`) in `work/modern/build`, and the frozen 2.11.2 toolchain built
by `make -C tb frozen` in `work/frozen/build`.

---

## Hole 1 - `oracle` computed seven metrics and gated on two

`tb/hexoracle.py` classifies every byte that differs between a produced
`www8051.rom` and the untouched 2001 `www8051.hex` into `addr16`, `acall11`,
`word16`, `pcode13`, `zero8` or `residual`, prints all of them, and compared
only the size delta and the residual count against a recorded value.

### Reproduction

`bfd/elf32-i51.c:407`, the write-back of `R_I51_16`, changed from big-endian to
little-endian - the whole fault, one token:

```
    case R_I51_16:
      contents += rel->r_offset;
      srel = (bfd_signed_vma) relocation;
      srel += rel->r_addend;
-     bfd_putb16 ((bfd_vma) srel & 0xFFFF, contents);
+     bfd_putl16 ((bfd_vma) srel & 0xFFFF, contents);
```

`make -C tb check` goes red on all ten projects, ten distinct hashes:

```
$ make -C tb check BUILD=.../work/modern/build WORK=.../work/f1
check rc=2
FAIL diag     reference=1267 84779b2386ba64a0347e227ac09cf18a produced=1267 8895939ab5e6fdec05619d6e4cde3b0e
FAIL ds1620   reference=6284 5bd93daf7609853f6c3db6541060c420 produced=6284 ac0e62717b3d8ac47e2050d556d1a4d3
FAIL ds1822   reference=6078 733b5d0483c7cd324156cd36da1743a6 produced=6078 5e66b6a2c11a48abdbface1692a2e4d1
FAIL lcd      reference=5754 7c0f4fccb4e9ee7305c1f8c8fe7bee1e produced=5754 39e198fc4533f1c26b2297c84aa1607c
FAIL led1     reference=5173 bd336522c8c54be539f2e45d5bbe7888 produced=5173 d7b04536434eef8b2ad34cb25e08fb14
FAIL led2     reference=5010 97e9cf0cf06ebf6ff10e98a6420f6f63 produced=5010 3c8108b745e0fe95bb4bee7e067d9cb5
FAIL led3     reference=5200 470097b25def9f33cde74fdb4c6264f1 produced=5200 23bace8529daaf153e3c199c20f9e0e6
FAIL serial   reference=8128 94c14915a302c599ff91b88244319f4d produced=8128 e9063d114369c1d99850e24a048474ac
FAIL welcome  reference=4812 0244913c2585c0dc9995a5e6a2e95d6d produced=4812 e29ef300fe74bfb04e74f799f2ea37b5
FAIL wjava    reference=4812 bbdbcb2b80d62a384aa8f3ec9d407315 produced=4812 1c08498d68bc9901b0584f09b622a043
```

`make -C tb oracle`, same toolchain, same ROMs, exits 0:

```
$ make -C tb oracle BUILD=.../work/modern/build WORK=.../work/f1
oracle rc=0
project   2001   ours  delta  addr16 acall11  word16 pcode13   zero8  residual  verdict
diag       1264   1267      3       0       0       0       0       0         0  explained +3
ds1620     6284   6284      0      37       1     137      25     633        25  ok
ds1822     6078   6078      0      36       1     141      22     722        28  ok
lcd        5754   5754      0      36       2     137      25     669        27  ok
led1       5173   5173      0      36       1     133      25     615        25  ok
led2       5010   5010      0      36       1     135      25     641        25  ok
led3       5200   5200      0      36       1     137      25     665        25  ok
serial     9647   8128  -1519       0       0       0       0       0         0  explained -1519
welcome    4812   4812      0      36       1     131      25     604        25  ok
wjava      4812   4812      0      36       1     131      25     604        25  ok

all 10 projects agree with the 2001 oracle: recorded size delta, every differing byte accounted for
```

The clean run of the same table has ds1620 at `addr16 308 ... zero8 400`. Under
the fault it reads `addr16 37 ... zero8 633`: 271 bytes moved out of the
16-bit-address class into the "2001 left it zero" class, in every project, and
the script printed the evidence and threw it away.

### Fix

`tb/hexoracle.py`. `EXPECT` now records all six counts per project, not the
residual alone, and the verdict compares every one of them:

```python
CLASSES = ["addr16", "acall11", "word16", "pcode13", "zero8", "residual"]
...
    "ds1620":  (6284, 0, _c(308, 1, 137, 25, 400, 25), None),
...
            moved = ["%s %d (recorded %d)" % (k, counts[k], want_counts[k])
                     for k in CLASSES if counts[k] != want_counts[k]]
```

The numbers come from a clean run and are a joint property of the frozen 2001
image and of a correct port; the file says so, so that a future run that
disagrees is read as a finding rather than as an expectation to refresh.

The two projects whose size delta is explained (`diag`, `serial`) still have no
byte classification - a walk over two images of different length classifies
nothing - and that is stated rather than faked.

### Proof

Same fault, same ROMs, fixed script:

```
$ make -C tb oracle BUILD=.../work/modern/build WORK=.../work/f1
oracle rc=2
project   2001   ours  delta  addr16 acall11  word16 pcode13   zero8  residual  verdict
ds1620     6284   6284      0      37       1     137      25     633        25  addr16 -271
...
FAIL ds1620: addr16 37 (recorded 308), zero8 633 (recorded 400)
FAIL ds1822: addr16 36 (recorded 357), zero8 722 (recorded 427)
FAIL lcd: addr16 36 (recorded 321), zero8 669 (recorded 422)
FAIL led1: addr16 36 (recorded 279), zero8 615 (recorded 398)
FAIL led2: addr16 36 (recorded 281), zero8 641 (recorded 422)
FAIL led3: addr16 36 (recorded 283), zero8 665 (recorded 444)
FAIL welcome: addr16 36 (recorded 264), zero8 604 (recorded 402)
FAIL wjava: addr16 36 (recorded 264), zero8 604 (recorded 402)

8 of 10 projects deviate from the 2001 oracle
```

On the clean tree it passes, and says which metrics it checked:

```
all 10 projects agree with the 2001 oracle: recorded size delta, and every one
of addr16/acall11/word16/pcode13/zero8/residual at its recorded count
```

---

## Hole 2 - a dropped linker-script arm survived every stage

A `*(...)` arm removed from a linker script does not lose a section and does
not lose a symbol. The input becomes an orphan, placed after the output
section it should have joined, and only the bytes disappear - out of
`objcopy -j .text`, which is exactly how a ROM is made here. That is how
`*(reset_network)` sat commented out in `lib/www51.sc` for the life of this
repository with everything green.

### Reproduction

`*(.rodata)` deleted from the `.text` output section of
`ld/scripttempl/elf32i51.sc`, `ld` rebuilt. A three-byte `.rodata` probe:

```asm
        .text
        .global _START
_START: ljmp    _START
        .section .rodata,"a",%progbits
        .global RO
RO:     .byte   0xaa, 0xbb, 0xcc
```

before:

```
objcopy -j .text image: 020000aabbcc22  (7 bytes)
  section .text @0x00000000
00000003 T RO
00000007 T _ETEXT
```

after:

```
objcopy -j .text image: 02000022  (4 bytes)
  section .text @0x00000000
  section .rodata @0x00000004      <- orphan, past _ETEXT
00000004 R RO
00000004 T _ETEXT
```

Three bytes gone from the image. The section is still there, the symbol still
resolves, and the ten stages the repository ran - `gate.yml`'s nine plus
`check`, which only `build.yml` ran - are all green:

```
$ sh oldgate.sh                     # with *(.rodata) removed
isa          GREEN
roundtrip    GREEN
branch       GREEN
bits         GREEN
reloc        GREEN
sim          GREEN
defaultlink  GREEN
commons      GREEN
oracle       GREEN
check        GREEN
```

`tb/sim/run-defaultlink.sh`, the one stage that links with the default script,
uses a probe with no `.rodata`, no `.init`, no `.fini`, no `vectors` and no
`.gnu.linkonce.*` in it, so eleven of the twelve `*(...)` arms of that script's
`.text` had no input anywhere in the testbench, both `KEEP (*(vectors))`
included.

### Fix

`tb/sim/run-script.py`, run by `make -C tb script`, added to `$(TOOLGATE)` and
so to both `$(GATE)` and `$(MUTGATE)`.

It covers **both** scripts: the port's own `ld/scripttempl/elf32i51.sc`,
through a link with the default emulation, and `lib/www51.sc` extracted from
`tb/base.7z`, through `-T`, which is what all ten projects link with. Every
arm gets an input section of its own carrying one identifiable byte, and the
run asserts

* the whole `objcopy -j .text` image byte for byte - the markers of the
  code-space arms in script order, so a dropped arm loses exactly its byte and
  a reordered pair shows up as well:
  `default` = `0102030405060708090a0b0c22`, `www51` = `0102...1617`;
* the address of a marker symbol in every RAM-space arm, computed from the
  script's own size arithmetic (`A_IDATA` at 0x2b, `W_BUFDATA` at 0x90, ...);
* the address and size of every output section;
* the content of every non-allocated stabs/DWARF output section;
* that `/DISCARD/` still discards `.note.GNU-stack`, `.gnu_debuglink` and
  `.gnu.lto_*`;
* that the output carries no section beyond the expected set - an orphan left
  by a dropped arm is caught here too.

146 arms are fed, 319 checks run. Four arms of `www51.sc` - `*(.xdata*)`,
`*(.xbss*)`, `*(.edata*)`, `*(.ebss*)` - cannot carry anything, because the
script declares their memory regions with `LENGTH = 0`; the test puts a byte
in each and asserts the four region diagnostics ld then prints, which name the
output section the arm feeds and so prove the arm collected the input.

38 arms are recorded as unreachable rather than faked: `www51.sc`'s
`*(.hash)`, `*(.dynsym)`, `*(.dynstr)`, `*(.gnu.version*)` and its 32
`*(.rel.*)` / `*(.rela.*)` arms. A hand-made `SHT_PROGBITS` section named
`.rel.text` is written back as `SHT_REL` and the output stops being an ELF the
tools can read:

```
$ ld-new -T www51.sc --no-check-sections -o w3.elf w3.o
$ objcopy -O binary --only-section=.text w3.elf w3.bin
objcopy: w3.elf: file format not recognized
```

The test reads both scripts and refuses to pass if either carries an arm that
is neither fed nor on that list, so "every arm" stays true as the scripts
change. That audit found a real gap while it was being written - the two
`KEEP (*(...))` arms were spelled differently in the inventory than in the
script and were reported as uncovered until the inventory was fixed.

### Proof - four arms, one at a time

Each fault: delete one arm, rebuild, run the ten old stages, then run the new
one. In all four cases the ten old stages were **all green**.

**1. `*(.rodata)` from `elf32i51.sc`** - the fault above:

```
FAIL default .text image: 01020304050607090a0b0c22, expected 0102030405060708090a0b0c22
FAIL default: _ETEXT/_etext: 0x0c, expected 0x0d
FAIL default: unexpected output sections ['.rodata'] - an arm that no longer collects its input leaves the input as an orphan section
run-script: FAIL (3 of 319 checks)
```

**2. `KEEP (*(vectors))` from `elf32i51.sc`**:

```
FAIL default .text image: 01030405060708090a0b0c22, expected 0102030405060708090a0b0c22
FAIL default: _ETEXT/_etext: 0x0c, expected 0x0d
FAIL default: unexpected output sections ['vectors'] - an arm that no longer collects its input leaves the input as an orphan section
run-script: FAIL (3 of 319 checks)
```

**3. `*(.idata)` from `elf32i51.sc`** - a RAM arm, caught by address alone:

```
FAIL default: *(.idata) -> A_IDATA: 0x2c, expected 0x2b
FAIL default: *(.idata.*) -> A_IDATAP: 0x2b, expected 0x2c
run-script: FAIL (2 of 319 checks)
```

**4. `*(reset_network)` from `lib/www51.sc`** - the original bug, re-created by
commenting the line out in a repacked copy of `base.7z`:

```
82:/*    *(reset_network) */
FAIL www51 .text image: 01020304050608090a0b0c0d0e0f1011121314151617, expected 0102030405060708090a0b0c0d0e0f1011121314151617
FAIL www51: _ETEXT/_etext: 0x16, expected 0x17
FAIL www51: unexpected output sections ['reset_network'] - an arm that no longer collects its input leaves the input as an orphan section
run-script: FAIL (3 of 319 checks)
```

On the clean tree:

```
== script arms: 146 covered, 319 checks, 38 unreachable
run-script: PASS (every reachable *(...) arm of elf32i51.sc and lib/www51.sc
placed its own input at its own address)
```

---

## Hole 3 - `frozen.expect` and `frozen-report.md` were stale

Both files were written before `*(reset_network)` was restored in
`lib/www51.sc` and were never touched afterwards. `git diff 5d02910 93270ae --
tb/frozen-report.md` is empty, though 93270ae is the commit that repacked
`tb/base.7z` with the restored script and rewrote `tb/reference.md5`.

The 32-bit binutils 2.11.2 build **was** possible in this container - `gcc -m32`
works, `gcc-multilib` is installed - so the numbers were re-derived rather than
worked around.

```
$ make -C tb frozen                 # binutils 2.11.2 + tb/ref.7z, gcc -m32
$ make -C tb check-frozen           # ten projects, tb/base2001.7z overlay
FAIL diag     build-failed
FAIL ds1620   reference=6284 5bd93daf... produced=6284 61a010c5...
... (nine differ, one does not link)
$ python3 tb/romdiff.py --reference work/refrom --produced work/tb \
      --projects "$PROJECTS"
| ds1620 | 6284 B | 6284 B | 217, from 0x40 | ...
| ds1822 | 6078 B | 6078 B | 225, from 0x40 | ...
| lcd    | 5754 B | 5754 B | 214, from 0x40 | ...
| led1   | 5173 B | 5173 B | 213, from 0x40 | ...
| led2   | 5010 B | 5010 B | 214, from 0x40 | ...
| led3   | 5200 B | 5200 B | 214, from 0x40 | ...
| serial | 8128 B | 8128 B | 325, from 0x40 | ...
| welcome| 4812 B | 4812 B | 213, from 0x40 | ...
| wjava  | 4812 B | 4812 B | 213, from 0x40 | ...
```

### What was actually stale, and what was not

The **differing-byte counts** in `frozen.expect` - 217/225/214/213/214/214/
325/213/213 - reproduce exactly. That is not luck: `reset_network` is three
bytes of `LCALL network_init` that both toolchains now emit identically, so
both ROMs grew by three bytes in the same place and nothing new diverged. The
recorded outcome `not-produced` for `diag` also still holds.

What was stale is the **length**, and the length was the one number
`frozen.expect` did not record - which is precisely why it could go stale and
keep passing. `frozen-report.md` did tabulate it, in
1264/6281/6075/5720/5170/5007/5197/8125/4809/4809, and every one of those is
wrong for the current tree (+3 for eight projects, +34 for `lcd`, whose inputs
also changed in the same repack).

### Fix

* `tb/frozen.expect` gains a third column, the size of the ROM the frozen
  toolchain produced, and records the re-derived values with the provenance of
  the run that produced them.
* `tb/romdiff.py` gates on that column, and **refuses** a line with fewer than
  three columns instead of defaulting the missing one, so an expectation file
  written before the column fails loudly:

```
$ python3 tb/romdiff.py ... --expect frozen.2col      # the new file, size column stripped
romdiff exit 1
FAIL frozen.2col:31: 'diag not-produced 0' gives 2 column(s) after the project
name, 3 required (outcome, differing bytes, ROM size) - this expectation file
predates the size column and cannot be trusted
```

* `tb/frozen-report.md` keeps its historical tables, labelled as the
  pre-restore run they were, and gains a "Re-derived, 2026-08-26" section with
  the measured numbers, the rebuilt section-by-section comparison of the two
  maps, and the restatement that the `.bss` common-alignment difference is
  untouched.

Nothing was edited to whatever the tree prints without a rebuild behind it:
every number in the new section came out of `make -C tb frozen`,
`make -C tb check-frozen` and `tb/romdiff.py` run here.

### Proof

Against the pre-restore sizes - the numbers `frozen-report.md` still carried -
the gate goes red on nine projects:

```
$ python3 tb/romdiff.py ... --expect frozen.stale
romdiff exit 1
PASS diag     not-produced 0 0
FAIL ds1620   differ 217 bytes differ, 6284 B ROM; recorded differ 217 6281
FAIL ds1822   differ 225 bytes differ, 6078 B ROM; recorded differ 225 6075
FAIL lcd      differ 214 bytes differ, 5754 B ROM; recorded differ 214 5720
FAIL led1     differ 213 bytes differ, 5173 B ROM; recorded differ 213 5170
FAIL led2     differ 214 bytes differ, 5010 B ROM; recorded differ 214 5007
FAIL led3     differ 214 bytes differ, 5200 B ROM; recorded differ 214 5197
FAIL serial   differ 325 bytes differ, 8128 B ROM; recorded differ 325 8125
FAIL welcome  differ 213 bytes differ, 4812 B ROM; recorded differ 213 4809
FAIL wjava    differ 213 bytes differ, 4812 B ROM; recorded differ 213 4809

**9 project(s) moved away from the recorded frozen outcome.**
```

Note that with the old two-column format every one of those nine lines passed:
the differing-byte counts did not move.

Against the re-derived file:

```
$ python3 tb/romdiff.py ... --expect tb/frozen.expect
romdiff exit 0
PASS diag     not-produced 0 0
PASS ds1620   differ 217 6284
... all 10 projects match the recorded frozen outcome.
```

---

## The two workflow facts

**`gate.yml` never ran `check`.** Its only contact with the ten projects was
`oracle`, which does not fail a project that will not build. The merge gate
therefore never once hashed a produced `www8051.rom` against the reference
`base.7z` ships - that ran only in `build.yml`, on a `paths:` trigger.

`tb/Makefile` now reads

```make
TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons script
GATE     := $(TOOLGATE) check oracle
MUTGATE  := $(TOOLGATE) check
```

and `gate.yml` runs that list, `check` and `check-canary` included.

**Neither workflow ran on `main` or on a pull request.** Both carried
`branches-ignore: [main]` and neither had a `pull_request` trigger, so the gate
never ran on the branch it gates, and never on the merge itself. Both now
carry a bare `push:` and a `pull_request:`.

That second change is what reaches the three mutants named in the brief.
`bfd-endian-398`, `bfd-howto-138` and `bfd-howto-168` survive every stage
`gate.yml` used to run - and all three are killed by `check`:

```
 91/195 bfd-endian-398               killed    check   bfd_getb16 -> bfd_getl16
110/195 bfd-howto-138                killed    check   R_I51_8 pc_relative false -> true
115/195 bfd-howto-168                killed    check   R_I51_H pc_relative false -> true
```

They were surviving the merge gate for one reason: the merge gate did not run
`check`. It does now.

---

## Final state

Full gate, clean tree:

```
$ make -C tb gate BUILD=.../work/modern/build
== isa / roundtrip / branch / bits / reloc / sim / defaultlink / commons
== script
== script arms: 146 covered, 319 checks, 38 unreachable
run-script: PASS
== check
all 10 projects match the reference
== oracle
all 10 projects agree with the 2001 oracle: recorded size delta, and every one
of addr16/acall11/word16/pcode13/zero8/residual at its recorded count
gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
```

`make -C tb mutants`, 195 mutants, each rebuilt and put through
`$(MUTGATE)` = `isa roundtrip branch bits reloc sim defaultlink commons script
check`:

```
baseline: isa roundtrip branch bits reloc sim defaultlink commons script check all pass

== 195 mutants in 5990s
   killed    110
   survived  85
   no-build  0 (excluded: the fault cannot exist in that form)
   KILL RATE 56.4% (110/195)
```

**56.4% (110/195)**, against the 55.9% (109/195) floor. The gained kill is
`ldsc-ldnum-183`, and the new stage is the only thing that catches it:

```
190/195 ldsc-ldnum-183               killed    script   0x0000 -> 0x0001
```

That is `.edata 0x0000 (INFO) :` in the default script moved to `0x0001` - a
memory space whose origin is one byte too high. Every other stage misses it
because no other stage puts anything in `.edata` and reads its address back;
`run-script.py` does, and `A_EDATA` comes out at 0x01 instead of 0x00.

`bfd-endian-398`, `bfd-howto-138` and `bfd-howto-168` are killed here by
`check`, which `$(MUTGATE)` already contained, so they were killed in the
previous run too - the mutation number is not what those three were about. What
they showed is that `gate.yml` did not run the stage that kills them, and that
is fixed above.

The clean tree passed all ten stages before the loop (`baseline: ... all pass`)
and the harness re-ran the gate after restoring the sources with no warning, so
no mutation leaked out of the run. The full survivor list is in the run output
and in `work/mutants/results.json`. Nothing was removed or weakened in any test
to move this number; one stage was added.

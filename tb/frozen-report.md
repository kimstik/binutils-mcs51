# The 2001 port against the current reference ROMs

What `make -C tb frozen && make -C tb check-frozen` does, and what it found.
The toolchain is binutils 2.11.2 patched with `tb/ref.7z`, the era the port was
written in. The inputs are `tb/base.7z` with `tb/base2001.7z` unpacked over it,
which swaps the precompiled `lib/` and `cgi/` objects for the 2001 originals -
see `base2001.PROVENANCE`. The reference ROMs are base.7z's own, produced by the
current port on binutils 2.47.

Run 32857320527 on `work/frozen-data`, ubuntu-24.04.

**The sizes in the two tables below are the reference ROMs as they stood
before `*(reset_network)` was restored in `lib/www51.sc`.** They are three
bytes short in eight projects and 34 bytes short in `lcd`, and they were left
unchanged when `base.7z` was repacked with the restored script (commit
93270ae, which changed `tb/base.7z` and `tb/reference.md5` and touched neither
this file nor `tb/frozen.expect`). The tables are kept as those runs reported
them; "Re-derived" at the end of this file carries the numbers as they stand,
measured here rather than copied.

## Result

| project | reference | frozen 2.11.2 | differing bytes |
|---------|-----------|---------------|-----------------|
| diag    | 1264 B    | does not link | -               |
| ds1620  | 6281 B    | 6281 B        | 423, from 0x40  |
| ds1822  | 6075 B    | 6075 B        | 444, from 0x40  |
| lcd     | 5720 B    | 5720 B        | 445, from 0x40  |
| led1    | 5170 B    | 5170 B        | 422, from 0x40  |
| led2    | 5007 B    | 5007 B        | 443, from 0x40  |
| led3    | 5197 B    | 5197 B        | 465, from 0x40  |
| serial  | 8125 B    | 8125 B        | 704, from 0x40  |
| welcome | 4809 B    | 4809 B        | 419, from 0x40  |
| wjava   | 4809 B    | 4809 B        | 419, from 0x40  |

Nine of ten link and produce a ROM of exactly the reference length. None is
byte-identical. The reference ROMs are untouched: `check` hashes the copies
base.7z ships and deletes them before anything is built, so the comparison only
ever sees a ROM the run itself produced.

## What differs

Every difference is an operand carrying an internal-RAM byte address or a bit
address. The instruction stream itself matches: same length, same opcodes, same
code addresses. The first divergence in all nine sits at ROM offset 0x40, and
the port's own objdump, run over the frozen `www8051.o`, names it:

```
      3e:	75 81 62    	mov	0x81, #0x62	; #98	#'b'     ds1620, frozen
```

`0x81` is SP, and its immediate is the byte at 0x40. The reference ROM holds
0x78 there, the frozen one 0x62: the reference puts the stack 22 bytes higher.
There is no reference `.o` to disassemble - base.7z ships the ROMs only - so
the reference side is read out of the hexdump `romdiff.py` prints.

Across a whole ROM the differing bytes form a near-permutation of the
0x20..0x78 internal-RAM range - for ds1620, 73 distinct reference byte values,
61 of which map to exactly one produced value:

```
0c->14 0d->15 0e->16 0f->17 11->19 13->1b 14->1c 20->28 21->29 22->2a 2a->32
30->38 31->39 32->20 34->24 35->20 36->3a 37->23 38->3b 39->21 3c->4b 40->3e
...  70->33 72->5f 73->39 74->3b 75->60 76->5e 77->61 78->62
```

That is one variable layout relabelled into another, not different code.

## Why the layout differs

`lib/www51.sc` computes every data section's address from the size of the one
before it, so a single section that changes size moves everything after it:

```
.data (((SIZEOF(.bit) + SIZEOF(.bitbss) + 7) / 8) + SIZEOF(.bbss) + ADDR(.bbss))
.bss  SIZEOF(.data) + ADDR(.data)      { *(.bss*) *(COMMON) }
.idata SIZEOF(.bss) + ADDR(.bss)       { ... PROVIDE (stack = .) }
```

The section that changed is `.bss`, and the cause is in the input objects. The
2001 assembler records the port's own storage classes as processor-specific
section indices, defined in the patched `include/elf/i51.h`:

```
SHN_I51_REGBANK   0xff00   SHN_I51_BDATA_C   0xff02
SHN_I51_RDATA_C   0xff01   SHN_I51_IDATA_C   0xff03
SHN_I51_XDATA_C   0xff04   SHN_I51_BITDATA_C 0xff06
```

Counting those indices in the symbol tables of each input, 2001 original
against the copy base.7z ships:

| input        | 2001                                          | base.7z          |
|--------------|-----------------------------------------------|------------------|
| libk80.a     | ff00:7  ff02:1  ff03:2  ff06:15  COMMON:17    | identical        |
| libk23.a     | ff00:7  ff02:2  ff03:2  ff06:18  COMMON:19    | identical        |
| libw23.a     | ff00:11 ff02:2  ff03:2  ff06:21  COMMON:10    | identical        |
| libw80.a     | ff00:11 ff02:2  ff03:2  ff06:21  COMMON:10    | **COMMON:46**    |
| web51_80.obj | ff02:1  ff06:6  COMMON:2                      | **COMMON:9**     |
| web51_23.obj | same shape                                     | **COMMON only**  |

Reproduce with a symbol-table walk over both archives; the counts above come
from one.

Those three inputs - `libw80.a`, `web51_80.obj`, `web51_23.obj` - are exactly
the three that `objects-report/REPORT.md` already identified as re-assembled by
the current port rather than converted from the 2001 object. Everything base.7z
converted with `i51elf_le2be.py` + `i51elf_sym_uc.py` keeps its indices; the
conversion does not touch `st_shndx`.

So in a frozen link those symbols are bit and bdata commons and land in
`.bitbss`; in the link that produced the reference ROMs they are ordinary
one-byte commons and land in `.bss`. For led1 the frozen `.bitbss` holds 28
bits and `.bss` 39 bytes, putting `stack` at 0x61; the reference has `stack` at
0x77, 22 bytes higher, which is the order of magnitude those 28 bits account
for when each becomes a byte.

**Open question, not answered here:** whether the current assembler no longer
emits the processor-specific indices at all, or whether these three inputs were
built from something else. The current linker clearly still understands them,
since base.7z's other libraries carry them and the modern testbench links
green. Answering it needs a run of the current assembler over `lib/web51.asm`
and a look at the `st_shndx` it writes.

## diag does not link

```
lib/www51.sc:266: undefined symbol `_reti_' referenced in expression
```

`diag` links neither `web51_80.obj` nor `web51_23.obj`, and `_reti_` is defined
in nothing else. The script only mentions it inside `PROVIDE (intIE0 = _reti_)`
and nine like it, for interrupt vectors `diag` never references - so under the
current linker the provide is skipped and the symbol is never needed. 2.11.2
folds the right-hand side first and consults the destination afterwards
(`ld/ldexp.c`, `case etree_provide`: `result = exp_fold_tree (tree->assign.src,
...)` runs before the `bfd_link_hash_lookup`), so the reference has to resolve
whether or not anything wants the symbol.

This is a difference between the two linkers, not between the two object sets.
It surfaces here only because base.7z's `projekt/diag/Makefile` passes
`--script $(LIBDIR)/www51.sc`, which the 2001 one did not:

```
-	$(LINKER) -L $(LIBDIR) $(OBJS) -lk80 -lw80 -M -o www8051.o ...
+	$(LINKER) --script $(LIBDIR)/www51.sc -L $(LIBDIR) $(OBJS) -lk80 -lw80 ...
```

The 2001 diag was linked with ld's built-in i51 script, so no frozen run can
reproduce base.7z's diag ROM by replaying base.7z's own command line.

## Status

`frozen.yml` still runs the testbench step with `continue-on-error: true` -
the 2001 toolchain is not expected to reproduce the reference ROMs - but the
comparison step after it does not: `romdiff.py --expect tb/frozen.expect` exits
nonzero on any movement and that is the job's failure. The reference ROMs were
not adjusted and no failure is suppressed.

Reconciliation is deferred. The choice is between rebuilding base.7z's three
re-assembled inputs so they carry the 2001 storage classes, accepting two
reference sets, or answering the open question above first - and none of that
should be decided from a single run.

---

# After the commons fix: how far the two lines converged

Added on `work/bitcomm`. The open question above is answered: the current
assembler could not emit the processor-specific indices at all.

## What changed in the toolchain

`elf_backend_section_from_bfd_section` was commented out in `bfd/elf32-i51.c`
with the note "Temporarily disabled - causes crashes with standard sections".
Without it an external `.bcomm` or `.bitcomm` was written as plain
`SHN_COMMON`, so the assembler could not produce the indices the 2001 objects
carry, and re-assembling any of those objects destroyed them.

The crash was real but had nothing to do with standard sections.
`include/elf/internal.h` redefines `SHN_LORESERVE` as `(-0x100u)`: inside bfd a
section index is a 32-bit field whose reserved range sits at the top of that
field, not at 0xff00. The port defined its indices as bare 0xff00..0xff06, so
enabling the hook made gas hand bfd an index of 0xff02, which reads as an
ordinary section number too large for the 16-bit `st_shndx` - and bfd then
tries to spill it into a `.symtab_shndx` table that gas has not got:

```
as-new: BFD (GNU Binutils) 2.47.20260726 internal error, aborting at
        ../../binutils-2.47/bfd/elfcode.h:224 in bfd_elf32_swap_symbol_out
```

The same mismatch silently disabled the read side, which compares an internal
index against the same file-format constant and can never match. Defining the
indices as `SHN_LORESERVE + n`, the way MIPS, TI C6X and x86-64 define theirs,
fixes reading and writing at once: on disk they stay 0xff00..0xff06.

`tb/sim/run-commons.sh` (`make -C tb commons`, in the gate) declares one
external common per space and checks the index of each. It reports every common
as `COM` before the fix and `PRC[0xff01]` through `PRC[0xff06]` after.

## What changed in the inputs

`lib/web51_80.obj`, `lib/web51_23.obj` and `lib/libw80.a` were re-assembled
copies, which is how they lost their indices. They now carry the 2001 originals
from `base2001.7z` converted with `i51elf_le2be.py` + `i51elf_sym_uc.py`, the
archive through the new `tb/i51elf_ar.py`. The table in the section above now
reads `identical` for every row. Provenance and hashes are in
`objects-report/PROVENANCE`.

Both lines therefore link the same code from the same objects. `base.7z` also
carries new reference ROMs, produced by the fixed toolchain and identical across
linux-x86_64, linux-arm64 and macos-arm64 (build run 32876629391, green in
32877344061).

## Convergence

Frozen ROMs from run 32857320527, reference ROMs as they now stand.
`frozen.yml` re-run on this branch, run 32878917600, reports the same
counts from its own build of the 2001 toolchain.

| project | size   | differing bytes, before | differing bytes, now | first |
|---------|--------|-------------------------|----------------------|-------|
| diag    | 1264 B | does not link           | does not link        | -     |
| ds1620  | 6281 B | 423                     | 217                  | 0x40  |
| ds1822  | 6075 B | 444                     | 225                  | 0x40  |
| lcd     | 5720 B | 445                     | 214                  | 0x40  |
| led1    | 5170 B | 422                     | 213                  | 0x40  |
| led2    | 5007 B | 443                     | 214                  | 0x40  |
| led3    | 5197 B | 465                     | 214                  | 0x40  |
| serial  | 8125 B | 704                     | 325                  | 0x40  |
| welcome | 4809 B | 419                     | 213                  | 0x40  |
| wjava   | 4809 B | 419                     | 213                  | 0x40  |

Roughly half the divergence is gone. No project is byte-identical yet.

`diag` still fails to link under 2.11.2 for the reason already given: the
2.11.2 `PROVIDE` folds its right-hand side before consulting the destination,
so `_reti_` has to resolve whether or not anything wants it. That is a linker
difference, untouched by this work.

## What is left, section by section

Both maps, same nine projects, frozen against the current port:

| project | .text | .rbss | .bdata | .bbss | .bit | .bitbss | .data | .bss         | .idata       | .ibss | .eeprom |
|---------|-------|-------|--------|-------|------|---------|-------|--------------|--------------|-------|---------|
| ds1620  | same  | same  | same   | same  | same | same    | same  | 0x28 -> 0x30 | 0x62 -> 0x6a | same  | same    |
| ds1822  | same  | same  | same   | same  | same | same    | same  | 0x32 -> 0x3b | 0x6c -> 0x75 | same  | same    |
| lcd     | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x2f | 0x61 -> 0x69 | same  | same    |
| led1    | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x2f | 0x61 -> 0x69 | same  | same    |
| led2    | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x2f | 0x61 -> 0x69 | same  | same    |
| led3    | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x2f | 0x61 -> 0x69 | same  | same    |
| serial  | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x30 | 0x65 -> 0x6e | same  | same    |
| welcome | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x2f | 0x61 -> 0x69 | same  | same    |
| wjava   | same  | same  | same   | same  | same | same    | same  | 0x27 -> 0x2f | 0x61 -> 0x69 | same  | same    |

`same` means the same address and the same size in both maps; the `.bss` and
`.idata` columns give size and address respectively, frozen first. Every space
the commons fix was about - `.bbss` for bdata, `.bitbss` for the bit space, and
the `.bit` and `.bdata` sections whose addresses are computed from their sizes -
now matches the 2001 layout exactly. led1 puts 28 bits in `.bitbss` and 4 bytes
in `.bbss` on both sides, where the reference used to put all of it in `.bss`.

One section is left: `.bss` is 8 bytes larger under the current linker, 9 for
ds1822 and serial. Everything after it, `.idata` included, moves up by that
much, and `PROVIDE (stack = .)` moves with it. The stack byte is what the first
differing byte at ROM 0x40 carries, the operand of `mov 0x81,#imm`: frozen 0x61,
current 0x69 for led1, where the old reference had 0x77.

## Why .bss is still bigger

Commons in the 2001 objects record an alignment, and the two linkers treat it
differently. `libk80.a(tcp.obj)` is the clearest case, ten commons whose
alignment comes straight from the object's `st_value`:

```
IPSRCADDR  align=4 size=4    IPLEN            align=2 size=2
TCPSRCPORT align=2 size=2    PACKET_ID        align=2 size=2
RCVSEQ     align=4 size=4    TCPWRITEPOINTER  align=2 size=2
SENDSEQ    align=4 size=4    DWORDTEMP        align=4 size=4
TIMEOUT1   align=1 size=1    RETRY1           align=1 size=1
```

2.11.2 lays them end to end and the block is 0x1a bytes, the exact sum of the
sizes; a 4-aligned symbol lands at 0x43. 2.47 honours the alignment and the
block is 0x21, plus one more fill byte later to put a 4-aligned `WORKREG` at
0x60. That is the whole 8 bytes.

The 2001 port did not get this by accident. `ref.7z`'s `i51.patch.112p` patches
`ld/ldlang.c` to switch common alignment off for this target and nothing else:

```
!   if (ldfile_output_architecture != bfd_arch_i51 )
!     {
!       /* Increase the size of the section.  */
!       section->_cooked_size = ALIGN_N ((section->_cooked_size + opb - 1) / opb,
!                                        (bfd_size_type) (1 << power_of_two)) * opb;
+       /* Adjust the alignment if necessary.  */
+         if (power_of_two > section->alignment_power)
+           section->alignment_power = power_of_two;
+     }
```

On a part with 128 bytes of directly addressable RAM, padding a common to a
4-byte boundary buys nothing, since the 8051 has no alignment requirement, and
it costs RAM the program may need. `mcs51/*.patch` carries no counterpart, so
the current port gets stock `lang_one_common` and pays the padding.

Closing the last 8 bytes therefore means deciding whether the port should carry
that patch, which is a decision about how the port allocates RAM and not a bug
to be fixed on the way past. It is left open here, and the reference ROMs were
not adjusted to hide it.

---

# Re-derived, 2026-08-26

Everything above was written against a tree in which `lib/www51.sc` still had
`*(reset_network)` commented out. Both of its inputs have changed since:
`tb/base.7z` carries the restored script and new reference ROMs, and the port
itself has moved. `tb/frozen.expect` and this file were not touched, so they
were describing a tree that no longer existed.

They are not corrected by copying what the tree prints. The 2.11.2 toolchain
was rebuilt and the comparison re-run:

```
$ gcc -m32 --version | head -1
gcc (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0
$ make -C tb frozen                 # binutils 2.11.2 + tb/ref.7z, 32-bit
$ make -C tb check-frozen           # ten projects, tb/base2001.7z overlay
$ python3 tb/romdiff.py --reference work/refrom --produced work/tb \
      --projects "$PROJECTS" --expect tb/frozen.expect
```

## What the rebuild produced

| project | reference | frozen 2.11.2 | differing bytes | first |
|---------|-----------|---------------|-----------------|-------|
| diag    | 1267 B    | does not link | -               | -     |
| ds1620  | 6284 B    | 6284 B        | 217             | 0x40  |
| ds1822  | 6078 B    | 6078 B        | 225             | 0x40  |
| lcd     | 5754 B    | 5754 B        | 214             | 0x40  |
| led1    | 5173 B    | 5173 B        | 213             | 0x40  |
| led2    | 5010 B    | 5010 B        | 214             | 0x40  |
| led3    | 5200 B    | 5200 B        | 214             | 0x40  |
| serial  | 8128 B    | 8128 B        | 325             | 0x40  |
| welcome | 4812 B    | 4812 B        | 213             | 0x40  |
| wjava   | 4812 B    | 4812 B        | 213             | 0x40  |

Nine of ten still link and still produce a ROM of exactly the reference length.
`diag` still fails on `_reti_` for the reason given above.

The differing-byte counts came out byte for byte the ones already recorded -
217/225/214/213/214/214/325/213/213 - and that is the expected result rather
than a coincidence: `reset_network` is three bytes of `LCALL network_init` that
both toolchains now emit identically, so both ROMs grew by the same three bytes
in the same place and nothing new diverged. What moved is the length, and the
length was the one number `frozen.expect` did not record.

`frozen.expect` therefore now carries a third column, the ROM size, and
`romdiff.py` rejects a line with fewer than three columns instead of defaulting
the missing one. Against the pre-restore sizes it goes red on nine projects:

```
FAIL ds1620   differ 217 bytes differ, 6284 B ROM; recorded differ 217 6281
FAIL lcd      differ 214 bytes differ, 5754 B ROM; recorded differ 214 5720
...
**9 project(s) moved away from the recorded frozen outcome.**
```

## The layout difference is unchanged

Both maps re-read, frozen against the current port, all nine projects that
link. `.text`, `.reg`, `.rbss`, `.bdata`, `.bbss`, `.bit`, `.bitbss`, `.data`,
`.ibss` and `.eeprom` are identical in address and size on both sides. Two
columns still move, and by the same amounts as before:

| project | .bss size, frozen -> current | .idata address, frozen -> current |
|---------|------------------------------|-----------------------------------|
| ds1620  | 0x28 -> 0x30                 | 0x62 -> 0x6a                      |
| ds1822  | 0x32 -> 0x3b                 | 0x6c -> 0x75                      |
| lcd     | 0x27 -> 0x2f                 | 0x61 -> 0x69                      |
| led1    | 0x27 -> 0x2f                 | 0x61 -> 0x69                      |
| led2    | 0x27 -> 0x2f                 | 0x61 -> 0x69                      |
| led3    | 0x27 -> 0x2f                 | 0x61 -> 0x69                      |
| serial  | 0x27 -> 0x30                 | 0x65 -> 0x6e                      |
| welcome | 0x27 -> 0x2f                 | 0x61 -> 0x69                      |
| wjava   | 0x27 -> 0x2f                 | 0x61 -> 0x69                      |

That is the common-alignment difference of "Why .bss is still bigger", intact.
Nothing in this re-derivation closes it and nothing here was adjusted to hide
it.

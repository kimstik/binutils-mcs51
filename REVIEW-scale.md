# REVIEW-scale.md — behaviour at scale and across many translation units

Review only. Nothing in `mcs51/`, `tb/`, `.github/` or any source was modified.

Axis: what happens when a program is big, or built from many pieces. Everything
below was produced by generating throwaway inputs and running the port's own
tools on them. Areas already covered by earlier rounds (opcode encoding, howto
internals, endianness, bit addressing, testbench honesty, mutation testing, gas
directives, the other binutils tools, malformed input, default-script section
chaining) are not re-audited here.

## Toolchain under test

Built from `mcs51/additions.patch` + `mcs51/modifications.patch` on binutils
2.47, target `i51-elf`, exactly as `tb/Makefile`'s `build` target does:

```
$ patch --fuzz 0 -p1 -d binutils-2.47 < mcs51/additions.patch
$ patch --fuzz 0 -p1 -d binutils-2.47 < mcs51/modifications.patch
$ ../binutils-2.47/configure --target=i51-elf --disable-nls --disable-werror \
      --disable-gdb --disable-shared
$ make -j4 MAKEINFO=true          # exit 0
```

Tools referred to below as `as`, `ld`, `ar`, `nm`, `objcopy`, `objdump`,
`readelf` are that build's `gas/as-new`, `ld/ld-new`, `binutils/*`.

---

# Findings, worst first

## 1. HIGH — directly addressed internal RAM is not bounded at 0x80. A program that outgrows 128 bytes of RAM links clean and reads SFRs instead of variables.

`ld/scripttempl/elf32i51.sc` places the direct-addressed arena
(`.regbank` → `.rdata` → `.rbss` → `.bdata` → `.bbss` → `.data` → `.bss`) and
then lets `.idata`/`.ibss` continue from wherever `.bss` ended. The only limit
asserted anywhere is

```
ASSERT (__IDATA_END <= 0x100, "internal RAM overflow (past 0xFF)")
```

Nothing asserts that the **direct** part stops at 0x7F. On an 8051, direct
addresses 0x80–0xFF are SFR space; the RAM there exists only through `@R0`/`@R1`.
So every direct-addressed variable that lands above 0x7F is compiled into an
access to a special function register.

150 bytes of `.bss` in one module, a four-byte variable in the next:

```
$ cat a.s
        .bss
        .global PAD
PAD:    .fill 150,1,0
$ cat b.s
        .bss
        .global LATE
LATE:   .fill 4,1,0
$ cat m.s
        .text
        .global _START
_START: mov a,LATE
        mov LATE,a
        mov a,PAD
        ret

$ ld -o o.elf m.o a.o b.o ; echo "ld exit=$?"
ld exit=0

$ nm -n o.elf | grep -E 'PAD|LATE'
00000020 ? PAD
000000b6 ? LATE

$ objdump -d o.elf
00000000 <_START>:
   0:	e5 b6       	mov	A, 0xB6
   2:	f5 b6       	mov	0xB6, A
   4:	e5 20       	mov	A, 0x20
   6:	22          	ret
```

`e5 b6` is `MOV A, direct 0xB6`. 0xB6 is SFR space, not RAM. Exit 0, no warning,
no map entry that flags it. The same run also shows the write, `f5 b6`, which
on a real part writes an SFR.

Independently corroborated by the memory-model reviewer from the symbol side: a
`.data` variable at 0x90 assembles `mov a,VAR` to `E5 90`, a read of P1,
verified in ucsim.

Why this is a scale bug and not a toy: one small file never gets there. 128
bytes of direct RAM is nothing for a project built from twenty modules that each
declare a handful of byte variables. The failure is silent at assembly, silent
at link, and shows up as corrupted I/O ports at run time.

The overflow that *is* checked fires only 128 bytes later:

```
$ ld -o o.elf cm.o d0.o … d19.o        # 20 modules x 20 bytes of .idata
ld: internal RAM overflow (past 0xFF)
$ echo $?
1
```

Where a fix would go: `ld/scripttempl/elf32i51.sc`, alongside the existing
asserts — an `ASSERT (__DATA_END <= 0x80, …)`. Worth deciding at the same time
whether `.idata` should *start* at 0x80 rather than simply continuing from
`__DATA_END`; the script's own comment says the same physical RAM continues, so
the direct/indirect split is currently a naming convention with nothing behind
it. Not fixed here.

## 2. HIGH — the same symbol declared as a common in two different memory spaces is silently unified, and which space wins depends on command-line order.

Every memory-space common carries a processor-specific section index in the
object, so the two declarations are distinguishable:

```
$ cat r1.s
        .xcomm SPLIT,16,1
$ cat r2.s
        .icomm SPLIT,16,1

$ readelf -s --wide r1.o | grep SPLIT
     … 16 OBJECT  GLOBAL DEFAULT PRC[0xff04] SPLIT        # xdata
$ readelf -s --wide r2.o | grep SPLIT
     … 16 OBJECT  GLOBAL DEFAULT PRC[0xff03] SPLIT        # idata
```

The linker takes whichever came first and says nothing:

```
$ ld -o os.elf mn.o r1.o r2.o d0.o ; echo "exit=$?  stderr lines: 0"
exit=0
    .xbss  addr=00000000 size=000010
    SPLIT value=00000000 size=16

$ ld -o os.elf mn.o r2.o r1.o d0.o ; echo "exit=$?  stderr lines: 0"
exit=0
    .ibss  addr=00000020 size=000010
    SPLIT value=00000020 size=16
```

Same objects, same symbol, two link orders: once `SPLIT` is external RAM at
0x0000, once internal RAM at 0x0020. Zero diagnostics either way. A module that
reaches it with `movx @dptr` and one that reaches it with `mov @r0` now disagree
about which physical memory the variable lives in, and reordering objects in a
Makefile flips it.

The same blindness applies to a common in one space versus a real definition in
another:

```
$ cat s1.s ; cat s2.s
        .xcomm CLASH,16,1
        .idata
        .global CLASH
CLASH:  .fill 16,1,0
$ ld -o o8.elf mn.o s1.o s2.o d0.o ; echo $?
0
$ nm o8.elf | grep CLASH
00000020 I CLASH          # the .idata definition won, the xdata common vanished
```

This is the classic multi-TU hazard the ELF common rules were designed to catch,
and the information needed to catch it is right there in `st_shndx`. Standard
size-merging *is* handled correctly (below), so it is only the *space* that goes
unchecked.

Where a fix would go: `bfd/elf32-i51.c`, at `elf32_i51_add_symbol_hook` (or a
`merge_symbol`-style hook) — when a symbol already has a memory-space common
section and the incoming one names a different space, report it. Not fixed here.

## 3. MEDIUM — a `.pcode` exec address that crosses 0x1FFF only after linking is truncated silently, while the same address written as a constant is a hard error.

`bfd/elf32-i51.c`, `R_I51_13_PCODE`:

```
      /* Use lower 13 bits for addresses > 0x1FFF */
      if (srel > 0x1FFF)
	srel = srel & 0x1FFF;
```

End to end, a `.pcode` naming a routine in another object, with the caller's
module padded so the routine drifts past 8K:

```
$ cat pt.s
        .text
        .global PTARGET
PTARGET: ret
$ cat pc.s                        # pad varies
        .text
        .global _START
_START: .fill <pad>,1,0
        .pcode PTARGET

pad=0x300   PTARGET=0x0303  ld OK   pcode word+flags = 03 03 00
pad=0x1f00  PTARGET=0x1f03  ld OK   pcode word+flags = 1f 03 00
pad=0x2000  PTARGET=0x2003  ld OK   pcode word+flags = 00 03 00     <-- wrong
pad=0x8000  PTARGET=0x8003  ld OK   pcode word+flags = 00 03 00     <-- wrong
```

`ld` exits 0 in every case. The pcode entry that should execute at 0x2003 will
execute at 0x0003.

The asymmetry is the tell — the same value as a literal is refused by the
assembler:

```
$ printf '        .text\n        .global _START\n_START: .pcode 0x2001\n' > k.s
$ as -o k.o k.s
k.s:3: Error: Pcode exec address out of 13-bit range: `8193'.
```

so `gas/config/tc-i51.c` treats >0x1FFF as an error and `bfd/elf32-i51.c` treats
it as a masking operation. Note that `tb/sim/run-reloc.py` **pins the current
behaviour as expected** (`('pcode-link-wrap', 0x2345, '034500', None)`), so this
is a deliberate decision rather than an oversight — but it is a decision that
only bites once a program is large enough to push a pcode target past 8K, which
is exactly the case a single-file test cannot reach. Worth revisiting; if the
mask stays, it deserves a warning.

## 4. LOW-MEDIUM — no linker option reports RAM headroom. `--print-memory-usage` only knows about `rom`.

The script declares one MEMORY region, `rom`. Every RAM space is an `(INFO)`
section with hand-written `ASSERT`s, so it is invisible to the region
accounting. A program using 200 of 256 bytes of internal RAM and 16K of xdata:

```
$ ld -o r.elf r.o --print-memory-usage
Memory region         Used Size  Region Size  %age Used
             rom:           2 B        64 KB      0.00%

$ readelf -S --wide r.elf | …
  .text    addr=00000000 size=000002
  .bss     addr=00000020 size=000064
  .idata   addr=00000084 size=000064
  .xdata   addr=00000000 size=004000
```

Two bytes of code, 0.00% of rom, and not a word about the 200 bytes of a
256-byte RAM already spent. On this part the RAM budget is the budget that
matters, and the only way to see it is to read `readelf -S` by hand. The `-Map`
output does list the space sections and their sizes, so the data exists; nothing
summarises it.

```
$ ld -o map.elf <201 objects> -Map map.txt
Memory Configuration
Name             Origin             Length             Attributes
rom              0x00000000         0x00010000         xr
*default*        0x00000000         0xffffffff
```

## 5. LOW — `--wrap` cannot work on this target, because gas folds every symbol to upper case and `ld` looks for a lower-case prefix.

```
$ ld --wrap=MALLOC -o c1.elf w.o wd.o
ld: w.o: in function `_START':
(.text+0x1): undefined reference to `__wrap_MALLOC'
$ echo $?
1
```

There is no assembler input that can define that symbol:

```
$ printf '        .text\n        .global __wrap_MALLOC\n__wrap_MALLOC: ret\n' > wl.s
$ as -o wl.o wl.s ; echo $?
0
$ readelf -s --wide wl.o | grep -i wrap
     … __WRAP_MALLOC
```

Supplying the upper-case spelling does not help — `ld` still asks for
`__wrap_MALLOC`. The same argument kills any `ld` feature keyed to a fixed
lower-case symbol name. Niche, and arguably a consequence of the uppercase fold
rather than of this axis, but it is a flatly broken option rather than an
unsupported one, and nothing says so.

## 6. LOW — RAM sections are emitted PROGBITS, so the linked ELF carries a byte on disk for every byte of RAM.

```
$ readelf -S --wide o8.elf
  [ 2] .xbss             PROGBITS        00000000 00005a 000040 00   W  0   0  1
```

A 64-byte `.xcomm` costs 64 bytes in the file. For a 2-byte program with 16K of
`.xdata` the ELF came out 17684 bytes. Harmless for the ROM image — `objcopy -j
.text` and `-O ihex` are unaffected — but the intermediate artefacts of a large
project grow with its RAM, not just its code.

## 7. LOW — SFR and register names are predefined symbols, so ordinary module-level labels collide.

Found by accident while generating inputs. Labels named `A`, `B`, `C`, `F0` all
fail:

```
$ as -o a2.o a2.s
a2.s:3: Error: symbol `B' is already defined
a2.s:3: Error: unknown instruction operand 1: `C'
```

Correct in isolation. Worth one line of documentation because at 200-module
scale the chance that some module wants a label named `B` or `F0` or `P1` is
high, and the message ("already defined") does not say *why*.

## 8. NOTE — there is no `.regbank` directive, and 0x00–0x1F is reserved unconditionally.

```
$ printf '        .regbank\nRB: .fill 64,1,0\n' > r.s ; as -o r.o r.s
r.s:1: Error: unknown pseudo-op: `.regbank'
```

`bfd/elf32-i51.c` maps `SHN_I51_REGBANK`/`.regbank` and the script has
`*(.regbank)`, but no assembler directive reaches it, so only the 2001 objects
can populate it. Meanwhile `.bdata MAX (0x20, …)` means `.bss` starts at 0x20
whatever the program does, i.e. all four register banks are always reserved —
24 bytes of a 256-byte RAM spent by a program that only uses bank 0. Both are
defensible design decisions; neither is written down.

---

# What works — checked, not assumed

Everything below was probed and passed.

**Many objects.** 501 modules, each `lcall`-ing three others in a wrap-around
pattern plus two `mov dptr,#sym` data references, all cross-referencing in every
direction:

```
  assemble 501 files: 734 ms
  link 501 objects:    32 ms  exit=0
  .text size=0x002cee
  checked 2500 refs across 500 modules, 0 wrong
```

The verifier re-derives each expected target from the generator's rule and
compares it against the bytes in the linked image. Nothing scales badly —
linking 501 objects takes 32 ms.

**Symbol resolution at scale.**

| case | result |
|---|---|
| 40 objects defining the same global | exit 1, **39** `multiple definition` diagnostics, first-definition named correctly |
| 100 undefined symbols in one object | exit 1, **100** `undefined reference` lines — no cap, no truncation |
| weak definition + strong definition, either order | strong wins both times (`WSYM` at the strong object's address) |
| undefined weak reference | links, resolves to 0: `12 00 00  lcall 0x0000` |
| weak definition only in an archive member | member **not** pulled, exit 0 — correct |
| same common, ten different sizes across ten files | `.bss size=0x28` — largest wins, correct |

**Memory-space commons across many files.** They keep their space in a plain
link, and they survive a chain of relocatable links:

```
$ ld -r -o r1.o <201 objects> ; ld -r -o r2.o r1.o ; ld -r -o r3.o r2.o
$ ld -o rfinal.elf r3.o
  r1.o: PRC[0xff04]  XSHARED
  r2.o: PRC[0xff04]  XSHARED
  r3.o: PRC[0xff04]  XSHARED
```

and the final image is byte-identical to a direct link of the same 201 objects:

```
41226eba7c0a75127b988911fb89dd1d  a.bin      # via -r -r -r
41226eba7c0a75127b988911fb89dd1d  b.bin      # direct
```

with identical space allocation (`.bss 0x20/0x48`, `.ibss 0x68/0x20`,
`.xbss 0x320/0xa0`) either way. `ld -r` output is itself reproducible
(`aff563f9…` twice).

**Archives.** All nine cases behaved:

| case | result |
|---|---|
| members in dependency order | exit 0, all three pulled |
| members in **reverse** dependency order | exit 0, all three pulled |
| two archives in the wrong order | exit 1, correct `undefined reference to SYMB`, names the member `libx.a(a1.o)` |
| same, with `--start-group`/`--end-group` | exit 0, resolved |
| archive with **no symbol index** (`ar rc`) | exit 0, resolved |
| **stale index** (`ar rcs` then `ar rc` append) | exit 0, the appended member's `NEWSYM` resolved |
| duplicate member names in one archive | exit 0 |
| member defining `.xcomm`/`.icomm`/`.bitcomm` | pulled, each common in its own space (`.xbss 0x40`, `.ibss 0x08`, `.bitbss 0x01`) |
| memory-space common referenced from the main object, defined only in a member | member pulled, `.xbss` size 0x40 allocated |
| 200-member archive | exit 0, all 200 pulled, `.text` 0x322 |

**Region overflow.** Every space is diagnosed, by name, with a nonzero exit:

```
.text 0x10001            → ld: o.elf section `.text' will not fit in region `rom'   exit 1
.text 9 x 8K = 72K       → ld: o.elf section `.text' will not fit in region `rom'   exit 1
.text 0xFFFF             → exit 0                          (boundary correct)
idata 20 x 20 = 400 B    → ld: internal RAM overflow (past 0xFF)                    exit 1
bdata 5 x 8 = 40 B       → ld: bit-addressable data overflow (past 0x2F)            exit 1
bit space 5 x 40 = 200 b → ld: bit space overflow (past bit 0x7F)                   exit 1
xdata 9 x 8K = 72K       → ld: xdata overflow (past 0xFFFF)                         exit 1
```

The 16 bit-addressable bytes at 0x20–0x2F are a budget **shared** between
`.bdata` and the named bit space, and the split is enforced exactly — no false
positives, no false negatives:

```
bd=16 bi=0    OK      bd=17 bi=0    FAIL bit-addressable data overflow (past 0x2F)
bd=0  bi=128  OK      bd=0  bi=129  FAIL bit space overflow (past bit 0x7F)
bd=8  bi=64   OK      bd=8  bi=65   FAIL bit space overflow (past bit 0x7F)
bd=15 bi=8    OK      bd=9  bi=64   FAIL bit space overflow (past bit 0x7F)
                      bd=16 bi=8    FAIL bit space overflow (past bit 0x7F)
```

(`bd` = bytes of `.bdata`, `bi` = bits of `.bitbss`. 9 bytes + 64 bits is 17
bytes of a 16-byte area and is correctly refused.)

**Page and range boundaries created only by the link.** These are the errors a
single-file test cannot produce, and all of them are caught.

`ACALL`/`AJMP` where the 2K page violation only exists after linking — target in
one object, caller padded into a later page in another:

```
acall pad=0x40    ld OK    41: 11 00   acall 0x0000            (same page, correct encoding)
acall pad=0x900   ld FAIL  (.text+0x900): relocation truncated to fit: R_I51_11 against symbol `TARGET' defined in .text section in callee.o
acall pad=0x1000  ld FAIL  (.text+0x1000): relocation truncated to fit: R_I51_11 …
ajmp  pad=0x40    ld OK    41: 01 00   ajmp  0x0000
ajmp  pad=0x900   ld FAIL  … R_I51_11 …
ajmp  pad=0x1000  ld FAIL  … R_I51_11 …
```

The same violation inside one file is *not* diagnosed by the assembler
(`as` exit 0 — the fixup is section-relative, so it is deferred), but the linker
catches it:

```
$ ld -o one.elf one.o
one.o: in function `_START':
(.text+0x901): relocation truncated to fit: R_I51_11 against `no symbol'
$ echo $?
1
```

A relative branch to an external symbol, at the exact boundary:

```
pad=125  OK    0: 80 7d   sjmp .+0x7F   ; 0x007F
pad=126  OK    0: 80 7e   sjmp .+0x80   ; 0x0080
pad=127  OK    0: 80 7f   sjmp .+0x81   ; 0x0081      (disp = +127, the maximum)
pad=128  FAIL  (.text+0x1): relocation truncated to fit: R_I51_7_PCREL against symbol `FAR' …
```

and a branch that fits before the link but not after (0x200 away once linked)
fails with the same message, exit 1.

**Linker options.**

- `--gc-sections`: collects genuinely unreachable input sections
  (`.text` 0x47 → 0x06, `DEADFN` gone) and **keeps** referenced memory-space
  commons in their correct spaces (`.bss 0x20/4`, `.ibss 0x24/8`,
  `.xbss 0x00/0x10` with `mov a,0x20` / `mov R0,#0x24` unchanged). Unreferenced
  commons are dropped, which is what the option is for.
- `--defsym EXTCONST=0x1234 --defsym EXTFUN=0x0007` → `90 12 34` and `12 00 07`.
  Correct.
- `-u NEEDED` pulls the archive member that plain linking leaves out (0 → 1).
- `-Map` on 201 objects: 2149 lines, correct `Memory Configuration` block,
  per-object `.text` placement, an `Allocating common symbols` table naming
  `SHARED 0x8` and `XSHARED 0x20`, and the space sections with their addresses.
- `--cref` on 201 objects: 2249 lines, every symbol attributed to its object.
- `objcopy -O ihex` on a 0xC001-byte image: exit 0, 3074 records, correct
  `:00000001FF` terminator, and `objcopy -I ihex -O binary` round-trips to a
  byte-identical 49153-byte image. (No extended-address records appear, and none
  should — the code space is 64K, so every address fits the 16-bit field.)

**Determinism.** Byte-identical output in every dimension tested:

```
same command run twice                       c150bc3380d70b525cba110284e805c6  (both)
run from a different working directory       c150bc3380d70b525cba110284e805c6
the whole tree copied to a different path    c150bc3380d70b525cba110284e805c6
objcopy -O binary -j .text of the above      41226eba7c0a75127b988911fb89dd1d  (both)
ld -r of 201 objects, twice                  aff563f98bbaa64eccea959fef3bbd31  (both)
4 files assembled serially vs in parallel    identical
```

Absolute paths do not leak into the image. Reversing the link order of the same
201 objects moves addresses, as it must, and the resulting image still verifies:
`checked 1000 refs across 200 modules, 0 wrong`.

---

# Summary

| # | Severity | Finding |
|---|---|---|
| 1 | HIGH | Direct-addressed RAM unbounded past 0x7F — variables silently become SFR accesses. `ld/scripttempl/elf32i51.sc`. Corroborated independently. |
| 2 | HIGH | Same symbol as a common in two memory spaces: silently unified, link-order dependent. `bfd/elf32-i51.c`. |
| 3 | MEDIUM | `.pcode` symbol past 0x1FFF silently masked at link time; the same value as a constant is an assembly error. `bfd/elf32-i51.c`, pinned by `tb/sim/run-reloc.py`. |
| 4 | LOW-MED | No RAM budget reporting; `--print-memory-usage` sees only `rom`. |
| 5 | LOW | `--wrap` unusable — gas uppercases, `ld` wants `__wrap_`. |
| 6 | LOW | RAM sections emitted PROGBITS; ELF carries a byte per RAM byte. |
| 7 | LOW | SFR/register names are predefined, so labels named `A`, `B`, `C`, `F0` … collide. |
| 8 | NOTE | No `.regbank` directive; 0x00–0x1F reserved unconditionally. |

Nothing broke at scale. 501 objects, 2500 cross-module references, 200-member
archives, `-r` chains three deep and every archive-ordering variant all produced
correct, reproducible images. The failures found are all cases where the tools
accept something and quietly produce the wrong program — and finding 1 is the
one an ordinary multi-module project will hit first, without any warning that it
has.

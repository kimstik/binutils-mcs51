# EM_I51: what the legacy value costs, and what happens to the 2001 objects

Branch `claude/em-legacy`, cut from `origin/work/green`. Review only, nothing patched.

Scope: the practical cost. The registry question belongs to another agent and is not
touched here.

Everything below was measured. Every claim carries the command that produced it.

---

## 0. Summary, up front

1. The 2001 lineage value is **0x7262, big-endian**. Measured on 246 ELF images.
2. The port's legacy escape hatch is `EM_I51_OLD 0x1051`. **No 2001 object carries
   0x1051.** Not one. 0x1051 was invented in 2025 by this repo's own converter
   (`tb/i51elf_le2be.py` line 38, hardcoded).
3. The port **cannot read a genuine 2001 object.** `objdump: architecture UNKNOWN!`,
   `ld: relocations in generic ELF (EM: 29282)`, `error adding symbols: file in wrong
   format`. Confirmed, not refuted.
4. `make check` links **zero** genuine objects. All 221 ELF images it consumes were
   produced by this repo's own scripts. Legacy compatibility is **theatre**.
5. Re-stamping is **not** a one-byte rewrite. Byte order and symbol case ride with it,
   and both are load-bearing. Proved below.
6. Cheapest option is **(a)**: emit EM_8051, read only EM_8051. Cost is a two-byte
   rewrite of 221 images inside `tb/base.7z`. **Run: all ten ROMs unchanged,
   `tb/reference.md5` unchanged.**

---

## 1. What the web51 lineage actually defines

```
$ 7z x tb/ref.7z          # -> i51.patch.112n, i51.patch.112p (no objects, patches only)
$ grep -n "EM_I51\|TARGET_BIG_SYM\|ELF_MACHINE_CODE" i51.patch.112n i51.patch.112p
i51.patch.112n:718:+   elf_elfheader (abfd)->e_machine = EM_I51;
i51.patch.112n:1059:+ #define ELF_MACHINE_CODE      EM_I51
i51.patch.112n:1062:+ #define TARGET_BIG_SYM       bfd_elf32_i51_vec
i51.patch.112n:1063:+ #define TARGET_BIG_NAME      "elf32-i51"
i51.patch.112p:625:+ #define EM_I51                0x7262
```

Two facts, not one. The 2001 port is **0x7262** and it is **big-endian only**.

```
$ grep -c "0x1051" i51.patch.112n i51.patch.112p
i51.patch.112n:0
i51.patch.112p:0
```

0x1051 appears nowhere in the 2001 lineage. It appears in exactly three places in this
repo:

```
$ grep -rn "0x1051" mcs51/ tb/*.py README.md
mcs51/additions.patch:3893:+#define EM_I51_OLD 0x1051
tb/i51elf_le2be.py:36:    # e_machine at offset 18 (2 bytes) - change from 0x7262 to 0x1051
README.md:28:  stock `readelf` names them; the unregistered `0x1051` that the 2001
```

`README.md:28-29` says "the unregistered `0x1051` that the 2001 lineage used". **False.**
The 2001 lineage used 0x7262. 0x1051 is this repo's own invention, and the port's
`EM_I51_OLD` accepts a value no 2001 toolchain ever wrote.

`mcs51/modifications.patch:362` prints it as `"MCS-51 8-bit microcontroller (legacy web51
value)"`. Also false. It is not a web51 value.

---

## 2. Census: every ELF image in the repo, e_machine read byte-for-byte

Read at file offset 18, two bytes, byte order taken from `e_ident[EI_DATA]` at offset 5.
Archive members walked by hand. No PROVENANCE file consulted.

### Totals

| source | ELF images | 0x7262 BE (genuine 2001) | 0x1051 LE (repo-converted) | anything else |
|---|---:|---:|---:|---:|
| `tb/base2001.7z` | 182 | **182** | 0 | 0 |
| `tb/base.7z` | 285 | **64** | 221 | 0 |
| `tb/objects-report/staged/**` | 28 | **0** | 28 | 0 |
| `tb/ref.7z` | 0 | 0 | 0 | 0 (patch text only) |
| **total** | **495** | **246** | **249** | **0** |

Byte order is not mixed within a value: every 0x7262 image is `EI_DATA=2` (MSB), every
0x1051 image is `EI_DATA=1` (LSB). No image carries EM_8051.

### `tb/base2001.7z` — 182 images, all genuine

```
$ python3 census.py base2001 | tail -3
base2001/lib/web51_80.obj   0x7262  BE  e_machine_bytes=7262 e_type=1 class=1  EM_I51 (web51 2001)
--- TOTAL ELF images: 182
SUMMARY  e_machine=0x7262 endian=BE : 182
```

26 loose `cgi/*.obj` + `libcgi.a`(26) + `libk23.a`(27) + `libk80.a`(27) + `libw23.a`(37)
+ `libw80.a`(37) + `web51_23.obj` + `web51_80.obj` = 182.

### `tb/base.7z` — 285 images, per file

```
$ python3 table.py base
cgi/$(basename  .asm).obj          0x1051   LE     1     <- a Makefile artefact, literally named
cgi/bd.obj  ... cgi/xon.obj        0x1051   LE    26
cgi/libcgi.a                       0x1051   LE    26
lib/libk23.a                       0x1051   LE    27
lib/libk80.a                       0x1051   LE    27
lib/libw.a                         0x1051   LE    37
lib/libw23.a                       0x1051   LE    37
lib/libw80.a                       0x1051   LE    37
lib/web51.obj                      0x1051   LE     1
lib/web51_23.obj                   0x1051   LE     1
lib/web51_80.obj                   0x1051   LE     1
lib/lib23_old/libk23.a             0x7262   BE    27
lib/lib23_old/libw23.a             0x7262   BE    37
total images: 285
```

The only genuine objects in `base.7z` are the 64 in `lib/lib23_old/`. Nothing references
that directory:

```
$ grep -rn "lib23_old" base/    # (extracted base.7z, all files)
$ echo $?
1
```

Dead weight. Never opened by any build.

### `tb/objects-report/staged/**` — 28 images, none genuine

All 28 are byte-identical to the copies already in `base.7z`:

```
$ sh cmp.sh
SAME  cgi/xon.obj
SAME  cgi/bd.obj
... 28 lines, all SAME ...
SAME  lib/web51_80.obj
```

The directory is named "staged" and its `REPORT.md` discusses old big-endian 0x7262
objects. It contains none. It is a copy of the converted output.

---

## 3. Can the current port read a genuine 0x7262 object? No.

Toolchain: `make -C tb build` on this branch, binutils 2.47 + `mcs51/*.patch`, zero fuzz,
zero offset. Object: `base2001/cgi/testP3.obj`, untouched, 1004 bytes, 0x7262 BE.

```
$ readelf -h orig.obj
  Data:      2's complement, big endian
  Machine:   <unknown>: 0x7262

$ objdump -f orig.obj
orig.obj:     file format elf32-big
architecture: UNKNOWN!, flags 0x00000011:
HAS_RELOC, HAS_SYMS

$ objdump -d orig.obj
objdump: can't disassemble for architecture UNKNOWN!

$ nm-new orig.obj
00000000 r cgibegin
00000000 T testP3
         U pret
   (works - generic ELF reader, no i51 knowledge needed)

$ ld-new -r orig.obj -o /dev/null
ld-new: orig.obj: relocations in generic ELF (EM: 29282)
ld-new: orig.obj: error adding symbols: file in wrong format
```

**Confirmed.** `architecture UNKNOWN!` is real. 29282 == 0x7262.

`readelf` and `nm` "work" only because they fall through to the generic ELF reader;
neither knows the architecture. `objdump` cannot disassemble and `ld` cannot link. The
file lands on the stock `elf32-big` vector, not on `elf32-i51`.

### Why: two gates, and the machine number is the second one

`bfd/elfcode.h` in binutils 2.47 checks byte order **before** it checks `e_machine`:

```
bfd/elfcode.h:552   switch (x_ehdr.e_ident[EI_DATA])
bfd/elfcode.h:554     case ELFDATA2MSB:      /* Big-endian */
bfd/elfcode.h:555       if (! bfd_header_big_endian (abfd))
bfd/elfcode.h:556         goto got_wrong_format_error;
...
bfd/elfcode.h:607   if (ebd->elf_machine_code != i_ehdrp->e_machine
bfd/elfcode.h:609       && (ebd->elf_machine_alt1 == 0
bfd/elfcode.h:610           || i_ehdrp->e_machine != ebd->elf_machine_alt1)
```

And the port ships one vector, little-endian:

```
$ grep -n "i51_elf32" bfd/targets.c bfd/config.bfd
bfd/targets.c:762:extern const bfd_target i51_elf32_vec;
bfd/targets.c:1109:     &i51_elf32_vec,
bfd/config.bfd:648:    targ_defvec=i51_elf32_vec
$ grep -n "TARGET_LITTLE_SYM\|ELF_MACHINE_ALT1" mcs51/additions.patch
1037:+#define ELF_MACHINE_ALT1     EM_I51_OLD
1041:+#define TARGET_LITTLE_SYM    i51_elf32_vec
```

So even setting `ELF_MACHINE_ALT1 = 0x7262` would change nothing: a big-endian object
dies at the byte-order gate and never reaches the machine check. Four variants of the
same object, through the same tools:

| variant | EI_DATA | e_machine | `objdump -f` | `ld -r` |
|---|---|---|---|---|
| `orig` — untouched 2001 | BE | 0x7262 | `elf32-big`, arch UNKNOWN! | wrong format (EM 29282) |
| `A` — e_machine -> 0x1051 only | BE | 0x1051 | `elf32-big`, arch UNKNOWN! | wrong format (EM 4177) |
| `B` — e_machine -> 165 only | BE | 165 | `elf32-big`, arch UNKNOWN! | wrong format (EM 165) |
| `C` — full byte swap, keep 0x7262 | LE | 0x7262 | `elf32-little`, arch UNKNOWN! | wrong format (EM 29282) |
| `D` — full byte swap + 0x1051 | LE | 0x1051 | **`elf32-i51`, architecture: i51** | reads |

`B` is the important row. Stamping the *registered* value on a genuine object still
fails. `C` is the other one: fixing byte order but keeping the legacy value still fails.
Only both together work.

---

## 4. What the testbench actually links

`tb/Makefile:46` — `DATA_OVERLAY ?=` — empty by default. `make check` extracts
`base.7z` and nothing else (`tb/Makefile:180-193`). `base2001.7z` is reached only by
`check-frozen` (`tb/Makefile:269-270`), which feeds the **2.11.2** toolchain.

What the ten projects put on the linker command line:

```
$ grep -h "LINKER\|CGI *=\|LIBDIR)/" base/projekt/*/Makefile | sort -u
CGI   = $(CGIDIR)/testP3.obj                    (and 4 other CGI sets)
www8051.o : $(OBJS) $(CGI) $(LIBDIR)/libw80.a $(LIBDIR)/libk80.a $(LIBDIR)/web51_80.obj
www8051.o : $(OBJS) $(CGI) $(LIBDIR)/libw23.a $(LIBDIR)/libk23.a $(LIBDIR)/web51_23.obj
```

No rule rebuilds `cgi/*.obj` or `lib/*.a`. They are consumed as `base.7z` ships them.
Every one of them is 0x1051 LE — output of `tb/i51elf_le2be.py` + `tb/i51elf_sym_uc.py`.
Proof, byte-for-byte:

```
$ python3 tb/i51elf_le2be.py base2001/cgi/testP3.obj p1.obj
$ python3 tb/i51elf_sym_uc.py p1.obj p2.obj
pipeline out : 71e6be54b6efd9f20e99ff30ed9224ac
base.7z copy : 71e6be54b6efd9f20e99ff30ed9224ac
staged copy  : 71e6be54b6efd9f20e99ff30ed9224ac

$ python3 tb/i51elf_ar.py base2001/lib/libk80.a libk80.a
ar pipeline  : f4b0643a750db5849828bf210367cb71
base.7z lib  : f4b0643a750db5849828bf210367cb71
```

### Verdict

**Legacy compatibility is theatre.** `make check` on `work/green` touches zero genuine
2001 objects. The 64 that survive in `base.7z` sit in `lib/lib23_old/`, which nothing
opens. `EM_I51_OLD` is exercised only against artefacts this repo produced, stamped with
a value this repo chose. Nothing in the merge gate would notice if `EM_I51_OLD` were
deleted **and** `base.7z` re-stamped in the same commit — section 6 runs exactly that and
it stays green.

The `check-frozen` path is the one that does read genuine objects, and it reads them with
the **2001** toolchain, not the port. It says nothing about the port's legacy support.

---

## 5. Conversion: not a one-byte rewrite

`tb/i51elf_le2be.py` is 190 lines and it changes:

- `e_ident[EI_DATA]` 2 -> 1
- all 13 fields of the ELF header
- all 10 fields of every section header (12 here)
- `st_name`, `st_value`, `st_size`, `st_shndx` of every symbol
- `r_offset`, `r_info`, `r_addend` of every RELA entry (3 reloc sections here)
- and it hardcodes `data[18:20] = struct.pack('<H', 0x1051)`

Section 3 already showed byte order alone is not enough and the machine number alone is
not enough. There is a third thing: **symbol case**. The port's gas uppercases symbols;
2001's did not.

```
$ nm-new D_le_1051.obj              # genuine object, byte order fixed, case untouched
00000000 r cgibegin      00000000 T testP3       U pret   U state80   U zflag
$ nm-new base/cgi/testP3.obj        # what check actually links
00000000 r CGIBEGIN      00000000 T TESTP3       U PRET   U STATE80   U ZFLAG
```

Substitute the byte-order-only conversion into `led1`'s real link and it dies:

```
$ make -C case/projekt/led1               # baseline, base.7z object
  LINK OK, rom md5 bd336522c8c54be539f2e45d5bbe7888

$ python3 tb/i51elf_le2be.py base2001/cgi/testP3.obj case/cgi/testP3.obj
$ make -C case/projekt/led1
ld-new: (.text+0x3): undefined reference to `zflag'
ld-new: (.text+0x5): undefined reference to `state80'
ld-new: (.text+0x9): undefined reference to `zflag'
ld-new: (cpu_files+0x3): undefined reference to `pret'
make: *** [Makefile:72: www8051.o] Error 1
```

So re-stamping a 2001 object needs three things, in order of size: byte order (whole
header, all section headers, all symbols, all relocs), symbol case (rewrites `.strtab`
in place and, in archives, the armap), and only then the two bytes of `e_machine`.
`objcopy` does none of it. `tb/i51elf_ar.py` exists precisely because the archive armap
has to be rewritten too.

**e_machine is the smallest of the three problems and the only one anyone talks about.**

---

## 6. Cost of each option, measured

`tb/reference.md5` hashes `projekt/*/www8051.rom`, which is `objcopy -j .text -O binary`
of the linked output. `e_machine` of an *input* object cannot reach that byte stream.
Tested rather than asserted.

### Baseline, this branch, unmodified

```
$ make -C tb check BUILD=work/modern/build
PASS diag     1267 84779b2386ba64a0347e227ac09cf18a
PASS ds1620   6284 5bd93daf7609853f6c3db6541060c420
PASS ds1822   6078 733b5d0483c7cd324156cd36da1743a6
PASS lcd      5754 7c0f4fccb4e9ee7305c1f8c8fe7bee1e
PASS led1     5173 bd336522c8c54be539f2e45d5bbe7888
PASS led2     5010 97e9cf0cf06ebf6ff10e98a6420f6f63
PASS led3     5200 470097b25def9f33cde74fdb4c6264f1
PASS serial   8128 94c14915a302c599ff91b88244319f4d
PASS welcome  4812 0244913c2585c0dc9995a5e6a2e95d6d
PASS wjava    4812 bbdbcb2b80d62a384aa8f3ec9d407315
all 10 projects match the reference
```

### Option (a) — emit registered, read only registered

Requires re-stamping `base.7z`'s 221 images from 0x1051 to 165. Two bytes per image, at
file offset 18, no length changes, no armap changes. Done and run:

```
$ python3 restamp.py ov          # 0x1051 -> 165 on every LE i51 image, loose and in archives
restamped lib/libk80.a    images=27
restamped lib/libk23.a    images=27
TOTAL restamped ELF images: 221
$ python3 census.py ov | tail -1
SUMMARY  e_machine=0x00a5 endian=LE : 221

$ make -C tb check BUILD=work/modern/build DATA_OVERLAY=/tmp/em51/em8051-overlay.7z
PASS diag     1267 84779b2386ba64a0347e227ac09cf18a
PASS ds1620   6284 5bd93daf7609853f6c3db6541060c420
PASS ds1822   6078 733b5d0483c7cd324156cd36da1743a6
PASS lcd      5754 7c0f4fccb4e9ee7305c1f8c8fe7bee1e
PASS led1     5173 bd336522c8c54be539f2e45d5bbe7888
PASS led2     5010 97e9cf0cf06ebf6ff10e98a6420f6f63
PASS led3     5200 470097b25def9f33cde74fdb4c6264f1
PASS serial   8128 94c14915a302c599ff91b88244319f4d
PASS welcome  4812 0244913c2585c0dc9995a5e6a2e95d6d
PASS wjava    4812 bbdbcb2b80d62a384aa8f3ec9d407315
all 10 projects match the reference
```

Every ROM md5 identical to the baseline. **`tb/reference.md5` does not move. Reference
ROMs do not move.**

Cost:
- ten projects: **nothing**, proved above
- `tb/base.7z`: repack with 221 two-byte edits, in the same commit
- staged objects: 28 of them, same two-byte edit, or delete the tree — it is a duplicate
  of `base.7z` and it is stale documentation either way
- frozen 2.11.2 line: **nothing**. `check-frozen` overlays `base2001.7z`, which replaces
  all 33 live precompiled paths with the 0x7262 originals; the 2.11.2 tools never see a
  re-stamped file. `tb/frozen-report.md` and `tb/frozen.expect` untouched.
- code: delete `EM_I51_OLD`, `ELF_MACHINE_ALT1`, two `case EM_I51_OLD:` arms in readelf,
  and `get_machine_name`'s wrong label. Four hunks smaller.
- `tb/i51elf_le2be.py:38`: `0x1051` -> `165`, and its docstring.
- what is lost: nothing that ever worked. The port could not read a genuine object before
  and cannot after.

### Option (b) — emit registered, accept a legacy alt on input

This is what green does today, and section 3 shows **the alt it accepts is the wrong
value**. Two sub-cases:

- *(b) as shipped, alt = 0x1051.* Costs nothing to keep, buys nothing. It admits only
  files this repo produced. The `README` and `get_machine_name` claims about it are false
  and would have to be corrected regardless.
- *(b) done honestly, alt = 0x7262.* Reading a genuine object also needs a big-endian BFD
  vector: `TARGET_BIG_SYM` in `elf32-i51.c`, a second entry in `bfd/targets.c` and
  `bfd/config.bfd`, a big-endian `ld` emulation and its `.sc` in `ld/emulparams` +
  `ld/Makefile.am`, plus `--enable-targets` fallout. Then the symbol-case wall in section
  5 still stops every link against freshly assembled sources. New surface, new gate
  stages needed to cover it, and the objects still do not link. **Highest cost, lowest
  return.**

### Option (c) — keep a private value

```
$ /usr/bin/readelf -h base/cgi/testP3.obj   | grep -i machine
  Machine:   <unknown>: 0x1051
$ /usr/bin/readelf -h orig.obj              | grep -i machine
  Machine:   <unknown>: 0x7262
$ /usr/bin/readelf -h work/tb/projekt/led1/www8051.o | grep -i machine
  Machine:   Intel 8051 and variants
```

Every non-port tool prints `<unknown>` for a private value. `make check` passes either
way — the gate is blind to `e_machine` entirely. Cost is permanent: no stock binutils,
no `file`, no third-party ELF reader ever names the architecture, and the repo goes on
carrying a value it invented while claiming it came from 2001.

### Which costs least

**(a).** It is the only option whose full price has been paid and measured in this
report: 221 two-byte edits, one `base.7z` repack, ten ROMs unchanged, `reference.md5`
unchanged, frozen line unchanged, and four hunks of code deleted. (b) as shipped costs
nothing but is a lie in the README. (b) done honestly costs a whole new BFD vector and
still does not link. (c) costs interoperability forever.

---

## 7. What must happen to the legacy objects

Nothing has to happen to them, because nothing reads them.

- `tb/base2001.7z` (182 images, 0x7262 BE): **leave untouched.** It is the input to the
  2.11.2 frozen line and that toolchain reads only this format. Re-stamping it would
  break `check-frozen`.
- `tb/base.7z` `lib/lib23_old/` (64 images, 0x7262 BE): unreferenced by every Makefile.
  Either delete it or say in `base.7z`'s provenance that it is a pristine sample kept for
  reference. It is currently neither documented nor used.
- `tb/base.7z` live inputs (221 images, 0x1051 LE): re-stamp to 165 under option (a).
  Reproducible from `base2001.7z` by `i51elf_le2be.py` / `i51elf_sym_uc.py` /
  `i51elf_ar.py` with one constant changed, so nothing is lost.
- `tb/objects-report/staged/**` (28 images): byte-identical duplicates of `base.7z`. Its
  `REPORT.md:13` describes them as "old big-endian ELF, `e_machine=0x7262`". They are
  little-endian 0x1051. Delete the tree or fix the text.

---

## Appendix: reproduction

```
git checkout -b claude/em-legacy origin/work/green
make -C tb build                                    # binutils 2.47 + mcs51/*.patch
7z x -o/tmp/em51/base       tb/base.7z
7z x -o/tmp/em51/base2001   tb/base2001.7z
7z x -o/tmp/em51/ref        tb/ref.7z
```

Then read `e_machine` at offset 18 with the byte order from offset 5, walking `!<arch>\n`
members by their 60-byte headers. All numbers in this report come from that read, never
from a PROVENANCE file.

Toolchain under test: `work/modern/build/{gas/as-new,ld/ld-new,binutils/{objdump,readelf,nm-new,objcopy}}`,
built from this branch with `OPTFLAGS=-O1`, both patches applied at zero fuzz and zero offset.

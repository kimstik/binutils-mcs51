# Robustness of the i51 port against hostile and malformed input

A binutils backend parses untrusted files by definition. This round attacks the
port with that in mind: malformed ELF, arbitrary bytes through the
disassembler, hostile assembler source, corrupt archives. Nothing here is about
whether the port produces correct code — earlier rounds cover that.

Everything below is a command and its output. Nothing is asserted that the
harness did not produce.

## Result

**20 crashes / sanitizer reports. 18 are the port's own code. 2 are upstream
gas, reached but not caused by the port.** After the fix below, a full re-run
reports 2 - the same two upstream ones.

All 18 have one root cause, in one function, and one fix, applied here:
`i51_final_link_relocate ()` in `bfd/elf32-i51.c` indexed the section contents
buffer with the relocation's `r_offset` without ever checking it against the
section, giving an attacker-controlled out-of-bounds **read and write** inside
`ld`.

| # | Severity | Where | What | Status |
|---|----------|-------|------|--------|
| 1 | **High** | `bfd/elf32-i51.c` `i51_final_link_relocate` | OOB write (`bfd_put_8`/`bfd_putb16`) at attacker-chosen offset during a final link | **fixed** |
| 2 | **High** | same function | OOB read (`bfd_get_8`/`bfd_getb16`) at attacker-chosen offset | **fixed** (same check) |
| 3 | Medium | `bfd/elf32-i51.c` `elf32_i51_relocate_section` | a malformed object that trips `bfd_reloc_outofrange` produces a *warning* and a successful link | report only |
| 4 | Low | upstream `gas/expr.c` | stack overflow on deeply nested parentheses | not ours — stock gas 2.42 does the same |
| 5 | Low | upstream `ld` + `ld/scripttempl/elf32i51.sc` | `sh_addralign = 0x80000000` costs 15 s of CPU for one link | not ours |

## How it was built and run

Two builds of the port on binutils 2.47, from `mcs51/*.patch`:

```
$ make -C tb build                      # the ordinary release build
$ .../configure --target=i51-elf --disable-nls --disable-werror \
    --disable-gdb --disable-shared --disable-gprofng \
    CFLAGS='-g -O1 -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer' \
    CXXFLAGS='...same...' LDFLAGS='-fsanitize=address,undefined'
$ nm asan/binutils/objdump | grep -c '__asan_report\|__ubsan_handle'
```

Every tool in the sanitizer build carries both ASAN and UBSAN:

```
binutils/objdump         ASAN UBSAN
binutils/readelf         ASAN UBSAN
gas/as-new               ASAN UBSAN
ld/ld-new                ASAN UBSAN
binutils/nm-new          ASAN UBSAN
binutils/objcopy         ASAN UBSAN
binutils/ar              ASAN UBSAN
binutils/strip-new       ASAN UBSAN
```

Everything below was run against the sanitizer build. Finding 1 turns out not
to need it — the release `ld` segfaults on that input too — but finding 2 does:
a one-byte overread does not fault, and the release `ld` says nothing about
it.

The harness is `tb/fuzz/`:

```
BUILD=<sanitizer build> tb/fuzz/run.sh /tmp/i51fuzz
```

Corpus, all generated, all deterministic:

| corpus | size | generator |
|--------|------|-----------|
| ELF mutants of one rich i51 object | 1512 | `tb/fuzz/elfmangle.py` |
| archive mutants | 95 | `tb/fuzz/armangle.py` |
| disassembler inputs | 523 | `tb/fuzz/gen_dis.sh` |
| hostile assembler sources | 406 | `tb/fuzz/gen_asm.sh` |
| random assembler sources | 2000 | `tb/fuzz/gen_asm_rand.py` |

The seed object (`tb/fuzz/seed.s`) carries one relocation of **every** type the
port defines — `R_I51_7_PCREL`, `R_I51_11`, `R_I51_16`, `R_I51_8`, `R_I51_L`,
`R_I51_H`, `R_I51_8_BIT`, `R_I51_8_B2B`, `R_I51_13_PCODE` — a memory-space
common in every space (`SHN_I51_REGBANK` … `SHN_I51_BITDATA_C`), bit data and a
`.pcode` record, so a single mutated copy reaches most of `bfd/elf32-i51.c`.

Each ELF mutant goes through eleven tool invocations (`nm`, `objdump -x/-D/-r`,
`readelf -a`, `objcopy`, `objcopy -O ihex`, `objcopy -O binary`, `strip`,
`ld -r`, `ld`); archives through five; disassembler inputs through two; each
assembler source through one: 18 600 runs in the pass that produced the 20
findings (the random assembler corpus was added afterwards), 20 600 in the
re-run after the fix. A signal, a sanitizer report or a 25-second timeout is a
finding; a diagnostic and a non-zero exit are not.

Rows 3 and 5 of the table above are not among the 20 - they are not crashes.
They were found alongside and are recorded because a future round would
otherwise have to find them again.

---

## 1 & 2 (High, ours, fixed) — unchecked `r_offset` in `i51_final_link_relocate`

### The bug

`bfd/elf32-i51.c` handles five relocation types itself and lets the rest fall
through to `_bfd_final_link_relocate ()`:

```c
    case R_I51_7_PCREL:
      contents += rel->r_offset;
      ...
      bfd_put_8 (input_bfd, srel, contents);
```

`r_offset` is a 32-bit field read verbatim out of the object file. The generic
path checks it — `_bfd_final_link_relocate ()` opens with

```c
  /* Sanity check the address.  */
  if (!bfd_reloc_offset_in_range (howto, input_bfd, input_section, octets))
    return bfd_reloc_outofrange;
```

— but the five cases the port handles itself never reached that code, and did
no equivalent check of their own. `R_I51_11` and `R_I51_13_PCODE` read two
bytes there (`bfd_getb16`), `R_I51_8_B2B` reads one, and all five write.

The same hole is reachable without touching a relocation at all: shrink
`.text`'s `sh_size` and every previously valid `r_offset` now points past the
end of the (smaller) contents buffer BFD allocated.

### Reproduction — out-of-bounds WRITE

`.rela.text` relocation 1 is an `R_I51_16` at `r_offset` 6; `.text` is 0x2b
bytes. Set `r_offset` to 0xffff:

```
$ tb/fuzz/elfmangle.py seed.o mutants/           # produces rel2_r1_off0000ffff.o
$ ld-new -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 --defsym EXTBIT=0x20 \
      -o /dev/null mutants/rel2_r1_off0000ffff.o
AddressSanitizer:DEADLYSIGNAL
==21842==ERROR: AddressSanitizer: SEGV on unknown address 0x50400001014f
==21842==The signal is caused by a WRITE memory access.
    #0 ... in bfd_putb16 bfd/libbfd.c:773
    #1 ... in i51_final_link_relocate bfd/elf32-i51.c:407
    #2 ... in elf32_i51_relocate_section bfd/elf32-i51.c:534
    #3 ... in elf_link_input_bfd bfd/elflink.c:11926
    #4 ... in _bfd_elf_final_link bfd/elflink.c:13189
    #5 ... in ldwrite ld/ldwrite.c:548
    #6 ... in main ld/ldmain.c:1001
```

`elf32-i51.c:407` is `bfd_putb16 ((bfd_vma) srel & 0xFFFF, contents);` in the
`R_I51_16` arm. The written value is `relocation + r_addend`, both from the
object file; the address is `contents + r_offset`, also from the object file.
Two attacker-controlled bytes at an attacker-controlled offset from a heap
buffer, during an ordinary `ld` of a supplied `.o`.

The sanitizer is not what makes this fatal. The **release** build, with the
fix removed and nothing else changed, dies the same way:

```
$ work/modern/build/ld/ld-new -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 \
      --defsym EXTBIT=0x20 -o out.elf tb/fuzz/repro/oob-write-r_offset.o
Segmentation fault
rc=139
```

Committed as `tb/fuzz/repro/oob-write-r_offset.o`.

### Reproduction — out-of-bounds READ

Set `.text`'s `sh_size` to 1 and leave the relocations alone:

```
$ ld-new -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 --defsym EXTBIT=0x20 \
      -o /dev/null mutants/sh01_text_sh_size_00000001.o
==26509==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x50200000043b
READ of size 1 at 0x50200000043b thread T0
    #0 ... in bfd_getb16 bfd/libbfd.c:745
    #1 ... in i51_final_link_relocate bfd/elf32-i51.c:358
    #2 ... in elf32_i51_relocate_section bfd/elf32-i51.c:534
    #3 ... in elf_link_input_bfd bfd/elflink.c:11926
    ...
0x50200000043b is located 0 bytes after 11-byte region [0x502000000430,0x50200000043b)
allocated by thread T0 here:
    #1 ... in bfd_malloc bfd/libbfd.c:291
    #2 ... in _bfd_elf_final_link bfd/elflink.c:13064
```

`elf32-i51.c:358` is `x = bfd_getb16 (contents);` in the `R_I51_11` arm. A
one-byte overread does not fault, so the **release** build, fix removed, says
nothing at all about it — but it says plenty about the *other* relocations in
the very same object:

```
$ work/modern/build/ld/ld-new ... -o out.elf tb/fuzz/repro/oob-read-sh_size.o
(.text+0x10): warning: internal error: out of range error
(.text+0x12): warning: internal error: out of range error
(.text+0x14): warning: internal error: out of range error
(.text+0x16): warning: internal error: out of range error
(.text+0x18): warning: internal error: out of range error
(.text+0x1a): warning: internal error: out of range error
(.text+0x1c): warning: internal error: out of range error
(.text+0x21): warning: internal error: out of range error
```

Those offsets are the `R_I51_8`, `R_I51_L`, `R_I51_H` and `R_I51_8_BIT`
relocations, which fall through to `_bfd_final_link_relocate ()` and are
correctly rejected by its address check. The offsets that are *missing* from
that list — 0x06, 0x08, 0x0a — are the `R_I51_16` and `R_I51_11` relocations
the port handles itself. The generic path had the check all along; only the
port's five types did not.

Committed as `tb/fuzz/repro/oob-read-sh_size.o`.

### All 18 reports, by crash site

```
ld_rel2_r1_off0000ffff.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel2_r1_off00010000.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel2_r1_off7fffffff.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel2_r1_offffffffff.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel2_r2_off0000ffff.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r2_off00010000.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r2_off7fffffff.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r2_offffffffff.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r3_off0000ffff.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r3_off00010000.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r3_off7fffffff.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel2_r3_offffffffff.log     bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
ld_rel4_r0_off0000ffff.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel4_r0_off00010000.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel4_r0_off7fffffff.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_rel4_r0_offffffffff.log     bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_sh01_text_sh_size_00000000  bfd_putb16 libbfd.c:773 | i51_final_link_relocate elf32-i51.c:407
ld_sh01_text_sh_size_00000001  bfd_getb16 libbfd.c:745 | i51_final_link_relocate elf32-i51.c:358
```

Every one is `i51_final_link_relocate`. The mutator only perturbs the first
four relocations of each relocation section, so the count is a floor, not a
census: any relocation with a bad `r_offset` does it.

### The fix

`bfd/elf32-i51.c`, at the top of `i51_final_link_relocate ()`, the same check
`_bfd_final_link_relocate ()` makes for everything else:

```c
  if (!bfd_reloc_offset_in_range (howto, input_bfd, input_section,
				  rel->r_offset
				  * bfd_octets_per_byte (input_bfd,
							 input_section)))
    return bfd_reloc_outofrange;
```

`howto` already carries the right sizes (1 for `R_I51_7_PCREL`, `R_I51_8_B2B`;
2 for `R_I51_11`, `R_I51_16`, `R_I51_13_PCODE`), so the check covers the
trailing byte of the two-byte relocations, which is where the read overflow
landed. The `default:` arm double-checks harmlessly.

After the fix, all six representative inputs diagnose instead of crashing:

```
rel2_r1_off0000ffff              clean rc=1
rel2_r2_off0000ffff              clean rc=1
rel2_r3_offffffffff              clean rc=1
rel4_r0_off7fffffff              clean rc=1
sh01_text_sh_size_00000000       clean rc=0
sh01_text_sh_size_00000001       clean rc=0
```

and a full re-run of the harness against the fixed sanitizer build reports
zero findings in the port's code.

---

## 3 (Medium, ours, report only) — `bfd_reloc_outofrange` is only a warning

Two of the six inputs above exit **0**. `elf32_i51_relocate_section ()` maps
`bfd_reloc_outofrange` onto

```c
	    case bfd_reloc_outofrange:
	      msg = _("internal error: out of range error");
	      ...
	  if (msg)
	    (*info->callbacks->warning) (info, msg, name, ...);
```

so an object whose relocations point outside their section now produces

```
ld-new: mutants/sh01_text_sh_size_00000001.o: warning: internal error: out of range error
```

and a successful link of a silently wrong output. That is better than a wild
read, but it is not a diagnosis.

Fixing it properly is structural, not a bounds check, so it is left as a report
item:

* `bfd_reloc_outofrange` is overloaded. The port already returns it from
  `R_I51_8_B2B` and `R_I51_13_PCODE` for a *value* that is not representable
  (`srel < 0x20`, `srel < 0x0100`), which is a user error in ordinary source —
  the unmodified `tb/fuzz/seed.s` produces two of these warnings on a clean
  link. Turning `bfd_reloc_outofrange` into a hard error would therefore also
  turn those into errors and change the behaviour of correct programs.
* The two need separating: a value that will not fit belongs in
  `info->callbacks->reloc_overflow` like `R_I51_7_PCREL` and `R_I51_11`
  already use, and a structurally impossible relocation belongs in a hard
  error that stops the link.
* The wording is also wrong. "internal error" tells a user that the linker is
  broken; the object is.

---

## 4 (Low, not ours) — gas stack overflow on nested parentheses

```
$ printf '\t.long %s1%s\n' "$(python3 -c 'print("("*50000,end="")')" \
                            "$(python3 -c 'print(")"*50000,end="")')" > deep.s
```

| depth | stock `as` 2.42 (x86-64, Ubuntu) | port `as` (release) | port `as` (ASAN) |
|-------|----------------------------------|---------------------|------------------|
| 10000 | 0 | 0 | 0 |
| 20000 | 0 | 0 | 139 |
| 50000 | **139** | **139** | 139 |
| 100000 | **139** | **139** | 139 |

Stock gas dies at the same depth as the port's gas. This is `expr.c`'s
recursive-descent parser with no depth limit, which every gas target shares;
the port neither causes it nor makes it worse. The ASAN build fails earlier
only because sanitizer frames are larger. Reproducer kept as
`tb/fuzz/repro/upstream-gas-deep-parens.s` so a future round does not re-file
it as ours.

## 5 (Low, not ours in code) — 22 s of CPU from a large `sh_addralign`

`sh_addralign = 0x80000000` on `.data` makes the port's `ld` place the output
section at 2^31 and then spend 15 seconds (release build; 22 in the sanitizer
build) laying out and discarding a 2 GB image:

```
$ time ld-new -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 --defsym EXTBIT=0x20 \
      -o big.elf mutants/sh03_data_sh_addralign_80000000.o
ld-new: internal RAM overflow (past 0xFF)
rc=1 elapsed=15387ms
(no output file)
```

The port's own linker script does notice: `internal RAM overflow (past 0xFF)`
is `ASSERT (__IDATA_END <= 0x100, ...)` at `ld/scripttempl/elf32i51.sc:206`.
But a failing `ASSERT` does not stop `ld` from finishing the link first, so
the work is done anyway. Stock `ld` with the same mutation on an x86 object
returns immediately, because an x86 layout puts the section somewhere
harmless; the difference is the linker script's low addresses, not port code.
Generic `ld` behaviour, recorded, not fixed. It sits right on the harness's
25-second timeout, which is why it shows up as a `TIMEOUT` in some passes and
not others - it is the harness's `TIMEOUT` classification that is arbitrary
here, not the behaviour.

## What did not break

Negative results, so a future round does not repeat this work.

**The disassembler is clean.** 523 objects: every one of the 256 opcodes placed
as the last byte of `.text`, every one placed one byte before the end so a
three-byte instruction runs off, an empty section, all 256 opcodes back to
back, all 256 padded, and eight 4 KB pseudo-random streams — through
`objdump -D` and `objdump -d -j .text`. No report.

This is structural, not luck: `print_insn_i51 ()` fetches every operand byte
through `info->read_memory_func`, checks the status, and returns -1 on failure:

```c
  status = info->read_memory_func (addr, buffer, 1, info);
  if (status != 0)
    { info->memory_error_func (status, addr, info); return -1; }
```

There is no direct indexing of the caller's buffer anywhere in
`opcodes/i51-dis.c`. The two adjacent hazards were checked by hand and are
absent as well:

* `opcode->args[0..2]` — every one of the 111 `I51_INS` entries in
  `include/opcode/i51.h` has a three-character `args` string, so indices 0..2
  are in bounds. Checked mechanically, not by eye.
* `inslen = opcode->insn_size & 0x03` can never be 0 for a matched opcode
  (sizes in the table are 1..3, optionally with bit 0x80), so `objdump` cannot
  be made to loop on a zero-length instruction.
* The `while ((opcode->insn_size & 0x80) == 0 && opcode->args[n] != mode)
  opcode++;` walks in `gas/config/tc-i51.c` are bounded by the 0x80 "last
  variant" flag. Every mnemonic group's final entry carries it — verified
  mechanically over all 111 entries — so the walk can never reach the
  `{NULL, NULL, 0, 0, 0}` sentinel and dereference `args == NULL`.

**The read side of the BFD backend is clean.** 1512 ELF mutants through `nm`,
`objdump -x/-D/-r`, `readelf -a`, `objcopy`, `objcopy -O ihex`,
`objcopy -O binary` and `strip`: no report. Truncation at every section
boundary, `e_shoff`/`e_shnum`/`e_shentsize`/`e_shstrndx`/`e_phoff`/`e_phnum`
corruption, per-section `sh_type`/`sh_flags`/`sh_offset`/`sh_size`/`sh_link`/
`sh_info`/`sh_addralign`/`sh_entsize`/`sh_name` corruption, the port's own
`SHF_CDATA` space codes stamped onto every section, out-of-range relocation
types, out-of-range symbol indices, symbols pointing at nonexistent sections,
symbols carrying every `SHN_I51_*` index and one past the last, overlapping
section offsets, all-zero and whole-file section sizes. The port's own input
paths that this exercises — `i51_info_to_howto_rela ()`,
`i51_elf_section_from_shdr ()`, `elf32_i51_symbol_processing ()`,
`elf32_i51_add_symbol_hook ()`, `i51_elf_common_section ()` — all hold up.

`i51_info_to_howto_rela ()` in particular already does the right thing:

```c
  if (r_type >= (unsigned int) R_I51_max)
    {
      _bfd_error_handler (_("%pB: invalid relocation type %d"), abfd, r_type);
      bfd_set_error (bfd_error_bad_value);
      return 0;
    }
```

**A local symbol with a `SHN_I51_*` index does not crash the linker.** This was
the second thing looked for after the `r_offset` hole, because
`elf32_i51_add_symbol_hook ()` only sees globals and generic
`elf_link_input_bfd ()` leaves `isec = NULL` for an unrecognised reserved
index, which would make `sec->output_section` in `elf32_i51_relocate_section ()`
a null dereference. It does not happen — `ld -r` rejects the object first:

```
$ ld-new -r -o /dev/null mutants/sym1_shndx_RDATA_C.o
ld-new: final link failed: bad value
```

and the final link reaches `relocate_section` with a non-null section. Checked
for `SHN_I51_REGBANK`, `_RDATA_C`, `_BITDATA_C` and one past the last
(`SHN_LORESERVE + 7`), on the `.text` section symbol, which is the one the
relocations actually name.

**The archive path is clean.** 95 mutants — truncation every 7 bytes through
the first 512, magic only, empty, corrupted magic, and per-member negative /
huge / blank / non-numeric size fields, corrupted header trailers, long-name
references past the end of the string table, garbage member bodies — through
`ar t`, `ar p`, `nm`, `ld -r` and `objdump -x`. No report. The port adds no
archive code; this is generic BFD, and it holds.

**The assembler is clean apart from the upstream recursion.** 406 hand-written
hostile sources and 2000 random ones. The hand-written set covers: empty input,
a one-byte file, 4 KB of `/dev/urandom`, NUL bytes, no trailing newline; every
one of the port's 30 directives with no argument, a bare comma, eight commas,
garbage, a negative argument, a 20-digit argument, a negative size, a
0x7fffffff size, a non-power-of-two alignment, a negative alignment and an
unterminated string; `.using` with nothing, at EOF with no newline, with 4,
with -1, with an expression, with a symbol, and used without `.using` at all;
`0x20.99`, `0xff.0`, `0x00.0`, a trailing dot, a negative bit base, a 48-bit
bit base, `.bit` with 2 / -1 / 0x7fffffff / nothing / a comma; `B2B(` with no
closing paren, no comma, a negative offset, a 99999 offset and a
non-bit-addressable base; 20000-deep unary chains, a 50000-term `+` chain,
a 100000-character symbol name, a 1 MB line, a 100000-character mnemonic,
50000 labels, division by zero, modulo by zero, a 96-bit constant, `1 << 9999`,
unterminated strings, `@` and `#` and `/` prefixes with nothing behind them,
`HIGH(` and `LOW(` with no closing paren, trailing commas, extra operands,
missing operands, unknown mnemonics, `.pcode` with every arity from zero to
four and with -1 and 0xffffffff operands, and `.local` with nothing, a comma,
built-in register names and a quoted string. Every one is diagnosed; none
crashes.

The random set is token soup built from the port's own vocabulary — the 43
mnemonics, the 27 register and SFR operand names, the `#`/`/`/`@`/`#HIGH(`/
`#LOW(`/`B2B(`/`#SWAP`/`#SHL8` prefixes, 37 hostile numeric literals, the 30
directives and 26 punctuation characters — glued at random and seeded by file
name, so any future crash is reproducible from the file it is in.

## The fix does not move anything

The patch was refreshed into `mcs51/additions.patch`, the tree rebuilt from
scratch with `patch --fuzz 0`, and the whole existing suite re-run against the
result:

```
$ make -C tb build
$ diff -u <edited source> work/modern/binutils-2.47/bfd/elf32-i51.c
SOURCE IDENTICAL

$ make -C tb gate BUILD=work/modern/build
...
all 10 projects agree with the 2001 oracle: recorded size delta, every differing byte accounted for
gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons oracle)

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

Ten reference ROMs, byte for byte. The check only rejects relocations that
point outside their own section, which no relocation any of these ten projects
emits ever does.

After the fix `ld` reports the offsets it used to walk off the end of:

```
$ BUILD=work/modern/build tb/fuzz/repro/repro.sh
================ oob-write-r_offset.o (wild write)
(.text+0xffff): warning: internal error: out of range error
rc=1
================ oob-read-sh_size.o (wild read)
(.text+0x4): warning: internal error: out of range error
(.text+0x6): warning: internal error: out of range error
(.text+0x8): warning: internal error: out of range error
(.text+0xa): warning: internal error: out of range error
...
```

0x06, 0x08 and 0x0a — the three that were silently overrunning before — are
now in the list. Which is also finding 3: the message is still a warning and
still says "internal error".

## Re-running

```
$ make -C tb build                                    # or a sanitizer build
$ BUILD=<build dir> tb/fuzz/run.sh /tmp/i51fuzz
$ BUILD=<build dir> tb/fuzz/repro/repro.sh            # the three known inputs
```

`run.sh` prints one line per finding and leaves the tool's full output in
`<outdir>/logs/`. It is not wired into `make gate`: it needs a sanitizer build
to be worth anything, and 20 500 sanitized tool runs take about fifteen minutes
on four cores.

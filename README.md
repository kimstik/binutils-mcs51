# binutils-mcs51

GNU binutils for the Intel MCS-51 / 8051.

It started as a patch against **binutils 2.11.2**, published on
http://web51.hw.cz in December 2001, and was forward-ported. The port
now applies to **binutils 2.47** as two patches, `mcs51/additions.patch`
(new files) and `mcs51/modifications.patch` (edits to existing files).

## Building

```
tar xf binutils-2.47.tar.xz && cd binutils-2.47
patch -p1 < .../mcs51/additions.patch
patch -p1 < .../mcs51/modifications.patch
./configure --target=i51-elf --disable-gdb   # bare --target=i51 works too
make
```

`tb/Makefile` (`make build`) automates exactly this, tarball download and
checksum included. `--enable-targets=all` and out-of-tree build dirs work.

## Target identity

- triplet `i51-elf` (canonicalises to `i51-unknown-elf`), object format
  `elf32-i51`, architecture `bfd_arch_i51`, linker emulation `elf32i51`
- output objects carry the registered ELF machine `EM_8051` (165), so a
  stock `readelf` names them
- objects are `ELFDATA2MSB`, container and section contents alike: everything
  the assembler writes into a section is high byte first, as the instruction
  set and Intel's `DW` define it. The MCS-51 has no architectural byte order -
  it has no 16-bit load or store to data memory at all - so little-endian data
  is written per datum, `.byte LOW(x), HIGH(x)`. There is no `-EB`/`-EL`.

## Changes from the 2001 port

`tb/ref.7z` holds the 2001 patch and `make frozen` builds it, so every claim
below can be checked against it.

Already there in 2001, and not this work: `TEMPLATE_NAME=generic` in the
emulparams file, and a custom `ld/scripttempl/elf32i51.sc` - 235 lines
declaring six `MEMORY` regions (text, bit, data, xdata, edata, eeprom) and
placing each section into one with `> region`. The memory spaces themselves,
the input section names that feed them and the address arithmetic that chains
one space to the next are 2001's as well.

What this work changed:

- One `MEMORY` region, `rom`, now holds the code, and every RAM space -
  regbank, rdata/rbss, bdata/bbss, bit, data/bss, idata/ibss, xdata, edata,
  eeprom - became a non-alloc `(INFO)` section at its real address inside its
  own space. Disjoint spaces may then share VMA ranges without tripping the
  linker's overlap check, and `objcopy -O ihex` extracts just the code image.
  `ASSERT`s bound the internal RAM, the bit space and the two external ones.
- Compiler-independent startup hooks, absent from all 235 lines of the 2001
  script: `.text` ends in `__I51_RET = . ; BYTE(0x22)`, and
  `__GSINIT_STARTUP`, `__EXTERNAL_STARTUP` and `__INIT_DATA` are PROVIDEd
  against it, so a runtime that leaves one undefined calls a bare RET instead
  of jumping into the reset vector. `ENTRY(_START)` is new too; 2001 named no
  entry point.
- The assembler folds symbol names to upper case, as MCS-51 assemblers do
  (`symbols_case_sensitive = 0`, which 2001 never set). Every symbol the
  script defines for use from code is spelled upper case accordingly -
  `STACK` where 2001 provided `stack`.
- `e_machine` is the registered `EM_8051` (165), not 2001's unregistered
  `EM_I51` 0x7262.
- The emulparams file adds `EXTRA_EM_FILE=genelf`, and the emulation is named
  `elf32i51` where 2001 spelled it `elf32_i51`.

## References

- the original port: http://web51.hw.cz
- an independent port of the same lineage onto binutils 2.38: https://github.com/github0null/binutils-mcs51
- sdcc-adjacent work referenced by the 2.45.1 release: https://github.com/volumit/sdcc_aurix_scr_42

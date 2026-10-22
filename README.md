# binutils-mcs51

GNU binutils for the Intel MCS-51 / 8051.

It derives from the port of **binutils 2.11.2** published on
http://web51.hw.cz in December 2001, and applies to **binutils 2.47** as two
patches, `mcs51/additions.patch` (new files) and `mcs51/modifications.patch`
(edits to existing files).

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

## Releases

A tag matching `v*`, or a hand dispatch of `.github/workflows/release.yml`,
publishes one stripped archive per host, both patches, and a `SHA256SUMS` over
all of it. A push to main publishes nothing.

Nothing is published from a tree that has not passed the gate: its sixteen
stages and the testbench canary run in the release run itself, and the
publishing job cannot start while any of them is red. The release note carries the binutils release, that tarball's
sha256 and the commit built from, all of them checked before the release is
created rather than typed into it.

Each archive unpacks to a directory of its own name holding `bin/`, the licence
and a `BUILD-INFO.txt` repeating those same three facts, so an unpacked copy
still says what it is.

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

## Differences from the 2001 port

`tb/ref.7z` holds the 2001 patch and `make frozen` builds it, so the
comparison below can be checked against it.

Shared with the 2001 port: `TEMPLATE_NAME=generic` in the emulparams file, and
a custom `ld/scripttempl/elf32i51.sc` (235 lines in 2001, declaring six
`MEMORY` regions - text, bit, data, xdata, edata, eeprom - and placing each
section into one with `> region`). The memory spaces themselves, the input
section names that feed them and the address arithmetic that chains one space
to the next are the 2001 port's as well.

Different in this port:

- One `MEMORY` region, `rom`, holds the code, and every RAM space -
  regbank, rdata/rbss, bdata/bbss, bit, data/bss, idata/ibss, xdata, edata,
  eeprom - is a non-alloc `(INFO)` section at its real address inside its
  own space. Disjoint spaces may then share VMA ranges without tripping the
  linker's overlap check, and `objcopy -O ihex` extracts just the code image.
  `ASSERT`s bound the internal RAM, the bit space and the two external ones.
  Register bank 0 is always reserved, `__STACK_SIZE` bytes are kept for the
  stack under `__IRAM_SIZE`, directly addressed RAM ends at 0x7F, and the
  EEPROM is bounded by `__EEPROM_SIZE`. Since nothing loads the RAM spaces,
  the linker refuses initialized data in them rather than drop it.
- Compiler-independent startup hooks, absent from the 2001 script: `.text` ends in `__I51_RET = . ; BYTE(0x22)`, and
  `__GSINIT_STARTUP`, `__EXTERNAL_STARTUP` and `__INIT_DATA` are PROVIDEd
  against it, so a runtime that leaves one undefined calls a bare RET instead
  of jumping into the reset vector. Each is PROVIDEd under its lower-case
  spelling as well - `__gsinit_startup`, `__external_startup`, `__init_data` -
  because a reference from an object built by a tool that does not fold names
  is spelled that way and the upper-case definition would never bind it.
  The script names `ENTRY(_START)`; 2001 named no entry point.
- The assembler folds symbol names to upper case, as MCS-51 assemblers do
  (`symbols_case_sensitive = 0`, which 2001 never set). Every symbol the
  script defines for use from code is spelled upper case accordingly -
  `STACK` where 2001 provided `stack`.
- `e_machine` is the registered `EM_8051` (165), not 2001's unregistered
  `EM_I51` 0x7262.
- The emulparams file adds `EXTRA_EM_FILE=genelf`, and the emulation is named
  `elf32i51` where 2001 spelled it `elf32_i51`.

## Testing

Two layers:

- `gas/testsuite/gas/i51` and `ld/testsuite/ld-i51`, inside the patches: the
  DejaGnu suites binutils itself runs. They hold regression tests and the
  tests of what has to be refused - an operand form the instruction set does
  not have, a value that does not fit, an operand in the wrong memory space.
  `make -C tb dejagnu` runs them.
- `tb/`: the ten projects built and compared byte for byte with reference
  ROMs and, byte class by byte class, with the 2001 images; the instruction
  set against third-party tables; a simulator run; linker-script coverage;
  and, on demand, mutation testing.

`make -C tb gate BUILD=<build tree>` runs the sixteen gate stages (`isa
roundtrip branch bits reloc guard sim defaultlink commons script disasm
doctruth dejagnu check libsrc oracle`) and stops at the first failure. `BUILD` has
to point at a configured build tree - after `make -C tb build` that is
`work/modern/build` - because the default is the frozen 2001 build.
`make -C tb check-canary` checks that `check` still fails on a broken
toolchain.

## Upstream

What still stands between these patches and binutils@sourceware.org:
copyright assignment or a DCO sign-off from every author, the `config.sub`
entry going through config-patches@gnu.org first, and review there.

## References

- the original port: http://web51.hw.cz
- an independent port derived from the same 2001 patch, onto binutils 2.38: https://github.com/github0null/binutils-mcs51
- sdcc-adjacent work: https://github.com/volumit/sdcc_aurix_scr_42

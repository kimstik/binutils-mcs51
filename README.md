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

## Key Changes:

- Migrated from 'elf' to 'generic' template
- Created custom ld/scripttempl/elf32i51.sc with MCS-51 MEMORY regions
- Compiler-independent startup hooks: the default linker script PROVIDEs
  `__GSINIT_STARTUP`, `__EXTERNAL_STARTUP` and `__INIT_DATA` (symbols are
  uppercased; each defaults to a bare RET) so a runtime may override them

## References

- the original port: http://web51.hw.cz
- an independent port of the same lineage onto binutils 2.38: https://github.com/github0null/binutils-mcs51
- sdcc-adjacent work referenced by the 2.45.1 release: https://github.com/volumit/sdcc_aurix_scr_42

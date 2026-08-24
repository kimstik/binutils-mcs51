# binutils-mcs51

GNU binutils for the Intel MCS-51 / 8051.

It started as a patch against **binutils 2.11.2**, published on
http://web51.hw.cz in December 2001, and was forward-ported.

## Key Changes:

- Migrated from 'elf' to 'generic' template
- Created custom ld/scripttempl/elf32i51.sc with MCS-51 MEMORY regions
- Implemented compiler-independent weak symbols ( __gsinit_startup, __external_startup, __init_data )

## References

- the original port: http://web51.hw.cz
- an independent port of the same lineage onto binutils 2.38: https://github.com/github0null/binutils-mcs51
- sdcc-adjacent work referenced by the 2.45.1 release: https://github.com/volumit/sdcc_aurix_scr_42

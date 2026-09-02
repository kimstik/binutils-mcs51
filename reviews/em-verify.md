# EM-VERIFY: e_machine = 165 on main @ 90ee2af

Verified by grep and by reading every ELF header in both archives. No build.

## Confirmed

| item | state |
|---|---|
| `ELF_MACHINE_CODE` | `EM_8051` (additions.patch:1024) |
| `ELF_MACHINE_ALT1` / `EM_I51_OLD` | removed, zero occurrences |
| `0x1051` in code | zero occurrences |
| readelf machine name | `case EM_8051` (modifications.patch:342,350) |
| `tb/base.7z` | 30 ELF objects, all `0xa5` LE |
| `tb/base2001.7z` | 28 ELF objects, all `0x7262` BE (correct: consumed by frozen 2.11.2 only) |
| `tb/i51elf_le2be.py` | writes 165 |
| README:27 | correct |

ALT1 removal and base.7z re-stamp are consistent with each other. Either alone would break `check`.

## Open

1. `tb/base2001.PROVENANCE:7` says base.7z carries `e_machine 0x1051`. False since the re-stamp; actual is 0xa5. Line 5 (`0x7262` for base2001.7z) is correct.
2. `e_flags` never set. No sub-machine discriminator. Standard pattern: `EM_AVR` + `EF_AVR_MACH`. Both sibling ports set it; Ghidra's loader keys on `(machine, flags)`.
3. `EI_DATA` = ELFDATA2LSB while gas emits 16-bit section data MSB-first. gABI applies EI_DATA to section data. 2001 original, both siblings, Ghidra's 8051 languages, TASKING are all BE. Consumers that trust EI_DATA (radare2, gdb) mis-decode: `02 01 12` shown as x86 `add (%ecx),%al`.

Items 2 and 3 are companions of the number, not alternatives to it. 165 is closed.

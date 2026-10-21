# i51 port review: disassembler and the binutils tools (objdump, readelf, nm, objcopy, size, strip, ar, addr2line)

Tools under test: `$B=/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/work/modern/build`.
I also built an ASAN+UBSAN copy of binutils and gas at
`/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/review/asan`.
Scripts are in `/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/review/scripts/`:
- `exh.py`: exhaustive disassembler check and round trip.
- `fuzz.py`: mutation fuzzer.
- `craft.py`: hand-crafted relocations and section indices.

The "real image" is the testbench `lcd` project, linked with `lib/www51.sc` (copied from `review/work-tb/tb/projekt/lcd/www8051.o` to `review/real/lcd.elf`).

## Findings, worst first

### 1. CRITICAL: `objcopy -O binary|ihex|srec` without `-j` silently overlays `.eeprom` on the reset vector

Any script that makes the memory spaces ALLOC+LOAD (the shipped `lib/www51.sc` does) gives `.eeprom` VMA = LMA = 0. That is the same LMA as `.text`. The default ld script avoids this only because every non-code space is `(INFO)`.

```
objdump -h lcd.elf      # .eeprom 0x172 bytes VMA 0 LMA 0, CONTENTS ALLOC LOAD
objcopy -O binary lcd.elf lcd.bin       # rc 0, no diagnostic
cmp lcd.bin lcd.rom     # 351 bytes differ in 0x0000..0x0171 (EEPROM bytes replace LJMP vectors)
objcopy -O ihex lcd.elf lcd.hex         # rc 0; two different :10000000 records (eeprom and code)
```

`readelf -l` shows two LOAD segments with PhysAddr 0 (RW size 0x172, R E size 0x167a).

Root cause:
- `bfd/elf32-i51.c` gives no backend hook that marks a non-code space as non-LOAD or as a different LMA space. Five 0-based spaces cannot share one ELF physical address space.
- `lib/www51.sc` and any user script place `.eeprom`, `.reg`, `.bss` and the others as ALLOC+LOAD.

The Makefile flow survives only because it always passes `-j .text` or `-j .eeprom`.

Fix options:
- Clear SEC_LOAD on non-code spaces in a `section_flags` or `fake_sections` hook.
- Have objcopy refuse overlapping LMAs for this target.
- At least document `-j` as mandatory.

### 2. CRITICAL: `strip` (and `objcopy` ELF to ELF) on such an image moves `.text` LMA from 0 to 0x172

```
strip-new -o lcd.str lcd.elf
  strip-new: lcd.str: section .text lma 0 adjusted to 0x172      (exit 0, warnings only)
  ... .bbss lma 0x20 adjusted to 0x17ec, .bitbss -> 0x17f0, .bss -> 0x180f
objcopy -O ihex -j .text lcd.str s.hex   -> first record :10017200 0200260201DA...   (code now at 0x0172)
objcopy -O srec -j .text lcd.str         -> S1130172...
```

`-O binary` still looks right because binary output is rebased to the lowest LMA, so the damage stays hidden until someone flashes a hex or srec. The cause is the same as in finding 1: `rewrite_elf_program_header` in `bfd/elf.c` resolves the overlapping PT_LOADs by moving LMAs.

### 3. MEDIUM: the disassembler drops bytes and prints a false error when an instruction straddles a symbol or the end of the section (`opcodes/i51-dis.c`, `print_insn_i51`)

Every operand read does `if (opdata < 0) return -1;` after `memory_error_func`, so nothing is printed for the opcode byte.

Real image:
```
objdump -d lcd.elf
    1299: 0a        inc R2
    129a: Address 0x129b is out of bounds.     <- 0x129b is inside .text; byte 0x40 at 0x129a never shown
0000129b <DMAREADLOOP>:
```
The `12d3:` case is the same. The cause is the data byte that the `ENDPORTDATA` macro leaves before a label in `lib/packet.asm`.

Minimal repro: `.text` / `.byte 0x00,0x10,0x20` gives `1: Address 0x3 is out of bounds.`. A trailing `.byte 0x02` gives `0: Address 0x1 is out of bounds.`

Fix: on a short read, print `.byte 0xNN` for the opcode and return 1, as other ports do.

### 4. MEDIUM: no usable debug information

- `as -g` and `--gdwarf-2/3/5` exit 0 but emit no `.debug_*` sections. `tc-i51.c` never calls `dwarf2_emit_insn`.
- `.file 1 "x.c"` / `.loc 1 5` fails with `Error: cannot relocate 4 bytes of data`. There is no 32-bit reloc (`tc-i51.c` ~2061 handles 1 and 2 bytes only, and R_I51_* has no 32-bit howto), so no compiler can hand DWARF to this assembler.
- `--gstabs` fails the same way.
- `addr2line -e pg.elf 0x3` prints `??:?`.

The silent `-g` is the misleading part.

### 5. MEDIUM: nm classes are misleading

With the default script (all data spaces are INFO, so not ALLOC), every RAM, bit, xdata and eeprom symbol prints as `?`:
```
00000021 ? DVAR, 00000000 ? XVAR, 00000000 ? FLAG, 00000000 ? EE, 00000005 ? XC ...
```

Symbols in `.idata` print as `i` and `I` (`00000024 i IVAR`, `00000024 I __IDATA_START`). That comes from the MSVC `{".idata",'i'}` entry in `bfd/syms.c:603`. nm documents `i` as an indirect function (ELF) or DLL section (PE), so for i51 it is wrong. Nothing tells the spaces apart: `.xbss`, `.ibss` and `.bitbss` commons all print `C`.

### 6. MEDIUM: `size` adds up incompatible spaces

Berkeley output for `lcd.elf` is `text 5754 data 481 bss 82`:
- data 481 = `.reg` 29 + `.data` 18 + `.ibss` 64 + `.eeprom` 370. EEPROM is counted as RAM.
- bss 82 = `.bbss` 4 + `.bitbss` 31 + `.bss` 47. `.bitbss` is measured in bits, not bytes.

With the default script it prints `data 0 bss 0` whatever the program holds. `size -A` gives one "Total" across code, IRAM, bits, xdata and eeprom.

### 7. LOW: `objcopy -R .ibss` (and `-R .xbss` and the others) also deletes the space-common symbols

The fabricated common section carries the real section's name (`elf32_i51_symbol_processing`, `bfd/elf32-i51.c` ~805-920).

Repro: `.section .ibss,"aw"` + `.icomm ICV,3,1`, then `objcopy -R .ibss d.o d2.o`. ICV is gone from `.symtab`. With a reloc against ICV, the run fails with "symbol `ICV' required but not present".

### 8. LOW: cosmetic issues in the disassembler

- No SFR or bit names: `mov 0x81, #0x60` rather than `SP`, and `setb 0xE7` rather than `ACC.7`. Raw hex is unambiguous and reassembles.
- `cjne A,#imm,rel` loses the `#dec 'c'` comment because the branch comment overwrites `comment1`.
- The ajmp/lcall target comes from `print_address_func` (`lcall 18 <HELPER>`, lower case, no 0x), while every other operand is `0x%02X`.
- No `insn_info_valid` or branch info is set, so `--visualize-jumps` does nothing.
- `objdump -D` of data sections may label an address with any space's symbol (`acall 22 <CC>` in `.xdata`, `.eeprom` starts at `<__EDATA_END>`). This is intended per the `i51_symbol_is_valid` comment, but it is noise.

### 9. LOW: readelf does not name the port's indices or flags

`readelf -s` prints `PRC[0xff01]` to `PRC[0xff06]` instead of `.rbss`/`.xbss` and so on. The `SHF_RDATA`... codes in `include/elf/i51.h` are never written, as the source documents. Relocation names R_I51_* print correctly. An unknown type (14 or 255, crafted) is reported cleanly.

## What was verified OK

**Disassembler, exhaustive.** I ran all 256 opcodes, 4669 instructions in total. Operands were 0x00, 0x01, 0x7F, 0x80, 0x81, 0xFE, 0xFF, 0x20, 0x2F, 0x30, 0xE0, 0xE7, 0xD7, 0x87, 0x88 and 0xF8 for 2-byte instructions, and 16x8 pairs for 3-byte ones. Each was compared against an independent decoder written from the Intel MCS-51 opcode map. **0 mismatches** in:
- mnemonic and operand order (`mov dir,dir` 0x85 swaps src and dst correctly; also `cjne`, `djnz dir,rel`, `jbc bit,rel`, `anl/orl C,/bit`)
- instruction length
- relative targets, both the `.±N` operand and the absolute comment
- ajmp/acall page taken from the next instruction (`7fe: 01 05` gives `ajmp 0x805`, and at 0xFFFF it wraps to 0x0010)
- 0xA5 printed as `.byte 0xA5 ; ????`

**Round trip.** The printed text of all 4669 instructions, with comments stripped, reassembles with `as-new` byte-identical: 12269 bytes, 0 diffs.

**objcopy and strip on relocatable objects.** Plain copy, `--strip-unneeded`, `-g`, `--prefix-symbols` and `--weaken` all keep SHN_I51_RDATA_C to SHN_I51_BITDATA_C (0xff01 to 0xff06) and keep real `.xbss`/`.ibss` sections separate from the commons. `-O ihex` and `-O binary` on the default-script image hold only `.text`. `strip` on the default-script image leaves LMAs alone.

**ar, ranlib and nm.** `ar rcs`/`t`/`x`, `nm -s` and links from the archive work with upper-case symbols. `libk80.a`, `libw80.a` and all `cgi/*.obj` and `lib/*.obj` files go through `objdump -dxr` and `nm` cleanly under ASAN.

**Crash hunting.**
- Crafted inputs: reloc type 14 and 255, reloc symbol index 0 and 999, r_offset 0xfffffff0, and st_shndx of 0xff00-0xff07, 0xff1f, 0xfff1 and 0xfff2 on local, global and section symbols. Each was run through `objdump -dr`, `objdump -x -D -W`, `readelf -a -W`, `nm -a`, `size -A`, `objcopy` (ELF and ihex) and `strip`. No crash, ASAN or UBSAN report, or hang.
- Mutation fuzzing: 600 iterations on the release build plus 400 iterations on the ASAN build, with 1-4 mutations each in the ELF header, section headers, symtab, rela or strtab. Each was run through 9 tool invocations. Result: 0 crashes, 0 sanitizer reports, 0 timeouts. Every malformed input was rejected with an ordinary bfd or readelf diagnostic.

## Cross-lane observation (for the as/ld reviewer)

`add a,xvar2`, where XVAR2 is a `.xdata` label, assembles to R_I51_8_DIR against `.xdata` and links to `add A, 0x04` with no diagnostic. That is an XDATA address used as an IRAM direct address. Repro: `review/prog/b.s` linked with `a.s` using the default script. Separately, `.rdata` with an empty `.regbank` is placed at 0x00, on top of register bank 0 (default script).

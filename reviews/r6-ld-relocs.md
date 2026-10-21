# i51 linker review: relocations, overflow, address spaces, commons

Tools: current-main build (`$B=/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/work/modern/build`).
All repro files are in `/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/review/ld/`.
Run `. ./env.sh` there first. It defines `$AS $LD $OD $NM $RE $OC` and `txt ELF`, which dumps the .text bytes.

Severity scale: CRITICAL = wrong bytes, silent; HIGH = crash; MEDIUM = bad or missing diagnostic, or wrong exit code; LOW = cosmetic or latent.

---------------------------------------------------------------------------
## C1 CRITICAL: relocations against SEC_MERGE sections (.rodata.str*) resolve to the wrong address

`elf32_i51_relocate_section` computes a local symbol as
`sec->output_section->vma + sec->output_offset + sym->st_value` (+ r_addend). It never calls
`_bfd_elf_rela_local_sym()`, so when string merging deduplicates or moves a string, the
section-symbol+addend reloc keeps the offset the string had before the merge.

ms1.s / ms2.s (two objects, both with `.section .rodata.str1.1,"aMS",@progbits,1`; ms2 has "XYZ", "WORLD", where "WORLD" duplicates a string in ms1):
```
$AS ms1.s -o ms1.o; $AS ms2.s -o ms2.o; $LD ms1.o ms2.o -o ms.elf   # rc 0
 .text: 90 00 10 90 00 16 12 00 09 | 90 00 20 90 00 24 22 | 48 45 4c 4c 4f 00 57 4f 52 4c 44 00 58 59 5a 00 | 22
```
- S3 ("XYZ") is at 0x1C, but the code loads `#0x0020`, which is the RET stub.
- S4 ("WORLD", merged into S2=0x16) gets `#0x0024`, which is past the end of the image.

`ld -r ms1.o ms2.o` followed by a final link is also wrong: the second link merges the duplicate inside the single input section and gives `#0x0020`.

Fix: in the local-symbol branch use `relocation = _bfd_elf_rela_local_sym (info->output_bfd, sym, &sec, rel);`. With `-r`, keep the section-symbol addend handling for merge sections, or set `elf_backend_rela_normal 1` (see M1).

---------------------------------------------------------------------------
## C2 CRITICAL: direct-RAM symbols placed at 0x80 and above link to SFR addresses

The script has one internal-RAM arena (`.rdata, .rbss, .bdata, .bbss, .data, .bss, .idata, .ibss`) and a single limit, `ASSERT(__IDATA_END <= 0x100)`.
- Nothing keeps `.data`/`.bss`/`.rdata`/`.bdata` below 0x80.
- `R_I51_8_DIR` accepts 0..0xFF because it does not know that a symbol in a RAM section (not ABS) must be below 0x80 when it is reached with a direct address.
- The gas check (`i51_check_direct`) only sees offsets within one file before layout.

d1.s (`.data` with `.skip 0x78`, `BIGV`) + d1b.s (9 bytes of `.rdata`):
```
$LD d1.o d1b.o -o d1.elf      # rc 0
 e5 98 ...   mov a,BIGV  ->  mov a,SCON   (BIGV = 0x98)
```
iv1.s/iv2.s (`.idata` symbol at 0x90, accessed directly from another object):
```
 e5 90 / 05 90   mov a,0x90 ; inc 0x90   -> reads/increments P1 (port write!)
```
Expected: an error, either from an ASSERT that `.data`/`.bss`/`.rdata`/`.bdata` end at or below 0x80, or from `R_I51_8_DIR` when the target symbol's output section is a RAM section and the value is 0x80 or more.

Source: ld/scripttempl/elf32i51.sc (ASSERT block) and bfd/elf32-i51.c (R_I51_8_DIR has no case of its own).

---------------------------------------------------------------------------
## C3 CRITICAL: R_I51_8_BIT has no overflow check (complain_overflow_dont)

bit.s: `setb BS / clr BS+1 / jb BS2,_START`
```
$LD bit.o --defsym BS=0x100 --defsym BS2=0x1ff -o bit.elf   # rc 0
 d2 00 c2 01 20 ff f9     (0x100 -> bit 0x00, 0x1ff -> 0xff)
BS=0xff:  clr BS+1 -> c2 00
BS=-1:    d2 ff
```
The bit space is 0x00..0xFF, so the HOWTO should use `complain_overflow_unsigned` like `R_I51_8_DIR`. gas rejects the same values when it folds them (md_apply_fix rejects anything outside -256..255), so gas and ld disagree.

Source: bfd/elf32-i51.c HOWTO R_I51_8_BIT.

---------------------------------------------------------------------------
## C4 CRITICAL: B2B on a symbol whose address is 0 (or an undefined weak symbol) is silently accepted

`case R_I51_8_B2B: if (srel == 0) break;` treats the value 0 as an "unresolved COMMON", but commons are always allocated before final relocation (`bfd_link_hash_common` cannot occur at that point). So a byte at RAM address 0 (R0 of bank 0), an ABS 0, or an undefined weak symbol leaves the in-place bit offset as the bit address.

b0.s:
```
setb B2B(W,3) ; W=0          -> d2 03  (bit 3 of byte 0x20!)
.weak WK ; setb B2B(WK,5)    -> d2 05
$LD b0.o --defsym W=0 --defsym W2=0x21 -o b0.elf    # rc 0
```
Expected: "0x0 is not bit addressable", which is what gas says for the folded case. `R_I51_13_PCODE` has the same `srel==0` skip: `.pcode PEX` with PEX=0 links to `00 00` (rc 0), while `PEX+5` is rejected (pc.s).

Source: bfd/elf32-i51.c, the R_I51_8_B2B and R_I51_13_PCODE cases.

---------------------------------------------------------------------------
## C5 CRITICAL: `.pcode` operand relocations give different bytes than the constant form

This is mostly the gas side, but it shows up after relocation.

pc.s:
```
.pcode 0x200 @BYTE 0x35   -> 82 00 40 34   (constant stored decremented, as documented)
.pcode 0x200 @BYTE SYMB   -> 82 00 40 35   (SYMB=0x35: NOT decremented)
.pcode 0x200 #SWAP 0x1234 -> 02 00 c2 34 12 (low byte first)
.pcode 0x200 #SWAP SYMW   -> 02 00 c2 12 34 (SYMW=0x1234: high byte first)
```
- `@BYTE` with a symbol writes 0xFF in place and relies on it being added. That would only work with REL; under RELA (`partial_inplace=false`) the in-place byte is discarded and the addend stays 0.
- `#SWAP`/`@SWAP` with a symbol emit a plain `R_I51_16` (big-endian) instead of a swapped pair (`LOW` then `HIGH`).

Fix:
- For `@BYTE`, emit the fixup with `X_add_number - 1`.
- For `SWAP`, emit two fixups: `BFD_RELOC_I51_8_LOW` at f and `BFD_RELOC_I51_8_HIGH` at f+1.

Source: gas/config/tc-i51.c `writePcodeOperand`.

---------------------------------------------------------------------------
## C6 CRITICAL: a branch to an overridden weak symbol in the same section is folded by gas

w1.s defines `.weak FOO` in .text and uses `sjmp FOO; ajmp FOO; ljmp FOO`. w2.s defines a strong FOO.
```
$LD w1.o w2.o -o w.elf     # rc 0
 0: 80 09  sjmp 0x000B   <- weak copy (wrong)
 2: 01 0d  ajmp 0x000D   <- strong FOO
 8: 02 00 0d ljmp 0x000D <- strong FOO
```
In `md_apply_fix`, the pcrel case sets `fx_done` for `S_GET_SEGMENT(sym) == seg` even when the symbol is weak, so no `R_I51_7_PCREL` reaches the linker. Branches to the same weak symbol then go to two different places.

Fix: do not set `fx_done` for `S_IS_WEAK` / `S_IS_EXTERNAL` symbols (or use `TC_FORCE_RELOC` / `generic_force_reloc`). The same applies to cjne, djnz and jb/jnb/jbc.

---------------------------------------------------------------------------
## C7 CRITICAL: no address-space check on any relocation (extends the known B2B/mov-on-xdata case)

as.s:
```
ljmp XV    (XV in .xdata) -> 02 00 05
acall XV               -> 11 05
sjmp DV    (DV in .data)  -> 80 19   (jumps to code 0x20)
mov a,_START (code label) -> e5 00
setb _START               -> d2 00
setb DV / setb XV / setb IV (byte symbols in .data/.xdata/.idata, bit2.s) -> d2 20 / d2 40 / d2 21
```
All of these link with rc 0. The output sections already identify each symbol's space: `.text` is code, while RAM, xdata and bit sections are INFO sections with known names. So the relocate_section could check, per reloc type, which output section the target lives in:

| Relocation | Target output section must be |
|---|---|
| 7_PCREL, 11, ljmp/lcall-16 | `.text` |
| 8_BIT | `.bit` / `.bitbss`, or ABS |
| 8_B2B | `.bdata` / `.bbss`, or ABS |
| 8_DIR | below 0x80 in internal RAM, or ABS |

---------------------------------------------------------------------------
## C8 CRITICAL (design): register bank 0 is not reserved unless the file uses `.using`

`.regbank` only gets `__RB__` if some file says `.using`. Without it, `.rdata`/`.rbss`/`.rcomm` start at 0x00 and overlap R0..R7, which every program uses from reset.

r2.s:
```
mov r0,#1 ; mov RC,#5 ; .rcomm RC,1   ->  78 01 75 00 05    (RC == R0)
```
With `.using 0` the same file gives RC=0x08. Expected: the script reserves bank 0 (`.regbank` minimum 8 bytes, or `MAX(0x08, …)` for `.rdata`).

Source: ld/scripttempl/elf32i51.sc, `.regbank`/`.rdata`.

---------------------------------------------------------------------------
## C9 CRITICAL: a memory-space common is silently resolved to a definition in another space

x1.s has `.xcomm BUF,4` and uses `movx` via `mov dptr,#BUF`. x2.s defines `BUF` in `.idata`.
```
$LD x1.o x2.o -o x.elf    # rc 0, mov dptr,#0x0023 ; BUF is idata 0x23
```
`elf32_i51_check_common_space` only compares common with common. A definition overrides a common in another space without any message. The same happens with plain `.comm BUF,1` (used by `mov a,BUF`) plus `.bitcomm BUF,4`: BUF becomes bit 0, so the direct access hits address 0 = R0 (x4.s + x3.s, rc 0). This is documented as "plain .comm not compared", but the result is still wrong bytes.

---------------------------------------------------------------------------
## C10 CRITICAL (edge): R_I51_11 does not check bits above 15, and R_I51_H does not check range

aj.s:
```
ajmp TGA with TGA=0x10005 from page 0 -> 01 05 (rc 0)
```
The page test is `(srel ^ pc) & 0xF800`, which ignores bits 16 and up and negative values (a negative srel in the 0xF800 page also passes).

hl.s:
```
mov a,#HIGH(X+0x10000), X=0x1234 -> 74 12 (rc 0)
.byte HIGH(Y) with Y=0x12345 -> 23
```
gas rejects values outside -65536..65535 for HIGH; the linker accepts them silently. This is the same class as the known R_I51_16 mask. The EEPROM space adds to it: there is no `ASSERT(__EEPROM_END <= 0x10000)`, so s3.s puts EEV at 0x1000F and `mov dptr,#EEV` becomes `90 00 0f` (rc 0).

---------------------------------------------------------------------------
## M1 MEDIUM: `--emit-relocs` writes wrong addends for section-symbol relocations

```
$LD --emit-relocs m1.o m2.o -o mE.elf ; $RE -r mE.elf
0x13 R_I51_8_DIR .data + 3       (target LD2=0x2B = .data(0x26)+5)
0x15 R_I51_8_B2B .bdata + 2      (should be +4)
0x17 R_I51_16    .xdata + 10     (should be +134)
0x08 R_I51_7_PCREL .text - 1     (target .text.two at 0x1E: should be +1d)
0x09 R_I51_11    .text + 0       (should be +1e)
```
The image bytes are correct. Only the emitted relocations are wrong, because the input-section `output_offset` is never added. `elf_backend_rela_normal` is 0, and the port does the addend adjustment by hand, but only when `bfd_link_relocatable`.

Fix: `#define elf_backend_rela_normal 1` and remove the manual -r adjustment.

## M2 MEDIUM: user range errors are reported as "internal error: out of range error"

This affects R_I51_8_B2B (not bit-addressable, offset > 7) and R_I51_13_PCODE below 0x100:
```
pc.o: (.text+0x15): internal error: out of range error: PEX
```
The link fails correctly (rc 1), but the message suggests a linker bug rather than a bad operand. Use `reloc_dangerous`, or a custom message that matches gas's ("0x.. is not bit addressable", "pcode exec address underflow").

## M3 MEDIUM: no stack reservation and no check

`PROVIDE(STACK = __IDATA_END)`. Filling `.idata` to 0xFF (s1.s) gives `mov sp,#STACK-1` = `75 81 ff`, rc 0: there are zero bytes of stack and no ASSERT. There is no `__STACK_SIZE`/`--defsym` minimum. The register-area size (more than 0x20 bytes of regbank+rdata+rbss) is not asserted either.

## M4 MEDIUM: initialized RAM data never reaches the ROM image

`.data`/`.rdata`/`.bdata`/`.idata`/`.xdata` are INFO sections with no LMA in `rom` and no load-address symbols. Meanwhile `__INIT_DATA` is PROVIDEd as a RET. s7.s: `.xdata .word _START,FARX` and `.data .byte LOW(_START)`. `objcopy -O ihex` then contains only the code (`:020000002222BA`). Initial values are silently lost unless the user writes their own copy loop from a table that the script never emits.

---------------------------------------------------------------------------
## L1 LOW: the HOWTO table does not match what relocate does

| Relocation | Problem |
|---|---|
| R_I51_R1 / R_I51_R3 | `dst_mask 0`, so the reloc is a no-op. Its bitsize is 8, not 1/3. rr.s: `.reloc 0,R_I51_R1,SYM` with SYM=1 still links `e6` (`@R0`), rc 0. gas never emits these; a foreign object would link silently wrong. |
| R_I51_7_PCREL | `complain_overflow_bitfield` (accepts -256..255) and `pcrel_offset false`. Only the hand-written path is correct. |
| R_I51_11, R_I51_13_PCODE | 16-bit `dst_mask 0xffff`. Any generic path (`bfd_perform_relocation`, `bfd_simple_get_relocated_section_contents` used by objdump/addr2line on .o) would overwrite the opcode or flag bits. |
| R_I51_8_B2B | The generic path writes the byte address without the bit transform. |
| R_I51_8 | `.byte X` truncates silently (X=0x1234 gives 0x34). This is documented and intentional, but no other ELF port behaves this way. |

The names in `objdump -r` / `readelf -r` are correct for all 14 types (rl.s).

## L2 LOW: relocations from debug sections to gc'd code are not tombstoned

`--gc-sections` with `.debug_ranges .word DEADG, DEADL` gives `0000 0001`: the local reference resolves to the section-relative offset 1, where other ports write 0. No crash.

---------------------------------------------------------------------------
## Verified correct (no finding)

- **R_I51_7_PCREL:** sjmp, cjne, djnz and jbc at exact ±boundaries (-128 / +127 OK, ±1 beyond is an error, rc 1), across sections and objects (pb.s, p2.s). The addend -1 from gas is consistent with the next-instruction base.
- **R_I51_11:** the page boundary is computed from the next instruction. `ajmp` at 0x7FE reaches 0x800..0xFFF and rejects 0x7FD and 0x1000 (aj2.s).
- **R_I51_8_DIR:** 0..0xFF with addends; -1 and 0x100 give errors.
- **R_I51_8_IMM:** -128..255; -129 and 256 give errors (di.s).
- **Local section-symbol relocs across 2 objects:** direct link, `ld -r` in both orders, and an archive member all give identical, hand-verified bytes for DIR, B2B, 16, PCREL, 11, H and BIT (m1.s/m2.s).
- **Memory-space commons:** `.xcomm .bitcomm .bcomm .icomm .comm .rcomm` across 2 objects, with `-r` round-trip, keep PRC[0xff0n] and give identical bytes (k1.s/k2.s).
- **Comdat:** a reference to a local in a discarded group copy gives a proper error.
- **Orphan alloc data:** an orphan alloc data section gives "no memory region specified".
- **Space limits:** `.text` over 64K gives a region overflow error; xdata past 0xFFFF trips the ASSERT.
- **`--gc-sections`:** keeps the entry, lcall targets and pointer-table targets; removes unused sections.

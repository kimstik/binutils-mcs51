# i51 review: directives, sections, memory model, docs vs behaviour

Tools: $BUILD/gas/as-new, ld-new, objdump, nm-new, readelf, objcopy (binutils 2.47 + mcs51 patches).
Scratch repros: /tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/dd/
S = .../work/modern/binutils-2.47. Known items (case folding, reloc has no space, jmp->0x73) not repeated,
except where a new consequence is shown.

## CRITICAL (wrong result, silent)

### C1. Initial values of every RAM section are silently discarded
ld/scripttempl/elf32i51.sc makes .data/.rdata/.bdata/.bit/.idata/.xdata/.edata/.eeprom `(INFO)` with
VMA = RAM address and no load address in `rom`; `__INIT_DATA` is PROVIDEd as a bare RET. No copy image
exists anywhere, no warning is given.
```
 .text
_start: mov a,ivar
 .data
ivar: .byte 5
 .xdata
xvar: .word 0x1234
```
`as t1.s && ld && objcopy -O ihex` -> hex contains only code (`E520 7820 900000 ...22`); 05 and 1234 are
nowhere. ld exit 0. The texi calls these "the initialized section" of each space; README only says
"objcopy -O ihex extracts just the code image". Firmware that relies on `.data` initialisers runs with
garbage RAM. Needs either an AT>rom load image + `__INIT_DATA` table, or an error/warning when a RAM space
section carries non-zero contents.

### C2. Direct-RAM sections are not bounded to 0x7F; objects land on SFRs
Script: `.data` starts at >=0x20, `.bss`/COMMON follow, `.idata` follows; the only bound is
`ASSERT(__IDATA_END <= 0x100)`. R_I51_8_DIR accepts 0x00-0xFF.
```
# b1.s                      # b2.s
 .text                       .globl v2
_start: mov a,v2             .data
 .data                      v2: .skip 4
v1: .skip 0x70
```
link OK, `V2 = 0x90`, code `e5 90` = `mov a,P1`. Single file: `.data; big1: .skip 0x60; big2: .skip 4;
.comm cbuf,8` -> BIG2=0x80 (P0), CBUF=0x88 (TCON), `mov a,big2` = `e5 80`, no diagnostic.
The gas check (tc-i51.c i51_check_direct ~1737) tests the symbol's *section offset* >= 0x80, ignoring
that the default script never places .data below 0x20 (offsets 0x60..0x7F are already SFRs). The texi
("A symbol the linker places ... is left to the linker") implies the linker checks; it does not.
Also: a direct operand on a `.idata`/`.ibss` symbol (by definition @Ri-only) is never diagnosed:
`mov a,ib` with ib in .idata at 0x92 -> `e5 92`.

### C3. Without `.using`, register-area data overlays R0-R7 of bank 0
`.regbank` is empty unless some file used `.using`, so `.rdata`/`.rbss`/`.rcomm` start at 0x00.
```
 .text
_start: mov r0,#3
 mov rv,#7
 .rbss
rv: .ds 1
```
-> `RV = 0x00` (= R0 of bank 0, which every program uses). No diagnostic. Texi says the register area is
"0x00 to 0x1F ... the .regbank space reserves the ones in use" - bank 0 is always in use. Fix: reserve at
least bank 0 (`. = MAX(., 8)`) or make __RB__ unconditional. (Converse: with `.using 3`, .rdata is placed
at 0x20+ i.e. not in "0x00 to 0x1F" as the texi says - harmless, but the doc is wrong.)

### C4. No stack reservation; RAM can fill to 0xFF and the stack wraps onto R0
`PROVIDE(STACK = __IDATA_END)` with no minimum-size ASSERT. `.data .skip 0x50; .idata .skip 0x8f;
mov sp,#STACK-1; lcall f` links (STACK=0xFF, SP=0xFE): the call's two pushes overwrite the last idata byte
and wrap to 0x00 (R0). Only when RAM is exactly full does `mov sp,#STACK` fail, and then with
"relocation truncated to fit: R_I51_8_IMM against symbol `STACK'". STACK/__STACK are not documented in
c-i51.texi or README at all (semantics: first free byte, SP must be loaded with STACK-1 because PUSH
pre-increments). Also the 0x100 limit is hard-coded: on a 128-byte 8051/8031 idata and stack silently
run into non-existent RAM; there is no `--defsym`-able RAM size.

### C5. `.local x` + `.comm x,n` (ELF static idiom) silently becomes one global common
`.local` is replaced by i51_local (tc-i51.c:1064), so `symbol_get_obj()->local` is never set and the
whole local branch of i51_common (tc-i51.c ~2260-2390) is dead code.
```
# l1.s: _start: mov counter,#1 / .local counter / .comm counter,1
# l2.s: g: mov counter,#2    / .local counter / .comm counter,1
```
nm l1.o: `C COUNTER` (global); linked: both `mov 0x20,#..` - two file-statics merged. A compiler (or a
human following ELF convention) emitting `.local`/`.comm` gets cross-file aliasing. Texi says `.local`
is not the ELF one but not this consequence. There is no way at all to get a file-local
.xcomm/.icomm/... (`.lcomm` only goes to .bss).

## HIGH (silent, layout)

### H1. `.ds n` reserves 2n bytes
Generic gas `{"ds", s_space, 2}` (read.c:377): `.ds 1` -> 2 bytes, `.ds 3` -> 6, `.ds.b 1` -> 1.
ASEM-51/sdas/ASM51 `DS n` is n bytes. Every ported `buf: .ds 16` doubles in 128 bytes of RAM, and in
code-space tables shifts every following offset. Texi mentions `.ds` as the way to allocate objects
(Opcodes section) without saying it means words; nothing warns. Consider overriding `ds` in
md_pseudo_table with size 1.

### H2. Re-declared memory-space common: warning lies, space silently changes
```
 .xcomm buf,4
 .icomm buf,8
```
-> `Warning: Length of .comm "BUF" is already 4. Not changed to 8.` but readelf: size 8, section
PRC[0xff03] (= SHN_I51_IDATA_C). Both length and space changed (i51_common falls through to
S_SET_VALUE/S_SET_SEGMENT after the warning). `.xcomm ,4` (empty name) is also accepted and creates a
nameless global common.
Cross-file: `.xcomm buf,4` (a.o) + `.comm buf,8` (c.o) -> BUF silently in internal .bss at 0x20 (a.o's
movx code then hits xdata 0x20) - documented ("A plain .comm names no space") but dangerous;
`.xcomm buf` + a defined `buf` in .idata of another file -> silently resolves to idata 0x20.

## MEDIUM

- M1. Memory-space common alignment is ignored (`.xcomm x2,4,256` lands at 0x0001; `.icomm i2,4,8` at
  0x21). Documented in texi, but the assembler accepts the argument without even a warning; 256-aligned
  xdata ring buffers (P2/@Ri idiom) break silently.
- M2. B2B out of range at link prints `internal error: out of range error: DV` (bfd/elf32-i51.c:625-626)
  for a plain user error (`setb B2B(dv,3)`, dv placed at 0x30). Also seen together with the bdata
  overflow ASSERT.
- M3. `.pcode`:
  - missing comma (`.pcode 0x200 1 2`): pcodeOperand calls ignore_rest_of_line and the next
    pcodeOperand keeps parsing the *following* source lines; all errors are reported at line 2 and the
    next statements are eaten (tc-i51.c ~2565-2580).
  - `.pcode 0x200,1` (comma after address) assembles silently to `02 00 d0 00 00 01`: an O_absent
    operand becomes a 2-byte zero word with no reloc and flags 0xC0 (wrong result, silent).
  - keywords are matched case-sensitively (`#byte 5` -> "Expected comma"), contrary to i51-Case
    ("directive names and operand names may all be written in either case").
  - the texi example `.pcode pc2x PKT_DEST, arpgwreq, #BYTE sizeofarpgwreq` assembles as documented.
- M4. `make -C tb doctruth` exists (tb/Makefile:21,515; tb/doctruth.py) and PASSes. It reads no prose
  and runs no tool: it checks only directive/operand/reloc/mnemonic name lists, two values, and that
  quoted diagnostics match some format string. It does not assemble any texi example, does not check
  the memory-space table (address ranges, "initialized section", "reserves the ones in use"), the
  `.ds` sentence, STACK, README claims, or whether a quoted diagnostic is actually produced for its
  example. Every finding above passes it.
- M5. No upper bound on `.eeprom` (`.eeprom; .skip 0x20000` links, section size 0x20000) and none
  for chip-sized RAM/ROM; xdata/edata have ASSERTs.

## LOW

- `.bit sym` with sym later `.equ`'d to 5 stores 5 (range check only for literal constants);
  `.bit 2` error path does not ignore_rest_of_line (cosmetic).
- `.using` accepts only a single literal digit: `.using bank` (equ'd), `.using (2)` -> "expected a
  register bank number"; `.using 0x1` -> junk error.
- Labels with built-in names (`rd:`, `t1:`, `p:`) are accepted at definition, then every use fails with
  "unknown instruction operand 1: `RD'"; `.bcomm fl,1` / `.bitcomm b,..` fail with "Ignoring attempt to
  re-define symbol" - misleading text for "name is a built-in SFR/bit (use .local)".
- `$` statement separator after a number in a data directive (`.byte 1 $ .byte 2`) is lexed as dollar
  local label `1$` -> confusing errors. `nop $ nop`, `mov a,#1 $ nop` work as documented.
- Operand-error recovery prints diagnostics against the next line number (`mov a,#LOW(1234h)` in a
  1-line file -> "q.s:2: junk ... `)'"; `mov a,#<0x1234` -> "q.s:2: unknown opcode `x1234'").
  Outside this lane, noted only.
- `.comm` placement after `.bcomm` pads (FLAGS 0x20, C1 0x24, C2 0x28): a few bytes of RAM lost.
- `.weak wk; lcall wk` undefined -> `lcall 0` (reset vector) - standard ELF, same hazard the startup
  hooks were added for.

## Verified correct / proper errors
.using 0-3 + AR0-7 (and "missing .using"), __RB__ sized to highest bank, max over files; bss sections
reject `.byte 7` ("attempt to store non-zero value"); .bcomm/.bitcomm/.data chaining (BB bit 0x10 ->
byte 0x22, DD 0x23); bdata/bit overflow ASSERTs; xdata overflow ASSERT; orphan alloc sections error
("no memory region specified"); `.byte ACC, CY` = E0 D7; `0x20.3`/`0x90.5`; B2B literal range errors;
HIGH/LOW on .word/ljmp/sjmp rejected; ACALL page diagnostic text matches texi; `.word`/`.float` big
endian; `--defsym` folded; `.equ`/`.set` redefinition as generic; `.local WMCON; .equ WMCON,0x96`
example; texi B2B/`.bcomm FLAGS` example links to `setb 0x03`; cross-space common diagnostic (with file
order reversed relative to the texi sample); .macro/.rept/.if with port directives; .size/.type/.weak.
README: i51-elf -> i51-unknown-elf, EM_8051 shown as "Intel 8051 and variants", ELFDATA2MSB, no -EB,
__I51_RET/BYTE(0x22), upper- and lower-case hook PROVIDEs bind (checked via objcopy --redefine-sym).

## SDCC / ASEM-51 interop
README makes no SDCC compatibility claim beyond the lower-case hook PROVIDEs (and a link). Behaviour:
`.area`, `.module`, `.db`, `.dw`, `DB`, `DW`, `foo EQU 5`, `1234h`/`12H`, `101b`, `#<x`/`#>x`,
`sjmp $` are all *rejected with errors* (not silent). `foo = 5`, `0x`, `0b`, `'A'`, `.` (location) work.
Silent divergences: `.ds n` (H1, 2n bytes) and `.org` (section-relative, not absolute as in an sdas ABS
area / ASEM CSEG AT). SDCC's sdas emits .rel, not ELF, so nothing SDCC builds can reach this linker
anyway; the lower-case hook PROVIDEs therefore have no current producer. (Unverified, from memory: SDCC's
own run-time hooks are spelled `__sdcc_gsinit_startup` / `__sdcc_external_startup`, which these
PROVIDEs would not match.)

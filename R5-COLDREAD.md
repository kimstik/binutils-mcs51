# R5 cold read: binutils-mcs51 on `main` (90ee2af)

Reader: stranger. Binutils maintainer asked to look at the port for the
first time. No prior review round read. Tools: the README build only.
Everything below: command, then output, then verdict. Caveman prose.

Tool prefix in the transcripts: `bin/as` = `gas/as-new`, `bin/ld` =
`ld/ld-new`, `bin/objdump`, `bin/nm`, `bin/readelf`, `bin/objcopy` from
the README build. Work dir was a scratch dir; paths shortened.

## 0. Fix first (the three)

1. **Assembler silently drops operands on one-form mnemonics.**
   `jmp label` assembles to `jmp @a+dptr` (0x73). `da x`, `mul x`,
   `rl 5`, `swap x`, `movc a,label` all assemble to the bare form. No
   diagnostic, wrong bytes. `jmp label` is the idiom every other 8051
   assembler accepts. Evidence: section 2.4 item S6. Cause:
   `i51_parse_operand1` takes `op1mode = opcode->args[0]` from the last
   entry of a group whenever the operand is not a register/SFR name, so
   a symbol operand "matches" `@`, `A`, `C`, `X`.
2. **Linker truncates 8/16-bit absolute relocs without a word.**
   `mov a,#label` with label at 0x300 links to `74 00`. `mov a,label`,
   `mov r0,#label`, `setb label` same. `ljmp label+0x10000` links to
   `02 03 00`. All `complain_overflow_dont`; R_I51_16 has its own case
   with `& 0xFFFF`. The assembler forces every absolute fixup out to
   the linker (`TC_FORCE_RELOCATION_LOCAL` default), so the assembler's
   own range checks in `md_apply_fix` never see them either. Evidence:
   S7. Same root: `acall` across a 2K page in the *same section* is
   only caught at link, as `relocation truncated to fit: R_I51_11
   against no symbol` (S8).
3. **Address spaces are not carried by relocs; wrong-space use links
   clean.** `setb B2B(w,1)` with `w` in `.xdata` at 0x25 links to
   `setb 0x29`; with `w` at xdata 0 the reloc is skipped entirely
   (`srel == 0` "unresolved COMMON" hack) and the byte is left as is.
   `mov a,w` with `w` in `.xdata` links to `mov a,0x25`. `B2B(x,0)` with
   `x` in `.idata` at 0xB0 links to `setb 0xB0` = P3.0. Evidence: S9.
   The port has seven space sections, seven common kinds, seven
   reserved section indices, and no space check on a single reloc.

Why these three: each one makes the tool emit wrong bytes and say
nothing. Everything else in this report is a diagnostic, a naming or a
review nit. Wrong-bytes-silent is the class that costs a user a week.

## 1. Build from the README

Followed README `Building` verbatim. Only change: paths.

```
$ curl -fsSL -o binutils-2.47.tar.xz https://ftp.gnu.org/gnu/binutils/binutils-2.47.tar.xz
$ sha256sum binutils-2.47.tar.xz
154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff  binutils-2.47.tar.xz
$ tar xf binutils-2.47.tar.xz && cd binutils-2.47
$ patch -p1 < .../mcs51/additions.patch      # 9 files, no offset/fuzz lines
additions rc=0
$ patch -p1 < .../mcs51/modifications.patch  # 29 files, no offset/fuzz lines
modifications rc=0
$ ./configure --target=i51-elf --disable-gdb
configure rc=0
$ make -j4
make rc=0
-rwxr-xr-x 1 root root 6504392 gas/as-new
-rwxr-xr-x 1 root root 7706888 ld/ld-new
$ grep -iE 'offset|fuzz|Reversed|reject' build.log | wc -l
0
$ grep -i warning make.log | grep -i i51 | wc -l
0
$ gas/as-new --version | head -1
GNU assembler (GNU Binutils) 2.47.20260726
$ ld/ld-new -V | head -4
GNU ld (GNU Binutils) 2.47.20260726
  Supported emulations:
   elf32i51
$ binutils/objdump -i | head -3
elf32-i51
 (header little endian, data little endian)
  i51
```

Verdict: README gets you there. Patches apply at zero offset. Tree
builds with `-Wall -Wstrict-prototypes -Wmissing-prototypes -Wshadow
-Werror` (gas/bfd default) and the port files raise no warning. Good.

Bare `--target=i51`:

```
$ ../binutils-2.47/configure --target=i51 --disable-gdb
configure rc=0
checking target system type... i51-unknown-none
$ ./config.sub i51 ; ./config.sub i51-elf
i51-unknown-none
i51-unknown-elf
```

`i51-*-*` matches in config.bfd, gas/configure.tgt, ld/configure.tgt.
I did not rebuild the whole tree for it (disk). README claim holds at
the configure level.

Where the README is thin, for a stranger:

- Says nothing about syntax. Nothing about `HIGH()`/`LOW()`/`B2B()`,
  `.using`, `.rcomm`/`.xcomm`/`.bitcomm`..., `.rbss`/`.xdata`/... space
  directives, `.pcode`, `.local`, `.bit`. A stranger finds them by
  reading `md_pseudo_table` in `tc-i51.c`.
- Says "symbols are uppercased" in one bullet about startup hooks. It
  is a global fact: every symbol in every object is folded to upper
  case (S1 below). Deserves its own paragraph. It breaks linking
  against anything case-sensitive (SDCC `_main`).
- Says nothing about how to get a ROM out: `objcopy -O ihex -j .text`.
  And nothing about the fact that `.data`/`.xdata` initialisers are
  never in the ROM image (S13).
- `tb/Makefile (make build)` needs `7z`, `python3`, `curl`,
  `sdcc-ucsim` for the gate. Not listed.
- "`--enable-targets=all` works": not tested here.
- Nothing about `$` being a statement separator, so `sjmp $` fails (S12).

## 2. My own program

Not the testbench's. Reset vector, timer 0 vector, sub across a 2K
page, `djnz` loop, SFR bit and RAM bit set/clear, `B2B` bit, `movc`
table read, `movx` to xdata, `.word` constant and `.word label`,
`HIGH()`/`LOW()` of a label.

```
        .section .vectors,"ax"
        ljmp    _start          ; 0x0000 reset vector
        .org    0x0B
        ljmp    t0_isr          ; timer 0 vector
        .org    0x30
        .text
_start: mov     sp,#0x40
        mov     dptr,#table
        mov     a,#2
        movc    a,@a+dptr       ; table[2] -> 0x33
        mov     r7,a
        mov     dptr,#0x1234
        movx    @dptr,a
        clr     a
        movx    a,@dptr
        setb    P1.0
        clr     P1.0
        setb    TR0
        setb    flag            ; bit in .bitbss
        clr     flag
        setb    B2B(bvar,3)     ; bit 3 of a .bdata byte
        mov     r0,#8
loop:   djnz    r0,loop
        mov     a,#HIGH(table)
        mov     b,a
        mov     a,#LOW(table)
        lcall   far_sub         ; other 2K page
        acall   near_sub
        mov     a,cnt
        inc     cnt
        mov     P1,#0x7F        ; verdict
stop:   sjmp    stop
t0_isr: reti
near_sub: ret
        .word   0xBEEF
        .word   table
        .byte   0x00, 0x00      ; wanted HIGH(table),LOW(table): refused (S2)
table:  .byte   0x11,0x22,0x33,0x44
        .org    0x900
far_sub: inc r7
        ret
        .bss
cnt:    .skip 1
        .bdata
bvar:   .byte 0
        .bitbss
flag:   .skip 1
```

### 2.1 Assemble, link, disassemble

```
$ bin/as -o prog.o prog.s ; echo as rc=$?
as rc=0
$ bin/ld -o prog.elf prog.o ; echo ld rc=$?
ld rc=0
$ bin/objdump -d prog.elf
00000000 <_START>:
   0:	02 00 30    	ljmp	30 <_START>
   b:	02 00 64    	ljmp	64 <T0_ISR>
00000030 <_START>:
  30:	75 81 40    	mov	0x81, #0x40	; #64	#'@'
  33:	90 00 6c    	mov	DPTR, #0x006C
  36:	74 02       	mov	A, #0x02	; #2
  38:	93          	movc	A, @A+DPTR
  39:	ff          	mov	R7, A
  3a:	90 12 34    	mov	DPTR, #0x1234
  3d:	f0          	movx	@DPTR, A
  3e:	e4          	clr	A
  3f:	e0          	movx	A, @DPTR
  40:	d2 90       	setb	0x90
  42:	c2 90       	clr	0x90
  44:	d2 8c       	setb	0x8C
  46:	d2 08       	setb	0x08
  48:	c2 08       	clr	0x08
  4a:	d2 03       	setb	0x03
  4c:	78 08       	mov	R0, #0x08	; #8
0000004e <LOOP>:
  4e:	d8 fe       	djnz	R0, .+0x00	; 0x004E
  50:	74 00       	mov	A, #0x00	; #0
  52:	f5 f0       	mov	0xF0, A
  54:	74 6c       	mov	A, #0x6C	; #108	#'l'
  56:	12 09 30    	lcall	930 <FAR_SUB>
  59:	11 65       	acall	65 <NEAR_SUB>
  5b:	e5 22       	mov	A, 0x22
  5d:	05 22       	inc	0x22
  5f:	75 90 7f    	mov	0x90, #0x7F	; #127
00000062 <STOP>:
  62:	80 fe       	sjmp	.+0x00		; 0x0062
00000064 <T0_ISR>:
  64:	32          	reti
00000065 <NEAR_SUB>:
  65:	22          	ret
  66:	be ef 00    	cjne	R6, #0xEF, .+0x03	; 0x0069
  69:	6c          	xrl	A, R4
0000006c <TABLE>:
  6c:	11 22       	acall	22 <_START+0x22>
  6e:	33          	rlc	A
  6f:	44 00       	orl	A, #0x00	; #0
00000930 <FAR_SUB>:
 930:	0f          	inc	R7
 931:	22          	ret
00000932 <__I51_RET>:
 932:	22          	ret
$ bin/nm -n prog.elf | grep -v ' __'
00000000 T _START
00000008 ? FLAG
00000020 ? BVAR
00000022 ? CNT
00000030 t _START
...
$ bin/readelf -r prog.o | head -16
00000004  00000109 R_I51_16     .text + 3c
00000017  00000f05 R_I51_8_BIT  .bitbss + 0
0000001b  0000100a R_I51_8_B2B  .bdata + 0
00000021  00000108 R_I51_H      .text + 3c
00000025  00000107 R_I51_L      .text + 3c
00000027  00000109 R_I51_16     .text + 900
00000029  00000104 R_I51_11     .text + 35
0000002c  00000306 R_I51_8      .bss + 0
```

Bytes check by hand: `.word 0xBEEF` = `be ef`, `.word table` = `00 6c`
(big-endian), `HIGH(table)`=0, `LOW(table)`=0x6c, `B2B(bvar,3)` with
bvar at 0x20 = bit 3, `flag` = bit 8 = byte 0x21 bit 0 (bit space starts
after `.bdata`'s one byte). `djnz` back to itself = `fe`. `acall`
encodes A10..A8 in opcode: `11 65` = page 0, 0x065. Correct.

`ld -r` round trip: identical.

```
$ bin/ld -r -o prog_r.o prog.o && bin/ld -o prog_r.elf prog_r.o
$ cmp <(bin/objcopy -O binary -j .text prog_r.elf /dev/stdout) prog.bin && echo identical
identical
```

### 2.2 Run in ucsim

```
$ bin/objcopy -O ihex -j .text prog.elf prog.hex
$ printf 'break 0x62\nrun\ninfo reg\ndump sfr 0x90 0x90\ndump xram 0x1234 0x1234\ndump iram 0x20 0x22\ndump sfr 0xf0 0xf0\nquit\n' > cmds
$ s51 -t C51 prog.hex < cmds
Stop at 0x000062: (104) Breakpoint
     R0 R1 R2 R3 R4 R5 R6 R7
     00 70 d4 b2 8a 29 54 34
@R0 00 .  ACC= 0x7f 127 .  B= 0x00
   DPTR= 0x1234 @DPTR= 0x33  51 3
0x90 P1:                  0b01111111 0x7f '.' 127
0x1234                      33 3
0x20                      ab 84 80 ...
0xf0 B:                   0b00000000 0x00 '.'   0
```

P1 = 0x7F (verdict), XRAM[0x1234] = 0x33 (table[2] via movc then
movx), R7 = 0x34 (0x33 + `inc r7` in far_sub across the page), B = 0 =
HIGH(table), IRAM[0x20] bit 3 set (0xab & 0x08), IRAM[0x21] bit 0 clear
(flag set then cleared), R0 = 0 after the djnz loop. Program ran right.
The tool chain produces a working image for a straight program.

### 2.3 Where the tool surprised me

Numbered S1..S16. Each: what I typed, what came out, what I expected.

**S1. Every symbol is folded to upper case. Objects carry `MYVAR`.**
```
$ printf 'myVar:\n\tmov a,myvar\n\tsjmp foo\nFoo:\tnop\n\t.globl myVar\n' > p_fold.s
$ bin/as -o p_fold.o p_fold.s && bin/nm p_fold.o
00000006 t FOO
00000000 T MYVAR
$ printf '\tmov a,#lower\n' > p_fold3.s && bin/as --defsym lower=1 -o p_fold3.o p_fold3.s && bin/nm p_fold3.o
00000001 a LOWER
```
Expected: ELF symbol names as written. Got: an assembler that rewrites
the symbol table. `--defsym` names too. A C toolchain cannot link
against this without a symbol-renaming pass (which `tb/i51elf_sym_uc.py`
is: the testbench needs one).

**S2. `HIGH()`/`LOW()` refused in data directives.**
```
$ printf '\t.byte HIGH(t), LOW(t)\nt: .byte 1\n' | bin/as -o /dev/null
{standard input}:1: Error: junk at end of line, first unrecognized character is `('
```
Expected a byte with R_I51_H. `HIGH(` is parsed by `strncmp` inside the
instruction operand parser only. Also case sensitive, and no space
allowed before `(`:
```
$ printf '\tmov a,#high(t)\n\tmov a,#HIGH (t)\nt: .byte 1\n' | bin/as -o /dev/null
{standard input}:1: Error: garbage at end of line
{standard input}:2: Error: unknown opcode `t'
```
The rest of the syntax is case-insensitive. `HIGH`/`LOW`/`B2B` are not.

**S3. Data is big-endian, ELF says little-endian.**
```
$ printf '\t.word 0x1234\n\t.long 0x11223344\n\tmov dptr,#0x1234\n' > p_endian.s
$ bin/as -o p_endian.o p_endian.s && bin/objdump -s -j .text p_endian.o | tail -1
 0000 12341122 33449012 34
$ bin/readelf -h p_endian.o | grep Data
  Data:                              2's complement, little endian
```
`tc-i51.h` sets `TARGET_BYTES_BIG_ENDIAN 1`; `elf32-i51.c` sets
`TARGET_LITTLE_SYM`. A `.long` with a symbol is not assemblable at all:
```
$ printf '\t.long t\nt: .byte 1\n' | bin/as -o /dev/null
{standard input}:1: Error: reloc 2 not supported by object file format
```
(`BFD_RELOC_32` has no i51 howto.) Not fatal for an 8051, but DWARF
emitters use `.long`.

**S4. `.local` does not mean local.**
```
$ printf '\t.local myvar\n\t.comm myvar,1\n\t.globl g\n\t.local g\ng:\tnop\n' > p_local.s
$ bin/as -o p_local.o p_local.s && bin/readelf -s p_local.o | grep -iE 'myvar| g$'
     4: 00000001     1 OBJECT  GLOBAL DEFAULT  COM MYVAR
     5: 00000000     0 NOTYPE  GLOBAL DEFAULT    1 G
```
Standard gas: `.local x; .comm x,1` gives a local bss object. Here
`.local` is overridden (`md_pseudo_table`) to delete built-in SFR/bit
names from the operand table so a user may redefine them. The ELF
meaning is gone and nothing says so. A directive that does not do what
its name implies.

**S5. Labels that happen to be SFR or bit names cannot be referenced.**
```
$ printf '\t.text\nes:\tnop\nwr:\tnop\n\tmov dptr,#es\n\tljmp wr\n' | bin/as -o /dev/null
{standard input}:4: Error: unknown instruction operand 1: `WR'
{standard input}:3: Error: unknown instruction operand 1: `ES'
$ printf '\t.text\n\tljmp p2\np2:\tnop\n' | bin/as -o /dev/null
{standard input}:2: Error: unknown instruction operand 1: `P2'
```
The label *defines* fine; only the *use* fails, with a message about an
"unknown operand". The escape hatch is S4's `.local es,wr`, undocumented.
Names in the table include `P`, `B`, `C`, `AC`, `OV`, `ES`, `EA`, `PS`,
`RD`, `WR`, `T0`, `T1`, `T2`, `RI`, `TI`, `FL`, `IE`, `IP`, `SP`.

**S6. Operands silently dropped on one-form mnemonics.** (fix-first #1)
```
$ printf '\t.text\nl:\tjmp l\n\tda l\n\tmul l\n\trl 5\n\tswap x\n\tmovc a,l\n' > p_silent.s
$ bin/as -o p_silent.o p_silent.s ; echo rc=$?
rc=0
$ bin/objdump -d p_silent.o | tail -6
   0:	73          	jmp	@A+DPTR
   1:	d4          	da	A
   2:	a4          	mul	AB
   3:	23          	rl	A
   4:	c4          	swap	A
   5:	83          	movc	A, @A+PC
```
Six lines, six wrong instructions, exit 0. `x` and `l` never referenced,
so no undefined-symbol backstop at link either.

**S7. Link-time truncation, no diagnostic.** (fix-first #2)
```
$ printf '\t.text\n\tmov a,#l\n\tmov a,l\n\tmov r0,#l\n\tsetb l\n\tljmp l+0x10000\n\tmov dptr,#l+0x10000\n\t.org 0x300\nl:\tnop\n' > p_trunc.s
$ bin/as -o p_trunc.o p_trunc.s && bin/ld -o p_trunc.elf p_trunc.o ; echo ld rc=$?
ld rc=0
$ bin/objdump -d p_trunc.elf | sed -n 7,12p
   0:	74 00       	mov	A, #0x00
   2:	e5 00       	mov	A, 0x00
   4:	78 00       	mov	R0, #0x00
   6:	d2 00       	setb	0x00
   8:	02 03 00    	ljmp	300 <L>
   b:	90 03 00    	mov	DPTR, #0x0300
```
Contrast: the same values as constants are caught by the assembler
(`mov a,#0x1234` -> `Operand out of 8-bit range: 4660`). So the check
exists once, in the wrong place, for the case that never reaches it.

**S8. `acall` across a page in the same section: caught late, badly.**
```
$ printf '\t.text\nstart:\n\tacall far\n\t.org 0x900\nfar:\tret\n' > p_far.s
$ bin/as -o p_far.o p_far.s ; echo as rc=$?
as rc=0
$ bin/objdump -dr p_far.o | sed -n 7,8p
   0:	11 00       	acall	0 <START>
			0: R_I51_11	.text+0x900
$ bin/ld -o p_far.elf p_far.o
p_far.o: in function `START':
(.text+0x0): relocation truncated to fit: R_I51_11 against `no symbol'
```
The assembler has a good message for this (`ACALL/AJMP target 0x1800 is
not in the same 2K page as 0xb`, seen with a constant) and never gets to
use it on a label.

**S9. Address spaces: wrong-space references link clean.** (fix-first #3)
```
$ printf '\t.text\n\tsetb B2B(w,1)\n\tsetb B2B(x,0)\n\tmov a,w\n\tsjmp .\n\t.xdata\n\t.skip 0x25\nw: .byte 0\n\t.idata\n\t.skip 0x90\nx: .byte 0\n' > p_b2bx.s
$ bin/as -o p_b2bx.o p_b2bx.s && bin/ld -o p_b2bx.elf p_b2bx.o ; echo ld rc=$?
ld rc=0
$ bin/objdump -d p_b2bx.elf | sed -n 7,9p
   0:	d2 29       	setb	0x29
   2:	d2 b0       	setb	0xB0
   4:	e5 25       	mov	A, 0x25
```
`w` is external RAM; `x` is above 0x7F (indirect only). Both became
direct/bit addresses. And with the xdata symbol at 0:
```
$ printf '\t.text\n\tsetb B2B(w,1)\n\tsjmp .\n\t.xdata\nw: .byte 0\n' > p_b2b.s
$ bin/as -o p_b2b.o p_b2b.s && bin/ld -o p_b2b.elf p_b2b.o && bin/objdump -d p_b2b.elf | sed -n 7p
   0:	d2 01       	setb	0x01
```
`elf32-i51.c` R_I51_8_B2B: `if (srel == 0) break;  /* unresolved COMMON */`.
In a final link a common is never unresolved; what this catches is any
symbol at address 0, and it leaves the assembler's placeholder byte in
place.

**S10. Error recovery invents statements on the next line.**
```
$ printf '\tinc dptr,1\n' > p_phantom.s ; wc -l p_phantom.s
1 p_phantom.s
$ bin/as -o /dev/null p_phantom.s
p_phantom.s:1: Error: garbage at end of line
p_phantom.s:2: Error: unknown opcode `ptr'
$ printf '\tmov a,b,c\n\tnop\n' | bin/as -o /dev/null
{standard input}:1: Error: garbage at end of line
{standard input}:2: Error: junk at end of line, first unrecognized character is `,'
```
A one-line file reports an error on line 2. `md_assemble` returns
without moving `input_line_pointer` past the operand it choked on, and
the reader resumes mid-token.

**S11. `.section .rbss` is not `.rbss`.**
```
$ printf '\t.section .rbss\nx: .skip 2\n\t.section .xbss\ny: .skip 2\n' | bin/as -o p_sect.o && bin/readelf -S p_sect.o | grep -E 'rbss|xbss'
  [ 4] .rbss             PROGBITS        00000000 000034 000002 00      0   0  1
  [ 5] .xbss             PROGBITS        00000000 000036 000002 00      0   0  1
$ printf '\t.rbss\nz: .skip 1\n\t.xbss\ny: .skip 2\n' | bin/as -o p_sect2.o && bin/readelf -S p_sect2.o | grep -E 'rbss|xbss'
  [ 4] .rbss             NOBITS          00000000 000035 000001 00  WA  0   0  1
  [ 5] .xbss             NOBITS          00000000 000035 000002 00  WA  0   0  1
```
`tc-i51.h` has an `ELF_TC_SPECIAL_SECTIONS` table meant to give these
names NOBITS+WA. That macro left gas around 2.16:
```
$ grep -rn 'ELF_TC_SPECIAL_SECTIONS\|MD_APPLY_FIX3\|TC_HANDLES_FX_DONE\|md_after_pass_hook' gas/ --include=*.c --include=*.h | grep -v config/tc- | wc -l
0
```
Four macros in `tc-i51.h` that nothing reads.

**S12. `$` is a statement separator, so `sjmp $` fails.**
```
$ printf '\tsjmp $\n' | bin/as -o /dev/null
{standard input}:1: Error: missing operand 1
```
`line_separator_chars[] = "$"`, copied from AVR (comment in the file
says so). Every 8051 assembler I know uses `$` for "here". `.` works.

**S13. Initialised `.data`/`.xdata` never reaches the ROM.**
```
$ printf '\t.text\n\tsjmp .\n\t.xdata\nxa:\t.byte 1,2,3\n\t.data\nda:\t.byte 4\n' > p_out.s
$ bin/as -o p_out.o p_out.s && bin/ld -o p_out.elf p_out.o && bin/objcopy -O ihex p_out.elf p_out.hex && cat p_out.hex
:0300000080FE225D
:00000001FF
$ bin/readelf -l p_out.elf | grep LOAD
  LOAD           0x000054 0x00000000 0x00000000 0x00003 0x00003 R E 0x1
```
All RAM spaces are `(INFO)` in the default script; no `AT>` copy, no
`__data_load_start`. The README's `__INIT_DATA` hook has nothing to
copy from. Not wrong, but a user finds out at runtime.

**S14. `objdump` names code after RAM-space script symbols.**
```
$ bin/objdump -d p_gc.elf | grep lcall
   1:	12 00 00    	lcall	0 <__BIT_END>
$ bin/nm p_gc.elf | grep -E '__BIT_END| F$'
00000000 t F
00000000 T __BIT_END
```
Empty `(INFO)` output sections get dropped by ld and their symbols
(`__BIT_END`, `__DATA_END`...) land in `.text` at 0. The port's
`i51_symbol_is_valid` filters by section flags, so it cannot see this.
Cosmetic, but every small program's disassembly starts with it.

**S15. The default script's `_START` and a user's `_start`.**
```
$ bin/nm -n prog.elf | grep _START
00000000 T _START
00000030 t _START
```
Case folding makes the user's local `_start` collide with the script's
`PROVIDE(_START = .)`; local does not satisfy PROVIDE, so both exist.
Entry = 0. Works here only because the vector table is at 0.

**S16. `.rcomm` data lands on register bank 0 when no file says `.using`.**
```
$ printf '\t.text\n\tnop\n\t.rcomm r1x,1\n' | bin/as -o p_comm.o && bin/ld -o p_comm.elf p_comm.o && bin/nm p_comm.elf | grep R1X
00000000 ? R1X
```
`.regbank` is sized by `__RB__`, which `i51_cleanup` only emits after a
`.using`. Without one, `.rdata`/`.rbss` start at 0x00 = R0.

Things that behaved: range errors on constants (`mov a,#256`, `-129`,
`ljmp 0x12345`, `mov dptr,#0x10000`); `sjmp` out of range at assembly
(`operand out of range: -135`) and at link (`relocation truncated to
fit: R_I51_7_PCREL`); undefined symbols at link; page-boundary `ajmp`
at 0x7fe to 0x800 accepted (correct: page of the *next* insn); `.using
1..3` with `AR0..AR7`; `anl c,/bit`; `mov 0x30,0x31` operand order
(`85 31 30`); `cjne @r1,#5,.`; `--gc-sections` with a global entry
(dropped section, no crash, relocs from a kept non-alloc section into
the dropped one resolve to 0); script `ASSERT`s (`internal RAM overflow
(past 0xFF)`, `bit-addressable data overflow (past 0x2F)`, `section
.text will not fit in region rom`); memory-space commons keep their
`PRC[0xff0n]` index through `ld -r` and archives.

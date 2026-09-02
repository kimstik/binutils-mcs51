# R5: the twenty open items, re-run on main

Branch reviewed: `origin/main` @ 90ee2af ("the port on 2.47: three review rounds,
honest gate"). Four earlier rounds reported these twenty items and none of them
was patched at the time. History was rewritten into main since. This round does
not read the commit messages or the prose. It builds the port and runs each
repro again.

Method. Pristine binutils 2.47 + `mcs51/additions.patch` + `mcs51/modifications.patch`,
built by `make -C tb build` (exit 0, zero patch offsets). Tools used below:

    AS=work/modern/build/gas/as-new
    LD=work/modern/build/ld/ld-new
    OBJCOPY/OBJDUMP/READELF/NM = work/modern/build/binutils/...

Baseline before any experiment: `make -C tb gate` PASS, all eleven stages
(isa roundtrip branch bits reloc sim defaultlink commons script check oracle),
`sim` P1=127, `check` 10/10 against the reference ROMs.

Three items (16, 17, 18) cannot be answered by reading a script, so they were
measured: the built tree was instrumented (two marker writes) and the r_offset
guard was deleted, binutils rebuilt, and the whole gate run again. Positive
controls first, so an empty marker file means "never called" and not "never
compiled in". The repository itself was not touched.

## Verdicts

| # | item | verdict | evidence, one line |
|---|------|---------|--------------------|
| 1 | `symbols_case_sensitive = 0` folds `count`/`Count` | OPEN | `count:` + `sjmp Count` assembles clean, `nm` shows one symbol `COUNT` |
| 2 | pcrel branch to a global in the same file | OPEN | `sjmp glo1` at 0x9, GLO1=0x8 emits `80 05` (target 0x10), not `80 fd` |
| 3 | direct RAM not bounded at 0x80 | OPEN | 150 bytes of `.bss` puts VAR at 0xB6, `mov a,VAR` emits `e5 b6`, ld exit 0 |
| 4 | `objcopy -O binary` overwritten by `.eeprom` | CHANGED | port's default script now emits `.eeprom` non-alloc, but a real project image still comes out `00 00 e8 ee ...`, exit 0 |
| 5 | `.xcomm`/`.icomm` same name in two files | OPEN | equal sizes: link order alone decides `.xbss`@0x00 vs `.ibss`@0x20, ld exit 0, silent |
| 6 | `.pcode` target over 0x1FFF | OPEN | PTARGET=0x2003 links to `00 03`, ld exit 0; the constant form is an assembler error |
| 7 | `R_I51_8_B2B` out of range | OPEN | `warning: internal error: out of range error`, ld exit 0, byte left `d2 01` |
| 8 | `mov a,AR0` without `.using` | FIXED | `Error: missing .using`, as exit 1, no internal error |
| 9 | `.byte LOW(sym)` / `HIGH(sym)` | OPEN | still `junk at end of line, first unrecognized character is '('` |
| 10 | `movx @Ri` paging | OPEN | xdata 0x00F0 and 0x01F0 both encode `78 f0`, P2 never touched |
| 11 | `hexoracle.py` `want_counts is None` | OPEN | both ROMs zeroed byte for byte, oracle still "all 10 projects agree", exit 0 |
| 12 | `isa_check.py --stages ''` | OPEN | prints PASS, exit 0; with no `--table` and no `--program` too |
| 13 | three copies of the stage list | OPEN | MUTGATE 10 stages, `run.py` STAGES 6, `gate.yml` 12 hand-written steps |
| 14 | `gen.py` drops mutants, emits comment-only ones | OPEN | 2 dropped on id collision, 1 mutant whose only change is inside a comment |
| 15 | `bits.py` `bit-0`/`bit-1` | OPEN | both cases want `''` and both produce 0 bytes: `b''` compared with `b''` |
| 16 | `i51_symbol_is_valid` coverage | OPEN | instrumented: 0 calls in the whole gate; control `objdump -d` on an ELF: 2 calls |
| 17 | `run-commons.sh` and `ld -r` | OPEN | no `-r` in run-commons.sh; the gate's one `ld -r` carries no space common, hook body run 0 times |
| 18 | removing the `r_offset` bounds guard | OPEN | guard deleted, rebuilt, full gate still PASS |
| 19 | `base2001.PROVENANCE:7` e_machine 0x1051 | OPEN | base.7z's 30 ELF objects carry e_machine 0xa5 little-endian, not 0x1051 |
| 20 | the 12 false statements of b89f1ae | CHANGED | 2 fixed (A2, B6), 10 still false on main |

Counts: **FIXED 1, OPEN 17, CHANGED 2.**
Inside item 20: **2 of 12 fixed, 10 still false.**

---

# Port correctness

## 1. `symbols_case_sensitive = 0` — OPEN

Still set, still folds.

    $ grep -n 'symbols_case_sensitive' work/modern/binutils-2.47/gas/config/tc-i51.c
    556:  symbols_case_sensitive = 0;

Define `count`, branch to `Count`. One symbol comes out, upper-cased:

    $ cat b.s
            .text
    count:  nop
            sjmp    Count
    $ $AS -o b.o b.s ; echo "as exit=$?"
    as exit=0
    $ $NM b.o
    00000000 t COUNT
    $ $OBJDUMP -d b.o | tail -2
       0:   00          	nop
       1:   80 fd       	sjmp	.-0x01		; 0x0000

Define both spellings and the fold is fatal:

    $ printf '\t.text\n\t.globl count\n\t.globl Count\ncount:\tnop\nCount:\tnop\n' > a.s
    $ $AS -o a.o a.s
    a.s:5: Error: symbol `Count' is already defined
    as exit=1

Two names the source distinguishes are one name in the object. Unchanged.

## 2. relative branch to a GLOBAL label in the same file — OPEN

The exact repro of the earlier round: `glo1` global at 0x8, `sjmp glo1` at 0x9.

    $ cat g.s
            .text
            .globl  glo1
            .byte   0,0,0,0,0,0,0,0
    glo1:
            nop
            sjmp    glo1
            sjmp    loc1
    loc1:
            nop
    $ $AS -o g.o g.s ; $OBJCOPY -O binary -j .text g.o g.bin ; od -An -tx1 g.bin
     00 00 00 00 00 00 00 00 00 80 05 80 00 00
    $ $OBJDUMP -d g.o
    00000008 <GLO1>:
       8:   00          	nop
       9:   80 05       	sjmp	.+0x07		; 0x0010
       b:   80 00       	sjmp	.+0x02		; 0x000D
    $ $READELF -r g.o
    There are no relocations in this file.

`sjmp glo1` must encode `80 fd` (next insn 0xB, target 0x8, disp -3). It encodes
`80 05`, i.e. target 0x10 = 0x8 + 0x8: the symbol value is added twice. The
local label on the next line (`sjmp loc1` -> `80 00`, target 0xD) is right, so
only the global path is wrong. The fixup is finished in the assembler
(`fx_done`), no relocation is left for the linker to correct. Unchanged.

## 3. direct RAM not bounded at 0x80 — OPEN

    $ cat r.s
            .bss
            .space  150
    var:    .space  1
            .text
            .globl  start
    start:
            mov     a, var
            mov     var, a
    $ $AS -o r.o r.s && $LD -o r.elf r.o ; echo "ld exit=$?"
    ld exit=0
    $ $NM r.elf | grep -i var
    000000b6 ? VAR
    $ $OBJCOPY -O binary -j .text r.elf r.bin ; od -An -tx1 r.bin
     e5 b6 f5 b6 22
    $ $OBJDUMP -d r.elf | sed -n '4,6p'
       0:   e5 b6       	mov	A, 0xB6
       2:   f5 b6       	mov	0xB6, A

`.bss` starts at 0x20, 150 bytes of it push VAR to 0xB6. On an 8051 a direct
operand of 0xB6 is not RAM, it is the SFR page. The linker allocates it, writes
`E5 B6` (a read of an SFR), and exits 0. The script's only bound is
`ASSERT (__IDATA_END <= 0x100)`, which 0xB7 passes. Unchanged.

## 4. `objcopy -O binary` and `.eeprom` at VMA 0 — CHANGED

`.eeprom` is emitted `(INFO)` by `ld/scripttempl/elf32i51.sc`, so it loses its
ALLOC flag and `objcopy -O binary` no longer sees it:

    $ cat e.s
            .text
            .globl  start
    start:
            ljmp    main
    main:
            nop
            .section .eeprom,"a"
            .byte   0xde,0xad,0xbe,0xef,0x11,0x22
    $ $AS -o e.o e.s && $LD -o e.elf e.o
    $ $READELF -S e.elf | grep -E 'Name|text|eeprom'
      [Nr] Name              Type            Addr     Off    Size   ES Flg Lk Inf Al
      [ 1] .text             PROGBITS        00000000 000054 000005 00  AX  0   0  1
      [ 2] .eeprom           PROGBITS        00000000 000059 000006 00      0   0  1
    $ $OBJCOPY -O binary e.elf e.bin ; echo "exit=$?" ; od -An -tx1 e.bin
    exit=0
     02 00 03 00 22
    $ $OBJCOPY -O ihex e.elf e.hex ; cat e.hex
    :050000000200030022D4
    :00000001FF

Note the `Flg` column: `.text` is `AX`, `.eeprom` is blank. The reset vector
`02 00 03` survives, no `de ad be ef` anywhere. With the port's own default
script the item is fixed.

But the item as reported was about a project image, and there it still happens.
`lib/www51.sc`, the script the ten projects link with, declares its own alloc
region `eeprom (rw!x) : ORIGIN = 0` and puts `.eeprom` in it. After `make check`:

    $ $READELF -S work/tb/projekt/serial/www8051.o | grep -E 'Name|text|eeprom'
      [Nr] Name              Type            Addr     Off    Size   ES Flg Lk Inf Al
      [ 1] .text             PROGBITS        00000000 0008e4 001fc0 00  AX  0   0  1
      [ 8] .eeprom           PROGBITS        00000000 000114 0007d0 00 WAX  0   0  1
    $ $OBJCOPY -O binary work/tb/projekt/serial/www8051.o serial-plain.bin
    objcopy exit=0
    $ od -An -tx1 -N8 serial-plain.bin        # what a plain -O binary gives
     00 00 e8 ee 10 35 00 00
    $ od -An -tx1 -N8 work/tb/projekt/serial/www8051.rom   # objcopy -j .text
     02 00 26 02 02 eb 00 00
    $ od -An -tx1 -N8 work/tb/projekt/serial/www8051.eep
     00 00 e8 ee 10 35 00 00

Both sections are ALLOC at address 0, `.eeprom` wins, the image opens with the
EEPROM bytes instead of the reset vector `02 00 26`, and objcopy exits 0. The
ten project Makefiles all use `objcopy -j .text -O binary`, so no shipped ROM is
wrong - but the trap is intact for anyone who does not pass `-j`.

Verdict CHANGED: the port's default script no longer overlaps, base.7z's project
script still does. Note `lib/www51.sc` is 2001 testbench data, not port source.

## 5. `.xcomm`/`.icomm` with the same name — OPEN

Two objects, one name, two different address spaces.

    $ printf '\t.xcomm\tbuf, 4\n\t.text\n\t.globl\tf1\nf1:\tnop\n' > f1.s   # xdata
    $ printf '\t.icomm\tbuf, 4\n\t.text\n\t.globl\tf2\nf2:\tnop\n' > f2.s   # idata
    $ $AS -o f1.o f1.s ; $AS -o f2.o f2.s
    $ $LD -o a.elf f1.o f2.o ; echo "ld exit=$?" ; $READELF -S a.elf | grep -E 'xbss|ibss'
    ld exit=0
      [ 2] .xbss             PROGBITS        00000000 000057 000004 00   W  0   0  1
    $ $LD -o b.elf f2.o f1.o ; echo "ld exit=$?" ; $READELF -S b.elf | grep -E 'xbss|ibss'
    ld exit=0
      [ 2] .ibss             PROGBITS        00000020 000057 000004 00   W  0   0  1

Same two inputs, opposite order, and the variable moves from external RAM
address 0x0000 to internal RAM address 0x0020. No diagnostic either way. With
unequal sizes the larger common wins instead, which is the same silent
unification by another rule:

    $ $AS -o f3.o f3.s   # .xcomm buf, 8
    $ $LD -o c.elf f3.o f2.o ; $LD -o d.elf f2.o f3.o   # both exit 0
      [ 2] .xbss             PROGBITS        00000000 000057 000008 00   W  0   0  1
      [ 2] .xbss             PROGBITS        00000000 000057 000008 00   W  0   0  1

The object files do carry the space (`PRC[0xff04]` for xdata, `PRC[0xff03]` for
idata, seen with `readelf -s`), so the information the linker would need is
there and is not used. Unchanged.

## 6. `.pcode` landing past 0x1FFF — OPEN

    $ cat p.s
            .text
            .globl  ptarget
            .pcode  ptarget
            .space  0x2000
    ptarget:
            nop
    $ $AS -o p.o p.s && $READELF -r p.o
    00000000  0000040b R_I51_13_PCODE    00002003   PTARGET + 0
    $ $LD -o p.elf p.o ; echo "ld exit=$?" ; $NM p.elf | grep -i ptarget
    ld exit=0
    00002003 T PTARGET
    $ $OBJCOPY -O binary -j .text p.elf p.bin ; od -An -tx1 -N4 p.bin
     00 03 00 00

0x2003 masked to 0x0003 and written out. The code in bfd/elf32-i51.c is
unchanged:

      /* Use lower 13 bits for addresses > 0x1FFF */
      if (srel > 0x1FFF)
        srel = srel & 0x1FFF;

The assembler still catches the same number when it is a constant, which is what
makes the linker's silence a hole rather than a policy:

    $ printf '\t.text\n\t.pcode\t0x2003\n' > pc.s ; $AS -o pc.o pc.s
    pc.s:2: Error: Pcode exec address out of 13-bit range: `8195'.
    as exit=1

Unchanged.

## 7. `R_I51_8_B2B` out of range is a warning — OPEN

    $ printf '\t.text\n\t.globl start\nstart:\n\tsetb\tB2B(bdvar,1)\n' > b.s
    $ $AS -o b.o b.s
    $ $LD --defsym BDVAR=0x100 -o b1.elf b.o ; echo "ld exit=$?"
    ld-new: b.o: in function `START':
    (.text+0x1): warning: internal error: out of range error
    ld exit=0
    $ $OBJCOPY -O binary -j .text b1.elf b1.bin ; od -An -tx1 -N3 b1.bin
     d2 01 22
    $ $LD --defsym BDVAR=0x10 -o b2.elf b.o ; echo "ld exit=$?"        # below the RAM window
    (.text+0x1): warning: internal error: out of range error
    ld exit=0
     d2 01 22
    $ $LD --defsym BDVAR=0x21 -o b3.elf b.o ; echo "ld exit=$?"        # legal, for contrast
    ld exit=0
     d2 09 22

`i51_final_link_relocate` does return `bfd_reloc_outofrange` now, but
`elf32_i51_relocate_section` routes that to `info->callbacks->warning` and then
returns 1. Warning text, exit 0, and the byte left in the image is the raw bit
offset `01` - a `setb 0x01`, a real instruction on a wrong bit. Unchanged.

## 8. register aliases without `.using` — FIXED

    $ printf '\t.text\n\tmov\ta, AR0\n' > u1.s ; $AS -o u1.o u1.s
    u1.s:2: Error: missing .using
    as exit=1
    $ printf '\t.text\n\tpush\tar7\n' > u2.s ; $AS -o u2.o u2.s
    u2.s:2: Error: missing .using
    as exit=1
    $ printf '\t.text\n\t.using\t0\n\tmov\ta, AR0\n\tpush\tar7\n' > u3.s ; $AS -o u3.o u3.s
    as exit=0
       0:   e5 00       	mov	A, 0x00
       2:   c0 07       	push	0x07

A plain `as_bad` with a file and line, exit 1. No internal error, no abort.
Fixed.

## 9. `.byte LOW(sym)` / `HIGH(sym)` — OPEN

    $ cat l.s
            .text
            .globl  sym
    sym:    nop
            .byte   LOW(sym)
            .byte   HIGH(sym)
    $ $AS -o l.o l.s
    l.s:4: Error: junk at end of line, first unrecognized character is `('
    l.s:5: Error: junk at end of line, first unrecognized character is `('
    as exit=1

Lower case is the same, and so is a constant argument:

    $ printf '\t.text\nsym:\tnop\n\t.byte\tlow(sym)\n' > l2.s ; $AS -o l2.o l2.s
    l2.s:3: Error: junk at end of line, first unrecognized character is `('
    $ printf '\t.text\n\t.byte\tLOW(0x1234)\n' > l3.s ; $AS -o l3.o l3.s
    l3.s:2: Error: junk at end of line, first unrecognized character is `('

The operand form does work, which is the whole of the difference: `LOW`/`HIGH`
are handled in the instruction operand parser and nowhere else.

    $ printf '\t.text\nsym:\tnop\n\tmov\ta,#LOW(sym)\n\tmov\ta,#HIGH(sym)\n' > l4.s
    $ $AS -o l4.o l4.s ; echo "as exit=$?" ; $READELF -r l4.o | tail -2
    as exit=0
    00000002  00000107 R_I51_L           00000000   .text + 0
    00000004  00000108 R_I51_H           00000000   .text + 0

The reported repro - the directive - is unchanged.

## 10. `movx @Ri` paging — OPEN

    $ cat x.s
            .xdata
            .space  0xf0
    lowobj: .space  1
            .space  0xff
    hiobj:  .space  1
            .text
            .globl  start
    start:
            mov     r0, #lowobj
            movx    a, @r0
            mov     r0, #hiobj
            movx    a, @r0
    $ $AS -o x.o x.s && $LD -o x.elf x.o ; echo "ld exit=$?"
    ld exit=0
    $ $NM x.elf | grep -iE 'lowobj|hiobj'
    000001f0 ? HIOBJ
    000000f0 ? LOWOBJ
    $ $OBJCOPY -O binary -j .text x.elf x.bin ; od -An -tx1 x.bin
     78 f0 e2 78 f0 e2 22

Two objects 0x100 apart in xdata, one encoding. `mov r0,#hiobj` truncates
0x01F0 to `#0xF0` with no diagnostic, and nothing writes P2, so both `movx a,@r0`
read the same external byte. Unchanged.

---

# Testbench honesty

## 11. `hexoracle.py` `want_counts is None` — OPEN

`diag` and `serial` are recorded with `None` in place of the six byte-class
counts, and the code takes the size check as the whole verdict for them:

    tb/hexoracle.py:104   "diag":    (1264,      3,  None, "...")
    tb/hexoracle.py:116   "serial":  (9647,  -1519,  None, "...")
    tb/hexoracle.py:236   elif want_counts is None:
                              verdict = "explained %+d" % delta

So overwrite both ROMs with zeros, keeping their length, after a real
`make oracle` run:

    $ python3 -c "...open(p,'wb').write(b'\0'*n)..." work/oracle/projekt/{diag,serial}/www8051.rom
    diag   zeroed, 1267 bytes
    serial zeroed, 8128 bytes
    $ python3 tb/hexoracle.py --tree work/oracle --oracle work/oracle-hex
    project   2001   ours  delta  addr16 acall11  word16 pcode13   zero8  residual  verdict
    diag       1264   1267      3       0       0       0       0       0         0  explained +3
    ...
    serial     9647   8128  -1519       0       0       0       0       0         0  explained -1519
    ...
    all 10 projects agree with the 2001 oracle: recorded size delta, and every
    one of addr16/acall11/word16/pcode13/zero8/residual at its recorded count
    hexoracle exit=0

Two of ten ROMs are 9395 bytes of zeros and the oracle says all ten agree, and
says so in the sentence that names the six classes it did not compute. The other
eight are still gated byte by byte. Unchanged.

## 12. `isa_check.py` degenerate invocations — OPEN

    $ python3 tb/isa_check.py --build $B --table tb/isa/8051.txt --stages ''
    == table: 280 instructions
    PASS
    exit=0

    $ python3 tb/isa_check.py --build $B
    PASS
    exit=0

    $ python3 tb/isa_check.py --build $B --stages ''
    PASS
    exit=0

`stages = [s for s in args.stages.split(',') if s]` makes the empty string an
empty list, the unknown-stage check passes vacuously, `run_table` skips all
three stage blocks, and `main` prints PASS because `failures == 0`. The 280-line
table is read and parsed - the "== table: 280 instructions" line is real - and
then nothing is done with it. `--table` and `--program` are both optional, so
the no-argument run asserts nothing at all. Unchanged.

## 13. three copies of the stage list — OPEN

    $ grep -n '^TOOLGATE\|^GATE\|^MUTGATE' tb/Makefile
    88:TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons script
    89:GATE     := $(TOOLGATE) check oracle
    90:MUTGATE  := $(TOOLGATE) check
    $ grep -n '^STAGES' tb/mutation/run.py
    33:STAGES = ['isa', 'branch', 'sim', 'defaultlink', 'commons', 'check']
    $ grep -n 'run: make -C tb' .github/workflows/gate.yml
    35: isa   39: roundtrip   43: branch   47: bits   51: reloc   55: sim
    59: defaultlink   63: commons   71: script   78: check   82: check-canary
    91: oracle

MUTGATE has ten stages. `run.py`'s STAGES has six - `roundtrip`, `bits`,
`reloc` and `script` are missing. `gate.yml` is a third copy, one hand-written
step per stage rather than the list. The Makefile's own comment above these
lines says the opposite:

    # The merge gate, in one list, so the workflow and the mutation harness cannot
    # drift apart from it.
    ...
    # check is in the list now and gate.yml runs the list.

`gate.yml` does not run the list, it repeats it. The only thing that saves
`make mutants` is that the Makefile passes `--stages $(MUTGATE)` on the command
line, so `run.py`'s own six-stage list is what anyone invoking `run.py`
directly gets. Three copies, still drifted. Unchanged.

## 14. `gen.py` drops mutants and emits unkillable ones — OPEN

Mutant ids are `file-operator-line`, so two mutants of the same operator on the
same line collide and the second is dropped without a word:

    tb/mutation/gen.py:401   if m['id'] in seen:
                                 continue

Instrumented copy of gen.py, run against the tree `make build` produced:

    $ python3 gen_instr.py --tree work/modern/binutils-2.47 --out m2.json
    158 mutants -> m2.json
    mutants dropped on id collision: 2
      DROPPED bfd-relop-353    | dropped ['      if (srel > ((1 << 7) - 1) || (srel <= - (1 << 7)))']
      DROPPED bfd-constpm1-390 | dropped ['      if ((srel < 0x30) && (((srel - 0x20) * 8 + x) >= 0x81)) ...']

Both are real single faults in `bfd/elf32-i51.c` - one loosens the 7-bit
pc-relative range check, one moves the bit-fold overflow bound - and neither is
ever tested.

Comment-only mutants are still generated too. Of the 158, one changes nothing
but a comment:

    bfd-relop-408   /* Use lower 13 bits for addresses > 0x1FFF */
              ->    /* Use lower 13 bits for addresses >= 0x1FFF */

That mutant is unkillable by construction: the compiler cannot see it. It counts
as a survivor and lowers the reported kill rate for a reason that has nothing to
do with the tests. Unchanged.

## 15. `bits.py` `bit-0` / `bit-1` — OPEN

    tb/isa/bits.py:113   dcase('bit-0',    '.bitdata\nBIT0:\t.bit 0', ''),
    tb/isa/bits.py:114   dcase('bit-1',    '.bitdata\nBIT1:\t.bit 1', ''),

`run-bits.py` turns `want` into `bytes.fromhex(c['want'])` and compares it with
the `.text` of the assembled fragment. Both fragments put nothing in `.text`:

    $ .bit 0 -> .text is 0 bytes: []
    $ .bit 1 -> .text is 0 bytes: []

So both cases evaluate `b'' != b''` and pass. The bit count the directive
reserves is never looked at, and the two cases are indistinguishable from each
other and from any other directive that emits no code. Unchanged.

## 16. `i51_symbol_is_valid` coverage — OPEN

The hook is installed (`opcodes/disassemble.c`, `info->symbol_is_valid =
i51_symbol_is_valid`) and it is the only thing keeping SFR equates from naming
code addresses. Measured, not inferred: a counter was compiled into the function
in the built tree and the full gate run.

Positive control first, so an empty counter means something:

    $ $OBJDUMP -d a.o > /dev/null          # an ELF with symbols
    symbol_is_valid calls: 2

Then the gate:

    $ rm -f marks/* ; make -C tb gate BUILD=work/modern/build
    gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
    $ ls marks/
    (empty)

Zero calls in the whole gate. The reason is in the tool log - every objdump the
gate runs was captured by wrapping the binaries:

    $ awk '{print $1}' toolcalls.log | sort | uniq -c
        584 binutils/objdump   750 binutils/objcopy   784 gas/as-new
         58 ld/ld-new           23 binutils/readelf    12 binutils/nm-new   1 binutils/ar
    $ grep '^binutils/objdump' toolcalls.log | sed 's|/[^ ]*/||g' | sort | uniq -c
        584 binutils/objdump -D -z -b binary -m i51 out.bin

All 584 are `-b binary`. A binary BFD has no symbol table, so the symbol filter
is never consulted. No gate stage disassembles an ELF. Unchanged: 0% coverage.

## 17. `run-commons.sh` and `ld -r` — OPEN

    $ grep -n -- '-r' tb/sim/run-commons.sh
    (no match: every link in it is a final link)

There is exactly one `ld -r` in the whole gate, and it is not in commons:

    $ grep '^ld/ld-new' toolcalls.log | grep -w -- '-r'
    ld/ld-new -o /tmp/tmpsf2vq92n/partial.elf -r /tmp/tmpsf2vq92n/a.o /tmp/tmpsf2vq92n/b.o
    $ grep -n 'partial' tb/sim/*.py
    tb/sim/run-reloc.py:346:  comb, log = t.link([a, b], 'partial', extra=['-r'])

Its two inputs (`A_SRC`/`B_SRC` in run-reloc.py) contain no memory-space common
at all - `BVAR` is a defined `.bdata` byte - so `elf32_i51_link_output_symbol_hook`
returns at its first `if` and its body never runs. Measured the same way as 16,
with a marker inside the body past the early returns:

    positive control:  $ $AS -o c.o c.s     # .xcomm mybuf, 4
                       $ $LD -r -o part.elf c.o
                       hook calls: 1
                       common in .xbss
                       $ $READELF -s part.elf | grep MYBUF
                            5: 00000001     4 OBJECT GLOBAL DEFAULT PRC[0xff04] MYBUF

    full gate:         $ ls marks/
                       (empty)

The hook's whole purpose - putting the `SHN_I51_*` space index back on a common
that a relocatable link degraded to `SHN_COMMON` - is executed zero times by the
gate. `run-commons.sh` still tests final links only. Unchanged.

## 18. removing the `r_offset` bounds guard — OPEN

The guard is in the tree:

    bfd/elf32-i51.c:335
      if (!bfd_reloc_offset_in_range (howto, input_bfd, input_section,
                                      rel->r_offset * bfd_octets_per_byte (...)))
        return bfd_reloc_outofrange;

Deleted it in the built tree, rebuilt, ran the whole gate:

    $ grep -c 'bfd_reloc_offset_in_range' work/modern/binutils-2.47/bfd/elf32-i51.c
    0
    $ grep -n 'GUARD REMOVED' work/modern/binutils-2.47/bfd/elf32-i51.c
    337:  /* GUARD REMOVED FOR THIS EXPERIMENT */
    $ make -j4 ; make -C tb gate BUILD=work/modern/build ; echo "exit=$?"
    == isa ... PASS         == roundtrip ... PASS     == branch 24 cases PASS
    == bits 50 cases PASS   == reloc 36 checks PASS   == sim P1=127 PASS
    == defaultlink PASS     == commons PASS           == script PASS
    == check  10/10 PASS    == oracle all 10 agree
    gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
    exit=0

Every stage green with the guard gone. No stage feeds the linker an object with
an out-of-range `r_offset`, so nothing notices. The gate is still blind to it.
Unchanged.

---

# Docs

## 19. `tb/base2001.PROVENANCE:7` — OPEN

    $ sed -n '5,8p' tb/base2001.PROVENANCE
    format the 2001 port emits - big-endian ELF, e_machine 0x7262, symbol case as
    written in the source. base.7z ships the same 33 paths in the format the current
    port emits - little-endian ELF, e_machine 0x1051, symbols uppercased by the
    assembler.

Actual, read out of the two archives:

    $ 7z x tb/base.7z ; 7z x tb/base2001.7z ; python3 em.py
    base.7z
       e_machine ('LE', '0xa5')   - 30 files, e.g. cgi/xon.obj
    base2001.7z
       e_machine ('BE', '0x7262') - 28 files, e.g. cgi/xon.obj

base.7z carries **0xa5**, not 0x1051. Not one object in either archive carries
0x1051 - the value is gone from the tree entirely (`grep -rn 1051 mcs51/ README.md`
finds nothing; the `EM_I51_OLD` case in readelf and the include/elf/i51.h comment
are both gone). The line is still wrong, in a new way: what it says about the
current port is now right (`readelf -h` on fresh gas output: little endian,
"Intel 8051 and variants" = 0xa5), and the number it gives is now the one thing
that no longer describes anything. Same sentence, still false. The claim about
base2001.7z on line 5 (0x7262 BE) is correct.

## 20. the 12 false statements of b89f1ae — CHANGED, 2 fixed, 10 still false

b89f1ae counted 12: five never-true (A1-A5) and seven stale (B1-B7). Re-checked
one by one against main.

### FIXED (2)

**A2 - 0x1051 attributed to the 2001 lineage, in three places.** All three
places are gone. README says nothing about 0x1051; the `include/elf/i51.h`
comment and the `case EM_I51_OLD:` readelf string are not in the patches:

    $ grep -n '1051\|web51.hw.cz lineage\|legacy web51' mcs51/*.patch README.md
    (no output)
    $ grep -n 'EM_8051' mcs51/additions.patch README.md
    mcs51/additions.patch:1024:+#define ELF_MACHINE_CODE	EM_8051
    mcs51/additions.patch:3875:+/* The machine number is the registered EM_8051 (165), ...
    README.md:27:- output objects carry the registered ELF machine `EM_8051` (165), so a

The wrong attribution cannot be made any more because the whole
accept-0x1051-on-input path is gone. (It survives in one place, in the file
covered by item 19 - counted there, not here.)

**B6 - `objects-report/PROVENANCE` §6 "md5 (now)" table.** The file no longer
exists:

    $ git ls-tree -r --name-only HEAD | grep -c objects-report
    0
    $ grep -rn 'md5 (now)\|objects-report' tb README.md .github
    (no output)

Fixed by deletion, which for a stale table is a fix.

### STILL FALSE (10)

**A1 - README "Migrated from 'elf' to 'generic' template".** Still in README
under "Key Changes". Still not a migration: the 2001 patch already used it.

    $ 7z x tb/ref.7z ; grep -n 'TEMPLATE_NAME' i51.patch.112n
    4098:+ TEMPLATE_NAME=generic
    $ grep -n -A2 'TEMPLATE_NAME' mcs51/additions.patch
    4086:+TEMPLATE_NAME=generic
    4087:+EXTRA_EM_FILE=genelf

**A3 - tb/Makefile: "oracle ... does not fail a project that will not build".**
The comment is at lines 84-87, verbatim. The recipe it describes:

    $ sed -n '/oracle: a project that does not build/,+1p' tb/Makefile
                    echo "oracle: a project that does not build cannot be compared"; \
                    exit 1; \

Oracle does fail such a project. The stated reason MUTGATE omits oracle is
still a reason that is not true.

**A4 - gate.yml: "oracle below would let it pass".** Still there, twice:

    $ grep -n 'does not fail a project that will not build\|would let it pass' \
          .github/workflows/gate.yml
    12:# projects was `oracle', which does not fail a project that will not build, so
    75:      # build is a failure here; oracle below would let it pass.

Same contradiction with the same `exit 1` in the oracle recipe.

**A5 - base2001.PROVENANCE header, "the format the current port emits ...
e_machine 0x1051".** See item 19. Still false, and now false against the archive
as well as against the port.

**B1 - base2001.PROVENANCE's own archive hash and size.**

    $ sed -n '18,19p' tb/base2001.PROVENANCE
    Archive sha256: 03399d746b3909d471548fefc7b4f3b66341c32521c2d5d4133e7f27bdf3ea13
    Archive size:   27907 bytes
    $ sha256sum tb/base2001.7z ; stat -c %s tb/base2001.7z
    056aed4d13749893182f9a1c4e48544ce6ce42f0e1cb85c7c6c5cf88c7d3c2ef
    27900

**B2 - §2 and §6 hashes and size of lib/www51.sc.** §2 records
`aeb3d964... 5629`, §6 records `b4b89651...` / `aeb3d964...` and "both 5629
bytes". Recomputed from the archives:

    base.7z:lib/www51.sc      3dc717e79adee15e04b03d091964a9e780f6e08615a4a5c6be9638f3d342cb1f  5623
    base2001.7z:lib/www51.sc  1c5cfb4c8c90ef72a5875a307d8c7ee17b569a08dd91bcdaf2e901dce77655cb  5623

All four numbers wrong; 265 lines is still right. The derivation §6 states does
still hold - `base.7z's script with _RETI_ -> _reti_` reproduces the overlay's
copy byte for byte (checked programmatically, True).

Beyond the counted item: every one of the seven §3 "what the overlay replaces"
hashes is now stale too, because base.7z was repacked (it now carries 0xa5, see
item 19). 7 of 7 mismatch on hash, 7 of 7 match on size. §2's other 33 entries
are all still correct.

**B3 - §5 "lib/www51.sc comments out *(reset_network)".** Still says so; the
line is live in both archives:

    $ grep -n 'reset_network' b/lib/www51.sc b2/lib/www51.sc
    b/lib/www51.sc:82:    *(reset_network)
    b2/lib/www51.sc:82:    *(reset_network)

**B4 - §6 "gnu13's own lib/www51.sc ... still has *(reset_network) live, where
base.7z's has it commented out".** Inverted, unchanged; same grep as B3.

**B5 - §4 "lib/web51.obj (a duplicate of base.7z's lib/web51_80.obj)".** Not a
duplicate, not even the same length:

    lib/web51.obj      265e5cc76b945617...  10172
    lib/web51_80.obj   fee841e7329e4b5e...  10280

**B7 - tb/Makefile oracle comment "Two repairs are made to the extracted tree
before building".** Still there. The recipe does no repair - it extracts
base.7z, moves the .hex files aside, deletes the shipped .rom, writes the tool
wrappers, builds, and runs hexoracle.py. And repair 1 as described (restoring
`*(reset_network)`) is already in base.7z (B3), so it describes a state the
archive left behind.

Tally for item 20: **2 fixed, 10 still false.** The two that were fixed were
fixed by deleting the code and the file that carried them, not by correcting a
sentence. Every one of the ten survivors is a sentence someone would have had
to edit.

---

# Counts

    port correctness (1-10)   FIXED 1   OPEN 8    CHANGED 1
    testbench honesty (11-18) FIXED 0   OPEN 8    CHANGED 0
    docs (19-20)              FIXED 0   OPEN 1    CHANGED 1
    ------------------------------------------------------
    total                     FIXED 1   OPEN 17   CHANGED 2

    inside item 20            2 of 12 fixed, 10 still false

FIXED: 8 (`missing .using` is a diagnostic now).
CHANGED: 4 (default script fixed, project script not), 20 (2 of 12).
OPEN: 1 2 3 5 6 7 9 10 11 12 13 14 15 16 17 18 19.

The gate is green on all eleven stages. Sixteen of the seventeen open items are
defects live in the tree that gate certifies; the seventeenth (18) is the gate
itself, shown green with a bounds check deleted out of the linker.

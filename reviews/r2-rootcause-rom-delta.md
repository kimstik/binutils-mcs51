# Root cause of the ROM delta against the 2001 `.hex`

`tb/base.7z` ships, for each of the ten projects, `projekt/<p>/www8051.hex` next to
`projekt/<p>/www8051.rom`. At commit 1563588 each `.hex` decoded byte-for-byte to
the `.rom` beside it, 10 of 10. The `.rom` files have since been regenerated three
times by this port; the `.hex` files never were. `www8051.hex` is therefore the
only 2001 artefact in this repository that nothing here can reproduce, and the
only reference `make check` was not measuring itself against.

Measured on `work/green` at 5d02910, `.rom` against the decoded `.hex`:

```
$ 7z x -owork/refrom tb/base.7z            # decode each shipped .hex, cmp against the .rom
$ python3 - <<'EOF'
  ... hexoracle.read_ihex(p + '/www8051.hex') vs open(p + '/www8051.rom','rb').read()
EOF
proj      2001hex  greenrom  delta
diag         1264      1264      0    (150 bytes differ)
ds1620       6284      6281     -3
ds1822       6078      6075     -3
lcd          5754      5720    -34
led1         5173      5170     -3
led2         5010      5007     -3
led3         5200      5197     -3
serial       9647      8125  -1522
welcome      4812      4809     -3
wjava        4812      4809     -3
```

Everything below is reproduced by `make -C tb oracle`.

---

## The table

| project | delta | cause | verdict |
|---------|-------|-------|---------|
| diag    | ±0, 150 bytes differ | 2001 linked diag with ld's built-in i51 script, not `www51.sc`; `reset_network` was an orphan on both sides, so both ROMs are `.text` alone at 0x4F0. Every differing byte is a 2001 relocation defect (below). | **2001 is broken, ours is right.** diag is the one project that `lcall network_init` from its own main, so it is also the one whose 2001 ROM is legitimately 3 bytes short of the others' shape. |
| ds1620  | −3  | `reset_network` | **our deliverable is broken.** Input defect: `base.7z`'s `lib/www51.sc` comments out `*(reset_network)`. |
| ds1822  | −3  | `reset_network` | same |
| lcd     | −34 | `reset_network`, 0x22 bytes here: 0x1F from `projekt/lcd/www8051.asm` plus the 3 from `packet.obj` | same |
| led1    | −3  | `reset_network` | same |
| led2    | −3  | `reset_network` | same |
| led3    | −3  | `reset_network` | same |
| serial  | −1522 | −1530 for `index.html` + `setup.html`, which `base.7z`'s `serial/Makefile` builds with `html2db.pl -cpueeprom` where 2001 used `-cpurom`, +8 for the extra directory word `-index 0` adds, −3 for `reset_network`. Zero toolchain involvement. | **ours is right, the 2001 image is dead.** At 9647 bytes it is 1455 bytes past the 8 KB `text` region `www51.sc` declares for the AT89S8252. Our linker refuses that link outright; 2.11.2 did not. |
| welcome | −3  | `reset_network` | same as ds1620 |
| wjava   | −3  | `reset_network` | same as ds1620 |

Two findings, then. One is ours and it is serious. One is the oracle's and it is
worse.

---

## 1. `serial` −1522: two HTML pages that no longer fit in ROM

The 2001 `serial` ROM carries `index.html` and `setup.html` inside the code image:

```
$ python3 -c "d=open('serial.bin','rb').read()[0x700:0xd60]; \
              print(''.join(chr(c) if 32<=c<127 else '.' for c in d))"
...</form></body></html><html><meta http-equiv="Cache-Control" content="no-cache">
<title>89C8252 WWW server</title>...<title>89C8252 WWW setup</title>...
```

Ours carries them in the EEPROM image instead:

```
$ grep -c "89C8252 WWW setup" work/tb/projekt/serial/www8051.eep   # ours
1
$ grep -c "89C8252 WWW setup" .../orig/projekt/serial/www8051.eep  # 2001, untouched in base.7z
0
$ ls -l www8051.eep
2001:  470 bytes      ours: 2000 bytes
```

`base.7z`'s `projekt/serial/Makefile` builds them with `html2db.pl -binutils
-cpueeprom`, which emits `.section ee_dir` / `ee_files`; `www51.sc` sends those to
`.eeprom`. 2001 used `-cpurom`, which emits `cpu_dir` / `cpu_files`, and those go
to `.text`.

Flipping the flag back reproduces the 2001 partition exactly:

```
$ sed -i 's/-cpueeprom/-cpurom/' projekt/serial/Makefile
$ make
ld: www8051.o section `.text' will not fit in region `text'
```

`www51.sc` declares `text (rx) : ORIGIN = 0, LENGTH = 0x2000` - the AT89S8252's
8 KB of flash. The 2001 image is 9647 bytes. Raising the region only to see the
number:

```
$ sed -i 's/LENGTH = 0x2000/LENGTH = 0x4000/' lib/www51.sc && make
rom = 9658   eep = 470          # 2001: rom 9647, eep 470
```

`.eeprom` lands on 470 bytes, byte-for-byte the 2001 size. The remaining 11 in
`.text` are 8 for the directory word `-index 0` adds to `index.obj`'s dir entry
(0x10 against setup's 0x08) and 3 for `reset_network`. Dropping both:

```
$ sed -i 's/ -index 0//' projekt/serial/Makefile          # and reset_network out
$ make
rom = 9647  eep = 470           # exact, both images
```

and the whole 9647-byte stream then classifies cleanly against the oracle
(`addr16 373, acall11 4, word16 221, pcode13 29, zero8 738, residual 55`), which
is what says the reconstruction is the right one and not an arithmetic
coincidence.

**Verdict: ours is correct.** The move to `-cpueeprom` is the change that makes
`serial` fit the part it is for. The 2001 `.hex` is a stale image that was 1455
bytes over the declared code region; 2.11.2 linked it anyway, the current linker
does not. −1522 is not a relocation slip, a dropped section, or an unlinked
archive member. It is 1530 bytes of HTML moving from flash to EEPROM, less 8
bytes of directory, less the 3 below.

---

## 2. The −3 / −34: `LCALL network_init` is missing from nine shipped ROMs

Confirmed, not refuted. The mechanism the earlier audit named is right and the
consequence is worse than a size delta.

```
$ objdump -h work/tb/projekt/led1/www8051.o
  0 .text         00001432  00000000 ...
  8 reset_network 00000003  00001432  00001432 ...   <- past _etext
$ grep -n reset_network work/tb/lib/www51.sc
82:    /* *(reset_network) */
```

`base.7z`'s `lib/www51.sc` has the line commented out, so `reset_network` matches
no output section, ld places it as an orphan immediately after `.text`, and
`objcopy -j .text -O binary` does not copy it. `tb/base2001.PROVENANCE` §5 already
records that this is base.7z's edit: gnu13's copy of `www51.sc` does not comment
it out.

What is in it:

```
$ sed -n '787,789p' work/tb/lib/packet.asm
	.section reset_network, "a"
	LCALL	network_init
```

The section sits between `reset_device` and `reset_end` in the script, i.e. inside
the straight-line reset sequence in `lib/web51.asm`. It is the only call to
`network_init` in nine of the ten projects:

```
$ grep -rn "network_init" work/tb/lib/*.asm work/tb/projekt/*/www8051.asm
lib/packet.asm:40:	.global	network_init
lib/packet.asm:407:network_init:
lib/packet.asm:788:	LCALL	network_init
projekt/diag/www8051.asm:108:	lcall	network_init      <- diag, and only diag
```

So every ROM `make check` currently certifies, for ds1620, ds1822, lcd, led1,
led2, led3, serial, welcome and wjava, never initialises the RTL8019AS. The
symbol is linked in and reachable at 0x11BC; nothing jumps to it.

Restoring the one line puts eight of the ten back on the 2001 ROM's exact length:

```
$ sed -i 's|/\* \*(reset_network) \*/|*(reset_network)|' lib/www51.sc && rebuild
proj      2001    before    after
diag      1264     1264     1267   (+3, explained: 2001 used the built-in script)
ds1620    6284     6281     6284    0
ds1822    6078     6075     6078    0
lcd       5754     5720     5754    0
led1      5173     5170     5173    0
led2      5010     5007     5010    0
led3      5200     5197     5200    0
serial    9647     8125     8128   (2001 serial has no reset_network either)
welcome   4812     4809     4812    0
wjava     4812     4809     4812    0
```

**Verdict: our deliverable is broken and the 2001 layout is right.** The fault is
not in the port - gas and ld do exactly what the script says - it is in
`base.7z`'s copy of `lib/www51.sc`. It is not fixed in `base.7z` here: that
archive also holds the `.hex` oracle and the objects `base2001.PROVENANCE` hashes,
and repacking it to change one line would have to drag ten regenerated reference
ROMs, `base2001.7z`'s derived copy of the same script, and that provenance
document along with it. `make -C tb oracle` applies the repair to its own
extraction, under a guard that the exact commented line is still there, and shows
the convergence above. Repairing the shipped archive is the follow-up.

---

## 3. What the 2001 `.hex` is, and why byte equality is not the goal

The 2001 ROMs are not correct code. With the layouts aligned, every remaining
differing byte falls into one of four defects, all of them one bug: **the 2001
build read and wrote every relocated 16-bit field little-endian**, and left 8-bit
internal-RAM operands unrelocated.

```
2001 led1 0x0000:  02 26 00  02 bb 00  ...       LJMP 0x2600, LJMP 0xBB00
ours led1 0x0000:  02 00 26  02 01 b8  ...       LJMP 0x0026, LJMP 0x01B8
                      ^^^^^ same low byte, high byte lost into the placeholder
```

| class | what 2001 wrote | why |
|-------|-----------------|-----|
| `addr16` | `(lo, 0x00)` where the ISA wants `(hi, lo)` | `LJMP`/`LCALL`/`MOV DPTR,#addr16`. The field is at offset+1 and the object placeholder is two zero bytes; little-endian puts `lo` where `hi` belongs and `hi` into the second placeholder byte, which is never written back. |
| `acall11` | `(lo, hi & 0xE0)` | `ACALL`/`AJMP`: three of the eleven bits live in the opcode byte (`page<<5 | 0x11`), read out of the wrong half and lost. In diag, `AJMP 0x032` (`01 32`) comes out `32 00`. |
| `word16` | `(lo, hi)` | plain `.word` and pcode fields with no flags. `cgi/grapht.obj`'s `.pcode graph_ds1620` is `06 a6 00` in ours - `GRAPH_DS1620` is at 0x06A6 and `lib/pcode.asm` reads MSB first (`MOV token,A ;save token MSB`, then `MOVC A,@A+DPTR ;get token LSB`). 2001 emits `a6 06 00`. |
| `pcode13` | `(lo, hi & 0x1F)` | `R_I51_13_PCODE` must carry three flag bits over from the object: `x = bfd_getb16(); x = (x & 0xE000) \| srel; bfd_putb16(x)`. Read little-endian, the flags come out of the low byte and are masked away. `lib/pcode.asm` reads them back with `JNB B2B(token,7)`..`,5` - the indirect flags for par1..par3. |
| `zero8` | `0x00` | every 8-bit internal-RAM, SFR and bit operand. `MOV SP,#stack` is `75 81 00` in all ten ROMs. SP = 0. |

Counts, from `make -C tb oracle`:

```
project   2001   ours  delta  addr16 acall11  word16 pcode13   zero8  residual
diag       1264   1267      3       0       0       0       0       0         0  explained +3
ds1620     6284   6284      0     308       1     137      25     400        25  ok
ds1822     6078   6078      0     357       1     141      22     427        28  ok
lcd        5754   5754      0     321       2     137      25     422        27  ok
led1       5173   5173      0     279       1     133      25     398        25  ok
led2       5010   5010      0     281       1     135      25     422        25  ok
led3       5200   5200      0     283       1     137      25     444        25  ok
serial     9647   8128  -1519       0       0       0       0       0         0  explained -1519
welcome    4812   4812      0     264       1     131      25     402        25  ok
wjava      4812   4812      0     264       1     131      25     402        25  ok
```

A ROM whose reset vector is `LJMP 0xE800` in an 8 KB part, and whose every ISR
vector, `LCALL` and `MOV DPTR` has lost its high byte, and whose stack pointer is
zero, never ran on hardware. These `.hex` files are output from an in-progress
2001 port, not the firmware that shipped.

The toolchain in `tb/ref.7z` is not the one that produced them. Built here and run
on the same inputs it emits correct big-endian code:

```
$ make -C tb frozen && make -C tb check-frozen
frozen 2.11.2 led1 0x0000:  02 00 26 02 01 b8 ...
current port  led1 0x0000:  02 00 26 02 01 b8 ...
2001 .hex     led1 0x0000:  02 26 00 02 bb 00 ...
```

So the `.hex` in `base.7z` predates the fix that `ref.7z`'s patches already carry.
It remains the only independent record of the 2001 **layout**, and that is what
the oracle checks: same `.text` length, same instruction lengths, same low byte of
every code address.

---

## 4. The residual: 25 to 28 bytes a project, and it is real

What is left after the four classes is the one genuine difference between the two
toolchains, and it is not new - `tb/frozen-report.md`, "Why .bss is still bigger",
found it from the other direction. Every residual byte is an internal-RAM or bit
address a multiple of 8 higher in ours:

```
led1, from `make -C tb oracle --verbose`:
    residual @0x0125  2001=03 ours=0b  (+8)
    residual @0x0385  2001=02 ours=0a  (+8)
    ...
    residual @0x0a0e  2001=07 ours=1f  (+24)
```

`ref.7z`'s `i51.patch.112p` patches `ld/ldlang.c` to switch common alignment off
for `bfd_arch_i51` and nothing else; `mcs51/*.patch` carries no counterpart, so
the current port gets stock `lang_one_common` and pads a 4-aligned common on a
part with no alignment requirement and 128 bytes of directly addressable RAM. The
frozen run reproduces the same 8 bytes against the reference ROMs
(`217 225 214 213 214 214 325 213 213` differing bytes, recorded in
`tb/frozen.expect`).

Whether the port should carry that patch is a decision about how it allocates
RAM. It is not decided here, it is counted: the oracle records the residual per
project and fails if it moves.

A handful of the residual bytes are 8-bit operands the 2001 link left at the
object's `0xff` filler rather than `0x00` (`@0x0979 2001=ff ours=5c`), and a
handful are the same +8 shift showing up inside a 16-bit pcode parameter
(`@0x075e 2001=2a ours=00`, ours `0x0032` against 2001's `0x002a`). Same family.

---

## 5. What changed in the testbench

`.github/workflows/frozen.yml` could not return nonzero: the testbench step
carried `continue-on-error`, the comparison went into the job summary and was
never checked, the verdict step raised a `::warning`, and the whole thing ran once
a month. That is why nine ROMs could lose `LCALL network_init` without anything
going red.

- `tb/frozen.expect` records what the 2001 toolchain actually produces - which
  project fails to link and how many bytes each of the other nine differs by.
  Reproduced here on ubuntu-24.04 / gcc 13.3.0 `-m32`, identical to the counts
  `frozen-report.md` recorded from GitHub run 32878917600.
- `tb/romdiff.py --expect` gates on that file and exits nonzero on any movement.
- `frozen.yml` now runs on every branch push and weekly, its comparison step is no
  longer `continue-on-error`, and its verdict step exits 1 - with `::error`, not
  `::warning` - when either the testbench outcome or the comparison leaves the
  recorded state.
- `tb/hexoracle.py` + `make -C tb oracle` make the 2001 `.hex` a first-class
  check: it decodes each `.hex`, applies the `reset_network` repair to its own
  extraction of `base.7z` under a guard, builds the ten projects, classifies every
  differing byte, and fails on an unrecorded size delta or a residual that moved.
  It is wired into `gate.yml`, which runs on every push.

Run against the tree as `make check` builds it today, the oracle reports exactly
the deltas this document opened with:

```
$ python3 tb/hexoracle.py --tree work/tb --oracle work/oracle-hex
FAIL led1: produced 5170 bytes against the 2001 oracle's 5173 (delta -3, recorded +0)
FAIL lcd: produced 5720 bytes against the 2001 oracle's 5754 (delta -34, recorded +0)
FAIL serial: produced 8125 bytes against the 2001 oracle's 9647 (delta -1522, recorded -1519)
```

---

## What is still divergent

- **`base.7z` still ships the broken `lib/www51.sc`.** `make check` still certifies
  nine ROMs that never call `network_init`. Only `make oracle` builds the repaired
  layout. Repacking `base.7z` - one line in `www51.sc`, ten regenerated reference
  ROMs, the derived copy in `base2001.7z`, and the hashes in
  `base2001.PROVENANCE` - is the follow-up and was not done here.
- **The 8-byte common-alignment gap is open**, exactly as `frozen-report.md` left
  it. 25 to 28 residual bytes a project, counted and gated, not fixed.
- **`diag` and `serial` are compared by size only.** Their 2001 ROMs were linked
  from project inputs `base.7z` no longer carries (diag: no `--script`; serial:
  `-cpurom`, no `-index 0`), so byte classification would be meaningless. Both
  deltas are reproduced exactly by hand, above, and recorded in `hexoracle.py`.
- **Nothing here proves our ROMs run.** The oracle proves layout agreement with a
  2001 artefact and correctness of the relocations against the ISA and against
  `lib/pcode.asm`'s own reader. `make -C tb sim` is the only execution evidence in
  the repository and it covers `testall.asm`, not these ten projects.

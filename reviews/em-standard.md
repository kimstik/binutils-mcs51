# e_machine for i51-elf: the answer is 165

**165 (`EM_8051`). Emit it. Nothing else. Keep `ELF_MACHINE_ALT1 = 0x1051` for input only.
`origin/work/green` already does exactly this. Question closed.**

Two small defects found on the way, both cosmetic, both listed at the end.

---

## 1. The registry says 165

Primary source. The gABI is the ELF generic ABI, SCO/Caldera/SCO Group/Xinuos, live at
`sco.com/developers/gabi/latest/ch4.eheader.html`. Copyright line on the page:

```
(c) 1997, 1998, 1999, 2000, 2001 The Santa Cruz Operation, Inc. All rights reserved.
(c) 2002 Caldera International. All rights reserved.
(c) 2003-2011 The SCO Group. All rights reserved.
(c) 2011-2015 Xinuos Inc. All rights reserved.
```

Fetched and parsed the `e_machine` table out of the HTML:

```
$ curl -sS -o gabi.html https://www.sco.com/developers/gabi/latest/ch4.eheader.html
$ python3 -c "...parse <tr>/<td>..." | grep -i '8051\|Intel'
EM_386 | 3 | Intel 80386
EM_IAMCU | 6 | Intel MCU
EM_860 | 7 | Intel 80860
EM_960 | 19 | Intel 80960
EM_IA_64 | 50 | Intel IA-64 processor architecture
EM_C166 | 116 | Infineon C16x/XC16x processor
EM_8051 | 165 | Intel 8051 and variants
EM_MCST_ELBRUS | 175 | MCST Elbrus general purpose hardware architecture
EM_L10M | 180 | Intel L10M
EM_K10M | 181 | Intel K10M
reserved | 182 | Reserved for future Intel use
EM_INTEL205 | 205 | Reserved by Intel
```

Registry row, verbatim: `EM_8051 | 165 | Intel 8051 and variants`.

binutils agrees. `include/elf/common.h` of the 2.47 tarball this port builds against:

```
$ grep -n 'EM_8051' binutils-2.47/include/elf/common.h
282:#define EM_8051		165	/* Intel 8051 and variants */
```

Same file, same line, in stock binutils. Not added by this port.

## 2. Nothing else in the registry covers an 8051

Swept the whole gABI table for 8-bit micros and anything "51"-shaped:

```
$ python3 -c "...parse..." | grep -Ei '\b51\b|80C51|8096|8-bit micro|microcontroller'
EM_960 | 19 | Intel 80960
EM_FX66 | 66 | Siemens FX66 microcontroller
EM_ST9PLUS | 67 | STMicroelectronics ST9+ 8/16 bit microcontroller
EM_ST7 | 68 | STMicroelectronics ST7 8-bit microcontroller
EM_68HC16/11/08/05 | 69-72 | Motorola
EM_ST19 | 74 | STMicroelectronics ST19 8-bit microcontroller
EM_AVR | 83 | Atmel AVR 8-bit microcontroller
EM_ST200 | 100 | STMicroelectronics ST200 microcontroller
EM_IP2K | 101 | Ubicom IP2xxx microcontroller family
EM_MSP430 | 105 | Texas Instruments embedded microcontroller msp430
EM_STM8 | 186 | STMicroeletronics STM8 8-bit microcontroller
matches: 15
```

Result:

- **No MCS-96 / 8096 entry exists.** Anywhere. Not in the gABI, not in binutils.
- **No 251 entry, no 151 entry.** They are 8051 *variants*. The registry text already
  says "Intel 8051 **and variants**". 165 is their entry.
- `EM_960 = 19` is the i960. Different chip, 32-bit RISC, not a 51.
- `EM_C166 = 116` is Infineon C16x. 16-bit, unrelated ISA, and `EM_XC16X = 0x4688` is
  its unofficial cousin. Neither is an 8051.
- `EM_MCS6502 = 254` is MOS 6502. "MCS" collides in the name only.
- `EM_IAMCU = 6` is Intel Quark x86. Not a 51.

165 is the only candidate. It is exact, it is official, its description literally names
this port's target.

## 3. What this project has used

Three values in the lineage. All three documented here from the artefacts.

### 0x7262 - the 2001 web51 original

Extracted `tb/ref.7z`, which holds the December 2001 patches against binutils 2.11.2:

```
$ 7z x tb/ref.7z
./i51.patch.112p
./i51.patch.112n

$ grep -n '0x7262' i51.patch.112p
622-  #define EM_AVR			0x1057
625:+ #define EM_I51			0x7262
```

Hunk context, verbatim from the patch:

```
diff -crB binutils-2.11.2/include/elf/common.h binutils-2.11.2.i51/include/elf/common.h
*** binutils-2.11.2/include/elf/common.h	Mon Jun 11 12:05:05 2001
--- binutils-2.11.2.i51/include/elf/common.h	Wed Dec 26 16:20:51 2001
  #define EM_AVR			0x1057
+ /* MCS-51 magic number - no EABI available.  */
+ #define EM_I51			0x7262
```

`grep -n 'EM_I51' i51.patch.112n` gives `#define ELF_MACHINE_CODE EM_I51` and
`elf_elfheader (abfd)->e_machine = EM_I51;`. So 2001 emitted 0x7262.

Genuine 2001 objects are shipped in `tb/base2001.7z`. Their headers:

```
$ 7z x -ob2001 tb/base2001.7z
$ od -A d -t x1 -N 24 b2001/cgi/xon.obj
0000000 7f 45 4c 46 01 02 01 00 00 00 00 00 00 00 00 00
0000016 00 01 72 62 00 00 00 01
              ^^^^^ e_machine = 0x7262, read big-endian (EI_DATA = 02)

$ python3 survey.py
b2001 {('BE', '0x7262'): 28}
```

**The 2001 objects are big-endian.** That matters below.

### 0x1051 - introduced by this repo, Aug 2026

```
$ git show 15b928d --stat | head -3
commit 15b928d7128b90d292da5ef0fca42a61e649884d
Author: kimstik <kimstik@github.com>
Date:   Mon Aug 24 13:40:19 2026 +0200
    up to 2.45.1

$ git show 15b928d -- mcs51/additions.patch | grep -n '0x1051\|0x7262\|EM_I51'
1152:-+   elf_elfheader (abfd)->e_machine = EM_I51;      <- old side, 0x7262 lineage
8265:++#define EM_I51 0x1051                             <- new side
```

`tb/base.7z`'s precompiled objects were regenerated with that toolchain:

```
$ python3 survey.py
bmain {('LE', '0x1051'): 30}
```

So 0x1051 is **this repo's own value**, little-endian, alive for exactly two commits
(`15b928d` .. `c907fad`). It was never web51's.

### 165 - what `origin/work/green` emits today

```
$ git log --oneline -S 'EM_8051' -- mcs51/
c907fad mcs51: the port on 2.47, both review rounds applied

$ grep -n 'EM_8051\|EM_I51_OLD' bfd/elf32-i51.c
602:  elf_elfheader (abfd)->e_machine = EM_8051;
982:#define ELF_MACHINE_CODE	EM_8051
983:#define ELF_MACHINE_ALT1	EM_I51_OLD

$ sed -n '26,29p' include/elf/i51.h
/* The registered machine number is EM_8051 (165), defined in elf/common.h.
   Objects from the 2001 web51.hw.cz lineage carry the unregistered value
   0x1051; it is still accepted on input.  */
#define EM_I51_OLD 0x1051
```

Built it clean from `origin/work/green`'s two patches on a fresh 2.47 tarball:

```
$ tar xf binutils-2.47.tar.xz
$ patch -p1 < mcs51/additions.patch && patch -p1 < mcs51/modifications.patch
$ .../configure --target=i51-elf --disable-gdb --disable-sim --disable-werror --disable-nls
$ make -j all-gas all-ld all-binutils
$ ./gas/as-new --version | head -1
GNU assembler (GNU Binutils) 2.47.20260726
```

Assembled a real object and looked at the header:

```
$ ./gas/as-new -o demo165.o demo.s
$ ./binutils/readelf -h demo165.o
ELF Header:
  Magic:   7f 45 4c 46 01 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF32
  Data:                              2's complement, little endian
  Type:                              REL (Relocatable file)
  Machine:                           Intel 8051 and variants
$ od -A d -t x1 -j 18 -N 2 demo165.o
0000018 a5 00        -> 0x00a5 = 165
```

Linked executable, same:

```
$ ./ld/ld-new -e _start -o demo.elf demo165.o
$ readelf -h demo.elf | grep -i 'Type:\|Machine'
  Type:                              EXEC (Executable file)
  Machine:                           Intel 8051 and variants
```

**`origin/work/green` emits 165. Correct.**

### Do 0x1051 or 0x7262 collide with anything?

Checked the *entire* `EM_*` namespace, not neighbours. 283 defines resolved to integers,
aliases followed:

```
$ python3 -c "...resolve every #define EM_* in include/elf/common.h..."
0x1051 4177 -> UNUSED
0x7262 29282 -> UNUSED
0xa5 165 -> ['EM_8051']
0x1057 4183 -> ['EM_AVR_OLD']
total EM_ defines: 283
near 0x1051 [('0x105', EM_TACHYUM), ('0x106', EM_56800EF), ('0x1057', EM_AVR_OLD), ('0x1059', EM_MSP430_OLD)]
near 0x7262 [('0x5441', EM_CYGNUS_FRV), ('0x5aa5', EM_DLX), ('0x7650', EM_CYGNUS_D10V), ('0x7676', EM_CYGNUS_D30V)]
```

Also swept every backend's declared machine code, in case a target used a bare literal:

```
$ grep -rh "define ELF_MACHINE_CODE\|define ELF_MACHINE_ALT[12]" bfd/ | awk '{print $3}' | sort -u
0 1998 1999 EM_386 ... EM_8051 ... EM_I51_OLD ... EM_Z80 E_NFP_MACH_3200 E_NFP_MACH_6000

$ grep -rn "0x1051\|0x7262\|\b4177\b\|\b29282\b" bfd/*.c bfd/*.h include/elf/*.h
include/elf/i51.h:28:   0x1051; it is still accepted on input.  */
include/elf/i51.h:29:#define EM_I51_OLD 0x1051
```

Neither value collides with a real `EM_*`. Both are still illegitimate - see next.

## 4. The rules for unregistered values

### The gABI: unassigned means reserved, not free

The gABI does not carve out a private range for `e_machine`. One sentence covers it,
verbatim from the page:

```
Other values are reserved and will be assigned to new machines as necessary.
```

That is the whole policy. No "vendor" window, no "experimental" window, no high-half
convention. Every value not in the table is **reserved to the registry** for future
assignment. Picking one is squatting on someone's future chip.

### binutils: squatting is a stopgap, and you get told off for it

`include/elf/common.h`, immediately after the last official number, verbatim:

```
/* If it is necessary to assign new unofficial EM_* values, please pick large
   random numbers (0x8523, 0xa7f2, etc.) to minimize the chances of collision
   with official or non-GNU unofficial values.

   NOTE: Do not just increment the most recent number by one.
   Somebody else somewhere will do exactly the same thing, and you
   will have a collision.  Instead, pick a random number.

   Normally, each entity or maintainer responsible for a machine with an
   unofficial e_machine number should eventually ask registry@sco.com for
   an officially blessed number to be added to the list above.	*/
```

Two rules. Pick a large random number. Then go get a real one. This port's target already
*has* a real one, so neither rule applies to output: it just uses 165.

### `EM_*_OLD` / `ELF_MACHINE_ALT1` is legitimate, and it is standard binutils practice

The mechanism. `bfd/elfcode.h`, the format-recognition gate:

```c
  /* Check that the ELF e_machine field matches what this particular
     BFD format expects.  */
  if (ebd->elf_machine_code != i_ehdrp->e_machine
      && (ebd->elf_machine_alt1 == 0
	  || i_ehdrp->e_machine != ebd->elf_machine_alt1)
      && (ebd->elf_machine_alt2 == 0
	  || i_ehdrp->e_machine != ebd->elf_machine_alt2)
      && ebd->elf_machine_code != EM_NONE)
    goto got_wrong_format_error;
```

ALT is **read-side only**. The write side is `final_write_processing`, which stamps the
canonical code unconditionally. `objcopy --alt-machine-code=1` exists
(`binutils/objcopy.c:436`) but a backend that hard-sets `e_machine` in
`final_write_processing` defeats it - proven:

```
$ ./binutils/objcopy --alt-machine-code=1 demo165.o demo1051.o
$ od -A d -t x1 -j 18 -N 2 demo1051.o
0000018 a5 00        -> still 165
```

That is not an i51 bug. AVR behaves identically, `bfd/elf32-avr.c:1593`:

```c
  elf_elfheader (abfd)->e_machine = EM_AVR;
```

and accepts the legacy value on input, `bfd/elf32-avr.c:1606`:

```c
  if (elf_elfheader (abfd)->e_machine == EM_AVR
      || elf_elfheader (abfd)->e_machine == EM_AVR_OLD)
```

Who else does it. Every one of these is upstream binutils 2.47, none is this port:

```
$ grep -rn "ELF_MACHINE_ALT1\|ELF_MACHINE_ALT2" bfd/*.c
bfd/elf-m10200.c:1381:   ELF_MACHINE_ALT1  EM_CYGNUS_MN10200
bfd/elf-m10300.c:5474:   ELF_MACHINE_ALT1  EM_CYGNUS_MN10300
bfd/elf32-am33lin.c:33:  ELF_MACHINE_ALT1  EM_CYGNUS_MN10300
bfd/elf32-arc.c:3125:    ELF_MACHINE_ALT1  EM_ARC_COMPACT2
bfd/elf32-avr.c:4148:    ELF_MACHINE_ALT1  EM_AVR_OLD
bfd/elf32-cr16.c:2800:   ELF_MACHINE_ALT1  EM_CR16_OLD
bfd/elf32-csky.c:5305:   ELF_MACHINE_ALT1  EM_CSKY_OLD
bfd/elf32-d10v.c:537:    ELF_MACHINE_ALT1  EM_CYGNUS_D10V
bfd/elf32-d30v.c:555:    ELF_MACHINE_ALT1  EM_CYGNUS_D30V
bfd/elf32-fr30.c:691:    ELF_MACHINE_ALT1  EM_CYGNUS_FR30
bfd/elf32-i51.c:962:     ELF_MACHINE_ALT1  EM_I51_OLD          <- this port
bfd/elf32-ip2k.c:1511:   ELF_MACHINE_ALT1  EM_IP2K_OLD
bfd/elf32-m32c.c:2120:   ELF_MACHINE_ALT1  EM_M32C_OLD
bfd/elf32-m32r.c:3700:   ELF_MACHINE_ALT1  EM_CYGNUS_M32R
bfd/elf32-microblaze.c:3521: ELF_MACHINE_ALT1  EM_MICROBLAZE_OLD
bfd/elf32-moxie.c:358:   ELF_MACHINE_ALT1  EM_MOXIE_OLD
bfd/elf32-msp430.c:2955: ELF_MACHINE_ALT1  EM_MSP430_OLD
bfd/elf32-pj.c:357:      ELF_MACHINE_ALT1  EM_PJ_OLD
bfd/elf32-ppc.c:10373:   ELF_MACHINE_ALT1  EM_CYGNUS_POWERPC   (+ALT2 EM_PPC_OLD)
bfd/elf32-s390.c:3908:   ELF_MACHINE_ALT1  EM_S390_OLD
bfd/elf32-score.c:4468:  ELF_MACHINE_ALT1  EM_SCORE_OLD
bfd/elf32-sparc.c:224:   ELF_MACHINE_ALT1  EM_SPARC32PLUS
bfd/elf32-v850.c:4131:   ELF_MACHINE_ALT1  EM_CYGNUS_V850
bfd/elf32-xtensa.c:11464:ELF_MACHINE_ALT1  EM_XTENSA_OLD
bfd/elf64-nfp.c:176:     ELF_MACHINE_ALT1/2  E_NFP_MACH_6000 / 3200
bfd/elf64-s390.c:4455:   ELF_MACHINE_ALT1  EM_S390_OLD
bfd/elf64-sparc.c:900:   ELF_MACHINE_ALT1  EM_OLD_SPARCV9
bfd/elfnn-ia64.c:4993:   ELF_MACHINE_ALT1  1999   /* EAS2.3 */  (+ALT2 1998 /* EAS2.2 */)
```

27 upstream targets. Emit registered, accept legacy. i51 is the 28th and does it the same
way. Pattern confirmed legitimate.

## 5. What a foreign toolchain does with each value

Foreign = the distro's own binutils, nothing to do with this port:

```
$ readelf --version | head -1
GNU readelf (GNU Binutils for Ubuntu) 2.42
```

Built the three objects: 165 from `as-new`, 0x1051 and 0x7262 by patching bytes 18-19 of
a copy. Then ran both toolchains against each.

```
########## demo165.o   e_machine = a500  (0x00a5 = 165)
--- STOCK readelf 2.42
  Machine:                           Intel 8051 and variants
--- STOCK objdump
demo165.o:     file format elf32-little
architecture: UNKNOWN!, flags 0x00000010:
--- PORT readelf
  Machine:                           Intel 8051 and variants
--- PORT objdump
demo165.o:     file format elf32-i51
architecture: i51, flags 0x00000010:

########## demo1051.o  e_machine = 5110  (0x1051)
--- STOCK readelf 2.42
  Machine:                           <unknown>: 0x1051
--- STOCK objdump
demo1051.o:     file format elf32-little
architecture: UNKNOWN!, flags 0x00000010:
--- PORT readelf
  Machine:                           MCS-51 8-bit microcontroller (legacy web51 value)
--- PORT objdump
demo1051.o:     file format elf32-i51
architecture: i51, flags 0x00000010:

########## demo7262.o  e_machine = 6272  (0x7262)
--- STOCK readelf 2.42
  Machine:                           <unknown>: 0x7262
--- STOCK objdump
demo7262.o:     file format elf32-little
architecture: UNKNOWN!, flags 0x00000010:
--- PORT readelf
  Machine:                           <unknown>: 0x7262
--- PORT objdump
demo7262.o:     file format elf32-little
architecture: UNKNOWN!, flags 0x00000010:
```

Read it plain.

- **165: a stock `readelf` that has never heard of this port names the chip.** "Intel 8051
  and variants". That string comes from upstream `binutils/readelf.c`, not from any patch
  here - the port only adds the `EM_I51_OLD` arm.
- 0x1051 and 0x7262: `<unknown>`. A stranger's tooling sees a mystery number. Every ELF
  consumer in the world - `file`, `gdb`, `pyelftools`, `LIEF`, a distro's `objdump`, a
  customer's build system - gets nothing.
- `objdump` says `UNKNOWN!` architecture in all three cases, correctly: no foreign binutils
  has an 8051 disassembler. That is a separate problem from naming, and 165 does not fix it.
  Naming is what 165 buys, and naming is the whole point.

Legacy input still works, and gets upgraded on the way out:

```
$ ./ld/ld-new -e _start -o demoold.elf demo1051.o
$ readelf -h demoold.elf | grep -i Machine
  Machine:                           Intel 8051 and variants
```

Feed the linker a 0x1051 object, get a 165 executable. That is the migration path, and it
is free.

## 6. Interoperability: who else emits ELF for an 8051

### SDCC: no.

SDCC's mcs51 port is ASxxxx, not ELF. Object suffix `.rel`, final output Intel HEX `.ihx`,
assembler `sdas8051`, linker `sdld`. From SDCC's own source, `src/mcs51/main.c`:

```
855://static const char *_asmCmd[] =
857://  "sdas8051", "$l", "$3", "$2", "$1.asm", NULL
934:    ".rel",     /* assembler object suffix */
1096:   ".rel",     /* linker object suffix */
```

SDCC's bundled binutils has no 8051 BFD target at all:

```
$ grep -in "i51\|8051\|mcs51" support/sdbinutils/bfd/config.bfd
(no output)
$ ls support/sdbinutils/bfd/elf32-*.c | wc -l
0
```

Confirmed against the SDCC manual: `.rel` intermediate, `.ihx` default load module,
`--out-fmt-s19` for Motorola S19, AOMF51 for debug. No ELF anywhere.
(https://sdcc.sourceforge.net/doc/sdccman.pdf)

### Keil, IAR, Tasking: no.

The commercial 8051 world is OMF51 / AOMF51 (Intel Absolute Object Module Format). That is
what SDCC's `--debug` emits for third-party debuggers and simulators, precisely because it
is what those tools read. Nobody in that world reads ELF.

### The two sibling ports: yes, and both squat, and both collided.

Both are forks of the same 2001 web51 lineage. Both replaced 0x7262 with a hand-picked
number. Both picked by incrementing the last official value by one. Both were then overtaken
by a real registration - exactly the failure `common.h` warns about.

`github0null/binutils-mcs51` (binutils 2.38 lineage, head `7ae1abd5`):

```
$ grep -rn "EM_I51" include/elf/common.h bfd/elf32-i51.c
include/elf/common.h:357:#define EM_I51		260	/* MCS-51*/
bfd/elf32-i51.c:866:  elf_elfheader (abfd)->e_machine = EM_I51;
bfd/elf32-i51.c:1214:#define ELF_MACHINE_CODE	EM_I51

$ sed -n '350,357p' include/elf/common.h
#define EM_LOONGARCH	258	/* LoongArch */
#define EM_KF32		259	/* ChipON KungFu32 */
#define EM_I51		260	/* MCS-51*/       <- 259 + 1
```

260 is now **`EM_U16_U8CORE`, LAPIS nX-U16/U8**, official:

```
$ grep -n "260" binutils-2.47/include/elf/common.h
360:#define EM_U16_U8CORE	260	/* LAPIS nX-U16/U8 */
```

`volumit/sdcc_aurix_scr_42` (SDCC 4.2.1 retargeted to drive an i51 binutils fork):

```
$ grep -rn "EM_I51" binutils/include/elf/common.h binutils/bfd/elf32-i51.c
binutils/include/elf/common.h:294:#define EM_I51          190     /* MCS-51*/
binutils/bfd/elf32-i51.c:877:  elf_elfheader (abfd)->e_machine = EM_I51;
binutils/bfd/elf32-i51.c:1230:#define ELF_MACHINE_CODE	EM_I51

$ sed -n '289,294p' binutils/include/elf/common.h
#define EM_MICROBLAZE	189	/* Xilinx MicroBlaze 32-bit RISC soft processor core */
#define EM_I51          190     /* MCS-51*/       <- 189 + 1
```

190 is now **`EM_CUDA`, NVIDIA CUDA architecture**, official:

```
$ grep -n "190" binutils-2.47/include/elf/common.h
308:#define EM_CUDA		190	/* NVIDIA CUDA architecture */
```

That fork's SDCC really does call this port's assembler, `src/mcs51/main.c:868`:

```c
    static const char *macroCmd_mcs51[] = {
        "i51-elf-as","-mmcs51 $1.asm","-o $2",NULL
    };
```

So it is a genuine downstream consumer of i51 ELF - emitting objects a stock `readelf` will
call an NVIDIA GPU.

### Verdict on interop

Four distinct values have been used for the same target by four forks of one 2001 patch:
0x7262, 0x1051, 190, 260. Zero interoperability between them. Two of the four now lie about
the chip to any conforming reader.

**165 is the only value that is not a private handshake.** It is the only one where two
independent implementations would agree without talking to each other, because the registry
already decided.

## 7. Recommendation

**Emit `EM_8051` = 165. Accept `EM_I51_OLD` = 0x1051 on input. Do not add an ALT for 0x7262.
`origin/work/green` is already correct - ship it.**

Reasoning, in order of weight:

1. **The value is registered and it names this exact target.** "Intel 8051 and variants."
   There is no judgement call. Using anything else is choosing to be wrong.
2. **It is the only value a stranger's tools decode.** Section 5: stock `readelf` 2.42 names
   the chip for 165 and says `<unknown>` for both alternatives. That is the entire practical
   payoff and it is not small.
3. **The alternatives are reserved, not private.** The gABI has no private range for
   `e_machine`; unassigned values are "reserved and will be assigned to new machines as
   necessary". 0x1051 and 0x7262 happen not to collide *today* (283 `EM_*` defines checked,
   both UNUSED) - but so did 190 and 260 once, and both are now taken.
4. **The two sibling ports are the proof.** Both squatted, both were overtaken by real
   registrations, both now mislabel their objects as CUDA and LAPIS. That is the failure
   mode, observed, not hypothesised.
5. **Nothing is lost.** ALT1 reads legacy objects, and `ld` upgrades them to 165 on output.
   Verified end to end in section 5.

### Keep the ALT - at 0x1051, and only 0x1051

**Yes, keep it. Value 0x1051. One ALT, not two.**

Why 0x1051 and not 0x7262: the objects that exist. `tb/base.7z` ships 30 objects at 0x1051,
little-endian, produced by this project's own 2.45.1-era toolchain. Those are readable, and
ALT1 is what makes them readable:

```
$ ./binutils/objdump -f bmain/cgi/xon.obj
bmain/cgi/xon.obj:     file format elf32-i51
architecture: i51, flags 0x00000011:
```

Why **not** a second ALT for 0x7262: it would be dead code. The genuine 2001 objects are
**big-endian**. BFD rejects on `EI_DATA` when picking the target vector, long before it ever
looks at `e_machine`, so an `ELF_MACHINE_ALT2 = 0x7262` on a little-endian-only backend can
never fire. Proven:

```
$ ./binutils/readelf -h b2001/cgi/xon.obj | grep -i 'Data:\|Machine'
  Data:                              2's complement, big endian
  Machine:                           <unknown>: 0x7262
$ ./binutils/objdump -f b2001/cgi/xon.obj
b2001/cgi/xon.obj:     file format elf32-big
architecture: UNKNOWN!, flags 0x00000011:
```

`elf32-big`, not `elf32-i51`. Adding ALT2 would change nothing. 2001 objects need
`tb/i51elf_le2be.py`, not an ALT. Correct call to leave it out.

### Exactly what the two files should contain

`include/elf/i51.h` - one define, and the comment must be **corrected**. Current text
misattributes 0x1051 to web51:

```c
/* The port emits the registered machine number EM_8051 (165), which is
   defined in elf/common.h and needs nothing from this header.

   EM_I51_OLD is the unregistered value this port itself emitted for two
   releases (commits 15b928d..c907fad, binutils 2.45.1).  The objects in
   tb/base.7z carry it.  It is accepted on input and never written; ld
   rewrites such input to EM_8051.

   It is NOT the value the 2001 web51.hw.cz port used.  That was 0x7262,
   in big-endian objects, which this little-endian backend cannot read at
   all -- an ALT for it would be dead code.  See tb/i51elf_le2be.py.  */
#define EM_I51_OLD 0x1051
```

Everything else in the file stays: the reloc table (`R_I51_*`), the `SHF_*` memory-space
masks, the `SHN_I51_*` commons. None of it touches `e_machine`.

Keeping `EM_I51_OLD` in `elf/i51.h` rather than `elf/common.h` is right, and better than
upstream's habit. `common.h` is the shared registry mirror; a value nobody registered and
only this port honours does not belong in it. It also keeps `modifications.patch` smaller.
`binutils/readelf.c:120` already has `#include "elf/i51.h"`, so the one out-of-BFD consumer
sees it.

`bfd/elf32-i51.c` - three lines, all already present and all correct:

```c
static bool
bfd_elf_i51_final_write_processing (bfd *abfd)
{
  elf_elfheader (abfd)->e_machine = EM_8051;
  return 1;
}

#define ELF_ARCH		bfd_arch_i51
#define ELF_MACHINE_CODE	EM_8051
#define ELF_MACHINE_ALT1	EM_I51_OLD
```

No `ELF_MACHINE_ALT2`. No conditional on the output value. Unconditional stamp in
`final_write_processing` is exactly what `elf32-avr.c:1593` does.

## 8. Two defects found, neither affects the answer

**a. `include/elf/i51.h:27-28` states a false provenance.** It says the 0x1051 objects come
from "the 2001 web51.hw.cz lineage". They do not - 0x7262 does. 0x1051 is this repo's own,
introduced 24 Aug 2026 in `15b928d`. The same wrong claim is in `README.md`: "the
unregistered `0x1051` that the 2001 lineage used". Replacement text is in section 7.

**b. `tb/i51elf_le2be.py` is stale.** It converts the genuine 2001 big-endian objects and
writes the *retired* value:

```
$ grep -n '0x1051' tb/i51elf_le2be.py
 4:to new i51 ELF objects (little-endian, machine 0x1051)
36:    # e_machine at offset 18 (2 bytes) - change from 0x7262 to 0x1051
39:    data[18:20] = struct.pack('<H', 0x1051)
```

Should pack `0x00a5`. Harmless today because ALT1 catches the output, but it means the one
tool that touches legacy objects produces objects a stock `readelf` cannot name. It is also
referenced by neither `tb/Makefile` nor `.github/`:

```
$ grep -rn "i51elf_le2be" tb/Makefile .github
(no output)
```

Neither defect changes the recommendation. Both are one-line fixes. Not applied - review only.

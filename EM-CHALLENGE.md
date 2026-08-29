# EM-CHALLENGE: prosecution of `EM_8051 = 165`

Brief: refute the claim that 165 is the correct and only `e_machine` for this
port. Below is the strongest case I could build against it, and what happened
to each charge.

**VERDICT: CONFIRMED.** 165 survives. Every attack line either found unanimous
agreement or found nothing at all. Two real defects turned up along the way,
both orthogonal to the number — they are recorded at the end because they are
true, not because they refute anything.

No fetch was blocked by the proxy. Every URL below returned HTTP 200; the
`curl -w` codes are quoted inline where it matters.

---

## 0. What the port actually claims

```
$ grep -n "EM_8051\|EM_I51_OLD\|0x1051" mcs51/*.patch
mcs51/additions.patch:656:+  elf_elfheader (abfd)->e_machine = EM_8051;
mcs51/additions.patch:1036:+#define ELF_MACHINE_CODE	EM_8051
mcs51/additions.patch:1037:+#define ELF_MACHINE_ALT1	EM_I51_OLD
mcs51/additions.patch:3890:+/* The registered machine number is EM_8051 (165), defined in elf/common.h.
mcs51/additions.patch:3893:+#define EM_I51_OLD 0x1051
mcs51/modifications.patch:362:+    case EM_I51_OLD:	return "MCS-51 8-bit microcontroller (legacy web51 value)";
```

Container is `TARGET_LITTLE_SYM i51_elf32_vec` / `"elf32-i51"`
(`additions.patch:1040-1041`), ELFCLASS32, ELFDATA2LSB. `bfd_i51_arch` is
8-bit word, 16-bit address, machine number 0 — one machine, no sub-machines
(`additions.patch:32-44`). The port sets **no** `e_flags`:

```
$ grep -n "e_flags\|EI_OSABI\|ELFOSABI" mcs51/additions.patch mcs51/modifications.patch
(no output)
```

Remember that last fact. It decides charge 2.

---

## Charge 1 — "the authorities disagree; 165 is ambiguous"

Sweep of every authority named in the brief, plus two the brief did not name.
All fetched fresh, all HTTP 200.

| authority | fetch | verdict at 165 |
|---|---|---|
| gABI, Xinuos (**live registry**) | `gabi.xinuos.com/elf/a-emachine.html` HTTP 200, 64160 B | `EM_8051` / `165` / `Intel 8051 and variants` |
| gABI, sco.com (stale mirror) | `www.sco.com/developers/gabi/latest/ch4.eheader.html` HTTP 200, 57280 B | same |
| binutils `include/elf/common.h` | sourceware git HEAD, HTTP 200, 67944 B | `#define EM_8051		165	/* Intel 8051 and variants */` (line 282) |
| glibc `elf/elf.h` | sourceware git HEAD, HTTP 200, 195703 B | identical text, line 299 |
| elfutils `libelf/elf.h` | sourceware git HEAD, HTTP 200, 195921 B | identical text, line 299 |
| LLVM `BinaryFormat/ELF.h` | github main, HTTP 200, 81911 B | `EM_8051 = 165,          // Intel 8051 and variants` (line 263) |
| Linux `include/uapi/linux/elf-em.h` | github master, HTTP 200, 2627 B | **absent** — see below |
| FreeBSD `sys/sys/elf_common.h` | github main, HTTP 200, 69105 B | **absent** — see below |
| radare2 `elf_specs.h` / `elf.c` | github master, HTTP 200, 179846 B | `case EM_8051: return strdup ("Intel 8051 and variants");` (elf.c:2726) |
| `file(1)` `magic/Magdir/elf` | github master, HTTP 200, 13780 B | `>18	leshort		165		Intel 8051 and variants,` (line 245) |
| Wireshark `epan/dissectors/file-elf.c` | GitHub code search | `{ 165,  "Intel 8051 and variants" },` |
| illumos `cmd/sgs/libconv/common/elf.c`, `cmd/file/file.c` | GitHub code search | carries `EM_8051` |

The comment string is **byte-identical** across binutils, glibc and elfutils
("Intel 8051 and variants"), which is what it looks like when every
downstream is a mechanical copy of one registry, not an independent guess.

**Linux and FreeBSD carry no 8051 entry — and that is not divergence.**
Neither header is a registry. `elf-em.h` is 2627 bytes total and lists only
machines Linux *runs on*; its full contents jump `... EM_HEXAGON 164 /
EM_NDS32 167 ...`, skipping 165 and 166 entirely. FreeBSD's file defines 98
`EM_*` values against binutils' 283, topping out at `EM_LOONGARCH 258` and
holding nothing in 111–182 except `EM_AARCH64 183`. Absence of an entry is
absence of an opinion. Neither header assigns 165 to anything else:

```
$ grep -nE "^#define[[:space:]]+EM_[A-Z0-9_]+[[:space:]]+1[5-7][0-9]" fbsd-elf_common.h
(no match, exit 1)
```

**The one divergence I did find is not at 165.** The Xinuos registry is
*ahead* of binutils: it runs to `EM_AIECTRLCODE 269`, while
`include/elf/common.h` stops at `EM_56800EF 262`. And Xinuos spells 180/181
`EM_L10M`/`EM_K10M` (digit one, digit zero) where binutils has
`EM_L1OM`/`EM_K1OM` (digit one, letter O). So authorities *do* drift — which
makes the unanimity at 165 evidence rather than assumption.

**Correction to the earlier agent's premise:** the registry is not "at
sco.com". The sco.com page's own copyright line reads
`© 2011-2015 Xinuos Inc.` and it is a frozen 2015 snapshot. The maintained
registry is `gabi.xinuos.com`, and the contact is `registry@xinuos.com`, not
`registry@sco.com`. Both copies agree on 165, so the conclusion is unharmed —
but the earlier agent cited a dead address.

**Charge 1 fails.** Twelve independent implementations, zero conflicts, zero
alternative names for 165.

---

## Charge 2 — "165 is the wrong granularity; 8052 / 80251 / vendor supersets need their own"

### 2a. Is there a rival registration?

No. Full-text scan of the live registry for every descendant family:

```
$ python3 -c "...scan xinuos-emachine.html for 251, 8052, C166, XC16, Infineon,
              Dallas, Maxim, Silicon Lab, Nordic, STC, Cypress..."
251      :: EM_VE 251 NEC Vector Engine            <- '251' matches only a value, not an arch
C166     :: EM_C166 116 Infineon C16x/XC16x processor
Dallas   :: EM_MAXQ30 169 Dallas Semiconductor MAXQ30 Core Micro-controllers
Cypress  :: EM_CYPRESS_M8C 161 Cypress M8C microprocessor
Infineon :: EM_JAVELIN 77 / EM_C166 116 / EM_SLE9X 179
STC / Silicon Lab / Nordic / Maxim / 8052 / 80251 :: (nothing)
```

And no relocation namespace or alternate name exists anywhere on GitHub:

```
search_code: "R_8051_" OR "R_MCS51_" OR "EM_80251" OR "EM_8052"   -> total_count: 0
```

### 2b. The near-miss entries, and precisely why each is inapplicable

- **`EM_C166 = 116`, "Infineon C16x/XC16x processor."** The tempting move is
  Infineon → XC800, which *is* an 8051 superset. It does not work: C166 names
  Infineon's **C16x/XC16x 16-bit core**, a completely different ISA from the
  8-bit XC800. Infineon ships them as separate product lines with separate
  compilers, and Keil confirms the split from the tool side (see 3b): the
  C166 toolset emits **OMF-166**, the C51 toolset **OMF-51**. Two formats, two
  architectures. Using 116 for an 8051 would be a genuine collision — with
  a family that has a real toolchain behind it. This is the *one* value where
  squatting would actually hurt someone, and it is exactly the value the port
  does not use. `EM_XC16X 0x4688` in `common.h` is the same C166-V2 core, same
  exclusion.
- **`EM_MAXQ30 = 169`, "Dallas Semiconductor MAXQ30."** Dallas also made the
  DS80C390 — an 8051 superset — so the vendor name matches. The core does not:
  MAXQ is Dallas's own 16-bit RISC, unrelated to MCS-51. Vendor identity is
  not architecture identity.
- **`EM_CYPRESS_M8C = 161`.** Cypress shipped 8051 cores (EZ-USB FX2), but
  M8C is the PSoC1 8-bit core, a different ISA.
- **`EM_IAMCU = 6`, "Intel MCU."** Intel Quark/MCU — an x86 variant with its
  own psABI. `readelf` groups it with `EM_386` in `guess_is_rela`
  (`readelf.c:1257-1258`) and radare2 maps it to `arch = "x86"`
  (`elf.c:2424-2426`). Nothing to do with MCS-51.
- **`EM_INTEL182 = 182`, `EM_INTEL206..209`.** The registry reads
  `reserved 182 Reserved for future Intel use` and `EM_INTEL206 206 Reserved
  by Intel`. Reserved *to Intel*, unassigned, and taking one would be
  squatting a block whose owner is named.

### 2c. "Does 'and variants' cover the 8052 this port targets?"

Yes, and the ISA evidence is in-tree. The gate corpus is
`tb/isa/8051.txt` (naken_asm comparison set, one instruction per line with an
independently-produced c51asm golden column) and `tb/isa/testall.asm`
(OpenCores oc8051, "covering every instruction except MOVX and RETI") —
`tb/isa/PROVENANCE`. The 8052 adds RAM, Timer 2 and SFRs; it adds **no
opcodes**. Timer 2 registers reach the assembler as symbols
(`readelf -s` on a staged object shows `ABS` SFR symbols like `P2`, `ACC.0`),
not as instructions. An 8052 object and an 8051 object are the same
instruction encoding — one machine.

### 2d. "Would a future 80251 port need a different value?"

It would need a different *sub-machine*, and ELF already has the field for
that. The binutils house pattern is one `e_machine` plus `e_flags`:

```
readelf.c:4307:  switch (e_flags & EF_AVR_MACH)
readelf.c:4309:    case E_AVR_MACH_AVR1:  ... AVR2, AVR25, AVR3, AVR31, AVR35, AVR4, AVR5, AVR51 ...
```

`EM_AVR = 83` covers fifteen AVR sub-architectures this way. MSP430 does the
same. This port's `bfd_i51_arch` already declares `0, /* Machine number - 0
for default. */`, and — from §0 — sets no `e_flags` at all. Both fields are
free and are the designated place for 8052/251/XC800 differentiation. That
is not a workaround; that is the mechanism, and the gABI blesses it directly:
`e_flags This member holds processor-specific flags associated with the file.
Flag names take the form EF_machine_flag.`

**Charge 2 fails.** No rival value exists, none of the near-misses fit, and
the granularity problem it raises is solved by `e_flags`, which the port has
deliberately left empty.

---

## Charge 3 — "165 is already in use in the wild with clashing conventions"

This was the strongest possible refutation. It found nobody.

**Searched for producers.** GitHub code search, exact phrases:

```
"e_machine = EM_8051"                 -> total_count: 0
"ELF_MACHINE_CODE" "EM_8051"          -> total_count: 0
"elf32-mcs51" OR "elf32-8051" OR "bfd_arch_mcs51"  -> total_count: 0
```

**Searched for consumers.** `"EM_8051" NOT "165"` returns 539 hits. I read the
top 40. Every single one is a **decoder table**: `llvm/lib/BinaryFormat/ELF.cpp`,
`ELFYAML.cpp`, `llvm-readobj/ELFDumper.cpp`, `illumos-gate` `libconv/elf.c` and
`cmd/file/file.c`, Wireshark `file-elf.c`, ELFIO `elfio_dump.hpp`,
`cole14/rust-elf` `to_str.rs`, pyelftools via `sqlelf`, `mortbopet/Ripes`.
A second search (`"165" "8051" filename:elf.h`, 541 hits) is entirely
glibc/musl `elf.h` copies vendored into unrelated projects.

**Every hit is something that can *name* 165. Not one is something that can
*emit* it.** The number is universally recognised and universally unclaimed.

**The vendor toolchains do not emit ELF at all.** Keil, from Keil's own
documentation (fetched `keil.com/support/docs/93.htm`), verbatim:

> "The Keil C51 tools use the Intel OMF-51 object module format for object
> modules generated by the assembler and compiler. The linker generates
> OMF-51 absolute object modules. The object-HEX converter generates Intel
> HEX files."

ELF is MDK/ARM only; C51/C166/C251 use OMF-51/OMF-166/OMF-251. IAR uses UBROF.
SDCC emits ASxxxx `.rel` and Intel HEX. So the three toolchains that dominate
8051 development in practice cannot collide with us — they never produce an
`e_machine` field to collide with.

**LLVM has no 8051 backend.** `EM_8051` appears in LLVM only in ELF.cpp,
ELFYAML.cpp and ELFDumper.cpp — decode paths.

**radare2 has an 8051 disassembler and still does not claim 165.** This was
the most promising collision candidate in the whole exercise: r2 ships an
`8051` arch plugin, so if `Elf_(get_arch)` mapped `EM_8051 → "8051"` it would
disassemble our objects under its own conventions. It does not:

```
elf.c:2309: char* Elf_(get_arch)(ELFOBJ *eo) {
elf.c:2310:   const char *arch = "unknown";
...            (case list: ARC, AVR, BPF, CRIS, 68K, MIPS, ARM, SPARC, PPC,
                RISCV, MSP430, SH, V850, S390, KVX, LOONGARCH, NDS32, x86,
                TMS320 — no EM_8051)
elf.c:2436:   default:
elf.c:2437:     R_LOG_ERROR ("Unknown e_machine 0x%02x", eo->ehdr.e_machine);
elf.c:2441:   return strdup (arch);
```

It logs `Unknown e_machine 0xa5` and returns `"unknown"`. It never guesses.

**Charge 3 fails, and the honest answer to "who else uses 165" is: nobody.**

---

## Charge 4 — "downstream special-cases 165 and gets our objects wrong"

Charges 1–3 were archaeology. This one I tested empirically. Method: take a
real object from the port's own corpus, patch `e_machine` to 165, run stock
Ubuntu 24.04 tools (`GNU readelf 2.42`) over it.

```
$ cp tb/objects-report/staged/cgi/rts.obj rts.o
$ od -A d -t x1 -N 32 rts.o
0000000 7f 45 4c 46 01 01 01 00 00 00 00 00 00 00 00 00
0000016 01 00 51 10 01 00 00 00 00 00 00 00 00 00 00 00
                ^^^^^ e_machine = 0x1051 (legacy)
$ python3 -c "d=bytearray(open('rts.o','rb').read()); d[18:20]=b'\xa5\x00'; open('rts165.o','wb').write(d)"
```

### 4a. Naming — correct

```
$ readelf -h rts165.o
  Class:                             ELF32
  Data:                              2's complement, little endian
  Type:                              REL (Relocatable file)
  Machine:                           Intel 8051 and variants

$ file rts165.o
rts165.o: ELF 32-bit LSB relocatable, Intel 8051 and variants, version 1 (SYSV), not stripped
```

Before the patch the same `readelf` said `Machine: <unknown>: 0x1051`. That
is the entire practical payoff of the switch, and it is real.

### 4b. The port's processor-specific conventions — correctly displayed

The port puts memory-space codes in the top bits of `sh_flags`
(`SHF_XDATA 0xA0000000` etc., `include/elf/i51.h`) and its memory-space
commons at `SHN_LORESERVE + 0..6` (0xff00–0xff06). I injected both into the
patched object and asked stock `readelf`:

```
$ readelf -S rts_probe.o | grep cpu_dir
  [ 5] cpu_dir           PROGBITS        00000000 000048 000008 00  Ap  0   0  1
                                                                       ^^ "p (processor specific)"
$ readelf -s rts_probe.o | sed -n 5p
     4: 00000096     0 NOTYPE  LOCAL  DEFAULT PRC[0xff04] WMCON
```

`readelf.c:1125-1126` is why:
`if (ndx >= SHN_LOPROC && ndx <= SHN_HIPROC) sprintf (name_buf, "PRC[0x%04x]", short_ndx);`
Since `SHN_LORESERVE == SHN_LOPROC == 0xff00`, the port's commons land inside
the range the standard reserves for exactly this, and stock tools label them
as processor-specific rather than corrupt. The comment in `include/elf/i51.h`
explaining why they are spelled `SHN_LORESERVE + n` rather than bare `0xff0n`
is doing real work.

### 4c. Relocations — undecoded, never misdecoded

```
$ readelf -r rts165.o
00000003  00004d06 unrecognized: 6       00000000   STATE80 + 0
00000012  00004e05 unrecognized: 5       00000000   ZFLAG + 0
```

`readelf.c` has no `case EM_8051:` in its reloc-type switch — the only
`EM_8051` in all 670967 bytes of `readelf.c` is line 3918,
`case EM_8051: return "Intel 8051 and variants";`. So it prints
`unrecognized: N` and stops. Offsets, symbol names and addends are all
correct; only the mnemonic is missing. Wrong-but-plausible would be dangerous;
blank is safe.

### 4d. The `guess_is_rela` trap — real, and never reached

`EM_8051` is not in either arm of `guess_is_rela`, so it falls to:

```
readelf.c:  default:
              warn (_("Don't know about relocations on this machine architecture\n"));
              return false;      /* i.e. guess REL */
```

The port emits **RELA**. A wrong guess here would misparse every relocation.
It does not fire: `guess_is_rela` has exactly one call site,

```
$ grep -n "guess_is_rela" readelf.c
1252:guess_is_rela (unsigned int e_machine)
2266:    rel_type = guess_is_rela (...) ? reltype_rela : reltype_rel;
```

and line 2266 is inside `dump_relocations` guarded by
`if (rel_type == reltype_unknown)` — the dynamic path. Static sections take
their type from `relsec->sh_type == SHT_RELA` (`readelf.c:16356`). The port
emits `ET_REL` objects with no dynamic segment, so the guess never runs, as
the clean `-r` output in 4c demonstrates. **Also note this trap is not
165-specific**: any value not in that switch, registered or invented, hits the
same default. Choosing an unofficial number would not avoid it.

### 4e. Disassembly — safe failure

```
$ objdump -f rts165.o
rts165.o:     file format elf32-little
architecture: UNKNOWN!, flags 0x00000011:
$ objdump -d rts165.o
objdump: can't disassemble for architecture UNKNOWN!
```

BFD matches by target vector, not `e_machine`. With no `elf32-i51` vec
compiled in, stock BFD falls back to the generic `elf32-little` reader,
reports `UNKNOWN!`, and refuses. It does not guess an architecture.

### 4f. The rest

- **elfutils**: no 8051 backend. `libebl/eblopenbackend.c` (23819 B) has 83
  `EM_` entries and no `8051` anywhere; the nearest is
  `{ hexagon_init, "elf_hexagon", "hexagon", 9, EM_QDSP6, ELFCLASS32,
  ELFDATA2LSB }` at 164. No backend means generic handling, no assumptions.
- **gdb**: drives off BFD arch, not `e_machine`; with no `bfd_arch_i51` it has
  nothing to assume. `search_code repo:bminor/binutils-gdb "8051"` returned 0.
- **`file(1)` and endianness**: the 165 line is `>18 leshort`, which looks like
  a little-endian-only match — but the dispatch at `Magdir/elf:355-358` is
  `>5 byte 1 LSB / >>0 use elf-le` and `>5 byte 2 MSB / >>0 use \^elf-le`. The
  `\^` byte-swaps the same table for MSB files. Both encodings covered; 220
  `>18 leshort` lines, 0 `beshort` lines, by design.
- **Linux binfmt**: `elf-em.h` has no 165, so `binfmt_elf` will never load one.
  Correct — these are freestanding ROM objects.

**Charge 4 fails.** Nothing downstream special-cases 165 in a way that
misreads this port, and the port's two unusual conventions (`SHF_MASKPROC`
space codes, `SHN_LOPROC` commons) are displayed correctly by stock tools
because they sit inside standard-reserved ranges.

---

## Charge 5 — "an unregistered private value would be more correct than squatting a shared number"

This charge inverts on inspection. There is no private range to retreat to.

**e_machine has no vendor range. At all.**

```
$ grep -c "EM_LOPROC\|EM_HIPROC\|EM_LOOS" gabi-machine.html xinuos-emachine.html
gabi-machine.html:0
xinuos-emachine.html:0
$ grep -c "EM_LOPROC\|EM_HIPROC" binutils-common.h glibc-elf.h llvm-ELF.h
binutils-common.h:0
glibc-elf.h:0
llvm-ELF.h:0
```

`e_type`, `sh_type`, `p_type`, `sh_flags`, `st_shndx` all have `LOPROC/HIPROC`
or `LOOS/HIOS` ranges — this port uses two of them. `e_machine` has none. The
whole 16-bit space is a single registry.

**EI_OSABI is not a substitute.** The gABI's OSABI appendix does define a
private range, and its wording is decisive:

> "Values in the architecture-specific value range may be used for a specific
> e_machine value, without registration. It is advisable to coordinate with
> other potential users of that architecture to avoid conflicts."
> — `gabi.xinuos.com/elf/b-osabi.html`; the range is `64-255`.

"For a specific `e_machine` value" — the private OSABI range is *scoped by*
an `e_machine`. It presupposes you already have one. It cannot replace one.

**`e_flags` is likewise downstream of `e_machine`**: `Flag names take the form
EF_machine_flag`. Same dependency.

**So the only alternative is an `EM_*_UNOFFICIAL` squat, and binutils itself
documents that as the inferior option.** `include/elf/common.h:364-374`,
verbatim:

> ```
> /* If it is necessary to assign new unofficial EM_* values, please pick large
>    random numbers (0x8523, 0xa7f2, etc.) to minimize the chances of collision
>    with official or non-GNU unofficial values.
>
>    NOTE: Do not just increment the most recent number by one.
>    Somebody else somewhere will do exactly the same thing, and you
>    will have a collision.  Instead, pick a random number.
>
>    Normally, each entity or maintainer responsible for a machine with an
>    unofficial e_machine number should eventually ask registry@sco.com for
>    an officially blessed number to be added to the list above.	*/
> ```

(Note that binutils' own comment still points at `registry@sco.com`, the dead
address — the same staleness the earlier agent inherited. The live contact is
`registry@xinuos.com`, per the Xinuos registry page quoted below.)

Three things follow, and all three cut against the charge.

1. The unofficial route is explicitly a *waiting room*: "should eventually
   ask ... for an officially blessed number." This port already has the
   blessed number. Retreating to an unofficial value would be walking the
   migration backwards.
2. `EM_AVR_OLD 0x1057` and `EM_MSP430_OLD 0x1059` sit four and eight above
   the legacy value this port inherited, `0x1051`. The legacy value is in a
   dense `0x105x` cluster of exactly the kind the comment warns about, and
   unlike its neighbours it is not registered in `common.h` at all — so no
   third party can even detect a collision with it. `0x1051` is the weaker
   choice under binutils' own rule, not the safer one.
3. The port already implements the migration correctly. `ELF_MACHINE_ALT1
   EM_I51_OLD` is input-only. BFD writes the primary code on every output:

```
bfd/elf.c:7046:      i_ehdrp->e_machine = bed->elf_machine_code;
```

   (the surrounding comment at 7038-7044 says the per-machine switch was
   deleted precisely so this is the single path). `ELF_MACHINE_ALT1` appears
   in `bfd/elfxx-target.h` only at line 956, filling the backend struct slot
   consumed by input matching. So legacy `0x1051` objects are read, and any
   pass through the toolchain upgrades them to 165. That is the AVR_OLD /
   MSP430_OLD / XTENSA_OLD pattern applied exactly.

**And registration is a live option, not a dead one.** The registry is
actively maintained — it carries `EM_AIECTRLCODE 269`, seven values beyond
binutils' `EM_56800EF 262`. Its stated procedure:

> "To request assignment of an e_machine value for a new architecture, please
> email your request to registry @ xinuos . com. Please include your contact
> information (preferably a company email address, not a free email provider),
> the name of the company, the name of the architecture with a brief
> description, your preferred EM_xxx name, and a link (if available) to any
> public information about the architecture."

Which matters only in the negative: **there is nothing left to register.**
Someone already did it. Asking for a second 8051 value would be asking the
registry to duplicate its own entry.

**Charge 5 fails, and inverts.** The unregistered path is not "more correct
than squatting a shared number" — using 165 is not squatting. It is the
registered value, used for the architecture it was registered for, by the
only project that emits it.

---

## The best counter-argument I could build, and why it fails

Not any of the five as briefed. The strongest case is a synthesis:

> *"Intel 8051 and variants" is a registry stub. Nobody has ever emitted an
> object under it, so no ABI exists behind it — no relocation numbering, no
> section conventions, no `e_flags` meaning. This port is therefore not
> "using the registered value"; it is unilaterally inventing an ABI and
> stamping a shared, unowned number on it. The first other party to ship
> EM_8051 objects — with different relocation numbers than `R_I51_NONE=0 …
> R_I51_13_PCODE=11`, or without `SHF_CDATA` in `sh_flags`, or big-endian —
> makes both toolchains' objects mutually unreadable under one number, with
> no field left to tell them apart. An unofficial random value would at least
> have been honestly ours.*

This is the real risk, and it is not imaginary. It fails on three grounds.

**First, it argues against having an ABI, not against having 165.** The same
ambiguity arises at any value: a second party could equally pick `0x1051`, and
`0x1051` is *worse*, because it is in the `0x105x` cluster `common.h` warns
about and is invisible to anyone checking for collisions. The counter-argument
concludes "pick a random number," which is precisely what binutils tells you
to stop doing as soon as a blessed number exists.

**Second, `e_flags` is the field the argument claims does not exist.** The
port leaves it 0. A future party who registers ABI variants under `EM_8051`
has 32 bits to work in — the AVR mechanism, quoted in charge 2d. The argument
assumes a hole in ELF that ELF does not have.

**Third, the premise "no ABI exists behind it" cuts the other way.** Being
the first mover on an unclaimed registered value is the *strongest* position
available, not the weakest — the port defines the conventions rather than
having to match someone else's. There is no incumbent to clash with. Charge 3
searched hard for one and found zero producers on GitHub, zero in LLVM, and
three vendor toolchains that emit OMF and HEX rather than ELF. The registry's
own procedure exists to prevent a *second* claimant on 165; it does not exist
to stop the first.

The counter-argument is a real long-term hazard. It is not a defect in the
choice of number.

---

## Two real defects found, both orthogonal to the verdict

Recorded because they are true, not because they refute anything. Neither
would be fixed by changing `e_machine`.

**1. `EI_DATA` vs. section content.** The port declares `ELFDATA2LSB`
(`TARGET_LITTLE_SYM i51_elf32_vec`; byte 5 of every staged object is `01`)
while gas emits 16-bit section data MSB-first (`TARGET_BYTES_BIG_ENDIAN 1`,
`additions.patch:3731`). The gABI says:

> "Byte `e_ident[EI_DATA]` specifies the encoding of both the data structures
> used by object file container **and data contained in object file
> sections**."

Under a strict reading that is a conformance defect. It largely does not bite
in practice: the 8051 is a byte machine with no 16-bit memory word, the
MSB-first order is an instruction-encoding property (`mov DPTR,#data16` is
high-byte-first) exactly as x86 `imm16` is LSB-first inside its opcode, and
`R_I51_L`/`R_I51_H` apply the halves explicitly. But a generic consumer
reading `.word` data would get it backwards. Worth a comment in
`include/elf/i51.h` at minimum. It exists identically at `0x1051` and at 165.

**2. Redundant write in `bfd_elf_i51_final_write_processing`.**
`additions.patch:656` sets `elf_elfheader (abfd)->e_machine = EM_8051;`
by hand. `bfd/elf.c:7046` already assigns `bed->elf_machine_code` for every
target. Harmless, but it hides the `ELF_MACHINE_ALT1` upgrade behaviour behind
a second, less obvious mechanism.

---

## Verdict

**CONFIRMED.** `EM_8051 = 165` is correct and, for this architecture, unique.

- Twelve independent authorities carry it; the three that maintain full
  registries carry byte-identical text. The two that omit it (Linux, FreeBSD)
  omit ~180 other values too and assign 165 to nothing.
- No competing value exists for any MCS-51 descendant. The three near-misses
  (`EM_C166`, `EM_MAXQ30`, `EM_CYPRESS_M8C`) are different cores, and
  `EM_C166` in particular is the value it would have been actively wrong to
  take.
- Nobody else emits it. Zero producers on GitHub; Keil, IAR and SDCC emit
  OMF-51, UBROF and HEX, not ELF; LLVM has no backend; radare2 has an 8051
  disassembler and still returns `"unknown"` for `e_machine 0xa5`.
- Empirically, stock `readelf 2.42`, `file` and `objdump` name the objects
  correctly, render `SHF_MASKPROC` as `p` and `SHN_LOPROC` commons as
  `PRC[0xff04]`, print `unrecognized: N` rather than a wrong mnemonic, and
  refuse to disassemble rather than guess.
- There is no private `e_machine` range. `EI_OSABI`'s private range is
  scoped *by* an `e_machine`, and `e_flags` is named *after* one. The only
  alternative is an unofficial squat that `include/elf/common.h` itself
  describes as a temporary state to be escaped by registration — which, for
  this architecture, has already happened.

Charge 3 was the one that could have ended this. The honest answer to "who
else is using 165" is: **nobody.** That is not a weakness in the choice. It is
the reason the choice is safe.

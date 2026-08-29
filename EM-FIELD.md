# EM-FIELD — who really emits and consumes 8051 ELF

Review only. Nothing patched. Every claim below is a command and its output, or a
fetched primary source. Where a fetch was blocked it says so and stops there.

Scope note: this report is field evidence — producers, consumers, artifacts. The
registry/standards question (who owns 165, what the gABI says) is a parallel
agent's lane and is not answered here.

Branch: `claude/em-field` off `origin/work/green` (0f45319).

---

## 0. Bottom line

**Nobody else was found emitting `EM_8051` (165) ELF.** Not one producer. Not in
any shipping toolchain reachable from here, not in any GitHub source, not in the
two sibling ports of our own lineage. 165 is, in practice, uncontested.

Three real problems remain, none of them about the number:

1. **Our own lineage has fragmented into four different `e_machine` values** for
   byte-identical relocation semantics: 0x7262 (2001 original), 0x1051 (this
   repo's own earlier value), 190 (volumit), 260 (github0null), 165 (us). Two of
   those squat on other people's registered numbers.
2. **`e_flags` is 0 and unused.** Both siblings set it. Ghidra's ELF loader keys
   sub-architecture selection off `e_flags`. We ship no discriminator.
3. **Every generic consumer names the machine and then gets the contents wrong.**
   Relocations decode as "unrecognized"/"Unknown"/"`<INVALID RELOC>`" in four
   independent readers, and radare2 + gdb silently disassemble our 8051 code as
   x86.

---

## 1. Toolchain census

Every 8051 toolchain examined, with what it actually emits.

| Toolchain | Object format | ELF? | `e_machine` | Endianness | Reloc numbering | Evidence |
|---|---|---|---|---|---|---|
| **this port** (i51-elf, binutils 2.47) | ELF32 | yes | **165 `EM_8051`**, accepts 0x1051 on input | `ELFDATA2LSB`, 16-bit fields stored BE | `R_I51_*` 0..11 | built + run, §3 |
| **2001 web51.hw.cz** (binutils 2.11.2) | ELF32 | yes | **0x7262** (29282, unregistered) | `ELFDATA2MSB` | `R_I51_*` 0..11 identical | `tb/ref.7z`, `tb/base2001.7z` |
| **github0null/binutils-mcs51** (2.38) | ELF32 | yes | **260** (= upstream `EM_U16_U8CORE`, LAPIS nX-U16/U8) | `TARGET_BIG_SYM` → MSB | `R_I51_*` 0..11 identical | cloned, §2 |
| **volumit/sdcc_aurix_scr_42** (binutils fork) | ELF32 | yes | **190** (= upstream `EM_CUDA`) | `TARGET_BIG_SYM` → MSB | `R_I51_*` 0..11 identical | cloned, §2 |
| **SDCC 4.2.0 mcs51** | ASxxxx `.rel` (ASCII), `.ihx`, AOMF51 | **no** | — | n/a | ASxxxx, not ELF | §4 |
| **SDCC stm8 / hc08 / s08** | ELF32 (`--out-fmt-elf`) | yes | `EM_STM8` 186 / `EM_68HC08` 71 | `ELFDATA2MSB` | n/a (executable only) | §4 |
| **Keil C51 / BL51 / LX51** | OMF-51, OMF2 (AOMF for absolute) | no | — | n/a | OMF-51 | §5 |
| **IAR EW8051 / XLINK** | UBROF (object); XLINK *can* output ELF/DWARF as an executable, "supported only for certain CPUs" | unproven | **unknown — not documented** | unknown | unknown | §5 |
| **TASKING VX-toolset for 8051 v6.3r1** | **ELF/DWARF 3 by default** | **yes** | **unknown — in the 8051 EDABI doc, which is not publicly reachable** | doc says 8051 data is **big-endian** | unknown | §5, §6 |
| **Raisonance RC51 / RIDE** | OMF-51 (+ Intel hex) | no | — | n/a | OMF-51 | §5 |
| **Wickenhäuser µC/51** | binary, Intel HEX, OMF51 | no | — | n/a | OMF-51 | §5 |
| **Silicon Labs 8051 / EFM8** | delegates to Keil C51; OMF-51 absolute object required for source debug | no | — | n/a | OMF-51 | §5 |
| **STC (STC15/STC8)** | delegates to Keil C51 via STC-ISP "Keil ICE Settings" | no | — | n/a | OMF-51 | §5 |
| **Debian/Ubuntu `as31` 2.3.1** | absolute output only: `hex\|bin\|tdr\|byte\|od\|srec2\|srec3\|srec4` | no | — | n/a | none (no object format) | §4 |
| **Debian/Ubuntu, Fedora packaging** | ship `sdcc` only; no 8051 binutils package exists | no | — | — | — | §4 |

---

## 2. The two sibling ports — cloned and read

Anonymous clone worked for both.

```
$ git clone --depth 1 https://github.com/github0null/binutils-mcs51 gh0     # 385M, HEAD 7ae1abd5
$ git clone --depth 1 https://github.com/volumit/sdcc_aurix_scr_42 vol      # 397M, HEAD 37cd564
```

### github0null uses 260, not 165

```
$ grep -rn "EM_8051\|EM_I51" gh0/include/elf/common.h gh0/bfd/elf32-i51.c
gh0/include/elf/common.h:279:#define EM_8051	165	/* Intel 8051 and variants */
gh0/include/elf/common.h:357:#define EM_I51	260	/* MCS-51*/
gh0/bfd/elf32-i51.c:866:  elf_elfheader (abfd)->e_machine = EM_I51;
gh0/bfd/elf32-i51.c:1214:#define ELF_MACHINE_CODE	EM_I51
```

They have `EM_8051 = 165` sitting right there in the same header and did not use
it. They appended 260 to the end of the list — the exact thing `common.h` warns
against three lines later ("Do not just increment the most recent number by one.
Somebody else somewhere will do exactly the same thing, and you will have a
collision"). 260 is taken:

```
$ grep -n "260" work/modern/binutils-2.47/include/elf/common.h
360:#define EM_U16_U8CORE	260	/* LAPIS nX-U16/U8 */
```

github0null is big-endian and does set `e_flags`:

```
$ grep -n "TARGET_BIG_SYM\|e_flags" gh0/bfd/elf32-i51.c
867:  elf_elfheader (abfd)->e_flags |= bfd_mach_i51;
1217:#define TARGET_BIG_SYM       i51_elf32_vec
$ grep -n "bfd_mach_i51" gh0/bfd/bfd-in2.h
1937:#define bfd_mach_i51      1
```

### volumit uses 190

```
$ grep -n "EM_I51\|EM_GTM_MCS" vol/binutils/include/elf/common.h
294:#define EM_I51          190     /* MCS-51*/
378:#define EM_GTM_MCS      0xAF0F  /* RB GTM MCS processor core */
$ grep -n "e_machine\|e_flags\|TARGET_BIG_SYM" vol/binutils/bfd/elf32-i51.c
877:  elf_elfheader (abfd)->e_machine = EM_I51;
878:  elf_elfheader (abfd)->e_flags |= bfd_mach_i51;
1233:#define TARGET_BIG_SYM       bfd_elf32_i51_vec
```

190 upstream is `EM_CUDA`. Proof that a stock reader mis-names a volumit object —
this is our own object with two bytes changed (`obj/m190.o`, `e_machine` ← 190):

```
$ readelf -h obj/m190.o | grep Machine
  Machine:                           NVIDIA CUDA architecture
```

vol also carries a *second* 8051-family target, `bfd/elf32-mcs.c`, on
`EM_GTM_MCS = 0xAF0F` — Bosch GTM MCS, a different core, unrelated to us.

### The relocations are identical across all three

The only differences in the HOWTO tables are the binutils API change (log2-size →
size-in-bytes, 2.39) and `FALSE`→`false`:

```
$ diff <(grep -A12 'HOWTO (R_I51' <ours>) <(grep -A12 'HOWTO (R_I51' <gh0>)
3,4c3,4
< 	 0,			/* size in bytes */
< 	 0,			/* bitsize */
---
> 	 2,			/* size (0 = byte, 1 = short, 2 = long) */
> 	 32,			/* bitsize */
...  (all remaining hunks are the same size-field convention change)
$ diff <(grep -A12 'HOWTO (R_I51' <gh0>) <(grep -A12 'HOWTO (R_I51' <vol>)
5c5
< 	 false,			/* pc_relative */
---
> 	 FALSE,			/* pc_relative */
...  (all hunks are false/FALSE only)
```

`include/elf/i51.h` is byte-for-byte the same relocation list, the same
`SHF_CDATA/RDATA/BDATA/IDATA/XDATA/EDATA` masks and the same
`SHN_I51_*` = 0xff00..0xff06 in all three.

**So: same lineage, same relocations, same section/symbol conventions, four
different machine numbers.** The fragmentation is in the header field only.

### 0x1051 is ours, not the lineage's

The README says "the unregistered `0x1051` that the 2001 lineage used". The 2001
sources say otherwise:

```
$ 7z x tb/ref.7z            # i51.patch.112n, i51.patch.112p
$ grep -n "EM_I51\|TARGET_BIG_SYM" ref/i51.patch.112*
ref/i51.patch.112p:625:+ #define EM_I51			0x7262
ref/i51.patch.112n:1062:+ #define TARGET_BIG_SYM       bfd_elf32_i51_vec
```

And the genuine 2001 artifacts agree:

```
$ 7z x tb/base2001.7z
$ file b2001/cgi/bd.obj
b2001/cgi/bd.obj: ELF 32-bit MSB relocatable, *unknown arch 0x7262* version 1 (SYSV), not stripped
$ readelf -h b2001/cgi/bd.obj | egrep 'Data|Machine|Flags'
  Data:                              2's complement, big endian
  Machine:                           <unknown>: 0x7262
  Flags:                             0x0
```

0x7262 is `'r','b'` — Radek Benedikt. `0x1051` appears nowhere in either sibling:

```
$ grep -rn "0x1051" gh0/include gh0/bfd/elf32-i51.c vol/binutils/include vol/binutils/bfd/elf32-i51.c
(no output)
$ git log --oneline -S"0x1051" -- mcs51/
c907fad mcs51: the port on 2.47, both review rounds applied
15b928d up to 2.45.1
```

`EM_I51_OLD 0x1051` is this repository's own intermediate value, introduced here.
The README sentence attributing it to the 2001 lineage is wrong; the value the
2001 toolchain wrote was 0x7262, big-endian, and this port cannot read those
objects at all:

```
$ work/modern/build/ld/ld-new -o /dev/null b2001/cgi/bd.obj
ld-new: b2001/cgi/bd.obj: relocations in generic ELF (EM: 29282)
```

---

## 3. Is 165 contested in practice?

**No producer of `EM_8051` ELF other than this port was found.**

What was searched, and what came back:

```
# GitHub code search (via the MCP GitHub tool; plain HTTPS to the API is 403 through the proxy)
"e_machine = EM_8051"                → 0 results
"R_MCS51" OR "R_8051_" relocation elf → 0 results
"EM_8051" path:bfd                    → 0 results
"elf32-i51" OR "bfd_arch_i51"         → 0 results
"EM_8051" NOT "165" in:file            → 539 results, ALL consumers:
      llvm/lib/BinaryFormat/ELF.cpp, llvm/lib/ObjectYAML/ELFYAML.cpp,
      llvm/tools/llvm-readobj/ELFDumper.cpp, illumos usr/src/cmd/file/file.c,
      illumos libconv/common/elf.c, freebsd contrib/llvm-project, ...
"e_machine" "165" 8051 elf language:c → 842 results, ALL name tables:
      radare2 libr/bin/format/elf/elf.c, wireshark epan/dissectors/file-elf.c,
      dotnet/runtime src/coreclr/inc/llvm/ELF.h, freebsd elftoolchain, ...
repo:llvm/llvm-project "EM_8051"      → 5 files, all in BinaryFormat / ObjectYAML /
      readobj / a machine-name test. No 8051 backend, no ELFRelocs/8051.def.

# GitHub repo search
"binutils 8051"  → exactly 3 repos: volumit/sdcc_aurix_scr_42,
                   github0null/binutils-mcs51, github0null/sdcc-binutils-mcs51
"8051 mcs51 elf binutils toolchain" → 0
```

Every `EM_8051` hit in the world's source is a *reader's* name table. Not one is
a writer.

### What that leaves unproven

Two commercial toolchains could not be settled with an artifact:

- **TASKING VX-toolset for 8051** — this is the one real risk, and it is real.
  Their own user guide (fetched, `c51_user_guide_v6.3r1.pdf`, 2019) says:

  > "13.1. ELF/DWARF Object Format
  > The TASKING VX-toolset for 8051 by default produces objects in the ELF/DWARF
  > 3 format."
  > "The implementation of the ELF object format and the DWARF 3 debug
  > information for the TASKING VX-toolset for 8051 is described in the TASKING
  > 8051 ELF/DWARF Application Binary Interface (EDABI) v1.2 [2018, Altium]."

  The EDABI is where `e_machine` and the relocation numbers live. **It is not
  publicly reachable.** Nine URL patterns under `tasking.com/support/8051/`,
  `/support/c51/`, `/support/tricore/` and `/documentation/PDF/` all return HTTP
  200 with a WordPress 404 page (`file` says "HTML document"), never a PDF.
  Web search for `"TASKING 8051 ELF/DWARF Application Binary Interface" EDABI`
  returns only the **C166** EDABI. The 8051 EDABI is behind the toolset
  purchase. **I cannot say what number TASKING's 8051 ELF carries.**

  Their C166 EDABI *is* public and shows their house style
  (`c166_elf_dwarf_abi_v1.4.pdf`, fetched, 19 pages):

  ```
   e_ident[EI_DATA]         ELFDATA2LSB    Identifies 2's complement little endian data
  1.1.2 E_MACHINE
   E_MACHINE        Value             Description
   EM_C166          116     Infineon C16x/XC16x processor
  1.1.3 E_FLAGS
  The E_FLAGS field will be used to distinguish between memory models
  ```

  TASKING uses the registered number and puts the memory model in `e_flags`. If
  they followed the same style for 8051 they used `EM_8051 = 165` — with their
  own relocation numbering, which will not be ours. That is the collision to
  worry about, and it is **unproven in both directions**.

- **IAR EW8051** — XLINK for 8051 lists ELF in its output table
  (`wwwfiles.iar.com/8051/webic/doc/xlink.ENU.pdf`, XLINK-641, fetched, table 12
  p.87: `ELF*   binary   elf   Yes   32 bits`), footnoted
  "`*` The format is supported only for certain CPUs and debuggers." IAR's 8051
  *object* format is UBROF; ELF is a link-time output for third-party debuggers.
  No `e_machine` is documented anywhere in that manual (grep for
  `e_machine|EM_` finds nothing). No IAR 8051 install obtainable here.
  **Unproven.**

So the honest statement is: **165 is uncontested among everything I could
obtain and everything published as source. It may be contested by TASKING's
8051 EDABI, which is paywalled.** If a TASKING 8051 `.elf` is ever obtainable,
`readelf -h` on it settles the question in one command.

---

## 4. SDCC — proven not to emit ELF for mcs51

sdcc 4.2.0 is packaged in Ubuntu noble and was installed and run.

```
$ sdcc --version
SDCC : mcs51/z80/.../mos6502 4.2.0 #13081 (Linux)
$ printf 'int g;\nvoid f(void){ g++; }\n' > t.c && sdcc -mmcs51 -c t.c
$ file t.rel
t.rel: ASCII text
$ head -4 t.rel
XH3
H 1A areas 3 global symbols
M t
O -mmcs51 --model-small
```

ASxxxx `.rel`. ASCII. Not ELF.

`sdobjcopy` is the sdbinutils-derived tool most likely to have an ELF path. It
has none:

```
$ sdobjcopy --info
BFD header file version (sdbinutils derived from GNU Binutils) 2.30
asxxxx / plugin / srec / symbolsrec / verilog / tekhex / binary / ihex
```

Eight targets. No `elf*` anywhere.

`--out-fmt-elf` exists in sdcc but the mcs51 port rejects it:

```
$ sdcc -mmcs51 --out-fmt-elf -c t.c -o a.rel
at 1: warning 117: unknown compiler option '--out-fmt-elf' ignored
$ sdcc -mz80   --out-fmt-elf -c t.c -o d.rel
at 1: warning 117: unknown compiler option '--out-fmt-elf' ignored
$ sdcc -mstm8  --out-fmt-elf -c t.c -o b.rel      # accepted, no warning
$ sdcc -mhc08  --out-fmt-elf -c t.c -o c.rel      # accepted, no warning
```

And what sdcc's ELF actually is, built here:

```
$ sdcc -mstm8 --out-fmt-elf m.c -o m.elf
$ file m.elf
m.elf: ELF 32-bit MSB executable, STMicroeletronics STM8 8-bit, version 1 (IRIX), statically linked
$ readelf -h m.elf | egrep 'Data|OS/ABI|Machine|Flags'
  Data:                              2's complement, big endian
  OS/ABI:                            UNIX - IRIX
  Machine:                           STMicroeletronics STM8 8-bit microcontroller
  Flags:                             0x7ffe
```

The writer itself, from sdcc's own source (volumit's tree carries it verbatim):

```
$ sed -n '68,78p;721p' vol/sdas/linksrc/lkelf.c
/* These e_machine values are from "Motorola 8- and 16-bit Embedded ...
  EM_NONE = 0,  EM_68HC05 = 72,  EM_68HC08 = 71,  EM_68HC11 = 70,
  EM_68HC12 = 53,  EM_68HC16 = 69,  EM_STM8 = 186
  ehdr.e_machine = TARGET_IS_STM8 ? EM_STM8 : EM_68HC08; /* FIXME: get rid of hardcoded value - EEP */
```

Two machine values, hardcoded, ternary. There is no 8051 branch and no place to
add one. **SDCC will never hand us an `EM_8051` file.** For mcs51 its debug
object is AOMF51 (`sdas/linksrc/lkaomf51.c`, `CreateAOMF51()` at
`lkmain.c:456`) and its deliverable is `.ihx`.

Distro packaging:

```
$ apt-cache search . | grep -iE "8051|mcs51|mcs-51"
as31 - Intel 8031/8051 assembler
dis51 - Disassembler for 8051 code in Intel Hex format
emu8051 - Emulator and simulator for 8051 microcontrollers
mcu8051ide - Graphical Integrated Development Environment for 8051
s51dude - In-System Programmer for 8051 MCUs using usbtiny
$ apt-cache search binutils | grep -i "msp\|avr\|8051\|z80"
binutils-avr / binutils-msp430 / binutils-z80        # no 8051
$ as31
  -Ffmt    output format [hex|bin|tdr|byte|od|srec2|srec3|srec4] (default=hex)
```

Debian/Ubuntu ship no 8051 binutils and no 8051 ELF producer. Fedora ships
`sdcc` and `sdcc-libc-sources` and nothing else 8051-shaped
(packages.fedoraproject.org/pkgs/sdcc/sdcc/). If this port is ever packaged it
will be the first `EM_8051` producer in any distro.

---

## 5. The closed toolchains (fetched, secondary where noted)

- **Keil C51.** "The C51 Compiler produces object (.OBJ) files in OMF51 or OMF2
  object format." BL51 links classic OMF-51, LX51 links OMF2. The primary Keil
  pages 301-redirect to `developer.arm.com` → `support.arm.com`, which serves a
  JS shell — **WebFetch returned a page with no body text; the primary quote
  could not be pulled.** The above is from search-result snippets of
  keil.com/support/docs/93.htm and keil.com/products/c51/lx51.asp. No ELF
  anywhere in the C51 chain.
- **Silicon Labs / EFM8.** AN104 "Integrating Keil 8051 Tools into the Silicon
  Labs IDE": the Keil tools must be configured "to generate an absolute object
  file in the OMF-51 format with object extensions and debug records enabled".
  (The AN104 PDF fetched as raw bytes the fetch tool could not render; quote is
  from the search snippet of silabs.com/documents/public/application-notes/an104.pdf.)
  Silicon Labs' 8051 line has no ELF path.
- **STC.** STC-ISP exposes a "Keil ICE Settings" tab that registers the STC
  device database with an existing Keil C51 install. STC ships no compiler; the
  format is whatever Keil emits, i.e. OMF-51.
- **Raisonance RC51/RIDE.** "The assembler can output object code in intelhex or
  intel OMF51 format." LX-51 linker. No ELF.
- **Wickenhäuser µC/51.** Output formats binary, Intel HEX, OMF51. No ELF.
- **IAR EW8051.** UBROF objects; XLINK can emit ELF for "certain CPUs and
  debuggers" — see §3.
- **TASKING VX-toolset for 8051.** ELF/DWARF 3 by default — see §3 and §6.

---

## 6. What consumers actually do with our objects

Built the port here and made real files.

```
$ (cd tb && make build)            # binutils 2.47 + mcs51/*.patch, zero-offset apply
$ work/modern/build/gas/as-new -o s.o s.s
$ work/modern/build/ld/ld-new -L work/modern/build/ld -e _START -Ttext 0x100 -o s.elf s.o
```

`s.s` exercises `ljmp`/`lcall` (`R_I51_16`), `acall`/`ajmp` (`R_I51_11`),
`mov a,#imm` (`R_I51_8`), a `.comm`, and a second file `c.s` exercises every
memory-space common.

| Consumer | Version | Names `EM_8051`? | What it gets wrong |
|---|---|---|---|
| `file(1)` | 5.45 | **yes** — "Intel 8051 and variants" | nothing; it only reads the header |
| `readelf` (stock) | GNU 2.42 | **yes** | every relocation → `unrecognized: 9`, `unrecognized: 4`, `unrecognized: 6` |
| `objdump` (stock) | GNU 2.42 | **no** | `file format elf32-little`, `architecture: UNKNOWN!`, `can't disassemble for architecture UNKNOWN!` |
| `eu-readelf` (elfutils) | 0.190 | **yes** | every relocation → `<INVALID RELOC>` |
| `pyelftools` | 0.33 | **yes** — `get_machine_arch()` → "Intel 8051" | relocations come through as bare integers; no name table |
| `llvm-readelf` | 18.1.3 | **yes** | every relocation → `Unknown` |
| `llvm-objdump` | 18.1.3 | **no** | `file format elf32-unknown`, `unable to get target for 'unknown--'` |
| `radare2` | 5.5.0 | **yes** in the `machine` field, **but** sets `arch x86`, `bits 32`, `os linux` | **disassembles 8051 as x86** |
| `gdb` | 15.1 | **no** | `file type elf32-little`, "architecture ... currently i386"; **disassembles 8051 as x86** |
| **Ghidra** | master (fetched) | **no mapping at all** | its 8051 languages carry no ELF `external_name`; loader cannot pick a language |

### The two that silently lie

radare2 5.5.0, on our linked executable:

```
$ r2 -qq -c "iI" s.elf
arch     x86
bits     32
endian   little
machine  Intel 8051 and variants
os       linux
$ r2 -qq -c "s 0x100; pd 6" s.elf
0x00000100  020112   add al, byte [ecx]
0x00000102  1212     adc dl, byte [edx]
0x00000104  0112     add dword [edx], edx
0x00000106  800931   or byte [ecx], 0x31
```

Those bytes are `ljmp 0x112 / lcall 0x112 / sjmp / acall`. r2 *has* an 8051
disassembler — it is simply never selected:

```
$ r2 -qq -a 8051 -c "s 0x100; pd 6" s.elf
0x00000100  020112   ljmp loc.TARGET
0x00000103  120112   lcall loc.TARGET
0x00000106  8009     sjmp loc.NEAR
0x00000108  3111     acall loc.NEAR
0x0000010a  2111     ajmp loc.NEAR
0x0000010c  7420     mov a, #0x20
```

Cause, from radare2 master fetched today
(`libr/bin/format/elf/elf.c`): `EM_8051` appears exactly twice —

```
2726:	case EM_8051:          return strdup ("Intel 8051 and variants");
6305:			"EM_8051=165,"
```

— the name table and an enum dump. `Elf_(get_arch)()` at line 2309 has cases for
`EM_AVR`, `EM_MSP430`, `EM_CUDA`, `EM_TRICORE`, … and no `EM_8051`, so it falls
through to `default: R_LOG_ERROR ("Unknown e_machine ...")` and keeps the
initialized `x86`.

gdb 15.1 does the same thing without even a warning:

```
$ gdb -batch -ex "file s.elf" -ex "show architecture" -ex "disassemble _START"
	`s.elf', file type elf32-little.
The target architecture is set to "auto" (currently "i386").
Dump of assembler code for function _START:
   0x00000100 <+0>:	add    (%ecx),%al
   0x00000102 <+2>:	adc    (%edx),%dl
```

### Ghidra has no route from 165 to its own 8051 language

`Ghidra/Processors/8051/data/languages/8051.ldefs` (master, fetched):

```
$ curl ... 8051.ldefs | grep 'tool='
    <external_name tool="IDA-PRO" name="8051"/>
    <external_name tool="IDA-PRO" name="8051"/>
$ curl ... 8051.ldefs | grep 'endian='
            endian="big"     x5
```

Two `external_name`s, both for IDA-Pro. No `tool="ELF"`. Compare
`Ghidra/Processors/Atmel/data/languages/avr8.ldefs`, which does carry
`external_name tool="gnu"` entries, and `avr8.opinion`:

```xml
<constraint loader="Executable and Linking Format (ELF)" compilerSpecID="gcc">
    <constraint primary="83" processor="AVR8" endian="little" />
    <!--  Elf e_flags are used for the secondary attribute TODO: need to mask with 0x7f -->
    <constraint primary="83" secondary= "31" processor="AVR8" size="16" variant="default"/>
    <constraint primary="83" secondary= "51" processor="AVR8" size="16" variant="extended"/>
    <constraint primary="83" secondary= "6"  processor="AVR8" size="24" variant="atmega256"/>
    <constraint primary="83" secondary= "107" processor="AVR8" size="24" variant="Xmega"/>
</constraint>
```

`primary` is `e_machine` (83 = `EM_AVR`), `secondary` is `e_flags`. Ghidra's
`ElfLoader.java` confirms it:

```java
123:  String machine = elf.getMachineName();
126:  results.addAll(QueryOpinionService.query(getName(), machine, compiler));
128:  results.addAll(QueryOpinionService.query(getName(), machine, elf.getFlags()));
```

There is no 8051 `.opinion` entry, so no `EM_8051` object opens with a language
selected. And note the two constraints Ghidra applies when it *does* match:
`endian` and `e_flags`. Both are §7 and §8 below.

### Our own memory-space conventions through a generic reader

```
$ work/modern/build/gas/as-new -o c.o c.s      # .rcomm/.bcomm/.icomm/.xcomm/.ecomm/.bitcomm/.comm
$ readelf -s c.o | tail -8                      # stock GNU 2.42, identical to our own readelf
     5: 00000001     4 OBJECT  GLOBAL DEFAULT PRC[0xff01] RCVAR
     6: 00000001     2 OBJECT  GLOBAL DEFAULT PRC[0xff02] BCVAR
     7: 00000001     8 OBJECT  GLOBAL DEFAULT PRC[0xff03] ICVAR
     8: 00000001    16 OBJECT  GLOBAL DEFAULT PRC[0xff04] XCVAR
     9: 00000001     4 OBJECT  GLOBAL DEFAULT PRC[0xff05] ECVAR
    10: 00000001     1 OBJECT  GLOBAL DEFAULT PRC[0xff06] BITVAR
    11: 00000004     4 OBJECT  GLOBAL DEFAULT  COM PLAIN
```

Honest but opaque: `PRC[0xff01]` is `SHN_LOPROC+1`, meaningful only to a reader
that knows an `EM_8051` ABI, and there is no published `EM_8051` ABI. Worse, the
`st_value` on those six is **1 = the alignment**, not an address; a generic tool
that treats `st_value` as an address (as it may for any non-`SHN_COMMON` symbol)
reads it as address 1. pyelftools hands the raw numbers straight through:

```
$ python3 -c "...ELFFile..."
'RCVAR' 65281 1 4      # (name, st_shndx, st_value, st_size)
'XCVAR' 65284 1 16
'PLAIN' SHN_COMMON 4 4
```

Section headers carry no space code at all. The port says so itself, in
`bfd/elf32-i51.c`:

> "This is where a memory-space code would be stamped into the top bits of
> sh_flags — `SHF_RDATA` on `.rbss`, `SHF_BDATA` on `.bbss` and so on — so that a
> consumer could tell one space from another from the section header alone.
> Nothing is stamped, and nothing can be … The classification is unimplemented."

Consequence in a linked image: `.data` at 0x20 and `.text` at 0x100 are
different address spaces expressed as flat, overlapping addresses, and `.data`
and `.bss` are not `SHF_ALLOC`, so no `PT_LOAD` covers them:

```
$ readelf -lSW d.elf
  [ 1] .text  PROGBITS  00000000 000054 000014 00  AX
  [ 2] .data  PROGBITS  00000020 000068 000003 00   W        <- no A
  [ 3] .bss   PROGBITS  00000023 00006b 000005 00   W        <- no A
Program Headers:
  LOAD  0x000054 0x00000000 0x00000000 0x00014 0x00014 R E 0x1
 Section to Segment mapping:
   00     .text
```

A segment-following consumer sees code only, and cannot tell that `.data`'s
0x20 lives in a different space from `.text`'s 0x20.

---

## 7. `e_flags` — set to nothing, and it is a real gap

This port never touches `e_flags`:

```
$ grep -n "e_flags" mcs51/additions.patch mcs51/modifications.patch
(no output)
$ readelf -h s.o | grep Flags
  Flags:                             0x0
```

Both siblings do (`e_flags |= bfd_mach_i51`, §2). The 2001 original did not
(`Flags: 0x0`, §2).

What upstream does with `e_flags` for exactly this purpose, read from the
binutils 2.47 tree the build unpacked:

**AVR** — low 7 bits are the sub-architecture, written on the way out and read
back to pick the machine:

```
$ grep -n "EF_AVR" include/elf/avr.h
27:#define EF_AVR_MACH 0x7F
31:#define EF_AVR_LINKRELAX_PREPARED 0x80
$ sed -n '1592,1615p' bfd/elf32-avr.c
  elf_elfheader (abfd)->e_machine = EM_AVR;
  elf_elfheader (abfd)->e_flags &= ~ EF_AVR_MACH;
  elf_elfheader (abfd)->e_flags |= val;
  ...
static bool elf32_avr_object_p (bfd *abfd) {
  if (elf_elfheader (abfd)->e_machine == EM_AVR
      || elf_elfheader (abfd)->e_machine == EM_AVR_OLD) {
      int e_mach = elf_elfheader (abfd)->e_flags & EF_AVR_MACH;
      switch (e_mach) { ... }
```

**MSP430** — identical pattern, `EF_MSP430_MACH 0xff`, same write/read pair at
`bfd/elf32-msp430.c:1573` and `:1588`.

**ARM** — `e_flags` carries the whole ABI discriminator: `EF_ARM_EABIMASK
0xFF000000` with `EF_ARM_EABI_VER1..VER5`, plus float ABI
(`EF_ARM_ABI_FLOAT_SOFT/HARD`), interworking, and — directly relevant to §8 —
`EF_ARM_BE8 0x00800000` / `EF_ARM_LE8 0x00400000`, which exist precisely because
`EI_DATA` alone cannot express ARM's code-vs-data byte order.

**TASKING** — a commercial 8051-family vendor, same idea:
"The E_FLAGS field will be used to distinguish between memory models"
(C166 EDABI v1.4 §1.1.3).

**Ghidra** — consumes it: `secondary="31"` etc. in `avr8.opinion` (§6).

### Assessment

Our port has:

- no `e_flags` write (`final_write_processing` sets only `e_machine`),
- no `e_flags` read (`elf32_i51_object_p` is `return 1;` — a stub that checks
  nothing),
- no `bfd_merge_private_bfd_data` hook at all, so nothing would ever reject a
  foreign `EM_8051` object at link time on ABI grounds.

Against 165 today that costs nothing measurable, because nobody else emits 165.
But it means:

- the port cannot express its own variants later (small/large/banked memory
  model, 8051 vs 8052 vs 80251 vs DS390) without a format break;
- if TASKING's 8051 EDABI turns out to use 165, we have no field with which to
  say "this one is ours" and no hook with which to refuse theirs — their objects
  would reach `elf32_i51_relocate_section` and be decoded with our HOWTO table.
  That is exactly the mis-decode the task asks about: same number, different
  relocation meanings, silent wrong output rather than an error;
- Ghidra's `(primary=165, secondary=e_flags)` query, if an 8051 opinion is ever
  written, would see 0 from us and 0 from anyone else who also left it unset.

`e_flags` is the standard discriminator, three upstream targets and one
commercial 8051-family vendor use it for exactly this, and we leave it at 0.
**This is a needed discriminator left unset.** Setting something non-zero and
documenting it (and checking it in `object_p`) is the cheap insurance; that is a
recommendation, not a patch.

---

## 8. Byte order — `TARGET_LITTLE_SYM` with big-endian instruction fields

The facts, all measured.

Our vec is little-endian only:

```
$ grep -n "TARGET_LITTLE_SYM" mcs51/additions.patch
1040:+#define TARGET_LITTLE_SYM	i51_elf32_vec
$ work/modern/build/binutils/objdump --info | head -4
BFD header file version (GNU Binutils) 2.47.20260726
elf32-i51
 (header little endian, data little endian)
  i51
```

One vec. There is no `elf32-i51-big`. A big-endian `EM_8051` object is
unreadable by these tools, full stop.

But the 16-bit instruction fields go out big-endian, by hand:

```
$ grep -n "bfd_putb16\|bfd_getb16" bfd/elf32-i51.c
373:      x = bfd_getb16 (contents);
375:      bfd_putb16 (x, contents);
413:      x = bfd_getb16 (contents);
415:      bfd_putb16 (x, contents);
422:      bfd_putb16 ((bfd_vma) srel & 0xFFFF, contents);
```

Proof in the bytes — `ljmp 0x112` is `02 01 12`, high byte first, in a file whose
`EI_DATA` says LSB:

```
$ work/modern/build/binutils/objdump -d s.elf
 100:	02 01 12    	ljmp	112 <TARGET>
 10e:	90 00 20    	mov	DPTR, #0x0020
```

The siblings reach the same bytes the honest way. `grep bfd_putb16` on
`gh0/bfd/elf32-i51.c` and `vol/binutils/bfd/elf32-i51.c` finds **nothing** —
they use plain `bfd_put_16`/`bfd_get_16` (gh0 lines 535, 537, 564, 566) under
`TARGET_BIG_SYM`, so the endianness comes from the vec.

And the 2001 original, the source of this whole lineage, was
`TARGET_BIG_SYM` + `ELFDATA2MSB` (§2).

### What a third-party consumer assumes

There is no `EM_8051` psABI to fix `EI_DATA`, so a consumer falls back on what
"8051" conventionally means. Every independent 8051 model reachable from here
says big-endian:

- **Ghidra**, all five 8051-family languages: `endian="big"`, ids
  `8051:BE:16:default`, `8051:BE:24:mx51`, `80251:BE:24`, `80390:BE:24`,
  `8051:BE:24:cip-51`.
- **TASKING**, in the 8051 user guide: "Note that the `__sfr` space is
  little-endian, while the other spaces are big-endian." and
  "`__BIG_ENDIAN__` Expands to 1. The processor accesses data in big-endian,
  except for the `__sfr` space which is little-endian." (`__LITTLE_ENDIAN__`
  expands to 0.)
- **the 2001 lineage** and **both sibling ports**: `ELFDATA2MSB`.
- **SDCC's own ELF writer**, for its 8-bit targets: `ELFDATA2MSB` (§4).

So: a consumer that has any prior at all about 8051 expects `ELFDATA2MSB`, and
we ship `ELFDATA2LSB`. To that consumer our combination looks wrong — and worse
than wrong, it looks *self-inconsistent*, because our multi-byte instruction
operands are big-endian inside a file that declares little-endian data.

Concretely, if Ghidra ever gained an `EM_8051` ELF opinion it would be written
against `endian="big"` (that is the only 8051 language it has); our
`ELFDATA2LSB` header would fail that constraint and the file still would not
open with a language selected. Our LSB choice actively closes the door that
adding an opinion entry would otherwise open.

To be fair to the port: `ELFDATA2LSB` is defensible on the hardware. The 8051's
`DPTR` low/high SFR pair and `MOVX` addressing are not obviously either; only
the instruction *encoding* is big-endian, and instruction encoding is not what
`EI_DATA` describes. Nothing measured here is broken by the choice — the port's
own tools round-trip fine, `file`, `readelf`, `eu-readelf`, `pyelftools` and
`llvm-readelf` all read the header correctly. The cost is interoperability with
the lineage (we cannot read the 2001 or the sibling objects, §2) and with the
prevailing 8051 convention. It is a real divergence and it should be a
documented, deliberate one rather than an accident of the `TARGET_LITTLE_SYM`
line.

---

## 9. Input acceptance, measured

Our own object with `e_machine` overwritten (`dd` at offset 18), fed to our `ld`:

| `e_machine` | stock `readelf -h` says | our `ld` |
|---|---|---|
| 165 (ours) | `Intel 8051 and variants` | links |
| 0x1051 (`EM_I51_OLD`) | `<unknown>: 0x1051` | links (ALT1) |
| 260 (github0null) | `<unknown>: 0x104` | `relocations in generic ELF (EM: 260)` → `file in wrong format` |
| 190 (volumit) | `NVIDIA CUDA architecture` | `relocations in generic ELF (EM: 190)` → `file in wrong format` |
| 0x7262 (2001) | `<unknown>: 0x7262` | `relocations in generic ELF (EM: 29282)` → rejected |

(Our own 2.47 `readelf` names 0x1051 "MCS-51 8-bit microcontroller (legacy web51
value)" — a label that, per §2, describes this repository's history, not
web51's.)

So the acceptance set is exactly {165, 0x1051}. Sibling and true-lineage objects
are refused cleanly, with a comprehensible message. That part is fine.

---

## 10. Answers to the four questions

**Does anyone else emit `EM_8051` ELF?** No producer found anywhere. Not the
siblings (260 and 190), not SDCC (no ELF path for mcs51, provably), not Keil,
Raisonance, Wickenhäuser, Silicon Labs, STC (all OMF-51), not any distro. Zero
GitHub source hits for any `EM_8051` writer. The one unresolved case is
TASKING's 8051 toolset, which does default to ELF/DWARF but publishes its
`e_machine` only in a paywalled EDABI — nine URL patterns all returned the
vendor's 404 page. IAR's XLINK can emit ELF for 8051 "for certain CPUs and
debuggers" with no documented `e_machine`. **Both unproven, both stated as such.**

**Is 165 contested in practice?** Not by anything obtainable. Our semantics are
not shared with anyone, because nobody shares the number.

**Do consumers mis-decode us?** Yes, in two ways, both reproduced above.
(a) Relocations: four independent readers say `unrecognized`/`Unknown`/
`<INVALID RELOC>`/raw-integer, because no generic tool has an `EM_8051`
relocation table. (b) Disassembly: radare2 and gdb both decode our 8051 bytes as
x86 and print plausible-looking garbage. Ghidra cannot pick a language at all.
Our big-endian 16-bit fields inside an LSB file are not the cause of any of
these — the cause is that nothing but this port knows what an `EM_8051` file
contains.

**Does anything need to accompany 165?** Yes, two things, and neither is a
crisis today:

1. **`e_flags`** should carry a discriminator and `elf32_i51_object_p` should
   check it. Precedent: AVR (`EF_AVR_MACH`), MSP430 (`EF_MSP430_MACH`), ARM
   (`EF_ARM_EABIMASK`, `EF_ARM_BE8`), TASKING C166 ("used to distinguish between
   memory models"), and Ghidra's loader, which queries on `(e_machine,
   e_flags)`. Both sibling ports set it; we do not. It is the only field that
   could ever separate our 165 from someone else's 165, and it is the field a
   consumer would look at.
2. **`EI_DATA`** should be a documented decision. Every other 8051 model in the
   field — Ghidra's five languages, TASKING's compiler, the 2001 original, both
   siblings, and SDCC's own 8-bit ELF writer — is big-endian. We are
   `ELFDATA2LSB` with hand-swapped big-endian instruction fields. That is not
   provably wrong, but it is provably unusual, it makes us unable to read our own
   lineage's objects, and it would fail Ghidra's `endian` constraint if an 8051
   ELF opinion were ever written.

A third, smaller item found on the way: the README sentence "the unregistered
`0x1051` that the 2001 lineage used" is not what the 2001 sources or artifacts
say. 2001 used `0x7262`, big-endian. `0x1051` originated in this repository.

---

## Appendix: environment

```
gcc / make / binutils 2.42 (Ubuntu) / file 5.45 / gdb 15.1
elfutils 0.190 (eu-readelf)  [apt-installed for this review]
radare2 5.5.0                [apt-installed for this review]
llvm 18.1.3 (llvm-readelf, llvm-objdump)
python3 + pyelftools 0.33    [pip-installed for this review]
sdcc 4.2.0+dfsg-1 (Ubuntu noble), sdbinutils 2.30
as31 2.3.1, dis51 0.5        [apt-installed for this review]
port under test: binutils 2.47 + mcs51/{additions,modifications}.patch,
                 built by `make -C tb build`, patches applied at zero offset
```

Fetches that were blocked, stated plainly:

- `tasking.com` 8051 EDABI PDF — 11 URL patterns, all HTTP 200 serving a
  WordPress 404 HTML page. Not obtainable.
- `keil.com/support/docs/93.htm` and `developer.arm.com/documentation/101655/...`
  — 301 → `support.arm.com`, which serves a JS shell with no body text. Primary
  Keil quotes could not be pulled; search snippets used instead and labelled.
- `silabs.com/.../an104.pdf` — fetched as bytes the tool could not render.
- `smtp.keil.com/support/man/docs/c51/...` — HTTP 503.
- `manualzz.com` TASKING 8051 guide — HTTP 403.
- GitHub REST API over plain curl — 403 through the proxy, as expected; the MCP
  GitHub tool was used instead and worked.
- Anonymous `git clone` of both sibling repos — **worked**, no auth needed.

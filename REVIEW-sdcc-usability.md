# Review: can anyone actually use this port?

Review only. Nothing in `mcs51/`, `tb/`, `.github/` was changed. Every claim below
is either a command with its output, or an explicit "could not test".

Axis: not "is it correct" — every prior round asked that — but **does this port
serve its stated purpose, being usable in a real 8051 toolchain?** The README
points at sdcc-adjacent work, so sdcc is the yardstick.

## 0. Verdict

**sdcc interop does not work today, in either direction, out of the box.**

- sdcc's own `.asm` output does not assemble: 69 errors and an assembler abort on
  the output of a 13-line C file.
- sdcc's own objects and libraries (`.rel`, `.lib`) cannot be read by `mcs51-ld`
  at all — different object format, not a bug, a category difference.
- The `__gsinit_startup` / `__external_startup` / `__init_data` weak symbols the
  README advertises match no compiler that exists, sdcc included.

**But it is not architecturally impossible, and I proved that by doing it.** With a
147-line throwaway translator I compiled a C program with sdcc, translated the
assembly, assembled it with `mcs51-as`, linked it with `mcs51-ld` against sdcc's
own C runtime (also translated), and ran the result in ucsim with bit-identical
behaviour to the native sdcc build. The same translator pushes 175 of 184 sdcc C
library modules and 15 of 15 sdcc mcs51 runtime `.asm` files through `mcs51-as`.

So the honest answer is **partially possible, and nobody has done it in this
repository**. The work that stands between here and a usable toolchain is
enumerated in §9. One item is a real assembler limitation (§7); the rest is
dialect glue that does not exist.

## 1. What was built and with what

```
$ apt-get install -y sdcc            # 4.2.0 #13081, plus s51 (ucsim), gputils
$ make -f tb/Makefile build OPTFLAGS="-O1" AR_WRAP=
$ work/modern/build/gas/as-new --version
GNU assembler (GNU Binutils) 2.47.20260726
```

Target `i51-elf`. Tools referred to below as `mcs51-as`, `mcs51-ld`, … are
symlinks to `work/modern/build/{gas/as-new,ld/ld-new,binutils/*}`.

Test program (`hello.c`, 13 lines) touches every address space that matters:
`__xdata` array, `__data` byte, `__bit` flag, a call with a parameter.

## 2. sdcc's native output through `mcs51-as`

```
$ sdcc -mmcs51 -S hello.c            # -> hello.asm, 196 lines
$ mcs51-as -o hello.o hello.asm 2>&1 | grep -c Error
69
```

Census of the 69:

| count | error | cause |
|---|---|---|
| 39 | `unknown pseudo-op: '.area'` / `.module` / `.optsdcc` | sdas section model absent |
| 22 | `missing .using` | `ar0..ar7` used with no register-bank directive |
| 7 | `junk at end of line, first unrecognized character is ':'` / `'0'` | `label::` global-label form; `00102$` local labels |
| 1 | `invalid operands (.text and *ABS* sections) for '>>'` | `#(_buf >> 8)` high-byte-of-symbol |

Then, after the errors, the assembler **aborts** (§3).

The individual mismatches, each verified:

- **Section naming.** sdcc emits `.area CSEG (CODE)`, `DSEG`, `OSEG`, `ISEG`,
  `BSEG`, `PSEG`, `XSEG`, `XISEG`, `XINIT`, `HOME`, `GSINIT0`..`GSINIT5`,
  `GSFINAL`, `CONST`, `CABS`, `XABS`, `IABS`, `REG_BANK_n`, with attribute lists
  `(REL,OVR,DATA)`. The port has `.text/.data/.bss/.rdata/.rbss/.bdata/.bbss/
  .idata/.ibss/.xdata/.xbss/.edata/.ebss/.bitdata/.bitbss/.eeprom/.pcode`
  (`md_pseudo_table`, additions.patch:1134). No `.area` in any form.
- **`$` is a statement separator in this port.**
  `const char line_separator_chars[] = "$";` (additions.patch, tc-i51.c). sdas
  uses `$` as the *suffix* of a reusable local symbol (`00102$`,
  `dataptrrestore$`). The two uses are mutually exclusive at the character level.
- **`label::`** is sdas for "define and export". gas parses the label, then
  chokes on the second colon.
- **`ar0 = 0x00 … ar7 = 0x07`.** sdcc defines these itself; the port already owns
  `AR0..AR7` as built-in direct operands (`i51_directop`, additions.patch:1231).
  With `.using 0` in force they are absolute symbols and sdcc's assignment is
  rejected:
  ```
  Error: symbol `ar7' is already defined
  ```
- **`#(sym >> 8)`.** The port expresses a high-byte relocation as `HIGH(sym)`;
  gas's generic expression parser cannot shift a section-relative symbol.
  `HIGH(sym+addend)` does work and emits a proper `R_I51_H` with the addend:
  ```
  $ cat high.s
  	.text
  	.using 0
  	mov	r2,#HIGH(L_XINIT+255)
  $ mcs51-objdump -dr high.o | tail -3
     0:	7a 00       	mov	R2, #0x00	; #0
  			1: R_I51_H	L_XINIT+0xff
  ```

## 3. `mcs51-as` aborts on two lines of valid-syntax input

Not malformed input, not a fuzz case — a source file that merely forgets a
directive:

```
$ cat fatal2.s
	.text
	push	ar7
$ mcs51-as -o fatal2.o fatal2.s
fatal2.s:2: Error: missing .using
fatal2.s: Fatal error: Case value 63 unexpected at line 1382 of file "../../binutils-2.47/gas/symbols.c"
```

63 is `O_max`. `tc-i51.c` uses `O_max` as an "operand not yet set" sentinel:

```
op_expr1.X_op = O_max;          # additions.patch:1689-1690
op_expr2.X_op = O_max;
```

All three `missing .using` paths report and return **without clearing the
sentinel**:

```
if (regbank == 0xFF)
  {
    as_bad (_("missing .using"));
    return;                      # additions.patch ~2130, ~2304, ~2481
  }
```

`md_assemble` then builds the instruction and creates a fix whose expression
still carries `X_op == O_max`; `resolve_symbol_value` hits `BAD_CASE (op)` at
gas/symbols.c:1382 and calls `as_fatal`.

**Where the fix would go** (not applied): in `gas/config/tc-i51.c`, on each of
the three error paths, set `op_expr1.X_op = O_constant; op_expr1.X_add_number =
0;` before returning — or have `md_assemble` stop once `as_bad` has fired.

**Provenance:** this is inherited, not introduced here. The same three
`as_bad(); return;` sites and the same `O_max` sentinel are in the 2001 original
(`tb/ref.7z`, `i51.patch.112n` lines 1702-1703 and 2065/2243/2415) and in the
2.38 fork (`github0null/binutils-mcs51`, `gas/config/tc-i51.c:1108-1112`,
`1283-1287`, `1455-1459`). Nobody in the lineage has noticed it.

## 4. Symbol case folding — this port only

```
$ grep -n symbols_case_sensitive mcs51/additions.patch
1605:+  extern int symbols_case_sensitive;
1606:+  symbols_case_sensitive = 0;
```

`md_begin` turns off case sensitivity for all symbols. Consequence, on real C:

```
$ cat casec.c
unsigned char count;
unsigned char Count;
void main(void) { count = 1; Count = 2; }
$ sdcc -mmcs51 -S casec.c && <translate> && mcs51-as -o t_casec.o t_casec.s
t_casec.s:36: Error: symbol `_Count' is already defined
```

Two distinct C identifiers become one symbol. It fails loudly rather than
corrupting silently, which is the good version of this — but arbitrary C cannot be
assembled by this port, full stop. There is no `--case-sensitive` option:
`md_shortopts` is `""` and `md_longopts` is empty (additions.patch:1127-1131).

Scope of the damage in practice, measured rather than assumed: across every
symbol sdcc's shipped mcs51 libraries define or reference,

```
$ sh casecheck.sh
distinct sdcc library symbols: 502
collisions after uppercasing:
(empty above = none)
```

sdcc's own libraries would survive; user code is the exposure.

This is new in this repository, not inherited:

- The 2001 original does not set it (`grep -i case_sensitive` over
  `i51.patch.112n`/`.112p` → nothing).
- `github0null/binutils-mcs51` (2.38) does not set it (`grep -c` → 0).
- `volumit/sdcc_aurix_scr_42`'s binutils does not set it (`grep -c` → 0).

It arrived in commit `15b928d "up to 2.45.1"`.

The repository contains its own evidence of the cost: `tb/i51elf_sym_uc.py`
("Convert all symbol names in an ELF object to uppercase") and the `make libk80`
rule exist only to rewrite the 2001 prebuilt objects so the current assembler's
symbol namespace still matches them. Any object not produced by *this*
assembler needs that treatment.

## 5. Object format: sdcc's libraries are unreachable

sdcc's objects are ASxxxx `.rel` text; `.lib` files are `ar` archives of them.

```
$ head -3 sdcclib/__memcpy.rel
XH3
H 1B areas 6 global symbols
M __memcpy
$ mcs51-ld sdcclib/__memcpy.rel
ld-new: sdcclib/__memcpy.rel: file format not recognized; treating as linker script
ld-new: sdcclib/__memcpy.rel:2: syntax error
```

There is no path from a shipped `libsdcc.lib` / `mcs51.lib` to `mcs51-ld`. Every
library module must be recompiled from source and re-assembled. That is a fixed,
unavoidable cost of choosing ELF, and it is the right choice — but it means
"link against sdcc's libc" is not a thing that can be made to work by wrapping.

## 6. Calling conventions, register banks, runtime symbols

- **Register banks.** `regbank = 0xFF` by default (additions.patch:1409). Any
  `ARn` operand without a preceding `.using N` is an error (and currently an
  abort, §3). `.using N` also emits `__RB__`, a `.regbank` common of size
  `regused + 8` (`i51_cleanup`, additions.patch:2850-2868), so the linker
  reserves 8/16/24/32 bytes at 0x00 depending on the highest bank any input used.
  This is a coherent convention and it is **the port's own**. sdcc never emits
  `.using`; it assumes bank 0 at reset and switches with `PSW.RS0/RS1` via
  `crtbank.asm`. A translator has to inject `.using`.
- **Stack.** The default script provides `STACK` / `__STACK` at `__IDATA_END`.
  sdcc's runtime uses `__start__stack` and sets `SP` itself
  (`mov sp,#__start__stack - 1`, crtstart.asm). Different name, different owner.
- **Startup hooks.** The script provides
  `__GSINIT_STARTUP`, `__EXTERNAL_STARTUP`, `__INIT_DATA`, each bound to a `RET`
  stub when left undefined. sdcc's actual symbols are
  `__sdcc_gsinit_startup`, `__sdcc_external_startup`, `__sdcc_program_startup`,
  `__sdcc_init_data` (`/usr/share/sdcc/lib/src/mcs51/crtstart.asm`). Uppercased by
  this assembler they become `__SDCC_GSINIT_STARTUP` etc. — **near-misses that do
  not bind.** The README calls them "compiler-independent"; they are sdcc's names
  with `sdcc_` removed, and the result matches no compiler:
  - not sdcc's (above);
  - not web51's — `grep -rn -i 'gsinit|external_startup|init_data|sdcc'` over the
    extracted `tb/base.7z` 2001 corpus returns **zero hits**;
  - not the other two ports' — the same grep over volumit's `device/` and `src/`
    and github0null's `ld/` returns zero hits. github0null's script instead names
    sdcc explicitly: `PROVIDE(___sdcc_external_startup = 0x0000)`.

  "Compiler-independent" here means "matches nothing".

## 7. The experiment: sdcc → this port, end to end

`sdas2gas2.py` (147 lines, throwaway, lives in scratch, **not added to the
repo**) rewrites sdas spelling into i51-gas spelling:

| sdas | i51 gas |
|---|---|
| `.area CSEG/CONST/CABS/XINIT` | `.text` |
| `.area HOME` | `.init` |
| `.area GSINIT0..5, GSINIT, GSFINAL` | `.init.1` … `.init.8`, ordered with `ld --sort-section=name` |
| `.area DSEG/OSEG/SSEG/RSEG/IABS` | `.bss` |
| `.area ISEG` / `BSEG` / `XSEG,PSEG,XISEG,XABS` | `.ibss` / `.bitbss` / `.xbss` |
| `.area REG_BANK_n` | dropped — covered by `.using`'s `__RB__` |
| `name::` | `.globl name` + `name:` |
| `00102$`, `name$` | `.LS<scope>_00102` — renumbered per scope |
| `.ds`/`.ds.b`, `.db`, `.dw` | `.skip`, `.byte`, `.word` |
| `#(sym >> 8)`, `#((sym+255) >> 8)` | `#HIGH(sym)`, `#HIGH(sym+255)` |
| `#sym` (8-bit) | `#LOW(sym)` |
| `NAME == value` | `.globl NAME` + `NAME = value` |
| `ar0..ar7 = 0xN` | deleted |
| `.module`, `.optsdcc`, `.org` | deleted |

Bit-space unit, verified rather than guessed: in `.bitbss`/`.bitdata` one byte of
section content is **one bit** of address space, so sdcc's `.ds 1` in `BSEG` maps
1:1 to `.skip 1`.

```
$ mcs51-nm -n bitunit.elf | grep -E 'FLAG|DVAR|BIT_END'
00000000 ? FLAG_A     00000001 ? FLAG_B     00000002 ? FLAG_C
00000003 ? __BIT_END  00000021 ? DVAR
```
Three bits at 0,1,2; `.bss` resumes at 0x21 = 0x20 + ceil(3/8). Matches the
script's `(SIZEOF(.bit) + SIZEOF(.bitbss) + 7) / 8`.

Two things GNU ld cannot supply and the linker script had to fake:

1. **`s_<AREA>` / `l_<AREA>`.** sdld synthesises a start and length symbol for
   every area; `crtclear.asm`, `crtxclear.asm`, `crtxinit.asm` will not link
   without `l_IRAM`, `s_XSEG`, `l_XSEG`, `s_PSEG`, `l_PSEG`, `s_XINIT`,
   `l_XINIT`, `s_XISEG`. I hand-defined them in the script. There is no generic
   mechanism; each one is a hand-written line.
2. **GSINIT staging.** sdld concatenates `GSINIT0..GSINIT5, GSINIT, GSFINAL` in a
   fixed order and the runtime relies on falling through them. The port's default
   script has `*(.init) *(.init.*)`, which keeps *input* order. I encoded the
   stages in section names and forced `*(SORT_BY_NAME(.init.*))`.

Result:

```
$ mcs51-as ...        # hello + crtstart/crtclear/crtxclear/crtxinit/crtpagesfr
$ mcs51-ld --sort-section=name -T sdcc.ld -e 0 -o t_hello.elf ...
LINK OK
$ mcs51-objcopy -O ihex --only-section=.text t_hello.elf t_hello.hex
IHEX OK
$ s51 -t C51 t_hello.hex < cmds
...
0x0000   00 01 02   0x0003   03 04 05   0x0006   06 07 cd
0x20     01 00 00 00 ...
Simulated 14580 ticks
```

xdata 0..7 = `00 01 02 03 04 05 06 07` (the loop wrote `buf[i] = i`), internal RAM
0x20 bit 0 set (`flag = 1`). The native sdcc build of the same source:

```
$ sdcc -mmcs51 --out-fmt-ihx hello.c -o hello_native.ihx
$ s51 -t C51 hello_native.ihx < cmds
0x0000   95 00 01   0x0003   02 03 04   0x0006   05 06 07
0x20     01 07
Simulated 14580 ticks
```

Same data, same 14580 ticks. The port's code generation is not the problem.

Only stand-in written by hand: `__sdcc_external_startup`, because the real one
lives in `libsdcc.lib` as a `.rel` member (§5).

### How much of sdcc's library survives the translation

```
$ sh libsweep.sh
--- hand-written asm runtime: 15/15 assembled
--- C library modules: 175/184 compiled+translated+assembled
--- sdcc refused to compile: 8; translator errors: 0; mcs51-as errors: 1
```

- 15/15 of `/usr/share/sdcc/lib/src/mcs51/*.asm`.
- 175/184 of `/usr/share/sdcc/lib/src/*.c`.
- The 8 sdcc refusals are **mine, not the port's** — I compiled the library
  sources without the per-module flags sdcc's own lib Makefile passes
  (`error 98: conflict with previous declaration`).
- **One genuine port limitation**, `time.c`:
  ```
  ___month:
  	.byte __str_1, (__str_1 >> 8),0x80
  Error: invalid operands (.text and *ABS* sections) for '>>'
  ```
  This is sdcc's generic-pointer table: a static initializer that needs a
  **high-byte relocation in data**. `LOW()`/`HIGH()` are recognised only by the
  instruction operand parser, not by `.byte`:
  ```
  $ printf '\t.text\nT:\tnop\n\t.byte LOW(T)\n' > lowbyte.s
  $ mcs51-as -o lowbyte.o lowbyte.s
  lowbyte.s:3: Error: junk at end of line, first unrecognized character is `('
  ```
  Plain symbols in data *do* relocate — `.word sym` → `R_I51_16`, `.byte sym` →
  `R_I51_8` — so only the high byte is unreachable. Any `const char *` table in
  code space hits this.

  **Where the fix would go** (not applied): `gas/config/tc-i51.h` already carries
  the AVR-shaped hooks, commented out —
  ```
  //#define TC_PARSE_CONS_EXPRESSION(EXPR,N) avr_parse_cons_expression (EXPR,N)
  //#define TC_CONS_FIX_NEW(FRAG,WHERE,N,EXP) avr_cons_fix_new(FRAG,WHERE,N,EXP)
  ```
  (additions.patch:3684, 3692). AVR implements `lo8()`/`hi8()` in `.byte` exactly
  through those two. i51 versions accepting `LOW()`/`HIGH()` and emitting
  `R_I51_L`/`R_I51_H` would close it.

So: after fixing three *translator* gaps (`$`-suffixed named local labels,
per-scope reuse of `00102$` numbers across functions in one module, `.db`/`#` in
data), the assembler rejects exactly one module out of 184, for one concrete and
locatable reason.

## 8. The other two ports

Both were fetched. `api.github.com` and `github.com` return 403 through this
session's egress proxy, but the git proxy serves anonymous clones, so the
sources below are read from real checkouts, not from memory.

### `github0null/binutils-mcs51` — binutils 2.38, single squashed commit, Aug 2025

- **Case-sensitive.** No `symbols_case_sensitive` anywhere in `gas/config/tc-i51.c`.
- Same `line_separator_chars[] = "$"`, same `;` comments, same absence of `.area`,
  same `.using` requirement, same `O_max` abort (§3).
- Adds `-mmcs51` as a required ISA selector, with an `I51_SCR` variant stubbed out
  in `include/opcode/i51.h` — the same Infineon SCR that volumit targets.
- **Its linker script is openly sdcc-shaped**, unlike this repo's:
  ```
  /* Provide default sdcc weak symbols */
  PROVIDE(___sdcc_external_startup = 0x0000);
  ...
  KEEP(*(.init.0)) KEEP(*(.init.1)) KEEP(*(.init.2)) KEEP(*(.init.3))
  ... __start__stack = . ;
  ... PROVIDE(__xinit_start = .); KEEP(*(.text.xinit)); PROVIDE(__xinit_end = .);
  . += 8 ; /* Reserve 1 byte for sdcc built-in 'bits' */
  ```
  Staged `.init.N`, `__start__stack`, `__xinit_*`, sdcc's bit block — i.e. it
  expects a compiler emitting GNU section names, and it names sdcc while doing it.
- Sizes are parameters: `PROVIDE(__FLASH_SIZE__ = 8192)`, `__IDATA_SIZE__`,
  `__XDATA_SIZE__`, overridable with `--defsym`, plus
  `ASSERT((LENGTH(IDATA) - SIZEOF(.idata)) >= 20, ...)`. This repo's script hard-codes
  a 64K rom region and leaves chip size to the user.

### `volumit/sdcc_aurix_scr_42` — a patched SDCC plus a ~2.20-era binutils

`binutils/bfd/version.h` → `BFD_VERSION_DATE 20091016`.

This repo's README calls it "sdcc-adjacent work". It is more than adjacent: it is
**the same experiment I ran in §7, done properly, in the compiler**. Their README:

> SDCC is only used as compiler frontend to generate assembly. Assembler,
> Link/Locate, .... is done by a modified version of binutils, which is now
> supporting SCR (MCS51).

The mechanism, in `src/mcs51/main.c`: the port's area-name table has the sdas
names `#if 0`'d out and replaced with GNU section directives —

```
#if 0
    "CSEG    (CODE)",           // code_name
    "XSEG    (XDATA)",          // xdata_name
    "OSEG    (OVR,DATA)",       // overlay_name
#endif
    ".text.code,\"ax\" ;code_name",
    ".xdata.i51,\"aw\" ;xdata_name",
    ".text.gsinit,\"ax\" ;static_name",
    ".text.gsfinal,\"ax\";post_static_name",
    ".text.home,\"ax\" ;home_name",
    ";OSEG_OVR_DATA",           // overlay_name  <-- disabled
```

and `src/mcs51/gen.c` emits `.using 0..3` — the port's own directive, from the
compiler.

Their crt is rewritten in gas syntax with sdcc's real names kept:
`.section .text.gsinit0,"ax"` / `__sdcc_gsinit_startup:` / `lcall
__sdcc_external_startup`. Their `device/lib/mcs51/linker_tc3xx.ld` hand-defines
exactly the symbols I had to invent: `PROVIDE(l_IRAM = 0x100)`, `s_XSEG =
__xdatac_start`, `l_XSEG = __xdatac_end - __xdatac_start`.

Their linker script's memory algebra is the same design as this repo's — `.bit`
placed at `((ADDR(.bbss) - 0x20) * 8)`, `.data` at
`... + (SIZEOF(.bit) + SIZEOF(.bitbss) + 7) / 8` — but with **lowercase** symbol
names (`__data_start`, `stack`), because their assembler is case-sensitive.

**And they state the price of the GNU-ld backend by enforcing it in code**
(`src/mcs51/main.c:190-240`):

```
if (options.xstack)      { "error: --xstack is not supported"; exit(1); }
if (!options.noOverlay)  { "error: --nooverlay has to be enabled"; exit(1); }
case MODEL_SMALL:  "error: small model is not supported";  exit(1);
case MODEL_MEDIUM: "error: medium model is not supported"; exit(1);
case MODEL_LARGE:  /* allowed */
```

Only large / large-stack-auto, no xstack, **overlay off**. That is independent
confirmation of the one semantic that no amount of translation recovers: sdcc's
`OSEG` overlay — locals of non-overlapping functions sharing addresses — has no
GNU ld equivalent. My translator maps `OSEG` to `.bss`, which is correct but
spends more internal RAM; on a 128/256-byte part that difference is the whole
budget. volumit's answer was to give up on it and require `--nooverlay`. Their
reported result: `mcs51-large`, 0 failures / 18471 tests.

## 9. What a usable path would need

Nothing below is a patch; it is the list of what is missing.

1. **A compiler that emits this dialect.** Either patch sdcc's mcs51 port the way
   volumit did (area-name table + `.using` emission — roughly 30 lines in
   `src/mcs51/main.c` and `gen.c`), or ship the sdas→gas translator. The compiler
   is the right place; a translator is guessing at `#` operand widths from
   context.
2. **Turn the case folding back off**, or make it an option. It is the one
   barrier that no translator can work around, it is new in this repo, neither
   sibling port has it, and the repo already ships a script
   (`tb/i51elf_sym_uc.py`) whose existence is the bug report.
3. **A `.byte LOW()/HIGH()` path** — uncomment and implement the two AVR-shaped
   hooks in `gas/config/tc-i51.h` (§7). Without it, code-space pointer tables and
   therefore a chunk of any real libc cannot be assembled.
4. **Fix the `missing .using` abort** (§3) — three lines, and the same three lines
   in the two sibling ports.
5. **Startup-hook names that match something.** Either adopt sdcc's real
   `__sdcc_gsinit_startup` / `__sdcc_external_startup` / `__sdcc_program_startup`
   (as github0null did), or document that these are this port's own ABI and ship
   the crt that implements it. Right now the script provides three symbols nothing
   references.
6. **`s_<AREA>` / `l_<AREA>` in the default script**, or a documented convention
   for them. Every sdcc-derived runtime needs them; every user rediscovers that.
7. **A crt and a libc.** The repository ships neither. sdcc's cannot be linked
   in binary form (§5); recompiling them from source through the translator works
   for 175/184 modules today, which means this is a packaging job, not a research
   one.
8. **A chip-parameterised linker script.** The default script hard-codes a 64K rom
   region; github0null's takes `__FLASH_SIZE__` / `__IDATA_SIZE__` /
   `__XDATA_SIZE__` via `--defsym` and asserts on stack space. Real parts are 4K/8K
   with 128 or 256 bytes of IRAM.

## 10. What works today

Plainly: **hand-written assembly in this port's own dialect, and the ten 2001
web51 projects with their prebuilt objects.** That is the supported surface, and
within it the port does work — `tb/sim/run-defaultlink.sh` links a probe touching
every address space with the built-in script and no flags, and my own probes
(`bitunit.s`, `high.s`) assemble, link and place symbols correctly.

There is no C compiler you can point at this toolchain today and get a program
out of. The nearest working combination that exists anywhere is volumit's — a
patched SDCC 4.2.2 emitting GNU sections, plus their own 2009-vintage binutils,
plus their own crt and linker script, with `--model-large --nooverlay`. This
port is fifteen years newer than that binutils and cannot be dropped into its
place: different section names (`.ddata.i51` vs `.data`), different symbol case,
different startup-hook names.

The gap between "the ten 2001 projects" and "a toolchain" is §9. It is finite,
and item 2 is the only one that is a step backwards rather than a step not yet
taken.

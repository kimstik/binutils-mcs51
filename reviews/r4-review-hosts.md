# Review: host portability and build reproducibility

Branch reviewed: `work/green` (as `claude/review-hosts`). Review only — nothing in
`mcs51/`, `tb/` or `.github/` was changed. Every claim below was produced on this
container unless marked "could not test". Environment: Ubuntu 24.04 x86_64, gcc
13.3.0, mingw-w64 13-win32 (both `x86_64-w64-mingw32` and `i686-w64-mingw32`),
wine 9.0 (wine64 + wine32:i386), binutils tarball 2.47 as pinned by `tb/Makefile`,
port applied from `mcs51/additions.patch` + `mcs51/modifications.patch`.

Builds made for this review, all from the same patched tree
(`make -C tb build` first, then hand-configured out-of-tree builds with the CI's
exact flags):

| build | host triplet | flags |
|---|---|---|
| native (tb) | x86_64-linux | `-Os -flto -march=haswell`, `AR=gcc-ar` |
| repro A, repro B | x86_64-linux | same as CI linux-x86_64, two different build dirs |
| win64 | x86_64-w64-mingw32 | same as CI win64 |
| win32 | i686-w64-mingw32 | same as CI win32 |
| m32 | i686-linux (`gcc -m32`) | `-Os` |

## Verdict, one paragraph

The Windows cross-builds are real, working toolchains: run under wine they
assemble, archive, link and objcopy a multi-module program to bytes identical to
the native linux output, and the **full `make check` testbench passes under wine
for both win64 and win32 — all ten reference ROMs byte-identical**. Output of
as/ld/objcopy is deterministic and host-independent everywhere I could measure
(linux 64, linux 32, win64, win32; two runs; different build dirs; different
input paths; CRLF input). Two genuine host-portability defects exist in the
port's own source, both proven with divergent runs below: the LLP64 `long`
truncation in `md_apply_fix`/`check_range`, and a locale-dependent `toupper` in
operand parsing that produces **silently wrong bytes** in a Turkish 8-bit
locale. `ar` is not deterministic by default (`D` is not on). The wine smoke
test in CI proves almost nothing; the full testbench demonstrably runs under
wine with an eight-line wrapper directory.

## 1. Do the Windows builds actually work?

Yes. Both cross-builds configure and compile cleanly with the CI's own flags
(`--host=x86_64-w64-mingw32` / `--host=i686-w64-mingw32`, `-Os -flto`,
`LDFLAGS=-s`, gcc-ar wrap). The resulting exes depend only on `KERNEL32.dll` and
`msvcrt.dll` (`objdump -p | grep 'DLL Name'`) — no libgcc/winpthread DLLs, so
the shipped tarballs are self-contained.

Real work under wine, not `--version`: assemble two modules, `ar rc` them, link
with the built-in default script, `objcopy -O binary`, and byte-compare against
the native linux build's output:

```
win64 under wine:   main.o util.o prog.elf prog.bin — all IDENTICAL to native
win32 under wine:   main.o util.o prog.elf prog.bin — all IDENTICAL to native
(md5 prog.bin = ebcaf6bb9544c3f26510f6e8ecb6ff86 on every host)
```

Then the actual testbench. `tb/Makefile check` only needs `BUILD` to contain
`gas/as-new`, `ld/ld-new`, `binutils/{objcopy,ar,nm-new,strip-new}`, so I made a
directory of eight 3-line `#!/bin/sh` wrappers, each `exec wine <path>.exe "$@"`,
and pointed `BUILD` at it:

```
make -C tb check BUILD=<wine-wrapper-dir>   # win64 exes
→ PASS all 10 projects, ROM hashes match tb/reference.md5
make -C tb check BUILD=<wine-wrapper-dir>   # win32 exes
→ PASS all 10 projects
```

The toolchain-only gates also pass against the win64 exes under wine:
`branch` (24 cases), `bits` (50 cases), `reloc` (36 checks), `defaultlink`,
`commons`, and `sim` (ucsim executes the wine-built ROM to the P1=127 verdict).
`isa` (280 golden-byte cases + testall) also passes — see §5 for the caveats
about running it under wine.

## 2. Reproducibility of the build

**Toolchain binaries are bit-reproducible.** Two independent builds (repro A and
B) with identical configure arguments in two different build directories produce
byte-identical `as-new`, `ld-new`, `objcopy`, `ar`, `nm-new`, `strip-new`
(md5 of as-new `5dc0aac74b36a59deceeecb5570e4508` from both). Rebuilding gas
with `-j1` reproduces the `-j4` binary exactly, so `-j` does not leak in. LTO,
`-Os` and `-s` do not introduce nondeterminism.

**The `--prefix` path is embedded in the binaries.** The tb-built tools differ
from repro A/B only because they were configured with a different prefix:
`strings as-new` shows `<prefix>/bin` and `<prefix>/lib/debug`, and `ld-new`
embeds its default search dirs (`<prefix>/i51-elf/lib`, ...). The string is the
unnormalized `$(WORK)` path (`.../tb/../work/modern/toolchain/...`). So the
release binaries depend on the checkout path. In CI this is invisible because
`$GITHUB_WORKSPACE` is the same on every run of a given repo; anyone rebuilding
elsewhere gets binaries that differ in exactly these strings. Not a defect,
standard binutils behavior — but it is the one thing standing between this build
and bit-for-bit third-party reproduction.

**The release tarball is never byte-identical across runs** even with identical
contents: `tar czf` stores member mtimes (verified: touching one file changes
the archive; two `tar czf` runs over unchanged files are identical). CI does not
pass `--mtime`/`--sort`.

**Tool output is deterministic.** Same input assembled and linked twice, in two
different directories: `main.o`, `util.o`, `prog.elf`, `prog.bin` byte-identical
every time, and identical across all four host builds. No timestamps, no
paths, no locale text in the objects: `nm -a` shows no file symbol, `strings`
shows no path, and assembling the same file via an absolute path produces a
byte-identical object. CRLF line endings in the source also produce an
identical object. No hash-iteration-order effects were observed anywhere
(symbol tables and section order stable across runs and hosts).

**`ar` is NOT deterministic; `D` is not the default.** Two `ar rc` runs on the
same object give different archives — the member headers embed the mtime
(`1787776888` vs `1787776893` visible at offset 24 in the two runs). The tb
configure line does not pass `--enable-deterministic-archives` and the built
`config.h` says `#define DEFAULT_AR_DETERMINISTIC 0`. `ar rcD` is byte-stable
(verified across a `sleep`). The linked ROMs stay reproducible because member
mtimes never reach the image, but any user of the released `mcs51-ar` gets
irreproducible `.a` files by default, and `tb`'s own `libk80` target (`ar rcs`)
inherits this. Fix would go in the `configure` invocation inside the `build:`
target of `tb/Makefile` (add `--enable-deterministic-archives`), which also
fixes CI since CI calls that target.

## 3. Host-dependent code in the port's sources

### 3a. LLP64 `long` truncation — proven divergence between CI's own hosts

`gas/config/tc-i51.c` (carried in `mcs51/additions.patch`):

- `md_apply_fix()` (line 777) declares `long value;` and assigns `value = *valuep;` where
  `valuep` is `valueT*` (64-bit on LP64/LLP64 hosts). All subsequent range
  checks (`value < -256 || value > 255`, the `-65536..65535` HIGH check, the
  PCREL7 check) then run on the truncated `long`. Also `long pc` in the
  R_I51_11 case, and `check_range(long num, int mode)`.
- On linux/macos 64-bit, `long` is 64-bit and the checks see the true value.
  On win64 `long` is 32-bit (LLP64): the value is truncated first.

Empirical proof, same input to two builds from the same source:

```
lab1:  nop
       mov a, #(lab2 - lab1 + 0xFFFFFFFF + 2)
lab2:  nop

linux x86_64 as-new:            Error: operand out of range: 4294967300  (exit 1)
win64 as-new.exe under wine:    exit 0, silently emits 74 04  (mov A, #0x04)
```

win32 and linux `-m32` also accept it, but through a different mechanism: on
32-bit hosts binutils 2.47 builds with `BFD_ARCH_SIZE 32`, `BFD64` undefined,
so `bfd_vma`/`offsetT` are 32-bit and the expression wraps in generic gas
arithmetic before the port ever sees it — generic binutils behavior, not the
port's. The port-specific defect is the win64 one: a 64-bit host silently
accepting what the other three 64-bit CI hosts reject. The impact is confined
to expressions whose value needs more than 32 bits, which no sane 8051 program
has, but it is a real accept/reject divergence inside the release matrix.

Where the fix goes: `gas/config/tc-i51.c` — `md_apply_fix` (`long value` →
`valueT`/`offsetT`, same for `long pc`) and `check_range` (`long num` →
`offsetT num`; while there, the `0xFFFFFF00`/`0xFFFF0000` masks only examine
bits 8..31 / 16..31, so values with bits ≥32 pass the IMM8/IMM16 checks on
every host — replace the masks with real range comparisons).

### 3b. Locale-dependent `toupper` — silently wrong bytes, proven

`extract_op()` in `gas/config/tc-i51.c` uppercases every operand with the
C-library `toupper((unsigned char)c)`, and gas calls
`setlocale(LC_CTYPE, "")` at startup (`gas/as.c:1333`), so the mapping follows
the user's locale. In any locale where `toupper('i') != 'I'` — Turkish 8-bit
locales, and the Turkish ANSI code page CP1254 that a Windows build picks up
via the same `setlocale` — built-in operand names containing `i` (`TI`, `RI`,
`IE`, ... from `i51_directop[]`) written in lower case stop matching the
operand hash. There is no error; the name falls through to
`md_undefined_symbol`, misses again, and assembles as an undefined symbol
worth 0:

```
loop:  jb  ti, loop
       mov a, ie

LC_ALL=C            → 20 99 fd   e5 a8      (jb 0x99 / mov A,0xA8 — correct)
LC_ALL=tr_TR.iso88599 → 20 00 fd e5 00      (jb 0x00 / mov A,0x00 — silent garbage,
                                             exit status 0, objects differ)
```

That is a worst-case portability bug: same source, same binaries, different
*bytes* depending on the user's locale, with a green exit code. This is the
only ctype call in the port. Where the fix goes: `extract_op` in
`gas/config/tc-i51.c` — use `TOUPPER` from `safe-ctype.h` (locale-independent,
what the rest of gas uses; gas's own case-insensitive symbol fold, which
`symbols_case_sensitive = 0` turns on, already uses safe-ctype, so today the
two folds don't even agree with each other outside the C locale).

### 3c. Clean, checked and found not host-dependent

- `opcodes/i51-dis.c`: all cursor math in `int` with explicit `& 0xFF`/`&
  0xFFFF` masks; reads bytes via `read_memory_func` and `bfd_getb16`; the
  printable-character test is `(opdata >= ' ') && (opdata < 0x7F)`, not
  `isprint`, so disassembly listings are locale-stable. No sprintf overflow
  (operands bounded by masks, buffers 16/40 bytes).
- `bfd/elf32-i51.c`: relocation math in `bfd_vma`/`bfd_signed_vma`, all section
  data accessed through `bfd_get_8`/`bfd_getb16`/`bfd_putb16` — no host
  byte-order assumption, no misaligned host loads. `strcasecmp` in
  `bfd_elf32_bfd_reloc_name_lookup` is the stock pattern of every BFD backend
  and mingw provides it.
- `bfd/cpu-i51.c`: a single const descriptor, nothing host-visible.
- `gas/config/tc-i51.c` otherwise: `md_atof` goes through `atof_ieee`; target
  byte order handled by `number_to_chars_bigendian`; the one `int temp =
  get_absolute_expression()` truncation in `i51_common` is int-width on every
  supported host, so consistent (sloppy, not host-dependent). No `time()`, no
  `qsort` on ambiguous keys, no `getenv`-driven behavior.
- Big-endian host: **could not test** — no big-endian machine or usable qemu
  system image in this container. Static review found no raw multi-byte host
  reads in the port (everything goes through the bfd accessors), so there is
  no concrete suspect; but nothing here has ever run on s390x/ppc64 as far as
  this repo shows.

## 4. 32-bit host

`CC="gcc -m32" --host=i686-pc-linux-gnu` builds the modern port cleanly. The
resulting 32-bit toolchain passes the **full testbench** — all ten projects,
ROMs byte-identical to the pinned references — and its output on the review's
test program is byte-identical to the 64-bit build's. The only observed
behavioral difference is the >32-bit expression acceptance described in §3a
(32-bit `offsetT`, generic to all 32-bit-host binutils, shared with win32).
So the answer is: yes, the modern port works as a 32-bit binary and produces
identical output for real input. (The frozen 2.11.2 `gcc -m32` build is a
separate, already-covered pipeline; nothing here touches it.)

## 5. The CI matrix

**The wine smoke test is worth almost nothing.** `as-new.exe --version | head -2`
proves the exe links against msvcrt and can start — it exercises zero lines of
i51 target code. Both host-portability bugs in §3 sail straight through it, and
so would any LLP64 relocation bug, any binary-mode `fopen` slip, any
path-separator problem. The gap is not hypothetical capability, it is measured:
the very testbench this repo already has passes under wine on the same runner
type CI uses.

**What it takes to run the real testbench on the Windows builds, today, on the
existing ubuntu runners:** a `BUILD` directory of eight 3-line `sh` wrappers
(`exec wine $ABS/<tool>.exe "$@"`) and nothing else — `make -C tb check
BUILD=<wrappers>` then runs unmodified and went green for both win64 and win32
in this review. Two practical notes from doing it: (1) the tb wrapper generator
writes `exec $(BUILD)/gas/as-new "$@"` with no `.exe`, and the `test -x
"$(BUILD)/gas/as-new"` guards likewise, so pointing `BUILD` straight at a mingw
build tree fails before doing anything — the natural place for a knob
(`EXEEXT`/`RUNNER`) is the `TOOLS` wrapper loop and the guards in
`tb/Makefile`; (2) wine process startup dominates: `check` costs a few minutes,
but `isa` spawns several wine processes per table row and takes tens of
minutes — and plain `exec wine ...` wrappers are not enough for it: wine's
per-prefix service processes (`winedevice.exe` etc.) inherit the wrapper's
stdout/stderr, and a driver that captures tool output through pipes then waits
on EOF forever (two isa runs hung this way, at 0 CPU, and had to be killed;
a prewarmed `wineserver -p` did not prevent it). The wrappers that work redirect
wine's output to temp files and cat them back, so no wine descendant ever holds
the caller's pipe; with those, `isa` passes under wine (280-case table PASS,
extra table PASS). Running the testbench on a *native Windows
runner* is a different project: it needs a POSIX layer (msys2: sh, GNU make,
perl, python3, GNU coreutils, p7zip) plus the same `.exe`-suffix handling,
since the project Makefiles inside `base.7z` run perl generators and `rm`.

**GNU-isms in `tb/`:** `tb/Makefile` itself depends on GNU/gnu-adjacent tools:
`stat -c %s` (BSD stat spells it `-f %z`), `md5sum`, `sha256sum -c`, `nproc`,
`7z`, `curl`. On macos CI this works only because the workflow prepends brew
coreutils' `gnubin` to `PATH`; on a stock mac, `make -C tb build`/`check` fails
at `nproc`/`stat`/`md5sum`. The `tb/sim/*.sh` scripts are clean POSIX
(portable `sed`/`awk`, `mktemp`, no `sed -i`), so the exposure is confined to
`tb/Makefile`. Either keep the documented coreutils dependency (it is at least
enforced by CI) or spell the four offenders portably; the file and line sites
are `tb/Makefile` lines 104/106/137/139 (`sha256sum`), 153 (`nproc`), 175/205
(`stat -c`, `md5sum`).

**Matrix shape**: five builds, three run the testbench, two run `--version`.
Given §1, promoting the wine jobs from smoke to `check` (+ the cheap gates;
leave `isa` native-only if runtime matters) closes the only real coverage hole
in the matrix. There is no linux 32-bit job; §4 shows it would pass today, and
it is the only cheap way to keep the 32-bit `offsetT` configuration honest —
win32's `--version` certainly doesn't.

## 6. Where the fixes would go (none applied — review only)

1. `gas/config/tc-i51.c` `md_apply_fix`: `long value`/`long pc` → `valueT`/
   `offsetT` widths (§3a).
2. `gas/config/tc-i51.c` `check_range`: `long num` → `offsetT`, replace the
   32-bit bitmask tests with range comparisons (§3a).
3. `gas/config/tc-i51.c` `extract_op`: C `toupper` → safe-ctype `TOUPPER`
   (§3b).
4. `tb/Makefile` `build:` configure line: add `--enable-deterministic-archives`
   (§2).
5. `tb/Makefile` `TOOLS` wrapper loop + `test -x` guards: `.exe`/runner knob;
   `.github/workflows/build.yml` wine jobs: run `check` (+ gates) through wine
   wrappers instead of `--version` (§5).
6. `tb/Makefile`: portable spellings (or a documented hard dependency) for
   `stat -c`, `md5sum`, `sha256sum`, `nproc` (§5).
7. Optional, for third-party bit-reproduction: normalize/relocate the embedded
   prefix (build with a fixed `--prefix`), and give the CI `tar` invocation
   `--sort=name --mtime` (§2).

## Appendix: what was run

- Native build: `make -C tb build` (defaults). Repro/cross/m32 builds:
  out-of-tree `configure` from `work/modern/binutils-2.47` with the flag sets
  in the table above; `make -j4 MAKEINFO=true`.
- Test program: two modules exercising `acall`/`ajmp` (R_I51_11), `sjmp`
  (R_I51_7_PCREL), `lcall`/`ljmp` (R_I51_16), `#LOW`/`#HIGH` (R_I51_8_LOW/HIGH),
  `jb`/`setb` (bit relocs), archive member resolution, default-script link,
  `objcopy -O binary`.
- Testbench runs: `make -C tb check BUILD=<m32|wine64-wrappers|wine32-wrappers>`
  each with its own `WORK=`; `make -C tb branch bits reloc sim defaultlink
  commons isa BUILD=<wine64-wrappers>`.
- Probes: `mov a,#(lab2-lab1+0xFFFFFFFF+2)` (§3a);
  `jb ti, loop` under `LC_ALL=C` vs `LC_ALL=tr_TR.iso88599` (locale built with
  `localedef -i tr_TR -f ISO-8859-9`) (§3b); double `ar rc` + header dump and
  `ar rcD` (§2); `strings`/`nm -a`/absolute-path assembly/CRLF re-assembly (§2);
  double `tar czf` with and without `touch` (§2).
- Versions: GNU assembler/ld 2.47.20260726 on every build; wine-9.0;
  mingw-w64 gcc 13-win32.

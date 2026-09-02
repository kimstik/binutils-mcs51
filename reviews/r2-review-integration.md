# Integration review: build plumbing, target identity, third-party buildability

Scope: everything between `mcs51/*.patch` and a clean third-party build from the
binutils 2.47 tarball. ISA correctness, testbench and CI are out of scope.
Every claim below was verified by building, not by reading. Line numbers refer
to a 2.47 tree with both patches applied, unless the patch file is named.

Verification matrix (all on this branch, after fixes):

| check | result |
|---|---|
| `./configure --target=i51-elf && make` (stock, -Werror on) | green |
| `--disable-werror` build (tb `make build` path) | green |
| `--enable-targets=all` build of bfd+opcodes+gas+ld+binutils | green |
| out-of-tree objdir (all builds above) | green |
| `tb make check` against the fixed toolchain | 10/10 PASS |
| both patches on pristine 2.47, `patch --fuzz 0` | 0 fuzz, 0 offsets |
| host (foreign) `readelf -h` on emitted object | names the machine |
| new objdump on a 0x1051-stamped legacy object | reads it |

## HIGH — fixed

### 1. Stock configure did not build: -Werror kills the new files
The 2.47 tarball ships `development=true` (`bfd/development.sh:19`), so
`--enable-werror` is the default. A third party running plain
`./configure --target=i51-elf && make` got:

    bfd/elf32-i51.c:323:35: error: variable 'h' set but not used

and 22 more: 4 in `bfd/elf32-i51.c` (unused-but-set `h` in `check_relocs`,
unused params in `elf32_i51_object_p` and `elf32_i51_add_symbol_hook`), 19 in
`gas/config/tc-i51.c` (dead `op_start` in `extract_word`/`extract_op`, dead
`fixS *fixp` in `fixup16`/`writePcodeOperand`/the pcode 13-bit path, and
`-Wshadow` hits where locals/params named `opcode`/`oper`/`op_expr1`/`op_expr2`
shadow the file globals at tc-i51.c:363-368). Only the tb Makefile's
`--disable-werror` hid this. **Fixed mechanically** (ATTRIBUTE_UNUSED, dead-var
removal, local renames `opc`/`dop`/`ex`/`expr1`/`expr2`; `check_relocs` body was
behaviorally `return true` and now says so). Rebuilt with stock configure:
green; `tb make check` still 10/10.

### 2. e_machine was the unregistered 0x1051; the registry has EM_8051 = 165
`include/elf/i51.h` defined `EM_I51 0x1051`. That value collides with nothing —
neither a registered `EM_*` nor any binutils private value (nearest neighbours:
`EM_AVR_OLD` 0x1057, `EM_MSP430_OLD` 0x1059) — but it is unregistered, and the
official registry has had **EM_8051 = 165, "Intel 8051 and variants"** for over
a decade; 2.47 already carries it (`include/elf/common.h:282`) and every stock
readelf prints it by name. A foreign toolchain on this port's objects said:

    Machine:  <unknown>: 0x1051

**Fixed, AVR-style**: output is now `EM_8051` (`elf32-i51.c` sets
`ELF_MACHINE_CODE EM_8051`), the legacy value is renamed `EM_I51_OLD` and still
accepted on input via `ELF_MACHINE_ALT1`; readelf handles both
(`binutils/readelf.c:1286,2389,3681`). Verified: host readelf now prints
"Intel 8051 and variants"; a 0x1051-stamped object still opens as `elf32-i51`;
`tb make check` passes 10/10 — and since those projects link the
0x1051-converted 2001 libraries, the PASS itself proves read-compat.
Heads-up for the testbench owners: `tb/objects-report/REPORT.md:16` and
`tb/base2001.PROVENANCE:7` describe `e_machine=0x1051` as the port's output
format; it is now input-only. `tb/i51elf_le2be.py:39` (stamps 0x1051 into
converted inputs) stays correct as-is.

## MEDIUM — fixed

### 3. `bfd_elf32_i51_vec` used the pre-2014 vector naming
Every target vector since the 2014 mass rename is `<cpu>_<format>_vec`
(`iamcu_elf32_vec`, `avr_elf32_vec`, ...). **Renamed** to `i51_elf32_vec` in
`bfd/elf32-i51.c` (TARGET_LITTLE_SYM), `bfd/targets.c` (both lists),
`bfd/config.bfd`, `bfd/configure.ac` + regenerated `bfd/configure`. Target
strings (`elf32-i51`, emulation `elf32i51`, arch `i51`) are unchanged.

### 4. gas/Makefile.am did not list the new tc files
`TARGET_CPU_CFILES`/`TARGET_CPU_HFILES` (gas/Makefile.am:144,219) list every
other target's `tc-*.c/h`; `tc-i51.*` were missing, so they were absent from
`POTFILES` (gas/Makefile.am:370) and `EXTRA_as_new_SOURCES`. **Fixed** in
Makefile.am and Makefile.in. Note on `make dist`: binutils has no automake dist
at all — `make distdir` errors out ("No rule to make target"), releases are cut
by `src-release.sh` tarring the whole tree — so the practical impact was NLS
string extraction and convention, not tarball content.

### 5. Checked-in generated po lists had no i51 entries
`bfd/po/SRC-POTFILES.in` (cpu-i51.c, elf32-i51.c), `gas/po/POTFILES.in`
(config/tc-i51.c/.h), `opcodes/po/POTFILES.in` (i51-dis.c),
`ld/po/BLD-POTFILES.in` (eelf32i51.c) — all missing, i.e. the patch edited some
generated files (Makefile.in, configure) but not these. Invisible under
`--disable-nls`; with NLS on, the new files' strings are never extracted.
**Fixed** with sorted insertions.

## LOW — fixed

### 6. Entries parked in the wrong blocks of sorted lists
- `bfd/config.bfd`: the `i51-*-*` stanza sat at the top of the CPU-sorted case
  list, before `am33_2.0`. Moved to the i-section, before `ia16-*-elf` (now
  config.bfd:647).
- `ld/Makefile.am`/`Makefile.in`: `eelf32i51.c` sat between `eelf_iamcu.c` and
  `eelf_s390.c`, i.e. inside the `eelf_*` x86 block. Moved into the `eelf32*`
  block before `eelf32ip2k.c`; the `.Po` dependency line in Makefile.in moved
  to match. (gas/ld `configure.tgt` placement is within those files' loose
  ordering; left alone.)

## INFO — verified, no change

### 7. Triplet name: `i51` works, but it lives on a config.sub fork
`config.sub` is imported from gnu-config; the patch's `| i51 \` hunk
(modifications.patch, config.sub:1320) is a local fork of an upstream-owned
file and will be lost on any config.sub refresh. Pristine 2.47 config.sub
already recognises **`c8051`** (line 1290; `c8051-*)` defaults to `obj=elf` at
1778) — that is gnu-config's registered name for this CPU. `mcs51-elf` and
`8051-elf` do not canonicalise at all. Behaviour as patched, verified:
`i51-elf` → `i51-unknown-elf`, bare `i51` → `i51-unknown-none`, both matched by
the `i51-*-*` patterns in bfd/config.bfd, gas/configure.tgt:228,
ld/configure.tgt:323. Verdict: `i51` is defensible (2001 lineage; consistent
`bfd_arch_i51` / `elf32-i51` / `elf32i51` family) as long as the port ships as
a patch; if the config.sub fork ever becomes a problem, `c8051-elf` is the
zero-fork alternative. Not changed.

### 8. Generated-file consistency proven
Ran bfd `make headers` (chew): regenerated `bfd-in2.h`/`libbfd.h` are
byte-identical to the patch's hand edits, so `reloc.c`/`archures.c` and the
generated headers agree. Patch hunk order applies `Makefile.am` before
`Makefile.in` and `configure` before `configure.ac`, and release trees have
maintainer mode off, so no autotools rerun is triggered on a third-party host.

### 9. Residual nits, deliberately left
- `bfd_arch_i51` is inserted mid-enum (bfd-in2.h:1470), renumbering every later
  `bfd_arch_*` relative to stock binutils. Source-consistent; only matters if
  someone mixes this port's headers with a stock libbfd binary.
- `bfd_elf_i51_final_write_processing` (elf32-i51.c:585) sets `e_machine` by
  hand; redundant with `ELF_MACHINE_CODE` but harmless.
- emulparams `MAXPAGESIZE=0x0800` vs `#define ELF_MAXPAGESIZE 1`
  (elf32-i51.c:920): inconsistent-looking; the generic template does not
  consult the emulparams value. Left for the ISA/linker reviewers.

## README.md — corrected
"Compiler-independent weak symbols ( __gsinit_startup, ... )" was wrong twice:
they are not weak symbols but `PROVIDE`d link-time defaults, and the port
uppercases symbols, so the real names are `__GSINIT_STARTUP`,
`__EXTERNAL_STARTUP`, `__INIT_DATA`, each defaulting to a shared `RET`
(elf32i51.sc:64-75). Rewritten, and the README now states the 2.47 base, how to
apply/configure (stock configure now works), the target identity, and the
EM_8051 / legacy-0x1051 story.

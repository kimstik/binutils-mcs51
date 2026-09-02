# Review: the delta `origin/main..origin/work/green` in `mcs51/`

Scope: only what the port gained on top of `origin/main`
(`git diff origin/main origin/work/green -- mcs51/`). The pre-existing opcode
table, howto sizes, endianness and the ACALL/AJMP paging work were covered in an
earlier round and are not re-audited here.

Line numbers are for the reconstructed sources, i.e. the tree `tb/Makefile`'s
`make build` produces at `work/modern/binutils-2.47/`. The patch files carry the
same text with a `+` prefix.

Verification: `make build` (binutils 2.47, `-O0`), then
`tb/sim/run-defaultlink.sh`, `tb/sim/run-commons.sh`, `tb/isa_check.py` (both
tables), `tb/sim/run-branch.py` and `make check` (all ten reference ROMs) —
before and after every change made below.

---

## 1. `add_symbol_hook` silently discards the contents of a real input section (HIGH)

`bfd/elf32-i51.c:897-936`. The hook maps `SHN_I51_*` onto a common section with

```c
*secp = bfd_make_section_old_way (abfd, ".rbss");
(*secp)->flags |= SEC_IS_COMMON;
```

`bfd_make_section_old_way` returns the **existing** section when the input BFD
already has one of that name, so `SEC_IS_COMMON` is OR-ed onto a real data
section. `bfd_is_com_section()` is just `flags & SEC_IS_COMMON`, so the linker
then treats that section as a common placeholder and never copies its contents.

Not exotic input: `.rbss .bbss .ibss .xbss .ebss .bitbss .regbank` are exactly
the names gas emits (`gas/config/tc-i51.c:107,2092` and the sibling directives)
and exactly the names the shipped linker script collects
(`ld/scripttempl/elf32i51.sc:92,105,…`). One object holding both a real `.rbss`
section and one `.rcomm` is enough.

Reproduction, the port's own gas and its own default script:

```
        .section .rbss,"aw",@progbits
RREAL:  .byte 0x11,0x22,0x33,0x44
        .rcomm RCVAR,4,1          ; <- remove this line and the data survives
```

with the `.rcomm`:    `Contents of section .rbss: 0002 00000000 00000000`
without the `.rcomm`: `Contents of section .rbss: 0002 11223344`

Silent data loss, no diagnostic, exit status 0.

MIPS — which this code is copied from — avoids it by naming its fake common
section `.scommon` (`bfd/elfxx-mips.c:7195`), a name no real section uses. The
fix is the same idea: give the seven commons private section names
(`.rcommon`, `.bcommon`, …) and teach `elf32_i51_section_from_bfd_section`
(`bfd/elf32-i51.c:681`), `elf32_i51_symbol_processing` (`:766`), gas's `md_begin`
fake sections (`gas/config/tc-i51.c:571-633`) and the linker-script wildcards
about them.

**Not applied** — a coordinated rename across bfd, gas and the ld script, well
past "small and clearly correct", and it needs its own test.

## 2. `ld -r` degraded every memory-space common to a plain common (HIGH) — FIXED

`bfd/elflink.c:10941` writes a common out as
`sym.st_shndx = bed->common_section_index (input_sec)`, and the port defined
neither `elf_backend_common_section_index` nor
`elf_backend_link_output_symbol_hook`, so the default
`_bfd_elf_common_section_index` (`bfd/elflink.c:15501`) returned `SHN_COMMON` for
all of them.

Before:

```
$ as-new -o com.o com.s ; readelf -s com.o
   5: ... PRC[0xff01] RCVAR
   6: ... PRC[0xff06] BITVAR
$ ld-new -r -o com_r.o com.o ; readelf -s com_r.o
   7: ... COM BITVAR      <- space lost
   9: ... COM RCVAR       <- space lost
```

A bit common that comes back as `COM` is allocated by the next link in
byte-addressed `.bss` and then carries a byte address where the B2B relocation
expects a bit address — precisely the failure `tb/sim/run-commons.sh` describes,
which that probe cannot see because it never runs `-r`. So "memory-space commons
keep their processor section index" held for a one-shot link only.

**Applied**: `elf32_i51_link_output_symbol_hook` (`bfd/elf32-i51.c:949`,
registered at `:1003`), mirroring `_bfd_mips_elf_link_output_symbol_hook`
(`bfd/elfxx-mips.c:8063`): when a symbol reaches output as `SHN_COMMON` and its
`input_sec` is one of the space sections, the processor index is put back. After
the fix `-r` shows `PRC[0xff01]` / `PRC[0xff06]` again, and plain `.comm` still
comes out `COM`.

Related, **not** applied: `elf_backend_common_definition` is still the generic
one (`bfd/elflink.c:15495`), so `bed->common_definition(isym)` is false for
`SHN_I51_*` at `bfd/elflink.c:5021`. Consequences: these symbols get `BSF_GLOBAL`
where a plain common gets none (`:5059`), and their alignment comes from
`new_sec->alignment_power` instead of `st_value` (`:5415`). Overriding it is the
MIPS answer (`_bfd_mips_elf_common_definition`, `bfd/elfxx-mips.c:16660`), but it
also routes these symbols through `info->inhibit_common_definition`, which turns
them into `SHN_UNDEF`. That interaction needs testing before it is changed.

Also: `ldscripts/elf32i51.xr` is 20 bytes — `elf32i51.sc:14` does
`test -z "${RELOCATING}" && exit 0`, so a relocatable link has no section map at
all and everything lands as an orphan. It works, but the port's memory-space
grouping is not applied to `-r` output.

## 3. Default linker script: RAM sections did not chain, so they overlapped (HIGH) — FIXED

`ld/ldlang.c:6216-6263`: an output section with no address expression takes
`os->region->current`, **not** the running dot; and `ld/ldlang.c:6454` only
updates `region->current` for sections with `SEC_ALLOC|SEC_LOAD`. Every RAM
section in this script is `(INFO)`, i.e. non-alloc, and only some of them carried
an address expression — so the ones that did not got whatever the last allocated
section left behind.

Measured with the shipped script, before the fix:

| probe | result |
|---|---|
| all RAM sections empty | `__RDATA_START = 0x07` (end of `.text`), `__BIT_START = 0xffffff38` |
| `.text` 4 bytes, `.regbank` 8 bytes | `.regbank` 0x00-0x07 and `.rdata` **0x04**-0x05 — overlapping the register bank |
| `.data` 3 bytes at 0x24, `.bss` 5 bytes | `.bss` 0x27-0x2b and `.idata` **0x27** — overlapping, and `__DATA_END`(0x2c) > `__IDATA_START`(0x27) |

`__BIT_START = 0xffffff38` comes from
`.bit ((ADDR (.bbss) + SIZEOF (.bbss) - 0x20) * 8)` (`elf32i51.sc:117`)
evaluating on an `ADDR(.bbss)` that had been pulled below 0x20. None of the
`ASSERT`s at `elf32i51.sc:206-213` catch any of it: they are all guarded by
`SIZEOF(...) == 0`.

"pin empty `.regbank` so its 0x00 anchor always holds" only pinned the
`__REGBANK_START` symbol; the anchor did not propagate to anything after it.

**Applied**: the explicit-address idiom the script already uses for `.bdata`,
`.bit` and `.data`, extended to the nine sections that lacked one — `.rdata`,
`.rbss`, `.bbss`, `.bitbss`, `.bss`, `.idata`, `.ibss`, `.xbss`, `.ebss` now read
`ADDR (prev) + SIZEOF (prev)` (`elf32i51.sc:86,92,…`). After the fix, on the same
three probes: `.rdata` 0x08 (after the 8-byte register bank), `.idata` 0x2c
(after `.bss`), and with everything empty `__RDATA_START = __BIT_START = 0`.

`make check` still reproduces all ten reference ROMs byte for byte; the projects
use their own script, so this only changes the built-in one.

## 4. Bit-address boundaries were off by one at the top of the RAM bit space (MEDIUM) — FIXED

Bit-addressable RAM is 0x20-0x2F → bit addresses 0x00-**0x7F**; 0x80 is already
`P0.0`. Both B2B paths accepted 0x80:

- `gas/config/tc-i51.c:894` (new in this delta): `if ((value - 0x20) * 8 + off > 0x80)` → now `>= 0x80`
- `gas/config/tc-i51.c:1641` (constant path): same `> 0x80` → now `>= 0x80`
- `bfd/elf32-i51.c:398`: same `> 0x80` → now `>= 0x80`

The SFR arm was worse. `gas/config/tc-i51.c:900` accepted any `value` in
0x80-0xFF and emitted `value + off`, so `B2B(0x85,3)` — 0x85 is `DP1L`, not
bit-addressable — silently produced 0x88, a bit of a *different* SFR; and
`value + off` past 0xFF was truncated by the cast. Bit-addressable SFRs are
exactly 0x80,0x88,…,0xF8, so the arm is now
`value >= 0x80 && value <= 0xF8 && (value & 7) == 0` and anything else falls into
the existing "not bit addressable" diagnostic. `bfd/elf32-i51.c:399` got the
matching `(srel & 7) != 0` guard.

`bfd/elf32-i51.c:394` also returned `bfd_reloc_ok` for `srel >= 0x100` — "skip
transformation for out-of-range addresses", i.e. leave the raw offset byte in the
image and report success. Now `bfd_reloc_outofrange`.

Boundaries re-verified after the change (`d2` = SETB):

```
SETB 0x20.0 -> d2 00     SETB 0x2F.7 -> d2 7f
SETB 0x80.0 -> d2 80     SETB 0xF8.7 -> d2 ff     SETB 0xD0.7 -> d2 d7
```

Still unchecked anywhere: `b2b_offset` is only validated `>= 0`
(`gas/config/tc-i51.c:1218,1377`), never `<= 7`.

## 5. `fold numeric .bit suffix` and `/C`: correct (INFO)

`gas/config/tc-i51.c:450-475`. The map is right at every boundary — see the
encodings above. `0x1F.0`, `0x30.0`, a non-multiple-of-8 SFR base and `0x100.0`
all produce "is not bit addressable". A multi-digit suffix (`0x20.10`) consumes
`.1` and leaves `0`, which `md_assemble` rejects as "garbage at end of line" —
noisy, not silent.

Two nits: on the error path the function returns without consuming the `.N`, so
one bad operand produces a second, confusing follow-on error; and the fold is
skipped whenever `X_op != O_constant`, which is fine for `.set` symbols (expr.c
folds absolute symbols to `O_constant` first) but leaves `.N` in the stream for a
relocatable one.

`{"/C", '/', 0xD7}` (`gas/config/tc-i51.c:179`) is right: CY is PSW.7, PSW is
0xD0, bit address 0xD7. The `op2mode == '/'` arm added at `:1448` is what
actually delivers it. In the disassembler the `'/'` case for `args[1]`
(`opcodes/i51-dis.c`) now consumes the operand byte instead of printing a bare
`/C` and desynchronising the decode — correct, the insn is two bytes
(`include/opcode/i51.h:57,124`).

## 6. `md_undefined_symbol` off the shared state: correct and complete (INFO)

`gas/config/tc-i51.c:1065-1089` now uses `symop`/`symoper` locals. `expression()`
is called from `i51_parse_operand1` (`:1198`) and `i51_parse_operand2`
(`:1358,1394`) with the globals `op`/`oper` live, so this was a real re-entrancy
bug. Nothing else in the function touches shared state, and no other
`expression()` caller in the file relies on `op`/`oper` surviving. Complete.

`i51_local` (`:1027`) and `i51_common` (`:1828`) changing `const char *name` to
`char *name` is required by `get_symbol_name (char **)`; and
`i51_common:1840-1844` now takes the symbol before `restore_line_pointer` writes
the delimiter back over the terminating NUL, which is the right order.

`cast offsetT diagnostics to long` is complete for `tc-i51.c` — every `%ld` has a
`(long)` and the remaining `%d`/`%x` all take `int`/enum arguments. But
`check_range (long num, int mode)` (`:1580`) and `long value` in `md_apply_fix`
(`:779`) still take `offsetT`/`valueT` by narrowing conversion. On LP64 that is
lossless; on the LLP64 host the CI cross-builds for (mingw, wine smoke) `long` is
32 bits and the value is truncated before it is range-checked. The cast pass
fixed the format-string mismatch, not the truncation.

The K&R → ANSI conversion itself is mechanical and I found no behaviour change in
it: no argument-order slips, no implicit `int`, no `void` vs no-arg change that
matters (`md_begin ()` → `md_begin (void)`, `i51_cleanup ()` → `(void)`, both
already prototyped at the top of the file). The dead code it dropped —
commented-out `i51_set`, debug `fprintf`s, dead `bfd_getb8` comments — is not
referenced anywhere.

## 7. Smaller items (LOW)

- `bfd/elf32-i51.c:304-334` — `elf32_i51_check_relocs` is entirely dead: the loop
  computes `h` and discards it (gcc says so: `warning: variable 'h' set but not
  used`). The "drop dead code" pass missed the largest piece of dead code in the
  file.
- `bfd/elf32-i51.c:735-761` — the seven `i51_elf_*com_symbol_ptr` statics are
  assigned in `elf32_i51_symbol_processing` and never read. Harmless
  (`symbol_ptr_ptr` is NULL for `bfd_com_section_ptr` too), but dead.
- `bfd/elf32-i51.c:766-893` — those lazily built fake sections skip the
  `gc_mark = 1` and `id` that `BFD_FAKE_SECTION` sets (`bfd/section.c:726`).
  Display-only path, so no observed effect with `elf_backend_can_gc_sections 1`,
  but a divergence from the template.
- `include/elf/i51.h:53-66` — the comment justifying `SHN_LORESERVE + n` claims a
  behavioural fix. `SHN_LORESERVE` is 0xFF00, so the values are numerically
  identical to the old `0xff00..0xff06`; the change is cosmetic and the comment
  overstates it.
- `gas/config/tc-i51.c:866-883` — the new ACALL/AJMP 2K-page check computes
  `pc = fx_frag->fr_address + fx_where + 2`, a *section* offset. Exact only while
  `.text` is linked at 0 (which the default script does). For a literal target in
  a section placed elsewhere it can both miss real errors and invent false ones;
  the linker-side check (`bfd/elf32-i51.c:375`) does it properly with
  `output_section->vma`. Reached only for constant targets — a symbolic one keeps
  its reloc.
- `gas/config/tc-i51.c:1591` — `check_range` for `I51_OP_JUMP_INPAGE` is now a
  plain 16-bit range test and the diagnostic at `:1715` says "16-bit range".
  Consistent with moving the page check into `md_apply_fix`, but the function's
  `I51_OP_JUMP_INPAGE` label no longer describes what it does.
- `gas/config/tc-i51.c:1755` and `:2361` — `fixS *fixp` assigned and never used.
- `gas/config/tc-i51.c:558` — `extern int symbols_case_sensitive;` declared inside
  `md_begin` rather than pulled from `symbols.h`.
- `gas/config/tc-i51.c:2058` — `S_SET_ALIGN (symbolP, temp)` uses `temp` *after*
  the power-of-two loop at `:1891` has shifted it down to 1, so every external
  common is written with alignment 1 whatever was asked for. Pre-existing, but it
  sits in the middle of the commons machinery under review; `align` is the value
  that was computed for this.
- `gas/config/tc-i51.c:1915` masks `common_segment & 0x7F`, `:2060` does not, and
  neither switch has a `default:` — an out-of-range value leaves the symbol's
  segment untouched instead of erroring.
- `ld/scripttempl/elf32i51.sc` — every RAM space is `(INFO)`, so `.data` and the
  other initialized RAM sections are not in the ROM image (`objcopy -O ihex`
  emits `.text` only; confirmed). Nothing carries initializers into flash for a
  startup copy loop, so initialized RAM data cannot reach the device. A design
  gap in the "links the port's own output" claim, not a bug in the script text.
- `bfd/elf32-i51.c:407-423` — `R_I51_13_PCODE` truncates a target above 0x1FFF
  (`srel &= 0x1FFF`) instead of reporting overflow, while gas
  (`gas/config/tc-i51.c:909-917`) only diagnoses underflow. The two ends disagree
  about the top of the range.

## 8. The uppercase weak-symbol problem: resolved (INFO)

gas sets `symbols_case_sensitive = 0` (`gas/config/tc-i51.c:559`), so source that
writes `__gsinit_startup` produces `__GSINIT_STARTUP`, and `elf32i51.sc:73-75`
provides the upper-case names. The hooks bind to a real `RET`
(`elf32i51.sc:65-66`) instead of the old `PROVIDE_HIDDEN (… = 0)`, so an
unprovided hook is a no-op call rather than a jump into the reset vector.
Verified: `__GSINIT_STARTUP == __I51_RET`, ROM ends `… 22`.

The overlapping-VMA problem is resolved by construction, not papered over:
because every RAM space is non-alloc, ld's overlap check does not apply to them,
which is what lets `.xdata` and `.text` both start at 0. The overlaps that *did*
exist were finding 3 — between RAM sections of the *same* space, where the check
would not have fired either.

---

## Changes applied in this branch

All to `mcs51/additions.patch`:

1. `ld/scripttempl/elf32i51.sc` — explicit `ADDR (prev) + SIZEOF (prev)` on
   `.rdata .rbss .bbss .bitbss .bss .idata .ibss .xbss .ebss` (finding 3).
2. `bfd/elf32-i51.c` — new `elf32_i51_link_output_symbol_hook` and its
   `#define elf_backend_link_output_symbol_hook` (finding 2).
3. `bfd/elf32-i51.c` / `gas/config/tc-i51.c` — B2B bit-address bounds
   (finding 4).

After the changes: `make build` clean, `run-defaultlink.sh` PASS,
`run-commons.sh` PASS, `isa_check.py` 280/280 + 3/3 PASS, `run-branch.py` 24/24
PASS, `make check` — all ten reference ROMs identical.

Finding 1 is left unfixed and is the one to take next.

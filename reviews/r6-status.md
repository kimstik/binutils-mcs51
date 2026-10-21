# R6 status: what became of each finding

Fixes are on branch `claude/r6-fixes`. Every CRITICAL item below was re-run
from its original repro against the fixed toolchain (`r6-repro/`), and each
has a DejaGnu test in `gas/testsuite/gas/i51` or `ld/testsuite/ld-i51` that
fails on the toolchain before the series. The gate - now sixteen stages,
with `dejagnu` added - passes, and the ten reference ROMs are byte-identical.

## CRITICAL (numbering of `r6-summary.md`)

| # | finding | status | test |
|---|---------|--------|------|
| 1 | `jmp lbl` → `jmp @A+DPTR` | fixed: whole-operand matching; `jmp`/`call` are the long forms | gas `jmp-call`, `operands-bad` |
| 2 | fallback to the last table row (`add 0x45,#0x5a`, `movx 0x45,a`, …) | fixed: no row fits → error | gas `operands-bad` |
| 3 | absolute branch targets resolved in gas | fixed: relocation to the linker | gas `branch-abs`, ld `abs-branch` |
| 4 | branch to a weak symbol of the same section | fixed | gas `branch-weak`, ld `weak` |
| 5 | forward references skip range checks | fixed | gas `range-fwd` |
| 6 | `HIGH()`/`LOW()` swallow the rest of the expression | fixed: they are expression operators | gas `high-low` |
| 7 | `HIGH()`/`LOW()` on a bit operand dropped | fixed: refused | gas `operands-bad` |
| 8 | text after the last operand assembled | fixed: junk is an error | gas `trailing` |
| 9 | `ARn` keeps the first `.using` | fixed: evaluated at each use | gas `regbank` |
| 10 | `.pcode` symbol forms differ from constants | fixed: `@BYTE` via addend, `#SWAP` low byte first | gas `pcode` |
| 11 | merged strings addressed by old offset | fixed: `_bfd_elf_rela_local_sym` | ld `merge` |
| 12 | `srel == 0` hack | removed | ld `b2b0` |
| 13 | 8-bit bit, 16-bit code, HIGH, page bit 16 overflow | fixed | ld `overflow`, `page` |
| 14 | relocations carry no address space | fixed: the linker checks the target's space | ld `space` |
| 15 | direct RAM past 0x7F across files | fixed: linker check + script ASSERT | ld `ram80`, `ramfull` |
| 16 | space common bound to another space | fixed, for definitions too | ld `commdef`, gas `comm-bad` |
| 17 | initialized RAM data dropped | refused at link: nothing loads RAM | ld `init` |
| 18 | `.rdata` over bank 0 | bank 0 always reserved | ld `bank0` |
| 19 | no stack reserved | `__STACK_SIZE` kept, `__IRAM_SIZE` checked | ld `stack`, `stack-ok` |
| 20 | `.eeprom` unbounded | `__EEPROM_SIZE` | ld `eeprom` |
| 21 | `objcopy` without `-j` overlays spaces (www51.sc) | not a tool defect: that script places every space at LMA 0 and is linked with `--no-check-sections`; the default script never does; documented | - |
| 22 | `strip` moves `.text` (www51.sc) | same cause as 21; documented | - |
| 23 | `.local` replaced; local commons impossible | `.local` is ELF's again; symbols shadow built-in names | gas `shadow`, `comm` |
| 24 | `.ds n` reserves 2n | **kept**: the ten projects rely on it (`mac_gateway: .ds 3` is a 6-byte MAC); documented, `.ds.b` reserves bytes | - |

## HIGH / MEDIUM

| finding | status |
|---------|--------|
| `--emit-relocs` addends | fixed (`rela_normal`), ld `emit` |
| "internal error" for user errors | gone: standard overflow / range messages |
| no DWARF | `as -g`, `.loc`, `addr2line` work (`R_I51_32`), ld `dwarf` |
| disassembler short read | fixed, gas `truncated` |
| `nm` `?` for RAM symbols | `d` now, ld `nm`; `.idata` → `i` is the generic PE table, documented |
| `size` sums spaces | `size` counts the image (code); documented |
| B2B on a byte operand, `.N` on any operand, negative direct/bit | refused, gas `operands-bad`, `range-fwd` |
| `PSW.n`, `IE.n`, … , `F1` missing | `NAME.N` for every bit-addressable SFR; `F1` added, gas `bitnames` |
| register names in expressions | refused, gas `names-bad` |
| labels named like SFRs | a program's symbol shadows the built-in name; use-then-define is refused |
| `.pcode` error recovery, keyword case | fixed, gas `pcode-bad` |
| alignment of space commons dropped | warned; the field cannot be honoured without moving existing links |
| SHF codes tested as bits | `SHF_I51_*` field compared whole |
| page size mismatch | emulparams no longer states one |
| `$` separator / dollar labels | `$` only separates statements, gas `separator` |
| `.using` literal only | absolute expression |

## Testbench / CI

| finding | status |
|---------|--------|
| gate never asserts rejection | DejaGnu suites in the gate (`dejagnu` stage) |
| link tests only with `--defsym` | ld-i51 links real sections of every space |
| released binaries not gated | Linux release builds run the whole gate on the shipped binaries; macOS runs check, isa, dejagnu |
| Windows probe passes without relocation | probe targets nonzero addresses |
| `-march=haswell` | dropped |
| mutation scope misses the parser | scope covers parser, operators, spaces, commons, `.pcode`, space checks |
| actions by tag, no `permissions` | pinned by commit; `contents: read` everywhere but publishing |
| archives not reproducible | commit time, sorted entries, no owner, `gzip -n`, `zip -X` |
| `check` goldens produced by the port | unchanged: `oracle` pins the 2001 images independently |

## Idioms

Done: standard symbol resolution in `relocate_section`, generic overflow
for the relocations whose field is the value, one table for the space
commons in bfd and gas, `s_comm_internal`, table-driven space directives,
`md_parse_name` instead of a private operand scanner, `ieee_md_atof`, no
global parse state, dead hooks and relocations removed, GNU comments,
GPLv3+ headers, NEWS entries, DWARF.sc.

Not done, by decision: the AT89S8252 SFR names stay built in (code of this
lineage uses them; a program can shadow any of them); the disassembler keeps
its branch text, which the round-trip tests read; the `ld -r` script stays
empty, which links as orphans and is what the commons tests exercise.

## Upstream

Still needed outside this repository: copyright assignment or DCO from each
author, and the `config.sub` entry through config-patches@gnu.org.

# Audit: `origin/claude/integrate-round2` (8c9a641) -> `origin/work/green` (afee4a5)

The owner rewrote `work/green` into three commits on top of `deeb785`, the merge
base the seven review branches also started from. The rewrite is not a descendant
of the integration. This file accounts for every difference.

```
$ git merge-base origin/work/green origin/claude/integrate-round2
deeb7858acc6db76effac64186f7c262bde47a60

$ git log --oneline origin/work/green -4
afee4a5 ci: build, gate and frozen workflows
93270ae tb: pinned references on original inputs, full gate suite, mutation harness
c907fad mcs51: the port on 2.47, both review rounds applied
deeb785 elf32-i51: add_symbol_hook takes a non-const Elf_Internal_Sym
```

## Verdict, one line

**No established fix was lost.** All twelve named fixes are present, byte for byte,
in `mcs51/additions.patch` on green. The 322-line delta is one new fix (memory-space
sections vs. real sections) plus the de-duplication it enabled; the net is negative
because twenty copies of a six-line boilerplate collapsed into one helper.

Two defects found, neither a lost fix:

1. `mcs51/additions.patch` carries **stale `index` blob hashes** for the two files
   the rewrite edited. Round2 commit `8e2665a` had refreshed exactly these; the
   rewrite re-introduced the staleness. Cosmetic under `patch -p1`, which is how
   `tb/Makefile` applies it.
2. `tb/frozen.expect` and `tb/frozen-report.md` were **not regenerated** although
   both of their inputs (`tb/base.7z` reference ROMs, `tb/base2001.7z` linker
   script) changed under them. Their tables still quote the pre-rewrite ROM sizes.
   `.github/workflows/frozen.yml` gates on `frozen.expect`.

## Every changed file

```
$ git diff --stat origin/claude/integrate-round2 origin/work/green
 AUDIT-green-honesty.md | 364 ----   AUDIT-isa-gate.md      | 627 ----
 AUDIT-provenance.md    | 238 ----   INTEGRATION.md         | 443 ----
 REVIEW-integration.md  | 141 ----   REVIEW-newcode.md      | 308 ----
 ROOTCAUSE-rom-delta.md | 338 ----   TESTS-mutation.md      | 293 ----
 mcs51/additions.patch  | 322 ++---  tb/Makefile            |  15 +-
 tb/base.7z             | Bin 140209 -> 140018   tb/base2001.7z | Bin 27907 -> 27900
 tb/reference.md5       |  21 ++     tb/sim/run-commons.sh  | 375 +++-
 14 files changed, 527 insertions(+), 2958 deletions(-)
```

| File | Change | Verdict |
|---|---|---|
| `mcs51/additions.patch` | 4684 -> 4614 lines. `bfd/elf32-i51.c` 983 -> 989, `gas/config/tc-i51.c` 2644 -> 2568. Seven other embedded files byte-identical. | **New fix + refactor. No fix dropped.** One regression: two stale `index` lines. |
| `tb/base.7z` | `lib/www51.sc` uncomments `*(reset_network)`; all ten `projekt/*/www8051.rom` regenerated. Nothing else. | **Fix.** ROMs now carry `reset_network`; 8/10 hit the 2001 length exactly, the other two explained. |
| `tb/base2001.7z` | `lib/www51.sc` only, same one-line change. | **Fix**, consistent with base.7z. |
| `tb/reference.md5` | New, 21 lines: 11 comment lines + 10 pinned `name size md5` lines. | **New gate.** Matches the archive exactly; cannot drift silently. |
| `tb/sim/run-commons.sh` | 108 -> 475 lines. Five new probes with 28 real assertions. | **New test, genuinely asserting.** Covers exactly the new `additions.patch` code. |
| `tb/Makefile` | +6 in `check` (pin enforcement), -5 in `oracle` (the in-tree `sed` repair, now redundant), +3 comment. | **Net gain.** Every gate stage still invoked. One stale comment left behind. |
| 8 `*.md` review reports | Deleted | Out of scope, reports only. |

## The twelve named fixes

Each verified by grep/extract against `green.patch` = `git show origin/work/green:mcs51/additions.patch`.
`base.patch` = the same file at the merge base `deeb785`, i.e. before the review rounds.

| # | Fix | Status | Evidence |
|---|---|---|---|
| 1 | howto `size` is a byte count, not log2 | **PRESENT** | `grep -c "size in bytes"` -> base 0, r2 12, green 12. `R_I51_16` has `2, /* size in bytes */`, `R_I51_8` has `1`; base had `1` and `0` with the old `/* size (0 = byte, 1 = short, 2 = long) */` comment. |
| 2 | big-endian 16-bit reloc application | **PRESENT** | `grep -c bfd_getb16` -> base 2, r2 5, green 5; `bfd_putb16` -> base 2, r2 6, green 6. Applied in `R_I51_11`, `R_I51_13_PCODE`, `R_I51_16` and the three gas fixups. |
| 3 | howto index bounds check in `elf32_i51_relocate_section` | **PRESENT** | `grep -n "r_type >= "`: base has only line 343 (`i51_info_to_howto`); r2 and green both add line 528 `if (r_type < 0 \|\| r_type >= (int) R_I51_max)` followed by `_bfd_error_handler`, `bfd_set_error`, `return 0`, immediately before `howto = elf_i51_howto_table + r_type;`. |
| 4 | ACALL/AJMP page checks | **PRESENT** | bfd side, `case R_I51_11`: `if (((srel ^ (rel->r_offset + ... + 2)) & 0x0000F800l) != 0) return bfd_reloc_overflow;`. gas side, `case BFD_RELOC_I51_11`: `if (((value ^ pc) & 0xF800) != 0) as_bad_where (... "ACALL/AJMP target 0x%lx is not in the same 2K page as 0x%lx" ...)`. |
| 5 | disassembler `mov direct,direct` operand order | **PRESENT** | `opcodes/i51-dis.c`, operand-2 `case 'B': case 'D':` ends with `if (opcode->args[0] == 'D')` and a three-`strcpy` swap, comment `MOV direct,direct (0x85) is the one insn that encodes the source byte first`. Opcode table entry `I51_INS ("mov", "DDN", 0x03, ..., 0x85, 0xFF)` selects it. Absent from base. |
| 6 | `anl/orl C,/bit` decoding | **PRESENT** | Operand-2 `case '/':` now reads a byte (`i51dis_opcode`, `addr++`, `offset++`) and prints `/0x%02X`. Base printed the literal string `"/C"` and consumed no operand byte. Table entries `anl "r/N" 0xB0` and `orl "r/N" 0xA0`. |
| 7 | 0x7E/0x7F displacement sign | **PRESENT** | Three copies (operand 1, 2, 3) of `disp = ((opdata ^ 0x80) & 0xFF) - 0x80;` with the comment `testing bit 7 of (displacement + insn length) turns the largest forward branches into backward ones`. Base tested `rel_addr = opdata+2; if (rel_addr & 0x80)`. `grep -c "Sign-extend the encoded"` -> base 0, green 3. |
| 8 | B2B bounds 0x80..0xF8 step 8 | **PRESENT** | bfd `case R_I51_8_B2B`: `if (srel >= 0x100) return bfd_reloc_outofrange;` / `if (srel < 0x20) return bfd_reloc_outofrange;` / `if ((srel >= 0x30) && ((srel < 0x80) \|\| (srel & 7) != 0)) return bfd_reloc_outofrange;`. gas `BFD_RELOC_I51_8_B2B`: `else if (value >= 0x80 && value <= 0xF8 && (value & 7) == 0)`. |
| 9 | `elf32_i51_link_output_symbol_hook` | **PRESENT** | green.patch:987 defines it, :1042 `#define elf_backend_link_output_symbol_hook elf32_i51_link_output_symbol_hook`. Absent from base (`grep -n link_output_symbol_hook base.patch` -> nothing). Body restores the processor-specific `st_shndx` for `SHN_COMMON` symbols whose input section names a memory space. |
| 10 | default script chaining via `ADDR(prev)+SIZEOF(prev)` | **PRESENT** | `ld/scripttempl/elf32i51.sc`: `.rdata (ADDR (.regbank) + SIZEOF (.regbank))`, `.rbss (ADDR (.rdata) + SIZEOF (.rdata))`, `.bdata MAX (0x20, ADDR (.rbss) + SIZEOF (.rbss))`, ... `.ebss (ADDR (.edata) + SIZEOF (.edata))` — 12 chained sections plus two `ASSERT`s on `__BDATA_END` / `__BIT_END`. |
| 11 | `EM_8051` with `ELF_MACHINE_ALT1` accepting 0x1051 | **PRESENT** | `#define ELF_MACHINE_CODE EM_8051`, `#define ELF_MACHINE_ALT1 EM_I51_OLD`, `#define EM_I51_OLD 0x1051` in `include/elf/i51.h`, and `elf_elfheader (abfd)->e_machine = EM_8051;` in the object-writer. |
| 12 | `i51_elf32_vec` naming | **PRESENT** | `#define TARGET_LITTLE_SYM i51_elf32_vec`. Base had `bfd_elf32_i51_vec`. |

`-Werror` cleanliness: not re-provable without a build, and `tb/Makefile` configures
with `--disable-werror` in both the `frozen` and `build` targets, so no gate in this
repository would catch a regression. Textually, the only code green adds over round2
is five regions; all declare and use every local, and every unused parameter carries
`ATTRIBUTE_UNUSED` (`i51_elf_fake_sections` now takes `Elf_Internal_Shdr *shdr
ATTRIBUTE_UNUSED, asection *asect ATTRIBUTE_UNUSED`). The old `flagword applicable;`
declaration in `i51_common` was removed together with both of its uses — `grep -n
applicable` over the extracted `tc-i51.c` returns only the two lines inside the new
`i51_space_section` helper, so nothing references a now-undeclared variable.

## `mcs51/additions.patch`: what the 322 lines actually are

The delta touches 24 hunks, all of them inside two of the nine embedded files:

```
$ grep -n "^@@" add.delta | head -4
5:@@ -51,7 +51,7 @@       (elf32-i51.c line count 983 -> 989)
14:@@ -665,43 +665,37 @@     i51_elf_section_from_shdr / i51_elf_fake_sections
80:@@ -925,47 +919,59 @@     i51_elf_common_section / add_symbol_hook
175:@@ -1040,7 +1046,7 @@    (tc-i51.c line count 2644 -> 2568)
```

The last hunk ends at outer line 3336. `gas/config/tc-i51.c` ends at 3617. So
`gas/config/tc-i51.h`, `include/elf/i51.h`, `include/opcode/i51.h`,
`ld/emulparams/elf32i51.sh`, `ld/scripttempl/elf32i51.sc`, `opcodes/i51-dis.c` and
`bfd/cpu-i51.c` are **byte-identical** between round2 and green. Fixes 1-8 and 10-12
live in those files or in untouched regions of the two edited ones.

Classification of every hunk:

| Hunk group | Kind | What |
|---|---|---|
| `i51_elf_section_from_shdr` | **new fix** | `if (hdr->sh_flags & SHF_CDATA) flags \|= SEC_IS_COMMON;` becomes `if ((hdr->sh_flags & SHF_CDATA) != 0 && (flags & SEC_HAS_CONTENTS) == 0)`. Stops a section that carries real bytes being read back as a size-only common. |
| `i51_elf_fake_sections` | **dead code removed** | The `.rbbs`/`.bbbs`/`.ibbs`/`.xbbs`/`.ebbs` name tests are gone, replaced by a 10-line comment explaining why the classification is unimplementable. **Not a lost fix**: this block is verbatim 2001 code present at the merge base, and the names it tests are misspelled (`.rbbs` for `.rbss`), so it never matched a section that exists. |
| `i51_elf_common_section` (new) | **new fix** | Walks `abfd->sections` for a section that is already `SEC_IS_COMMON`, has `elf_section_data (sec)->this_idx == 0` and the right name; otherwise `bfd_make_section_anyway`. Replaces `bfd_make_section_old_way`, which would hand back the object's own real section of that name and then set `SEC_IS_COMMON` on it. |
| `elf32_i51_add_symbol_hook` | **reformat + routed through the new helper** | Seven near-identical `case` blocks collapse to a name-lookup table; the `default: return 1;` arm is new. Same seven `SHN_I51_*` codes, same `*valp = sym->st_size`. |
| `i51_space_section` (new) | **new fix** | Sets flags and `seg_info(sec)->bss` only when it actually created the section, mirroring `obj-elf.c`. |
| 20 call sites in `i51_common`, `i51_rbss` … `i51_eeprom` | **reformat** | Each 6-line `subseg_new` + `bfd_set_section_flags` + `seg_info(...)->bss = 1` block becomes one `i51_space_section (".rbss", I51_SPACE_BSS)` call. This is the whole of the net -76 lines in `tc-i51.c`. |

Nothing else was removed. Full C-level diff of the extracted files confirms it:

```
$ diff -u ex2/tc-i51.c ex/tc-i51.c | grep "^-" | grep -v "applicable|subseg_new|bfd_set_section_flags|seg_info"
(only bare braces)
```

### Regression: stale `index` blob hashes

`additions.patch` creates nine files. Extracting each and hashing it:

| Embedded file | `index` line says | Actual `git hash-object` | |
|---|---|---|---|
| `bfd/cpu-i51.c` | `ab3d9f53` | `ab3d9f5379…` | ok |
| `bfd/elf32-i51.c` | `6908bb26` | `8b350c887f…` | **stale** |
| `gas/config/tc-i51.c` | `00684525` | `1f53d76304…` | **stale** |
| `gas/config/tc-i51.h` | `4848a100` | `4848a1002d…` | ok |
| `include/elf/i51.h` | `89d0944e` | `89d0944ef2…` | ok |
| `include/opcode/i51.h` | `21f41f87` | `21f41f8702…` | ok |
| `ld/emulparams/elf32i51.sh` | `808ad3c2` | `808ad3c21b…` | ok |
| `ld/scripttempl/elf32i51.sc` | `fbe9a587` | `fbe9a5878d…` | ok |
| `opcodes/i51-dis.c` | `43beef98` | `43beef9899…` | ok |

The two stale ones are exactly the two files the rewrite edited: the bodies changed,
the `index` lines were carried over from round2 unchanged. Round2 commit `8e2665a`
("mcs51/additions.patch: refresh the three stale blob index lines") had fixed the
same class of defect; on round2 both hashes verify (`6908bb26300b…`, `0068452594…`).

Impact is low: `tb/Makefile:144` applies the patch with
`patch --fuzz 0 --no-backup-if-mismatch -p1`, which ignores `index` lines, and plain
`git apply` only consults them under `-3`. `make refresh` regenerates the patch into
`work/refreshed/` and uploads it as an artifact; it never diffs against `mcs51/`, so
nothing in CI notices.

The hunk **line counts** are correct — each `@@ -0,0 +1,N @@` matches the number of
`+` lines that follow (42, 989, 2568, 161, 70, 153, 9, 249, 319). `tb/fixhunks.py`
exists to maintain exactly those, and was evidently run; the `index` lines were not.

## `tb/base.7z` and `tb/base2001.7z`

```
$ diff -rq x/r2base x/gbase
Files x/r2base/lib/www51.sc and x/gbase/lib/www51.sc differ
Files x/r2base/projekt/{diag,ds1620,ds1822,lcd,led1,led2,led3,serial,welcome,wjava}/www8051.rom … differ

$ diff -u x/r2base/lib/www51.sc x/gbase/lib/www51.sc
@@ -79,7 +79,7 @@
     *(reset_device)
-    /* *(reset_network) */
+    *(reset_network)
     *(reset_end)

$ diff -rq x/r2b2001 x/gb2001
Files x/r2b2001/lib/www51.sc and x/gb2001/lib/www51.sc differ     # same one line
```

Nothing else in either archive moved. **Yes — the rewrite fixed the `reset_network`
drop, at the source, in the shipped inputs.** Round2 had the same repair, but as a
`sed` applied to the extracted tree inside the `oracle` target only, so `make check`
kept certifying ROMs three bytes short. Green puts the repair in the archive, which
is why `check` and `oracle` now see the same inputs and the `sed` could be deleted.

### Lengths: previous ROMs, new ROMs, 2001 `.hex` oracle

The oracle is `projekt/*/www8051.hex`, still shipped in all three archive
generations and byte-identical across them. Decoded independently (Intel HEX,
checksums verified) rather than trusting `tb/hexoracle.py`:

| project | 2001 `.hex` | ROM at 1563588 | round2 ROM | green ROM | green − oracle |
|---|---|---|---|---|---|
| diag | 1264 | 1264 | 1264 | **1267** | +3 |
| ds1620 | 6284 | 6284 | 6281 | **6284** | 0 |
| ds1822 | 6078 | 6078 | 6075 | **6078** | 0 |
| lcd | 5754 | 5754 | 5720 | **5754** | 0 |
| led1 | 5173 | 5173 | 5170 | **5173** | 0 |
| led2 | 5010 | 5010 | 5007 | **5010** | 0 |
| led3 | 5200 | 5200 | 5197 | **5200** | 0 |
| serial | 9647 | 9647 | 8125 | **8128** | −1519 |
| welcome | 4812 | 4812 | 4809 | **4812** | 0 |
| wjava | 4812 | 4812 | 4809 | **4812** | 0 |

Eight of ten hit the 2001 length exactly. The `+3` on every project is the restored
`LCALL network_init`. The two that do not are the two `tb/hexoracle.py` records
reasons for, and green matches those records exactly (`diag` +3, `serial` −1519).

Running the checked-in oracle over green's shipped reference ROMs, without building
anything:

```
$ python3 tb/hexoracle.py --tree x/gbase --oracle x/gbase
project   2001   ours  delta  addr16 acall11  word16 pcode13   zero8  residual  verdict
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
all 10 projects agree with the 2001 oracle

$ python3 tb/hexoracle.py --tree x/r2base --oracle x/r2base
…
10 of 10 projects deviate from the 2001 oracle
```

That is the clearest single statement of the change: the ROMs round2 shipped as its
reference fail the checked-in oracle; green's pass it.

Caveat worth recording: none of the ten ROMs is byte-identical to the 2001 image,
and none has been since commit `5d02910`. The ROMs shipped at `1563588` **were**
byte-identical (`md5(orig.rom) == md5(hex image)` for all ten). Since then the
reference has been the port's own output on the 2001 inputs, so `make check` is
circular by construction — which is what `tb/reference.md5` and `make oracle` exist
to contain. The `.hex` files remain the only input no run of the toolchain has
written, and they are unchanged.

## `tb/reference.md5`

A checked-in expectation, and it **cannot drift silently**. `make check` regenerates
the same three columns from the extracted archive and diffs them:

```make
	done | tee $(WORK)/tb/reference.md5
	@grep -v '^#' $(HERE)/reference.md5 > $(WORK)/tb/pinned.md5; \
	if ! diff -u $(WORK)/tb/pinned.md5 $(WORK)/tb/reference.md5; then \
		echo "reference ROMs in base.7z do not match the pinned tb/reference.md5"; exit 1; \
	fi
```

Reproducing the generator's exact `printf '%-8s %5d %s\n'` format over the ten ROMs
in green's `base.7z` and comparing to the ten non-comment lines of the file:

```
$ python3 refcheck.py
generated lines : 10   pinned lines : 10
  OK   'diag      1267 84779b2386ba64a0347e227ac09cf18a'
  OK   'ds1620    6284 5bd93daf7609853f6c3db6541060c420'
  … all ten OK …
reference.md5 matches base.7z byte for byte: True
```

Verdict: real, enforced, currently accurate.

## `tb/sim/run-commons.sh`, +375 lines

108 -> 475 lines. It asserts; it does not print. `st=0` / `fail() { echo "FAIL: $*";
st=1; }` at line 73, `if [ "$st" -ne 0 ] … exit 1` at the end, 28 `expect_*` call
sites. Three new helpers read real state out of the produced files —
`secfield` (readelf `-S --wide` column), `symval` (readelf `-s --wide`), and
`sechex` (`objcopy --dump-section` piped through `od -tx1`) — so the checks are on
bytes and addresses, not on log text. `binutils/objcopy` was added to the
tool-presence precondition.

Five new probes, each aimed squarely at the code the same rewrite added:

| Probe | Asserts |
|---|---|
| `mixed.s` | An object holding a real `.rbss` **and** an external `.rcomm` in the same space: the real section keeps its four bytes `11223344`, the common lands at its own address. Fails if `i51_elf_common_section` hands back the real section. |
| `split.s` | Same across two objects. |
| `spaces.s` / `spacesw.s` | `.section .rbss` with bytes, then the `.rbss` directive: bytes survive in object and image, and bytes written *through* the directive append (`112233445566`). Fails if `i51_space_section` resets flags on an existing section. |
| `localcom.s` | A `.local` memory-space common still comes out `PRC[0xff01]`; pins the assumption that this port's `.local` does not mark symbols local. |
| `xspace.s` | Read-only `.xdata` keeps flags `A` (not `WA`) after the `.xdata` directive — catches a flag reset even where the bytes happen to survive. |
| `named.ld` | A common arrives in a section carrying the **plain** space name, so a script pattern `*(.regbank)` / `*(.ibss)` still places it: `__PROBE_REG_END == 8`, `ICVAR == 0x90`, `__PROBE_IBSS_END == 0x98`. |

That last one is what protects fix #10's cousin: the 2001 `www51.sc` places commons
by bare space name, with no wildcard.

## `tb/Makefile`, the 15 lines

```
+6   check:    enforce tb/reference.md5 against the extracted archive (above)
-5   oracle:   delete the in-tree `sed 's|/\* \*(reset_network) \*/|*(reset_network)|'`
              repair and its guard — base.7z now ships the script repaired
+3/-1 commons: comment only
```

Every gate stage still runs. The lists are unchanged from round2:

```make
TOOLGATE := isa roundtrip branch bits reloc sim defaultlink commons
GATE     := $(TOOLGATE) oracle
MUTGATE  := $(TOOLGATE) check
```

`.github/workflows/gate.yml` (identical on both branches) invokes all nine by name:
`isa`, `roundtrip`, `branch`, `bits`, `reloc`, `sim`, `defaultlink`, `commons`,
`oracle`. `build.yml` invokes `build`, `check`, `check-canary`, `isa`, `dist`,
`refresh`. Nothing lost.

**Stale comment.** The 20-line block above `oracle:` still says "Two repairs are
made to the extracted tree before building" and describes the `www51.sc` repair as
one of them. Only repair #2 (leaving `diag/Makefile` alone) is still a thing the
target does; repair #1 now lives in the archive. Documentation only.

## Not changed, and arguably should have been

`tb/frozen.expect` and `tb/frozen-report.md` are byte-identical to round2, but both
of the things they measure moved underneath them:

- the reference ROMs in `base.7z` gained three bytes each;
- `base2001.7z`'s `www51.sc` now links `reset_network`, so the frozen 2.11.2 build
  produces three more bytes too.

`tb/frozen-report.md` still tabulates the pre-rewrite sizes:

```
$ grep -n "1264\|6281\|5170\|8125\|4809" tb/frozen-report.md | head -6
16:| diag    | 1264 B    | does not link | -               |
17:| ds1620  | 6281 B    | 6281 B        | 423, from 0x40  |
20:| led1    | 5170 B    | 5170 B        | 422, from 0x40  |
23:| serial  | 8125 B    | 8125 B        | 704, from 0x40  |
24:| welcome | 4809 B    | 4809 B        | 419, from 0x40  |
```

No occurrence of 1267, 6284, 5173, 8128 or 4812 anywhere in the file. The
"Convergence" table it derives `frozen.expect` from (`ds1620 217`, `led1 213`,
`serial 325`, …) is from run 32878917600, taken against the old references.
`.github/workflows/frozen.yml` runs `romdiff.py … --expect tb/frozen.expect` with no
`continue-on-error`, so if those counts shifted the frozen workflow goes red.

Whether they shifted cannot be settled here: it needs the `make frozen` build —
binutils 2.11.2, `gcc -m32`, `--build=i686-pc-linux-gnu`. Both sides of the
comparison grew by the same three bytes, so the counts may well survive; the point
is that nobody re-derived them, and the report that documents them is now wrong
about its own inputs.

## Method

```
git show origin/claude/integrate-round2:mcs51/additions.patch > r2.patch
git show origin/work/green:mcs51/additions.patch              > green.patch
git show deeb785:mcs51/additions.patch                        > base.patch
git diff origin/claude/integrate-round2 origin/work/green -- mcs51/additions.patch > add.delta
# each embedded file sliced out with sed and de-prefixed with sed 's/^+//',
# then git hash-object for the index lines
7z x -o./x/{r2base,gbase,r2b2001,gb2001,origbase} <each archive>
# origbase = tb/base.7z at 1563588, for the 2001 .hex oracle
```

Intel HEX decoding was re-implemented independently (record types 0/1/2/4, checksum
verified on every record) rather than reusing `tb/hexoracle.py`, so the oracle sizes
in the table above are not circular; they agree with that script's recorded
`EXPECT` values for all ten projects.

# Provenance of the missing testbench objects

Investigates the origin of `lib/web51_80.obj`, `lib/web51_23.obj` and the 26
`cgi/*.obj` files missing from `tb/base.7z`, by converting three candidate
1999-2001-era source trees through the repo's `tb/i51elf_le2be.py` +
`tb/i51elf_sym_uc.py` pipeline and comparing the result byte-for-byte against
`gnu13-binutils-2.45.1-reference.tar.gz` (source B, "the November 2025
reference set" - what the actual test runs linked with).

## Candidate sources

- **A** - `precompiled_gnu114.rar`, six board/clock variants, each with its
  own `lib/` + `cgi/` tree (old big-endian ELF, `e_machine=0x7262`).
- **B** - `gnu13-binutils-2.45.1-reference.tar.gz` (backup mirror blob
  `claude/archive-retrieval-dannie-...:gnu13-binutils-2.45.1-reference.tar.gz`).
  New format, little-endian, `e_machine=0x1051`, uppercase symbols. This is
  the comparison target, not a candidate.
- **C** - `gnu13.tar.gz` (backup mirror blob `mcs51-2.11.2-original:gnu13.tar.gz`),
  the 2001 original source/precompiled tree. Old format, same as A.

## Headline result

**None of the six rar (A) variants reproduce B exactly, for anything.**
Source **C is the true ancestor** of most of B's missing objects - not the
rar. The rar's directory naming (`precompiled_gnu114`, "gnu 1.14") already
hints it is a *later* snapshot than the "gnu13" (1.3) tree that both B and C
are named after; the byte evidence confirms it: A is missing library modules
that both B and C already contain, and 9 of A's 26 cgi objects are an older
build superseded by what's in B/C.

| Target                    | Best of 6 rar variants (A)                    | Source C                                              |
|----------------------------|------------------------------------------------|--------------------------------------------------------|
| cgi/*.obj (26 files)       | 17/26 identical, 9 differ (same 9 in all 6)     | **26/26 byte-identical**                                |
| lib/web51_80.obj           | not identical (+152..+372 B, symtab/strtab)     | not identical (+108 B), but all program-content sections byte-identical - diff confined to symtab/strtab/shstrtab and the `.rela*` entries that index them |
| lib/web51_23.obj           | not identical (same pattern)                    | not identical (same pattern)                            |
| lib/libk80.a                | 2/31 members identical, 4 modules entirely absent from A (http.obj, makeipreply.obj, smtp.obj, udpchecksum.obj) | **27/27 real members byte-identical** (whole archive is 42638 B pre-conversion in both B and C - same size, only endianness differs) |
| lib/libw80.a                | 0/41 identical, renamed/missing modules (div2x1<->div2x2, mul2x2/fsearch/fsend/eewrite missing) | 0/37 whole-member identical, but **36/37 members have byte-identical `.text`** (actual code) - all differences confined to section *order* (`.shstrtab` moved to end of file) and its knock-on effect on symtab/strtab layout. Sole real code difference: `disp4.obj`. |

Conclusion: **use source C, not the rar, as the ancestor for reconstructing
the missing objects.** cgi/*.obj and libk80.a reproduce B exactly through the
existing conversion pipeline. web51_80.obj, web51_23.obj and libw80.a do not
reproduce B byte-for-byte from any candidate source we have - the underlying
code matches (near-)perfectly, but B's copies carry a different section
layout and a slightly different symbol table, consistent with B having been
re-assembled by a different (likely the modern, in-repo) assembler rather
than literally repackaged from a vintage precompiled object.

## Six rar (A) variants x {web51 obj, cgi set} matrix

Priority order per operational directive (most likely ancestor first).

| # | Variant                          | web51 obj vs B                        | cgi set vs B (of 26)     |
|---|-----------------------------------|----------------------------------------|----------------------------|
| 1 | 8252/22.1184Mhz/80                | differ, len 10324 vs 10172 (+152 B)     | 17 identical, 9 differ     |
| 2 | 8252/22.1184Mhz/23                | differ, len 10852 vs 10604 (+248 B)     | 17 identical, 9 differ     |
| 3 | rd2/2x20MHz/80                    | differ, len 10448 vs 10172 (+276 B)     | 17 identical, 9 differ     |
| 4 | rd2/2x20MHz/23                    | differ, len 10976 vs 10604 (+372 B)     | 17 identical, 9 differ     |
| 5 | rd2/2x22.1184MHz/80               | differ, len 10448 vs 10172 (+276 B)     | 17 identical, 9 differ     |
| 6 | rd2/2x22.1184MHz/23               | differ, len 10976 vs 10604 (+372 B)     | 17 identical, 9 differ     |

The differing cgi set is **the same 9 files across all 6 variants**:
`bd.obj bdc.obj fl.obj ip.obj mac.obj rts.obj shcl.obj shreg.obj xon.obj`.
Since cgi objects don't depend on board/clock config, this is expected - and
it means the divergence is a genuine source-revision difference between A's
snapshot and B/C's, not noise. For these 9 files, `fl.obj`, `ip.obj`,
`mac.obj`, `rts.obj`, `xon.obj` differ in `.text` itself (real code change,
larger file); `shcl.obj`, `shreg.obj` differ only in `.symtab` (same code,
different local-symbol bookkeeping); `bd.obj`, `bdc.obj` differ in `.text`
plus board-name string tables (`cpu_dir`/`cpu_files`).

Source C reproduces all 26, including these 9, exactly.

## web51_80.obj: what actually differs (representative: 8252/22.1184Mhz/80 vs source C)

Per-section byte comparison (via a small ELF32 section walker, not
`readelf` - not available on this box) shows, for **both** A's variant-1 and
C, against B:

```
buf_data / vectors / reset_begin / reset_end / fast_begin / fast_end /
slow_begin / slow_end            -> byte-identical content in ALL cases
cpu_rom                          -> identical for C vs B; DIFFERS for A(variant-1) vs B
.rela* (relocation sections)     -> same size, different bytes (symbol indices
                                     shift because the symbol table differs)
.symtab / .strtab / .shstrtab    -> different size and content in all cases
```

So C's web51_80.obj matches B's actual ROM/vector/reset/fast/slow code
content bit-for-bit; only the symbol table (and the relocation entries that
reference it) differ. A's variant-1 additionally has a genuinely different
`cpu_rom` - a real code difference, not just metadata.

## libw80.a: what actually differs (source C vs B, all 37 shared members)

```
.text sections identical:  36 / 37
.text sections DIFFERENT:  1 / 37  -> disp4.obj (real code difference)
section order identical:   0 / 37  (ALL members have .shstrtab positioned
                                     differently: before .symtab in C's
                                     converted output, after .strtab in B)
```

Sampled in detail on `div2x2.obj` (same length in both, 544 B): `.text`,
`.data`, `.bss` sections are byte-identical; the only difference is
`.shstrtab`'s physical position in the file (last in B vs before `.symtab`
in the converted object), which shifts `e_shoff`/`sh_offset` fields and
everything downstream. This is a section-*layout* difference (assembler
convention), not a code difference, for 36 of the 37 members.

## Archive member set differences, A vs B (why A is disqualified outright)

`libk80.a`: A's 6 variants are all missing **`http.obj`, `makeipreply.obj`,
`smtp.obj`, `udpchecksum.obj`** entirely - modules B/C already have.

`libw80.a`: A's 6 variants use different member names for some routines
(`div2x1.obj` where B/C have `div2x2.obj`) and are missing
`mul2x2.obj`, `fsearch.obj`, `fsend.obj`, `eewrite.obj` outright, while B/C
have `http.obj` in libw80.a that A does not.

This confirms A is an earlier development snapshot than the tree that
produced B; it is not a plausible byte-exact ancestor for anything checked
here.

## Exact reproduction commands

Retrieve source C (read-only, from the backup mirror):

```
git fetch --depth=1 L:/ai/binutils-mcs51/backup/binutils-mcs51.git mcs51-2.11.2-original
git show FETCH_HEAD:gnu13.tar.gz > gnu13.tar.gz
tar xzf gnu13.tar.gz
```

Retrieve source B (comparison target, same mirror):

```
git fetch --depth=1 L:/ai/binutils-mcs51/backup/binutils-mcs51.git claude/archive-retrieval-dannie-01PR939eUPRbzB3PQUAtXEtz
git show FETCH_HEAD:gnu13-binutils-2.45.1-reference.tar.gz > gnu13-binutils-2.45.1-reference.tar.gz
tar xzf gnu13-binutils-2.45.1-reference.tar.gz
```

Convert one object (cgi or lib), from source C's `gnu13/`:

```
python tb/i51elf_le2be.py gnu13/cgi/bd.obj bd.le2be.obj
python tb/i51elf_sym_uc.py bd.le2be.obj bd.obj
```

Convert an archive member: extract with `ar x libk80.a <member>.obj` (GNU ar
or `7z x`), run the same two-step pipeline on the extracted member, compare
against the member extracted from B's `lib/libk80.a` the same way.

## Staged output

`tb/objects-report/staged/` contains the 28 files a later step needs to pack
into `tb/base.7z`, all converted from source C:

- `staged/cgi/*.obj` (26 files) - **verified byte-identical to B**.
- `staged/lib/web51_80.obj`, `staged/lib/web51_23.obj` - closest
  reproduction available (code-identical where checked, but NOT byte-identical
  to B - see PROVENANCE for exact hashes). If exact reproduction of the
  November 2025 test environment matters more than pipeline provenance, the
  integrator should consider copying these two files directly from source B
  instead, since neither A nor C reproduces them exactly.

Library archives (`libk80.a`, `libw80.a`) were compared member-by-member but
are **not** staged as repacked `.a` files, since the task background only
lists `lib/web51_80.obj`, `lib/web51_23.obj` and `cgi/*.obj` as the missing
files 9 projects link against. See PROVENANCE for the full member hash list
if a later step needs to rebuild `libk80.a`/`libw80.a` (C reproduces
`libk80.a` exactly - trivial to regenerate; `libw80.a` cannot currently be
reproduced byte-exact and would need repacking B's own object with `ar`, or
accepting the section-layout difference).

## Post-commit integrity check

After committing, all 28 `staged/` files were read back from the git blob
(`git cat-file -p HEAD:tb/objects-report/staged/...`) and re-hashed: 28/28
match the sha256 values recorded in PROVENANCE exactly - the commit did not
corrupt any binary object (no CRLF mangling despite `.gitattributes`
`text=auto`, since git correctly auto-detects these ELF objects as binary).

## Follow-up

The three inputs this report could not reproduce byte-exact - `libw80.a`,
`web51_80.obj`, `web51_23.obj` - turn out to be the same three that carry a
different storage-class encoding, and that is what makes the 2001 toolchain
lay out internal RAM differently. Measured in `../frozen-report.md`.

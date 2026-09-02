# Audit: can the 2001 reference blobs be trusted, and should they be in the repo?

Scope: `tb/base2001.7z` + `tb/base2001.PROVENANCE`, `tb/objects-report/**`
(28 staged `.obj`), `tb/isa/PROVENANCE`, `tb/frozen-report.md`, and the copies
inside `tb/base.7z` they claim to explain. Audited on `origin/work/green`
(5d02910), 2026-08-25. Every claim below is backed by a command that was run;
the ELF/ar parsing was done with a standalone python walker, not the port's
own tools.

## Verdict in one paragraph

The arithmetic in the PROVENANCE/REPORT files is honest: every hash, size,
census and md5 that can be checked from inside this repo checks out, and the
conversion pipeline reproduces every committed artifact byte-for-byte. What
cannot be checked is the one thing that matters most: the chain of custody.
Every "2001 original" traces to a git blob on a **private local drive
(`L:/ai/...`) that is not on the public remote**, so the entire provenance
rests on trusting whoever wrote the PROVENANCE files. Separately, the golden
ROMs the testbench gates on are **the port's own output** — a regression
baseline, not ground truth — and the modern-format inputs in `base.7z` are
**derived by this repo's own conversion scripts**. The genuinely-vintage
bytes (`base2001.7z`) are only exercised by the non-gating `frozen` job,
which still shows 213–325 differing bytes per ROM and one project that does
not link. Finally, the web51 material carries a third-party copyright notice
and **no license at all**.

---

## Findings, by severity

### F1 — CRITICAL (trust): provenance chain ends at an unverifiable private mirror

Both PROVENANCE files derive everything from
`git blob "mcs51-2.11.2-original:gnu13.tar.gz"` in
`L:/ai/binutils-mcs51/backup/binutils-mcs51.git` — a Windows drive-letter
path on someone's machine. The comparison target "source B"
(`gnu13-binutils-2.45.1-reference.tar.gz`, branch
`claude/archive-retrieval-dannie-...`) lives in the same private mirror.
Neither ref exists on the public remote:

    $ git ls-remote origin        # 16 refs, all listed
    # no mcs51-2.11.2-original, no claude/archive-retrieval-dannie-*

`gnu13.tar.gz`'s own sha256 is not even recorded — only its blob size
(132303 bytes). Consequences:

- Nobody cloning this repo can re-derive or falsify the "byte-for-byte from
  gnu13" claims. They are consistent internally (see F6) but the root of the
  tree is an assertion.
- Every claim about "source A" (`precompiled_gnu114.rar`) and "source B" in
  REPORT.md — the whole 17/26, 27/27, 36/37 comparison matrix — is
  unverifiable from the repo. The rar and the B tarball are nowhere.
- web51.hw.cz is dead, so there is no independent second copy to check
  against.

Fix: commit `gnu13.tar.gz` itself (132 KB, smaller than `base.7z`), or at
minimum record its sha256 and push the `mcs51-2.11.2-original` mirror branch
somewhere public. Until then the correct label for everything here is
"consistent with 2001 origin, provenance asserted but not verifiable".

### F2 — CRITICAL (methodology): the golden ROMs are the port's own output

`tb/base.7z projekt/*/www8051.rom` — what `make check` hashes — were
produced by the toolchain under test (binutils 2.47 + `mcs51/*.patch`, CI
run 32876629391) and were **regenerated in the same commit (5d02910) that
changed the toolchain and the inputs** (the commons fix). Verified: the 10
shipped ROM md5s equal the "md5 (now)" column of base2001.PROVENANCE §6
exactly (`md5sum` over the extracted `base.7z`); the "was" column is gone.

So the gate is: *the port today produces what the port produced last week*.
That is a legitimate regression baseline and cross-arch determinism check
(3 platforms byte-identical), but it is **not ground truth**, and any
codegen bug present at baseline time is frozen into the "golden" ROMs.
The reports themselves never hide this — but the words "reference ROMs"
oversell it.

The only external anchor is the frozen 2.11.2 toolchain run over the 2001
objects (`frozen-report.md`), which today produces: diag does not link,
and 213–325 differing bytes per ROM on the other nine (RAM-layout only,
plausibly explained by the missing common-alignment patch — but "explained"
is not "eliminated"). The genuinely-2001 build products that do sit in
`base.7z` (`www8051.hex`/`.eep` next to each ROM) are admitted to be
un-reproducible leftovers ("decoding the shipped .hex has never reproduced
the shipped .rom, for any project, at any point"). Net: **no artifact in
this repo is simultaneously (a) of verified 2001 origin and (b) used as a
gating golden value.**

### F3 — HIGH (circularity, mitigated): the modern-format test inputs are made by the repo's own scripts

Everything the green gate links — the 26 `cgi/*.obj`, `lib/web51_80.obj`,
`lib/web51_23.obj`, the four `lib*.a` in `base.7z` — is the claimed 2001
object run through `tb/i51elf_le2be.py` + `tb/i51elf_sym_uc.py`
(+ `tb/i51elf_ar.py`), i.e. transformed by tooling that lives in the same
repo as the code under test. Mitigations, all independently verified here:

- Re-running the pipeline over the `base2001.7z` originals reproduces all
  28 staged objects and all 4 converted archives **byte-for-byte**
  (26/26 cgi ok, both web51 objs REPRODUCED, all four `.a` reproduce the
  `base.7z` copies). The conversion is deterministic and auditable
  (~500 lines of python that swap endianness, uppercase symbols, rewrite ar
  headers).
- Independent ELF walk confirms the conversion preserves structure: e.g.
  `web51_80.obj` original mach=0x7262 BE, 317 syms, st_shndx census
  {0xff02:1, 0xff06:6, COMMON:2}; staged copy mach=0x1051 LE, same 317
  syms, identical census, 94 lowercase symbol names → 0.
- The frozen line reads the **untouched** originals, so the two lines share
  source bytes, not converted bytes.

Residual risk is real but bounded: a bug in the conversion scripts would
corrupt the gate inputs and the frozen comparison would be the only thing
that could notice.

Also note: REPORT.md concludes that "source B" — the November 2025 test
reference this work was reconciling against — itself contained three files
(`web51_80.obj`, `web51_23.obj`, `libw80.a`) **re-assembled by the modern
port**, which had silently destroyed the processor-specific common indices
(verified from git history: pre-repair `base.7z` at a1989a8 has
`libw80.a` census {COMMON:46}, `web51_80.obj` {COMMON:9},
`web51_23.obj` {COMMON:12}, exactly as claimed, hashes 71fce8…/2f2191…/
fe00ff… matching PROVENANCE §5's "what they replaced" block). So the
previous reference set was already partially self-referential; this round
replaced it with conversions of the claimed originals. That is an
improvement — conditional on F1.

### F4 — HIGH (legal): no license for the web51 binaries and sources

The `.asm` sources inside `base.7z` (same tree the objects were compiled
from) carry:

    ; P-Code Aritmetic Library (c)Copyright 2000, 2001, Radek Benedikt
    ;	benedikt@lphard.cz, http://benedikt.lphard.cz

No license grant anywhere: `grep -ril licen` over the extracted trees finds
only these copyright headers, and the repo root has **no COPYING/LICENSE
file at all** (`ls -a`: README.md, mcs51/, tb/ only). So the repo publicly
redistributes ~380 KB of a third party's compiled objects and sources with
no stated right to do so. web51.hw.cz was a free-publication hobby project
and the author may well not care, but "probably fine" is not a license.
Plainly: committing them to a public repo is not currently defensible on
paper. Fix: ask Benedikt (address is right there), or document a
good-faith basis in a NOTICE file; and add the GPL text for the binutils
patches while at it.

Contrast: `tb/isa/PROVENANCE` is done right — naken_asm `8051.txt`
(GPL-3.0) and oc8051 `testall.asm` (LGPL-2.1+) with pinned upstream URLs,
sha256 and sizes that match the committed files exactly (verified:
a597813…/7374 bytes and 7869c57…/30704 bytes), vendored byte-verbatim with
fixes kept in a separate documented patch.

### F5 — MEDIUM (dating): "2001 originals" are January 2002 builds, and only the archives are datable

Independent ar-header walk over the `base2001.7z` archives:

    lib/libk80.a   28 members, all mtime 2002-01-19 23:42 UTC
    lib/libw80.a   38 members, all 2002-01-19 23:42
    lib/libk23.a   28 members, all 2002-01-19 23:43
    lib/libw23.a   38 members, all 2002-01-19 23:43
    cgi/libcgi.a   27 members, 2002-01-17 12:32 / 12:58

Loose ELF `.obj` files carry no timestamps and no toolchain ident strings
(only `VERSION` symbol names), so they cannot be dated at all from content.
The uniform 2002-01 mtimes, big-endian `e_machine=0x7262` format (all 28
loose objects checked), and old-gas section conventions are *consistent*
with a vintage tree, and the flat timestamps look like one batch `make` —
consistent with "the tarball's own precompiled tree", not a modern
re-assembly (a modern re-assembly could not have produced the 0xff0x
indices anyway, per F3). But strictly: era-consistent, not proven, and the
"2001" label is off by a few weeks.

### F6 — LOW (accuracy): the reports' own numbers all check out

Everything checkable from inside the repo was recomputed and matched:

- `sha256sum tb/base2001.7z` = 03399d74… , 27907 bytes — matches.
- All 34 files inside `base2001.7z`: sha256+size match PROVENANCE §2, 34/34.
- All 28 staged objects: sha256 match objects-report PROVENANCE §2, 28/28.
- The 7 replaced copies inside current `base.7z`: match §3 hashes, 7/7.
- `lib/lib23_old/lib{k,w}23.a` inside `base.7z` byte-identical to the
  overlay copies, as claimed.
- `www51.sc`: overlay copy == base.7z copy with 10× `_RETI_`→`_reti_` and
  nothing else (replayed the exact substitution; hashes match both sides).
- Symbol censuses in frozen-report's table: recomputed independently,
  match row for row (including the pre-repair COMMON:46/9/12 from git
  history).
- ROM sizes 1264…8125 match the frozen-report table.

One cosmetic defect: objects-report PROVENANCE §2's heading says the staged
files were "verified byte-identical to source B" — they are conversions of
source C *compared against* B, and two of them are explicitly *not*
identical to B. The per-file annotations are correct; the heading is
sloppy. Also the loose-object count is 28 (26 cgi + 2 lib), not 25.

### F7 — LOW (hygiene): triplicated blobs, dead weight, gitattributes gap

- **Every one of the 28 `tb/objects-report/staged/*.obj` is byte-identical
  to the copy inside `tb/base.7z`** (verified 26/26 + 2/2), and nothing
  consumes `staged/` — no reference in `tb/Makefile` or `.github/`
  (`grep -rn objects-report`). The same logical objects therefore exist
  three times: original bytes in `base2001.7z`, converted bytes in
  `base.7z`, converted bytes again loose in `staged/`. The staged tree is
  pure dead weight; the PROVENANCE hash list already pins the values.
  Delete it (or stop shipping it once F1 is fixed by committing the
  tarball, which supersedes `base2001.7z` too).
- Size itself is a non-issue: whole pack is 567 KiB (`git count-objects
  -vH`), largest blob `base.7z` at 137 KiB. Fetch-instead-of-commit is not
  an option — upstream is dead — so committing is right *if* F4 is
  resolved; the objection is duplication, not bytes.
- `.gitattributes` covers `*.7z` but has **no rule for `*.obj` or `*.a`**;
  the loose objects ride on `* text=auto` binary autodetection. It worked
  (REPORT.md's post-commit read-back, re-confirmed here by hash), but it is
  one text-looking object away from silent CRLF corruption. Add
  `*.obj binary` and `*.a binary`.

---

## Classification of every artifact

| Artifact | Class |
|---|---|
| `base2001.7z`: 26 `cgi/*.obj`, `web51_80/23.obj`, 4 `lib*.a`, `cgi/libcgi.a` | Claimed 2001 (actually 2002-01) originals; era-consistent on inspection; **provenance unverifiable** (F1) |
| `base2001.7z`: `lib/www51.sc` | **Derived/hand-edited** (10 symbol renames); honestly declared |
| `base.7z`: converted `cgi/*.obj`, `web51_*.obj`, `lib*.a` | **Reconstruction by this repo's own scripts** from the above; conversion independently reproduced byte-exact |
| `base.7z`: `projekt/*/www8051.rom` ("reference ROMs") | **Output of the port under test.** Self-referential baseline, not ground truth |
| `base.7z`: `projekt/*/www8051.hex`, `.eep`, `.map` | Probably genuine 2001 leftovers; admitted inconsistent with the ROMs; unused |
| `staged/**` (28 objects) | Redundant third copy of the converted set; unused by any build |
| REPORT.md claims about sources A and B | **Unverifiable** — neither source is in the repo |
| `tb/isa/8051.txt`, `testall.asm` | Verified verbatim against pinned public upstreams; properly licensed |

## Bottom line

Trust as *golden ground truth*: **no**. The gating goldens are the port's
own output, and the one genuinely independent oracle (the 2001 toolchain
over the 2001 objects) does not yet reproduce them. Trust as a *carefully
documented regression baseline plus a vintage cross-check corpus*: yes —
the internal bookkeeping is the most rigorous part of the repo. To make the
trust real: publish `gnu13.tar.gz` (or its hash + a public mirror ref),
settle the Benedikt licensing, delete `staged/`, add `*.obj binary`, and
stop calling the port's own ROMs "reference".

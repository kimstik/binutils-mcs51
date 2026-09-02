# Build / CI / testbench review

Scope: mcs51/modifications.patch (build integration), tb/Makefile, tb/*.py, .github/workflows/*.
Findings ranked by severity. "FIXED" = fix applied on this branch.

## CRITICAL

- **The testbench has never tested anything. Every CI PASS is fake.**
  `7z x` does not restore unix exec bits, so every helper in `work/tb/bin/`
  (`rm`, `perl`, `bin2hex`, `*.pl` - shipped in base.7z) comes out non-executable.
  Every project make dies on its first `$(RM)` with `Permission denied`, both
  failure legs are masked (`make clean ... || true`, `make ... || true`,
  tb/Makefile check loop), and the reference ROM shipped in base.7z - which the
  build was supposed to overwrite - survives to be md5-compared against itself.
  Ten green PASSes, zero builds.
  Evidence: CI run 32760399911 (HEAD 38a3861, "success"), job 97537612389:
  `== building` 18:07:26.393 -> `== comparison` 18:07:26.470. Ten projects
  "built" in 77 ms, all ten hashes byte-identical to the `== reference` listing.
  Reproduced locally: with non-exec bin/, all projects fail instantly.
  FIXED (two parts): `chmod +x $(WORK)/tb/bin/*` after extraction, and
  `rm -f $$p/www8051.rom` before each project build so a failed build can never
  match the reference again (tb/Makefile check target). NOTE: CI will now go
  honestly red until the next item is resolved.

- **base.7z is missing the objects the projects link against - `make check`
  cannot succeed even with the masking removed.** The archive contains no
  `*.obj` at all (packed with them excluded): 8 projects need `../../cgi/*.obj`
  plus `lib/web51_80.obj`, wjava needs `lib/web51_23.obj`. cgi objects are
  regenerable (cgi/Makefile) - FIXED: check now builds them first
  (tb/Makefile `== cgi objects` step, hard failure, cgi.log uploaded).
  `web51_80.obj` / `web51_23.obj` have NO rule anywhere (lib/Makefile only
  builds `web51.obj` from web51.asm); provenance unknown - NOT FIXED, needs the
  port owner. Data point: with a naive `cp web51.obj web51_80.obj`, led1 links
  but the ROM is 5170 B / f0a2a4af... vs reference 5173 B / 6c579304... - either
  wrong variant or a real port regression. diag (needs neither cgi nor web51)
  reproduces its reference ROM byte-for-byte with the current 2.47 port.

- **win32 wine smoke test never executed the binaries; its green status is
  fake.** Ubuntu 24.04 `wine64` alone cannot run i686 PE. Same "successful" run,
  job 97537612354: `it looks like wine32 is missing`, `wine: failed to load
  ntdll.dll`, `ShellExecuteEx failed` - no version string ever printed. The step
  stayed green because `wine ... | head -2` masks wine's exit status (default
  step shell is `bash -e` without pipefail).
  FIXED: `dpkg --add-architecture i386` + `wine32:i386` for the i686 host, and
  `set -o pipefail` in the smoke step (.github/workflows/build.yml:59-67,88).

## HIGH

- **PORT_SHA256 was empty: the tarball CI builds and publishes artifacts from
  was never verified.** tb/Makefile:28 shipped `PORT_SHA256 ?=` and the verify
  branch silently did nothing. FIXED: pinned to
  `154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff`
  (binutils-2.47.tar.xz; identical from ftp.gnu.org and the sourceware.org
  mirror), plus a warning when unset.

- **modifications.patch was stale against 2.47 and only applied thanks to
  `--fuzz 3`.** The ld/configure.tgt hunk fails outright at fuzz 0 (its context
  carries a pre-2.47 h8300 emulation list) and landed at "fuzz 2, offset -17";
  other hunks drifted up to 372 lines. Fuzzy application can silently place
  hunks in the wrong spot. FIXED: patch regenerated against pristine 2.47
  (verified: applies with zero fuzz, zero offsets; full i51-elf build from the
  regenerated patches succeeds), and tb/Makefile build now applies with
  `--fuzz 0 --no-backup-if-mismatch` (tb/Makefile:107-108) so drift fails loudly
  instead of fuzzing through. `--no-backup-if-mismatch` also stops GNU patch's
  default `.orig` backups from leaking into `make refresh` output
  (`git add -AN` + `--diff-filter=A` would sweep them into additions.patch).

- **bfd/Makefile.am edits broke the file's own sync invariant: only the
  `*_CFILES` lists got i51 entries, not `ALL_MACHINES` / `BFD32_BACKENDS`
  (.lo lists).** An `--enable-targets=all` build selects objects from the .lo
  lists and fails to link (`bfd_i51_arch` / `bfd_elf32_i51_vec` undefined).
  FIXED in the regenerated patch: `cpu-i51.lo` and `elf32-i51.lo` added to both.

- **bfd/Makefile.in and opcodes/Makefile.in were not patched at all.** Release
  tarballs run with maintainer mode off, so the Makefile.am edits were inert;
  the port compiled only by accident (configure's `tb=`/`ta=` lists + generic
  suffix rules), with no dependency tracking for the new files. ld/Makefile.in
  had the source-list entry but not the `eelf32i51.Po` depfile include.
  FIXED: regenerated patch mirrors every Makefile.am edit into the
  corresponding Makefile.in (source lists, .lo lists, `.Plo`/`.Po` includes),
  matching what automake would emit.

## MEDIUM

- macos jobs never installed 7z; `make check` needs it for base.7z. It worked
  only because the macos-14 runner image happens to ship a 7z - an undeclared
  image dependency, gone whenever the image changes.
  FIXED: `brew install p7zip` (.github/workflows/build.yml:75).
- Stale comment claimed mcs51/*.patch are "byte-identical to the 2001 patches
  ... same binutils release" - false since the 2.45/2.47 bumps, and it hides
  the fuzz risk above. FIXED: comment rewritten (tb/Makefile:88-93).
- `make refresh` uses `git diff --diff-filter=A` / `--diff-filter=M` only:
  file deletions and renames in the port would be silently dropped from the
  regenerated patches. NOT FIXED (no deletions exist today; fix when one does:
  add D/R handling or split by pathspec).
- Wine "smoke test" is far weaker than the native check even when it works:
  `--version` exercises no assembly, no relocation, no linking. The testbench
  could run under wine via binfmt/wrapper scripts. NOT FIXED (design change).

## LOW

- Actions pinned by tag (`actions/checkout@v7`, `actions/upload-artifact@v7`,
  build.yml:51,93; frozen.yml) not by commit SHA - supply-chain hygiene.
- `upload-artifact` with `if: always()` + `if-no-files-found: ignore`
  (build.yml:94-97): a job where packaging silently produced nothing still
  uploads an empty-ish artifact without complaint. Job status covers the hard
  failures, but a missing results.md5 goes unnoticed.
- No caching of the binutils tarballs: 5 jobs x 29 MB from ftp.gnu.org on every
  push; GNU ftp flakiness = spurious red. Consider actions/cache keyed on the
  sha256.
- Hardcoded "10" in check messages drifted from $(PROJECTS). FIXED:
  `$(words $(PROJECTS))`.
- tb/i51elf_le2be.py: converts SHT_RELA (type 4) only - SHT_REL (9) sections
  would pass through half-converted; endianness/machine warnings are non-fatal;
  no guard for `e_shentsize == 0` header (only per-section entsize).
- tb/i51elf_sym_uc.py: the old-offset -> new-offset remap is dead code (upper()
  preserves length, mapping is always identity) and misses suffix-shared
  st_name offsets if it ever were live; the "larger than old" warning is
  unreachable. Harmless today, misleading tomorrow.
- tb/Makefile libk80 target: per-file python/mv failures inside the for-loop
  are not checked; only the last iteration's status reaches make.

## Verification done on this branch

- binutils-2.47.tar.xz sha256 cross-checked ftp.gnu.org vs sourceware.org.
- additions.patch + regenerated modifications.patch apply to pristine 2.47 at
  `--fuzz 0` with zero offsets.
- Full `configure --target=i51-elf && make all-{bfd,opcodes,gas,ld,binutils}`
  from the patched tree succeeds; as-new/ld-new report 2.47.
- diag project rebuilt with that toolchain reproduces its reference ROM
  byte-for-byte (1264 B, 66cb267cc8485b84f2aea3847c41d156).

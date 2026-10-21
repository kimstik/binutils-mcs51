# Review 7: do the tests, docs and CI back what the r6 series claims?

Scope: branch `claude/r6-fixes` (13 commits, origin/main..95ecb8d). I worked in a copy of the patched tree and build at
`review7/tests/m/`. The harness is `review7/tests/mutate.py`, with raw results in `review7/tests/results.json` and logs in `review7/tests/logs/`.
The baseline copy passes the gate (15 stages) and DejaGnu (gas 18/18, ld 18/18). I restored and re-verified the copy after the run.

## 1. Mutation results (48 single faults, each rebuilt, then DejaGnu plus every other gate stage)

Every mutant built.

**Killed by a DejaGnu test that targets it (36):** fallback (jmp-call, operands-bad, names-bad), space-all and space-ram80 (space, ram80), init, code16-ovf, h-ovf, pcode-ovf (overflow),
page16 (page), srel0 (b2b0), rela-local (merge), rela-normal (emit), secflags (nm), commdef, bank0, assert-stack, iram-default and stack-default (stack),
assert-data80 (ramfull), assert-eeprom, dwarf, absfx (branch-abs, abs-branch), weak (branch-weak, weak), fixrange (range-fwd), junk (trailing),
arn-first (regbank), pcode-byte and pcode-swap (pcode), regname and frob (names-bad), b2b-byte (operands-bad), comm-align, comm-recover, comm-local,
comm-space, dollar-local (separator), dis-trunc (truncated).

Every fix the brief names is protected: the last-row fallback, the space check, the init-data check, the R_I51_16_CODE overflow check, dwarf2_emit_insn, the bank-0 reservation and fx_done for pcrel to abs.

**Not caught by any DejaGnu test:**

| mutant | what it reverts | caught elsewhere? |
|---|---|---|
| init-relocs | init check ignores relocated bytes in RAM data (`.data; .byte sym`) | no |
| assert-iram | `ASSERT(__IDATA_END <= __IRAM_SIZE)` removed | no (the stack ASSERT covers it unless `__STACK_SIZE=0`) |
| high-const | HIGH() 16-bit range check on a constant | no |
| shf-bits | SHF_I51 space tested as bits (BDATA counts as a regbank common), an r6-status row | no |
| using-range | `.using 4` accepted | no |
| dollar-lex | `LEX_DOLLAR` back on (`$` a name char), part of the "`$` only separates" claim | no |
| dis-insntype | disassembler insn_type/target, claimed in 821964f | no |
| highlow-msg | 95ecb8d's new message; operands-bad.l matches `Error: .*` | tb reloc only |
| checkdirect | gas "`X' is at 0x90 ... direct address cannot reach", quoted in the manual | tb reloc only |
| dir-ovf | R_I51_8_DIR overflow in ld (the manual says it is refused) | tb reloc only |
| r8-compat | R_I51_8 adds the in-place byte (old objects "link to the same bytes") | tb check only |
| init-load-exempt | "a script that loads the section is left alone" | tb script, disasm |

I also ran the 36 DejaGnu tests against the pre-series toolchain (old as, ld and binutils swapped into the build). 35 fail; `shadow` passes. The r6-status sentence "each [CRITICAL] has a test that fails before the series" holds, except that #23 (`shadow`) is backed only by `comm`.

## 2. A defect the tests miss (HIGH)

The tests miss a defect: **#6 (HIGH()/LOW() swallow the rest of the expression) is fixed only for constants.**

`mov a,#high(sym)+1` assembles **without a diagnostic** to `R_I51_H SYM+0x1`, which is high(sym+1). With SYM=0x1234 it links to `74 12`, not `74 13`. `#1+high(sym)` and `.byte high(sym)+1` do the same, and `#low(sym)+2` becomes `R_I51_L SYM+2`.

The manual says the operator "has to be the whole operand", which implies an error. high-low.s only uses constants and a forward `.equ`, so it cannot see this. The repro is `review7/tests/doc/t4.s`.

Separately, `mov a,#2*high(sym)` produces "can't resolve value for symbol `L0'" (LOW).

## 3. Loose tests (MEDIUM/LOW)

- operands-bad.l: 26 lines of `Error: .*`. Any error passes, including a wrong one, so r6-status row 7 and commit 95ecb8d are unpinned.
- abs-branch.d checks only the out-of-range error. No test checks the bytes of an in-range absolute branch after linking (`sjmp 0x110` from 0x100).
- bank0.d matches `0+8 . R` (any symbol class).
- `#pass` appears in bank0, dwarf, emit, nm and stack-ok. Each is used after the lines that matter, so I count it as acceptable.
- The commdef example in the manual lost its `@c doctruth: diagnostic` marker, so no gate checks it.

**r6-status rows with no backing test: 8.**
- CRITICAL 21, 22 and 24 (documented, not fixed).
- "internal error gone", "size counts the image", "nm `.idata` → i", "SHF codes compared whole" and "page size mismatch".

**Rows only partly protected: 4.**
- #6 (relocatable case broken).
- #7 (any error accepted).
- `$` (LEX_DOLLAR).
- `.using` (range).

## 4. Docs (c-i51.texi, README)

What I verified against the tools: `.byte ACC, CY` = e0 d7. PSW.3, IE.7 and TCON.4 = d3, af, 8c; 0x20.3 = 03 and 0x90.5 = 95. `#HIGH(0x1234)+1` = 13. `.ds 3` reserves 6 bytes and `.ds.b 3` reserves 3. `mov a,0x20.3` is an error. `.quad sym` gives the quoted error, and so do r0 and "missing .using". `.using 1+1` works.

On the linker side: `-g` works, and addr2line maps to the right lines. nm shows `d` for RAM symbols and `size` reports text = 9. The `__STACK_SIZE` (16) and `__IRAM_SIZE` (0x100, or 0x80 via --defsym) defaults behave as documented, and so does the commons diagnostic. jmp/call give the long forms.

Wrong or missing:
- **(MEDIUM)** The "has to be the whole operand" rule is not enforced (§2).
- **(MEDIUM)** The `.bit` entry is stale. It still calls `.bit` "how initialized data is written in the bit space", but the default link now refuses `.bitdata` + `.bit 1` with "reserve the space with .space".
- **(MEDIUM, undocumented)** `.eeprom` initialized data is exempt from the init check and links clean. With the default script, `objcopy -O ihex -j .eeprom` yields an empty image (an INFO section), so the bytes vanish silently. The manual describes `-j .eeprom` extraction only for multi-region scripts.
- **(LOW)** The `__EEPROM_SIZE` default is 0x10000, so there is effectively no bound. The manual does not say so.
- **(LOW)** Global `.idata` symbols show as `I`, while the manual says `i`.
- **(MEDIUM)** README: "`make -C tb gate` runs all sixteen stages" is wrong. `gate` runs 15; the canary is separate.
- **(MEDIUM)** README: `make -C tb dejagnu` and `make -C tb gate` default to `BUILD=work/frozen/build` (the 2.11.2 tree). They need `BUILD=work/modern/build`.
- **(MEDIUM)** README: "a test for each defect the reviews found" is overstated (see the 8 untested rows above).

## 5. CI

- **HIGH: coverage.yml will go red.** `MUTGATE` now includes `dejagnu` (through TOOLGATE), and `mutants-coverage` defaults `MUTSTAGES` to it. coverage.yml installs only `p7zip-full sdcc-ucsim`, with no `dejagnu`. The stage then exits 2 ("runtest is not installed"), and run.py's baseline refuses with exit 3. The commit says "the mutation harness all run it", but coverage.yml was only pinned and given `permissions`.
- **MEDIUM: reproducibility claim.** I re-ran the Package step locally on identical trees: tar.gz and zip are byte-identical. However, `make dist` writes `built: $(date -u …)` into BUILD-INFO.txt, so two runs of one commit never pack to the same bytes, contrary to fcc91c1 ("the same commit packs to the same bytes"). zip also stores local time, so the bytes depend on TZ (runners are UTC; LOW).
- These checks pass locally:
  - `release-vars` gives GATE_STAGES = the 16 names, identical to release.yml's `want`; `gate-list` is 16 words and `ci-list` is consistent.
  - release_manifest.py accepts five fake archives made by the new Package commands.
  - dist_check.sh passes against the real tools, and the probe image is `0200050000110980fc2222` with __I51_RET=0xa and _ETEXT=0xb. Every target is nonzero, so an unapplied relocation shows.
- Package names exist: apt `dejagnu` and `sdcc-ucsim` (noble/universe), brew `deja-gnu` and `gnu-tar`. Actions are pinned by 40-hex SHA with a version comment. I could not confirm that the SHAs are real v7 commits offline.
- Not verifiable here:
  - `sdcc-ucsim` on ubuntu-24.04-arm: the Linux arm64 job now runs the full gate, including `sim`.
  - `make -C build/ld check` on macOS-14.
  - brew `p7zip` availability (it predates the series).
- LOW: tb/Makefile's default `OPTFLAGS` still has `-march=haswell`, which gate.yml and release.yml builds use, and which breaks a plain `make -C tb build` on an arm host.

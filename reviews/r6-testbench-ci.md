# i51 binutils port: testbench, CI and release review

Scope: `tb/` (Makefile, sim/*, isa/*, mutation/*, hexoracle.py, dist_check.sh,
release_manifest.py) and `.github/workflows/*.yml`. The repo was not modified.
Build under test: `scratchpad/work/modern/build`. It was configured with **CFLAGS=-O1**,
not the CI flags `-Os -flto -march=haswell`, so it is not byte-for-byte the CI binary.
Work dirs: `scratchpad/review/work-tb`, `.../review/work-tb2` and `.../review/mut`. Probes are in `.../review/probe`.

## 1. Gate run

Environment: `s51` (sdcc-ucsim 4.2.0) and **`7z`** were both missing. I installed both with
apt (`apt-get update` was needed first). Without 7z, `check`, `oracle`, `check-canary` and `script`
also fail. Without s51, `sim` exits 3 and the gate goes red, which is correct (it is not skipped).

| stage | result | time |
|---|---|---|
| isa | PASS (8051.txt + testall assembles; extra.txt 3; zeroops 18) | 4s |
| roundtrip | PASS | 4s |
| branch | PASS 24/24 | <1s |
| bits | PASS 60/60 | <1s |
| reloc | PASS 78/78 | 1s |
| guard | PASS 24/24 | <1s |
| sim | PASS (P1=127) | <1s |
| defaultlink | PASS | <1s |
| commons | PASS | <1s |
| script | PASS (146 arms, 38 unreachable .rel/.dyn arms) | <1s |
| disasm | PASS 12/12 | <1s |
| doctruth | PASS 42 checks | <1s |
| check | PASS 10/10 md5 | 2s |
| check-canary | PASS (10 FAIL reported) | 1s |
| oracle | PASS (8 classified, 2 size-only) | 1s |

`make gate` end to end: PASS. I saw no flakiness: the whole gate is deterministic
and takes about 15s. The things that depend on the environment are 7z, the unpinned apt
`sdcc-ucsim` version (the output parser has two formats), and the host gcc. Nothing pins the runner image or the compiler.

## 2. Why the three known bugs pass the gate

I reproduced each one with the build under test:

```
jmp lbl            -> 73          (jmp @A+DPTR), rc 0. Also `jmp 0x1234` -> 73.
ljmp lbl+0x10000   -> 02 00 03    links clean
setb B2B(XV,1)     XV in .xdata   -> d2 01, links clean
mov a,XV  (xdata)  -> e5 00 R_I51_8_DIR, links clean
ljmp XV   (xdata)  -> R_I51_16, links clean
```

The missing test classes are:

* **Negative/differential ISA testing.** Every ISA corpus (8051.txt, extra.txt, zeroops.txt,
  testall.asm) is a *positive* list of encodings: "this source gives these bytes".
  Nothing asserts that a mnemonic/operand combination the corpus does not list is
  either encoded correctly or rejected. 8051.txt has no generic `jmp <addr>`/`call <addr>`
  row, and testall uses only `jmp @a+dptr`. So a wrong match in the opcode table
  (`I51_INS("jmp","@NN",...)` accepting a bare label) is invisible to the gate. Two fixes would close this:
  a differential test against an independent assembler (sdas8051 from sdcc, or asem51/naken)
  over a generated operand grammar, and a table of must-reject forms.
* **Link-time overflow for every relocation kind.** `reloc`'s `range` step covers
  R_I51_7_PCREL and R_I51_11, and `kinds` covers R_I51_8_DIR/8_IMM. bits covers B2B, and PCODE_LINK covers PCODE.
  **R_I51_16, R_I51_8_BIT, R_I51_H and R_I51_L have no link-time out-of-range case.** The only
  16-bit overflow tests (`fold-16-konst`, `fold-high-over`) are gas-side constant folds.
  In the linker, `case R_I51_16` is `bfd_putb16(srel & 0xFFFF)` with no check. Further probes:
  `lcall X` X=0x10000 -> `12 00 00`; `ljmp X` X=-1 -> `02 ff ff`; `mov dptr,#X` X=0x12345 -> `23 45`;
  `setb BS` BS=0x1ff -> `d2 ff`; `mov a,#HIGH(X)` X=0x12345 -> `74 23` (gas rejects
  this same case when it can fold it); **`acall X` X=0x10000 at 0 -> `11 00`**. The R_I51_11 page
  test masks with `0xF800`, so bit 16 is ignored and a 64K wrap passes. The `reloc` page cases stop at 0x1000.
* **Address-space typing of relocations.** Every link-time reloc test resolves its
  symbol with `--defsym`, which makes it an *absolute* symbol. No test links an instruction against a symbol
  that lives in a different memory space (xdata/eeprom/code vs data/bit). So the gate has no concept of
  "a direct/bit/B2B operand must point into data/bdata/SFR space", and
  "ljmp/acall must point into code space".
* **Boundary value 0 in B2B and PCODE.** `R_I51_8_B2B` and `R_I51_13_PCODE`
  do `if (srel == 0) break;` ("unresolved COMMON"). Any symbol whose final address is 0 is
  therefore never folded or range-checked. `setb B2B(BD,1)` with BD=0 links as `d2 01`
  (bit 1 of byte 0x20), while BD=0x10 is refused. The first object in .xdata/.data is at
  address 0, which is why the xdata probe above gives `d2 01`. bits LINK_CASES never uses addr 0.

## 3. Findings, worst first

### HIGH

**H1. No test asserts rejection of an instruction form, or checks generic jmp/call.** See §2. The corpora are
positive-only. 8051.txt is a third-party table that the gate takes as complete.
`jmp lbl`/`jmp 0x1234` silently encode `jmp @A+DPTR`, a correct-looking program that
jumps somewhere else at runtime. This is the class that lets opcode-table matching bugs through.

**H2. Link-time range checking exists for only 4 of 9 emitted relocation kinds.** R_I51_16
(ljmp/lcall/mov dptr/.word), R_I51_8_BIT, R_I51_H and R_I51_L truncate silently, and the gate
has no case that would see it. The R_I51_11 cases miss the 64K wrap
(`acall 0x10000` accepted). The asymmetry is easy to see: gas refuses `mov dptr,#0x12345` (fold-16-konst) but ld
accepts the same value from a symbol.

**H3. No relocation test involves a symbol's address space** (§2). All resolve tests use
absolute `--defsym` symbols. setb/B2B/direct/ljmp against `.xdata` link clean.

**H4. Release binaries are not the binaries the gate tested, and 4 of 5 hosts are barely tested.**
- release.yml `gate` job builds its own linux-x86_64 toolchain and runs 15 stages on it.
  The *published* archives come from build.yml jobs, which are separate builds, and no hash ties them to the
  tested binary.
- build.yml runs only `check`, `check-canary` and `isa` on linux-x86_64, linux-arm64 and macos-arm64.
  bits/reloc/guard/sim/branch/commons/script/disasm/defaultlink/oracle never run on
  arm64 or macOS.
- **windows-x86_64 and windows-i686 get `--version` under wine plus `dist_check.sh`'s probe, and nothing else.**
  The probe is `_START: ljmp _START` at address 0. The expected image `02 00 00 22` is
  produced whether or not R_I51_16 was applied, and in either byte order. So a Windows build with
  broken relocation (LLP64 `long`, a 32-bit host `bfd_vma` on i686) ships green. Running
  `check` and `reloc`/`bits` under wine would fix this, since they are Python/sh drivers that call tools.

### MEDIUM

**M1. `check` is a self-referential golden.** reference.md5 says it is "built by the
ported toolchain". It is a regression lock, not a correctness check. Correctness of the
10 ROMs rests on `oracle`, which is loose:
- `addr16` accepts any pair with `produced[i+1]==oracle[i]` and `oracle[i+1]==0`, so the
  high byte of every LJMP/LCALL/DPTR target (about 300/ROM) is compared against nothing.
- `zero8` accepts any value where 2001 has 0x00 (400+ bytes/ROM: every SFR/RAM/bit operand).
- Only the counts per class are pinned. A wrong value that stays in its class (a wrong SFR
  address, a wrong high byte) does not move the oracle. Only `check`'s md5 would catch it, and
  that md5 came from the port itself.

**M2. B2B/PCODE `srel == 0` skip** (§2). This is a silent no-op at a reachable address, and no case
uses address 0.

**M3. The relocation-type bound check has no test (mutant `bfd-guard0-325` survives).** Removing
`if (r_type >= R_I51_max)` in `i51_info_to_howto_rela` passes the whole MUTGATE. `guard`
crafts only `r_offset`, never `r_type`, so an out-of-bounds read of the HOWTO table on a malformed
object goes unseen. R_I51_R1/R_I51_R3/R_I51_NONE have HOWTOs with `dst_mask 0` and no test
at all.

**M4. Mutation scope excludes the code where the known bugs live.** gen.py SCOPES for gas omit
`md_assemble`, `i51_parse_operand1/2` (operand classification: the jmp bug),
`i51_parse_cons_expression`, `i51_pcode`, `i51_using`, the space/common directives,
and for bfd `i51_elf_section_from_shdr`, `i51_elf_fake_sections`, `i51_elf_common_section`.
The disassembler's `i51_symbol_is_valid` is also out, even though the `disasm` stage exists for it. ld
emulation code is not mutated either. A function name in SCOPES that does not match the source is silently
ignored, with no warning. So the kill rate measures only the code the tests were written for.

**M5. Release x86_64 binaries are built with `-march=haswell`** (linux-x86_64 and
windows-x86_64 in build.yml, and the Makefile default). The published archives may SIGILL on pre-Haswell or
low-end Atom/Celeron CPUs. The release notes do not say so. (Not confirmed by disassembly: the
local build used -O1.)

**M6. doctruth cannot fail on port behaviour.** It compares the texinfo lists with the source lists.
It is honest about this, but it is one of the "15 stages" the release body counts.

### LOW

- L1. Actions are pinned by major tag (`actions/checkout@v7`, `upload-artifact@v7`,
  `download-artifact@v7`), not by SHA, and `checkout` persists credentials by default.
- L2. gate.yml, build.yml, coverage.yml and frozen.yml have no `permissions:` block, so they get the repo-default
  token. release.yml and upstream.yml are scoped correctly (contents: read, with write only on
  `publish`/`issues`). Inputs reach shell through `env:` everywhere, so I found no injection.
- L3. Release builds are not reproducible. BUILD-INFO has `built: $(date)`, `tar czf`/`zip`
  record mtimes and owners, there is no SOURCE_DATE_EPOCH, and the runner image, gcc and apt packages are unpinned.
  SHA256SUMS exists and is inlined in the release body, but there is no signature or provenance attestation.
- L4. check-canary sabotages only by making `as` exit 1. It proves that a dead toolchain goes red, not that one
  wrong byte does (md5 makes that true anyway).
- L5. The mutation harness generates equivalent mutants (e.g. `gas-oporder-1541`, which swaps two
  independent assignments), and these understate the kill rate.
- L6. testall (the sim stage) excludes MOVX and RETI by provenance, so those are covered by encoding only.
  `.set`/`.equ` and the long `*common` aliases have no direct test, and `.using` is tested only with 0.

### What is sound

- gate.yml runs exactly `ci-list`, and `ci-list` is checked against `$(GATE)`+canary. The loop counts the stages it ran against
  `gate-list`. Local `make gate` = `$(GATE)` (no canary), which is documented.
- release.yml: `publish needs [gate, build]`, and the tag must point at GITHUB_SHA. BUILD-INFO
  commit/version/sha is verified per archive, the release is a draft until the asset count matches, and SHA256SUMS is included.
- The tarball sha256 is pinned, patches apply with zero fuzz/offset, and the reference ROM md5s are pinned.
- sim uses a real independent oracle (ucsim execution). bits/branch use hand-derived
  goldens, and 8051.txt is from an independent assembler (c51asm).

## 4. Mutation harness

Run: gen.py `--cap 1` (69 mutants) through run.py with the MUTGATE stage list, on a copy of the
build (`scratchpad/review/mut`). The run took about 75 minutes. Results are in `scratchpad/review/mut/results1.json` and `run1.log`.

**Kill rate: 59.4% (41/69); 28 survived.** First-red stage for the kills: isa 19, reloc 13,
check 3, bits 2, guard 2, roundtrip 2. `sim`, `commons`, `script`, `disasm` and `defaultlink` made
no first kill. That is expected from their position in the fail-first order; it is not evidence that they are useless.

Notable survivors:
- `gas-constpm1-454`: `input_line_pointer[1] > '7'` becomes `> '8'` in `i51_fold_bit_suffix`. **`0x20.8` would be
  accepted as a bit operand.** bits tests `B2B(x,8)` but has no `.8` suffix case. This is a real gap.
- `bfd-guard0-325`: the reloc-type bound check is deleted (M3). This is a real gap.
- `dis-cond0-51`: `if (status != 0)` is forced to 0 in the disassembler's read_memory error path. Nothing tests
  disassembly of a truncated buffer.
- 18 `bfd-howto-*`: HOWTO fields of R_I51_16, 8_BIT, 8_B2B, 11, 7_PCREL, 13_PCODE, R1, R3 and NONE.
  The port's `i51_final_link_relocate` hand-applies most kinds, so a HOWTO is
  largely dead for final links. It still drives `ld -r` output, `objdump -r`, the generic overflow
  complaint for R_I51_8_BIT/8_DIR, and foreign-object handling. Survivors in R_I51_8_BIT
  (bitsize, dst_mask) agree with H2: nothing checks 8_BIT range.
- 5 `opc-opctab-*` (mask 0xFF->0xFE on add/jb, "size" column +1 on anl/cpl/mov). These need
  triage. They are either equivalent (table order makes the mask moot) or fields nothing reads. If
  the "size" column is really read, then that is untested.
- `gas-oporder-1541` and `dis-constpm1-62` (`buffer[2]` -> `[3]`) are equivalent mutants.

Remember M4: the population excludes the operand parser and the section/space code, so this 59%
says nothing about where the known bugs live.

## 5. Coverage gaps (no test at all)

- Generic `jmp`/`call` operand forms, and any must-reject instruction form.
- Link-time overflow: R_I51_16, R_I51_8_BIT, R_I51_H, R_I51_L. R_I51_11 across 64K.
- Relocation against a symbol in the wrong memory space (any kind).
- B2B/PCODE with a symbol at address 0.
- The `.8`/`.9` bit-suffix rejection (mutant gas-constpm1-454 survives).
- Disassembly of a truncated buffer (the read_memory error path).
- Malformed `r_type`, and R_I51_R1/R_I51_R3/R_I51_NONE in input objects.
- `.set`, `.equ` (beyond prose), `.rcommon/.icommon/.xcommon/...` aliases, `.using 1..3`.
- Tools: `strip`, `size`, `ranlib`, `objcopy -O ihex` beyond sim, and the `tb/i51elf_*.py` helpers
  are not exercised on i51 objects in any gate stage.
- Any functional test of arm64/macOS beyond check+isa, and of Windows beyond a probe at address 0.

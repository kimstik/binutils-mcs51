# Review 8: do the tests, docs and CI back the series? (lane r8-tests)

Scope: branch `claude/r6-fixes` at HEAD `ee28858`. My copy of the source tree, `review8/tests/src`, matches HEAD's `mcs51/additions.patch` byte for byte for tc-i51.c/.h, elf32-i51.c, i51-dis.c, elf32i51.sc and c-i51.texi.

The shared tree `work/modern/binutils-2.47` and the repo's `mcs51/*.patch` changed under me during the run: the repo shows uncommitted `M mcs51/additions.patch` and `M mcs51/modifications.patch`, and tc-i51.c gained a `tc_frob_label`. This report covers HEAD only. I made no edits outside `review8/`.

Workspace: `review8/tests/`. The pieces:
- `src/` and `build/` are the copy, configured with the brief's flags.
- `mutants.py` holds the 77 new mutants, `mutants_r7.py` the r7 set re-run, and `mutate.py` is the harness.
- `results*.json` and `logs*/` hold the results.
- `probes.py` and `probes*.json` show that each survivor behaves differently.
- `fullsuite.py` and `fullsuite.json` run the whole generic gas/ld/binutils suites per survivor.

The clean copy passes everything:
- the gate: 16 stages in 13 s;
- the i51 DejaGnu suites: gas 27/27, ld 31/31;
- the full generic suites: gas 260 PASS / 84 XFAIL, ld 252 / 234, binutils 170 / 66, with 0 FAIL, XPASS, ERROR or UNRESOLVED.

So "generic suites clean" (ee28858) holds.

## 1. Mutation testing

Each of the 77 new single faults was run as follows:
1. Rebuild (all built).
2. Run gas+ld `i51.exp`.
3. Run every gate stage except `doctruth`. `doctruth` reads `mcs51/additions.patch`, not the tree, so it cannot see a mutant.
4. For each survivor, run a probe that shows the clean and the mutant tools behave differently.
5. Then run the whole generic gas/ld/binutils suites on it.

### 1a. Killed (40)

| mutant | fault | killed by |
|---|---|---|
| op-whole, op-addend, op-nested, op-allowed | whole-operand rule, addend, nesting, `.equ` | operators-bad |
| rng-imm, rng-dir | range table rows | range-fwd, ranges-bad |
| rng-bit, rng-code16 | range table rows | ranges-bad |
| rng-high | HIGH() row | range-fwd, tb reloc |
| nooverflow-all | write.c data-range handoff off | range-fwd, ranges-bad, tb reloc |
| pcrel-addend | pcrel addend -1 | 4 ld/gas tests, tb branch/reloc |
| comm-alignmax, comm-alignfail, comm-align-val, comm-object | commons and parse_align | comm-bad, comm, align |
| comm-local-sec, rd-bssalloc | `.local` common, bss_alloc_section | **tb commons only** |
| eflags-gas, abi-gen0, merge-unknown, merge-out, common-def | ABI generation, merge_private_bfd_data, common_definition | eflags, align, ABI tests |
| rb-size | `__RB__` size | **tb commons/libsrc only** |
| mmcu-ignored | `-mmcu` | mcu |
| pcode-min, pcode-ind1, pcode-comma | `.pcode` | pcode, pcode-bad |
| space-branch, space-bitaddr | space checks | space |
| init-zero | init check | many |
| r8imm-range | R_I51_8_IMM range | **tb reloc only** |
| outsym-shndx | `ld -r` space index | merge, tb commons |
| secflags-direct | nm class | nm |
| dis-trunc | truncated instruction | truncated |
| dis-ddswap | mov dir,dir | **tb roundtrip only** |
| sc-misc | misc-sections in default script | **tb script only** |
| sc-ret | `__I51_RET` | many |
| rd-commnull | s_comm_internal NULL path | comm-bad |
| rd-listing | listing dummy frag | listing |
| b2b-bitnum | literal bit 8 | **tb bits only** |

### 1b. Killed only by the generic suites (4)

These suites run nowhere in the gate or in CI (see §3.1).

| mutant | fault | killed by |
|---|---|---|
| canon-section | section names folded | ld-elf/group4, linkonce notes, strip group 5 |
| canon-startof | `.startof.`/`.sizeof.` folded | gas `.startof. / .sizeof.` |
| re-32 | readelf R_I51_32 predicate (commit dcd1792) | gas DWARF2 1/2/3/5... (40 FAIL) |
| re-16 | readelf R_I51_16 predicate | gas DWARF2 5/7/11/12... (22 FAIL) |

### 1c. Survive everything, and the behaviour does differ (23)

Repro for each: `probes.py` in the workspace (the probe source is in `probes1.json`/`probes.json`).

| mutant | what goes unguarded | clean / mutant behaviour |
|---|---|---|
| **init-bitspace** | init check on the bit space. The manual cites `.bitdata` + `.bit 1` as refused. | `.bitdata`/`.bit 1` + `ld`: refused / links |
| **init-xdata** | init check on xdata | `.xdata`/`.byte 1`: refused / links |
| **rng-rel** | sjmp +127/+128 boundary in gas | `sjmp l` / `.ds.b 128` / `l:`: error / accepted (stores 0x80, a jump of -128) |
| **sc-bdata** | `ASSERT __BDATA_END <= 0x30` (README: "ASSERTs bound ... the bit space and the two external ones") | `.bdata`/`.ds.b 17`: refused / links |
| **sc-bitspace** | bit-space ASSERT | `.bitbss`/`.ds.b 0x81`: refused / links |
| **sc-xdata** | xdata ASSERT | `.xbss` 0x10001 bytes: refused / links |
| **sc-lchook** | lower-case startup hooks (README and manual) | object with `lcall __init_data`: binds to RET / undefined reference |
| **rb-defined** | "a program that defines `__RB__` itself is refused" | error / accepted |
| **rb-max** | `__RB__` sized by the highest `.using` | `.using 2`/`.using 0`: size 0x18 / 8 |
| **using-cleanup** | `.using` does not carry into the next input file | `as a.s b.s`: "missing .using" / accepted |
| **secname-dot** | the space of a `.xdata.foo` or `.data.foo` style input section | `ljmp x` in `.xdata.foo`: refused / links |
| mmcu-8052 | `-mmcu=8052` names | `mov a,t2con`: `e5 c8` / R_I51_8_DIR T2CON |
| mmcu-unknown | unknown `-mmcu` | error / silently accepted |
| r16-range | R_I51_16 -65535 bound (ee28858) | `--defsym Y=-65536`: truncated / links |
| rng-11 | constant acall/ajmp target > 0xffff | error / accepted |
| direct-0x80 | gas direct check at exactly 0x80 | error / accepted |
| high-const | HIGH() constant range (also open in r7) | `#high(0x10000)`: error / accepted |
| bitsuffix-imm | `#0x20.3` (manual: a bit address is accepted only where a bit is expected) | error / accepted |
| pcode-oprange | `.pcode` operand range | error / accepted |
| pcode-swap1 | 2nd `.pcode` operand cannot swap | error / accepted |
| space-dir-indirect | `.idata` symbol below 0x80 by direct | links / refused (the clean behaviour matches the manual, but nothing pins it) |
| dis-page | ajmp/acall target page is taken from the next instruction | `ajmp` at 0x7fe prints `850` / `50` |
| oe-symver | `.symver` version-name folding (ee28858) | `@@@vers` then `@@@VERS`: accepted / "only one version name". The full suite shows it only as an XPASS of `symver2`. |

### 1d. Survivors I could not tell apart from the clean tools (likely equivalent; 10)

- b2b-fix-bitnum: the `where[0] > 7` check in md_apply_fix is dead code, because every path checks the bit number earlier.
- ordcomm-space: `*COM*` maps to SPACE_ANY anyway.
- re-rela and re-none: guess_is_rela matters only without section headers.
- dis-abs and dis-sjmp-type: objdump output is identical. `--visualize-jumps` treats condbranch the same.
- sc-r-misc and sc-r-eeprom: orphan placement in `ld -r` gives the same section order.
- shdr-common: no current producer writes SHF_I51 NOBITS.
- oe-commonrest: no visible difference.

### 1e. Re-running the r7 survivors on HEAD

| r7 survivor | status now |
|---|---|
| init-relocs | killed (init-reloc) |
| assert-iram | killed (iram) |
| dir-ovf | killed (dirovf) |
| r8-compat | killed (reloc8) |
| init-load-exempt | killed (load) |
| using-range | killed (using-bad) |
| highlow-msg | **still tb reloc only**. operands-bad.l is now pinned, but no `.l` file holds "not allowed on a code or bit address". |
| high-const | **still survives** (§1c) |
| dollar-lex | survives, probably equivalent: `nop$nop` and `x$y:` behave the same, because line_separator_chars wins |
| dis-insntype | the code was rewritten; its stand-in dis-sjmp-type looks equivalent |
| shf-bits, checkdirect | the code was rewritten; covered by shf.d and direct-bad.l |

The 31 other r7 mutants still apply and are all killed by DejaGnu.

## 2. Ranked findings

1. **HIGH: the generic suites guard four claimed fixes, and nothing runs them.** The four are canon-section, canon-startof, re-32/re-16 (commit dcd1792 "apply i51 relocations in DWARF sections") and oe-symver. ee28858's "generic suites clean" is true today, but:
   - the gate's `dejagnu` stage is `make check RUNTESTFLAGS=i51.exp`;
   - no workflow runs `check-gas`, `check-ld` or `check-binutils`.

   So a regression in any of these, or a new generic FAIL, reaches main green. Repro: apply `re-32` from `mutants.py`. The gate passes, and `make -C build check-gas` gives 40 FAIL.
2. **MEDIUM: these documented behaviours have no test at all** (§1c, the bold rows):
   - the init check for the bit space and for xdata, although the manual names `.bit 1` in `.bitdata`;
   - the bdata, bit-space and xdata ASSERTs, which README claims;
   - the lower-case startup hooks, which README and the manual give a paragraph each;
   - the `__RB__` rules: defining it is refused, it is sized by the highest bank, and `.using` is per file;
   - the space of suffixed sections (`.xdata.foo`);
   - the sjmp/jcc +127/+128 boundary in gas;
   - the R_I51_16 -65535 bound from ee28858.
3. **MEDIUM: four behaviours are pinned only by tb stages, not DejaGnu.** Upstream binutils would not see them:
   - `.local` space commons and bss_alloc_section's segment (tb commons);
   - `__RB__` size (tb commons/libsrc);
   - mov dir,dir disassembly (tb roundtrip);
   - the HIGH/LOW-on-code/bit message of 95ecb8d (tb reloc).
4. **LOW: the manual's `.bit` entry is inaccurate.** It says "`HIGH ()` and `LOW ()` are not accepted here", but `.bitdata` / `.bit high(0x100), low(1)` assembles without a diagnostic, because a constant operand folds. Only an unresolved operand is refused.
5. **LOW: `.comm` and `.xcomm` of one name link silently** (documented: "A plain .comm names no space and is never compared"). The address then depends on link order: `.comm buf,4` in a.o and `.xcomm buf,4` in b.o give BUF=0x20 (direct RAM) for `a.o b.o` and 0 (xdata) for `b.o a.o`. It is worth a sentence in the manual, or a warning.
6. **LOW: MUTGATE includes `doctruth`, which reads the repo's patch, not the mutated tree.** It can never kill a mutant, so coverage.yml's table will always show it with zero kills.

## 3. Docs, README and CI

**c-i51.texi.** I checked every `doctruth: diagnostic` block and quoted value against the tools. All hold except item 4 above. What I checked:
- the diagnostics: r0, ES, whole-operand, "allowed only as an instruction operand" (`.equ`, `.org`, `.sleb128`, `.pcode`), BUF at 0x90, `.quad` 8 bytes, and the commons message (the manual's example has the other link order);
- `.byte ACC,CY` = e0 d7; PSW.3 = d3, IE.7 = af, TCON.4 = 8c, 0x20.3 = 03, 0x90.5 = 95; `#HIGH(0x1234)+1` = 0x13;
- `.ds 3` = 6 bytes and `.ds.b 3` = 3; `.using 4` refused; `.using 1+1` works; the B2B rules on a literal, a resolved symbol and the linker;
- the `.pcode` address range 0x100..0x1fff; the common alignment cap 0x10000;
- R_I51_8 ±255, R_I51_16 ±65535 and R_I51_8_IMM -128..255, in gas through write.c and in ld;
- the `-mmcu` sets, `-g`/addr2line, `.word` big-endian and `.float`;
- `__STACK_SIZE` 16 (`.idata .ds.b 0xd0` links, 0xd1 does not, 0 lifts it), `__IRAM_SIZE=0x80`, and `__EEPROM_SIZE` with no limit unless set (0x800 refuses 0x801);
- the EEPROM objcopy command (`:03000000010203F7`; plain `-j .eeprom` gives an empty hex);
- nm classes d/D, with `.idata` as i/I; `size` text = code only; ABI generation (gen 0 → align 1; gen 2 and flags 0x10 refused; `ld -r` writes 1);
- the jmp/call long forms; acall/ajmp always go to the linker; all the manual's examples assemble.

The r7 HIGH() defect (`#high(sym)+1`) is fixed. `-high`, `~low`, `*1`, `|0`, `+1` and `1+` are now refused.

**README.**
- Sixteen stages plus the canary = 17, matching release.yml and `gate-list`. `BUILD` is explained for `gate`.
- The 2001 script really is 235 lines with 6 MEMORY regions and no ENTRY.
- `i51-elf` → `i51-unknown-elf`; bare `i51` → `i51-unknown-none`, which config.bfd's `i51-*-*` accepts.
- LOW: "`make -C tb dejagnu` runs them" still omits `BUILD=` (the default is the frozen tree).

**CI.**
- r7's HIGH is fixed: coverage.yml installs `dejagnu`.
- `ci-list` = `$(GATE)` + canary in CI order, and `gate-list` has 17 words = release.yml's `want`.
- OPTFLAGS defaults to `-Os -flto` (r7 LOW fixed).
- Reproducibility is fixed:
  - BUILD-INFO `built:` is the commit date (`DIST_DATE`, or SOURCE_DATE_EPOCH);
  - Package uses `TZ=UTC`, `touch -d @epoch` (GNU coreutils on macOS via gnubin), `zip -X` over sorted names, and `tar --sort=name --mtime`/`gzip -n`.
- Stale comments (LOW):
  - release.yml: "$(GATE): the thirteen toolchain stages, then check and oracle". `libsrc` is missing from that sentence.
  - tb/Makefile:746: "the sixteen names it names in the release body". The body says seventeen.
- Not verifiable offline: the action SHAs, `sdcc-ucsim` on ubuntu-24.04-arm, and brew `deja-gnu`/`p7zip`.
- **See §2.1:** no CI job runs the generic suites, although ee28858's correctness claims rest on them.

## 4. Testsuite markings (sampled 22, checked against the logs of a full run in my build)

The reasons are true for every sample:

| test | stated reason | what the log shows |
|---|---|---|
| gas/elf pr27228 | NAME.N | `.LTHUNK5.lto_priv.0` → "B2B() of a value not known here" |
| `.org test 4`, struct, `macro test 1`, symver0, Multibyte syms, `weak and common` | folding | `BAR` vs `bar`, `FOOBAR` |
| macros `strings` | ONLY_STANDARD_ESCAPES | `unknown escape '\a'` |
| SHF_GNU_RETAIN 1a, warn3, Regular archive link, comm-data4 (notarget) | init data refused | "initialized data in internal RAM" (plus `(AA)` folding for the archive test) |
| pr24511, pr26256-1b | no region for writable orphans | `no memory region specified for loadable section .init_array.01000` and `__patchable_function_entries` |
| pr22450 | 16-bit addresses | `.dc.a` is 2 bytes → `corrupt GNU_PROPERTY_TYPE (5) size: 0xa` |
| readelf relr | `.dc.a` 16-bit | `.dc.a 0x1234` → `12 34` |
| provide-1, var1, DEFINED, `--entry foo archive`, sort-common, readelf -r, objcopy group | folding | `undefined symbol var2`, `EXTERNAL_SYMBOL`, `VAR_*` |

Minor: in sec64k.exp the `i51` clause is reachable (is_generic is false for i51), so it is not dead.

# Where the work stands, and what is next

Code branch: `claude/r6-fixes`, HEAD b47a487, gate green (16 stages, the
dejagnu stage runs the full gas/ld/binutils suites, 0 unexpected).
Reviews: r8-*.md (fixed in f681863, 11c5fba, 907bdd9, b47a487) and
r9-quality.md / r9-tests.md (open, list below).

## Progress
- [x] -mcase-sensitive + dot rule: 9e66673 (gate green).
- [x] bfd: M1, M2, LOW3, LOW4, LOW9, LOW14 + ld tests: 1705e45.
- [x] gas: LOW1,2,5,6,7,8,11,12,13,15,16 + gas tests: bf7eb5c.

## Decision by the owner
Symbol names: fold to upper case by default (compatibility), plus an option
to turn folding off.  Started (uncommitted, in wip-r9-*.patch, which are the
full mcs51 patches including it):
- `-mcase-sensitive` gas option, `i51_fold_case`;
- tc_canonicalize_symbol_name: a name starting with `.` keeps its case
  (sections, .startof./.sizeof.; no section lookup any more; fixes r9-quality
  LOW 10).  The corpus has no dot-names.
Still to do for it: manual (-mcase-sensitive in Options, the dot rule in
Case), NEWS, a gas test (case-sensitive: foo and Foo distinct), md_show_usage
is done.

## Resume
1. `make -C tb build WORK=<w>` (or reuse), then replace mcs51/*.patch with
   reviews/wip-r9-*.patch, rebuild, `make -C tb gate WORK=<w> BUILD=<w>/modern/build`.
   Rule: refresh patches BEFORE the gate (doctruth reads the patch);
   never push red.

## Open r9 items (fix each, add a DejaGnu test)
gas (tc-i51.c):
- LOW1 SFR.N (TCON.4) used then defined: note full NAME.N in i51_names_used
  on the built-in path of i51_parse_name too.
- LOW2 built-in used then `.global/.weak` without definition: i51_frob_symbol
  should also check external/weak undefined symbols.
- LOW5 `.bit` range checked only for a literal (forward equ / extern).
- LOW6 pcode byte with extern and negative addend refused by write.c: set
  fx_no_overflow unless fx_done for BFD_RELOC_8/16/32 (ld checks the value).
- LOW7 `#SWAP` constant range: use the HIGH range -32768..65535.
- LOW8 `.comm` default align: also for `,"bss"` and `,0` (S_GET_ALIGN==0).
- LOW11 `.pcode 0x200 (1)`: address scan stops at `(` after a term.
- LOW12 bare WORD/BYTE/SWAP/SHL8 keyword is a symbol when one exists.
- LOW13 built-in bit name keeps its class: set i51_operator_class from
  i51_builtin_value (`mov a,#P1.1` refused like `#0x90.1`).
- LOW15 `.comm __RB__` / `.equ __RB__`: report at the line (common_parse).
- LOW16 `@r 0`: no whitespace skip inside the `@` name (scrubber already
  removes the others); test `@a+dptrx` refused.
bfd (elf32-i51.c):
- M1 ordinary .comm vs a definition in another space: refuse (manual says so).
- M2 `.rodata`, `.rodata.*`, `.gnu.linkonce.r.` are CODE in i51_section_spaces.
- LOW3 SEC_KEEP only on `.regbank` (other unreferenced space commons GC'd).
- LOW4 R_I51_13_PCODE needs a code target in i51_check_space.
- LOW9 two space commons of different sections (.bcomm vs .rcomm) refused.
- LOW14 i51_check_space gets the sign-extended value (message 0xfff..).
Tests the mutants showed missing (r9-tests §1c/§2): ordinary common vs
.xcomm in BOTH link orders; R_I51_7_PCREL bounds (Y=0x10000 from 0xfffe,
Y=-1); malformed alignment st_value 0, 3, 0x20000 separately; direct check
in `.data.foo`; xdata symbol at 0x90 left to ld; `.pcode 0x200) 1`;
`.pcode (0x100)*2 1`; `WORD 65536`; `BYTE -256`; `SHL8 0` -> 02 00 00;
`.comm x,4,4` keeps 4; `.using` per file (`as a.s b.s`); `.idata` byte <0x80
as a direct operand links; ajmp at 0x7fe to 0x850 disassembles as 850;
edata ASSERT; ld -r -g keeps DWARF order; b-dir-neg / r8imm-range /
b2b-bitnum into DejaGnu.
Docs/harness: manual .pcode "zero byte" wording (the operand is zero);
manual commons text vs the ordinary-common rule; tb/Makefile:624 "twelve" ->
13; tb/mutation/run.py docstring (doctruth, WORK use); gen.py/REBUILD_MARK
should cover binutils/readelf.c and include/elf/i51.h; oversize commons
(>0xFFFF) only warn - document or refuse.

Then: gate, clean-room build (`make -C tb build` into a fresh WORK), round 10
review (quality + tests lanes), repeat until clean.  Final report: only
"done" and "impossible in the repo" (branch deletion/tag push via proxy 403;
copyright assignment/DCO; config.sub upstream; `.ds` stays 2 bytes/unit by
decision).

# r6-fixes: C correctness review (UB, memory safety, parser state)

Tree: work/modern/binutils-2.47 (HEAD of claude/r6-fixes). Build used: review7/asan
(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all). Repros live in
review7/probe and review7/fuzz/*/crash.

## Findings, ranked

### 1. CRITICAL: `HIGH(sym)±c`, `B2B(sym,n)±c` and `sym.N±c` assemble silently to the wrong value
tc-i51.c:721-733 (i51_apply_operator) keeps the operand's addend in X_add_number of
an O_md1/O_md2/O_md3 expression. Generic gas expr.c:1941-1987 ("X + constant",
"X - constant", "Constant + X") folds any `± constant` into X_add_number whatever X_op is.
So the constant moves inside the operator. A constant operand folds correctly, which
makes the two paths disagree:

    .global X ; .equ X,0x1234 (other file);  .equ X2,0x20
     mov a,#HIGH(X)+1      -> R_I51_H X+1  -> 74 12   (should be 0x13)
     mov a,#HIGH(0x1234)+1 ->                 74 13
     mov a,#HIGH(X)-0x13   -> 74 12            (should be 0xFF)
     setb X2.0+1           -> R_I51_8_B2B X2+1 -> d2 08 (should be bit 0x01)
     jb B2B(x,3)+1,. / .byte HIGH(x)+1 / 1+HIGH(x): same

No diagnostic is printed. `LOW(x)±c` is the same value mod 256, so only its range check
is lost. Fix: add md_optimize_expr. It should refuse arithmetic on an O_i51_* left or right
operand, or wrap the operator result with make_expr_symbol so that X_add_number
means a post-operator addend.

### 2. CRITICAL (narrow): `.org HIGH(fwd)` becomes `.org 0`
` .org HIGH(y)\n nop\n .equ y,0x1234` assembles with rc=0 and .text size 1. It should
`.org 0x12`. The O_md expression symbol resolves to 0 without a diagnostic (see 3).

### 3. HIGH: gas internal error (abort) whenever an operator result is not consumed by fixup8/cons
"symbol definition loop ... Internal error in S_SET_SEGMENT at symbols.c:2519" happens
in both the ASAN build and the normal build. Triggers:
- nested operators: `mov a,#HIGH(LOW(x))`, `setb B2B(B2B(x,1),2)`, `.byte HIGH(x.3)`. These go
  through tc-i51.c:729 make_expr_symbol(arg) with arg->X_op = O_md*.
- `mov dptr,#HIGH(x)`: fixup16 (tc-i51.c:1754) never calls i51_strip_operator.
- `.pcode 0x100 HIGH(x)` and `.pcode HIGH(x)`: pcode_byte, pcode_word and i51_pcode pass
  O_md* to fix_new_exp.
- `.equ y,LOW(x)` then any use of y, `.sleb128 HIGH(x)`, `#HIGH(x)-HIGH(y)`.
Fuzzing hit this in about 920 of 48.7k gas cases. Fix: an operator result must be stripped or
refused at every consumer, or md_optimize_expr must refuse it inside a larger expression.
`.equ`, `.org` and `.pcode` must refuse it too.

### 4. HIGH (silent): `.xcomm buf,8` then `.comm buf,8` in one file moves buf out of its space
The check at tc-i51.c:1987 only covers the direction space-common then space-common. For
.comm, elf_common_parse (:1970) runs without it. The repro (`... mov dptr,#buf; movx a,@dptr`)
assembles and links silently, and BUF ends up as internal RAM 0x20. The reverse order
is refused.

### 5. HIGH: per-file md_cleanup corrupts `__RB__` when gas is given several input files
i51_cleanup (tc-i51.c:1845-1862) runs after each input file. It overwrites
`__RB__` and resets regused. `as f1.s f2.s` gives f1 `.using 3; mov a,ar7` and f2
`.using 0`. The result is `__RB__` size 8, but bank 3 needs 32 (`as f2.s f1.s` gives 32). The
register-bank reservation is silently too small.

### 6. HIGH (assert): a user-defined `__RB__` label aborts gas
`__RB__: .using 1` gives "Internal error in i51_cleanup at tc-i51.c:1858" from `know()`.

### 7. LOW
- `setb flags.10`: a bit suffix of two or more digits is silently a reference to an
  undefined symbol `FLAGS.10`. NAME.N only looks at one digit (tc-i51.c:806).
- The include/elf/i51.h R_I51_8 comment says the linker "says nothing about the rest".
  elf32-i51.c:544 actually rejects values outside -128..255.
- `.local x; .rcomm x,4,0x8000000000000000` is accepted, giving frag_align(63). The global form
  truncates the alignment into the 32-bit st_value.
- elf32_i51_final_link judges non-ELF inputs by section name, so `ld ... -b binary blob`
  (.data) is refused as "initialized data in internal RAM".
- Upstream, not the port: UBSAN shift-exponent-32 at linker.c:3172 and elflink.c:10942
  for SHN_COMMON st_value=0xfffffffe, and abort() at elflink.c:10694 for a weak SHN_COMMON.

### Checked clean
These were checked and found clean, by reading the code and by tests:
- i51_parse_name restore/write-back on every path, including end of buffer and `HIGH` without `(`.
- extract_word, i51_builtin and pcode_keyword bounds.
- md_apply_fix: fx_addsy is never NULL on the 7_PCREL path, because write.c:1124 substitutes abs_section_sym.
- i51_final_link_relocate offset checks: 0 silent out-of-bounds links in the sweep.
- relocate_section with sec NULL or undefweak.
- check_common_space.
- section_flags (bfd_section is set before the hook).
- The disassembler table: bytes consumed equal insn_size for all 112 rows. A failed read
  falls back to the sentinel.
- The fixup8, fixup11 and fixup16 expression counts against the opcode table. The three
  clang-analyzer NULL warnings are false positives.

## Tools and statistics
- gcc 13 -O2 -Wall -Wextra -Wshadow -Wformat=2 -fanalyzer on the 3 port files gives 0 warnings.
  -Wconversion gives only benign masked narrowings. clang --analyze gives 3 false positives
  (tc-i51.c:1641/1738/1758).
- DejaGnu under ASAN+UBSAN: gas i51.exp 18/18 and ld i51.exp 18/18.
- tb under ASAN+UBSAN: isa, reloc, guard, bits, branch, commons, script, disasm,
  defaultlink, roundtrip and check (10/10 ROMs) all pass, with 0 sanitizer reports.
- gas fuzz (grammar plus opcode-table-driven; also -g --gdwarf-5, --gstabs, and with ld -r/ld/objdump
  on the outputs): 48,700 cases. Sanitizer reports: 0. Internal errors: 929, all
  in families 3 and 6.
- ld fuzz (structure-aware ELF mutation of relocs, symbols, shdr flags/sizes/names; ld, ld -r,
  ld -r then ld, --gc-sections, objdump -dxr, nm): 12,200 objects plus an exhaustive sweep of
  3,042 reloc types × offsets and reserved st_shndx values. Port findings: 0. Upstream:
  3 UBSAN and 10 aborts (item 7).
- Disassembler: 249k inputs under ASAN+UBSAN (every opcode × truncation × random tail,
  plus random streams), 51k under valgrind memcheck, and 400 random blobs through
  objdump -D. Findings: 0.

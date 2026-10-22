# r9-quality: correctness review of the MCS-51 port (binutils 2.47)

Tree: `work/modern/binutils-2.47` (read only), copied to `review9/quality/src`. Sanitizer build:
`review9/quality/asan` (`-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all`).
Scripts: `review9/quality/scripts` (`t.sh` = assemble one snippet and print diag/.text/relocs; fuzzers
`gfuzz.py`, `gvalid.py`, `diff.py`, `lfuzz2.py`). Cases: `review9/quality/t`.
In repros, `as`/`ld`/`nm`/`objdump` are `as-new`, `ld-new`, `nm-new`, `objdump` from either build; `ld` uses the
built-in default script.

No CRITICAL or HIGH findings.

## MEDIUM

### M1. An ordinary `.comm` is silently satisfied by a definition in another memory space
`elf32_i51_check_common_space` (bfd/elf32-i51.c:993-994) returns early when neither side is a
*memory-space* common. A plain `.comm`, which the same function treats as internal RAM elsewhere
(`i51_common_space`, :963-969), can therefore be resolved by a definition in `.xdata`, `.xbss`, `.bitbss`,
`.ebss` and so on. The generic rule that a definition beats a common then applies. This is the defined-symbol
counterpart of r8 HIGH-4: `.comm X` against `.xcomm X` is now refused, but `.comm X` against a defined `X` in
`.xbss` is not. The manual says (Memory Spaces) "nor can a common of one space be satisfied by a definition in
another".

    c6.s:  .comm X,10 / mov r0,#X / mov a,@r0
    c2.s:  .xdata / .global X / X: .space 4 / .text / mov dptr,#X
    as c6.s -o c6.o; as c2.s -o c2.o; ld -e 0 -o cc.elf c6.o c2.o   -> rc 0
    nm: 00000000 D X;   78 00 e6 ... 90 00 00
The internal-RAM user reads `@R0` with R0 = 0, which is bank-0 R0, not a 10-byte buffer. A direct `mov X,a` is
caught later only because R_I51_8_DIR is space-checked; an immediate or `@R0` use is never checked.
Expected: the same "symbol `X' is in ... here and in ..." refusal as for `.comm`/`.xcomm`.

### M2. `.rodata` (code space in the default script) escapes every relocation space check
`i51_section_space` (bfd/elf32-i51.c:391-410) classifies a section as CODE only by SEC_CODE. Otherwise it
classifies by name, and the list has no `.rodata`. The default script places `.rodata`, `.rodata.*` and
`.gnu.linkonce.r.*` in `.text`, but they are I51_SPACE_ANY, so `i51_check_space` accepts every operand kind
against them.

    a.s: .global _START / _START: mov a,T / setb T / .section .rodata / .space 3 / T: .byte 1
    as a.s -o a.o && ld -o a.elf a.o   -> rc 0;  e5 09 / d2 09    (direct and bit address 9 = a code address)
The same program with `T` in `.text` is refused ("a direct address cannot name code memory", "a bit
address cannot name code memory"). Constant tables in `.rodata` are what a C compiler emits.

## LOW

1. **Using SFR.N and then defining it is not refused, but the rule requires that.** `i51_parse_name` (tc-i51.c:903-913) records only the
   base name for an SFR that is not in the table (`TCON.4`, `PSW.3`, `IE.7`, through `i51_builtin_value`, which notes
   `TCON`). A later definition of `TCON.4` is not refused:
   `' setb TCON.4\nTCON.4: nop\n setb TCON.4\n'` gives rc 0, `d2 8c ... d2 00 (R_I51_8_BIT .text+2)`. `' setb PSW.3\n .equ PSW.3,0x20\n setb PSW.3\n'`
   gives `d2 d3 d2 20`. The names in the table (`ACC.3`, `P1.1`) are refused as the manual says.
2. **A built-in name used first and then declared with `.global` or `.weak` without a definition** gets two meanings in one
   file with no diagnostic. i51_frob_symbol (tc-i51.c:685) only looks at defined symbols.
   `' setb ES\n .global ES\n setb ES\n'` gives `d2 ac` followed by `d2 00 R_I51_8_BIT ES`.
3. **`--gc-sections` never removes an unreferenced memory-space common.** The r8 HIGH-2 fix puts SEC_KEEP on every fake common section
   (elf32-i51.c:949-951), not just `.regbank`. `.rcomm RV,8 / .icomm IV,40 / .comm CV,8 / .xcomm XV,100` used only
   from a section that GC drops: `ld --gc-sections` removes `COMMON` (CV) but keeps RV, IV and XV.
   That costs scarce internal RAM, and ordinary commons behave differently.
4. **R_I51_13_PCODE (a code address) has no space check** (i51_check_space default case, elf32-i51.c:460).
   `_START: .pcode XV 1` with `XV` at xdata 0x200 links, rc 0, `02 00 40 01`. `ljmp XV` is refused.
5. **The `.bit` range 0..1 is checked only for a literal** (tc-i51.c:1687). `.bit K` with a forward `.equ K,2` gives
   `02`, with K=-1 it gives `ff`, and an extern goes through R_I51_8, -255..255. Differential fuzz: 13 cases. The manual says "each of
   which must be 0 or 1".
6. **A pcode byte operand with an extern symbol and a negative addend is refused by write.c**, but its constant and forward
   forms are accepted. `pcode_byte` uses BFD_RELOC_8, and md_apply_fix leaves `fx_no_overflow` clear for it
   (tc-i51.c:1491-1493), so the generic addend check fires before the symbol is known.
   `.pcode 0x200 @K-256` with K=0xf8: the constant and forward forms give `82 00 40 f8`. Extern K gives "value of ffffff00 too large
   for field of 1 byte". The same happens for `@BYTE`/`@SWAP` (4 differential cases).
7. **The `#SWAP` range depends on the form.** A constant is checked as a word, -65535..65535 (pcode_flags, tc-i51.c:2096).
   A symbol goes through R_I51_L + R_I51_H, whose range is -32768..65535 (tc-i51.c:2053-2056). `.pcode 0x200 #SWAP -40000`
   gives rc 0, `02 00 c2 c0 63`. The same value through a forward `.equ` gives "operand of HIGH() out of range: -40000".
8. **The `.comm` default alignment is incomplete** (tc-i51.c:1814-1818: "aligned" means only "a comma follows").
   `.comm Y,4,"bss"` gives st_value 4, which is min(size,16), although no alignment was given. `.comm X,4,0` gives 4, while
   `.xcomm Z,4,0` gives 1. The manual says "A common that gives no alignment is aligned to a byte".
9. **The manual and the linker disagree on commons.** In c-i51.texi (Memory Spaces): "A plain `.comm` names no space and is never
   compared this way". The linker now refuses `.comm X` against `.xcomm X` (r8 HIGH-4 fix). Also, `.bcomm X` and
   `.rcomm X`, which the manual's table lists as separate spaces, are arbitrated by size because both are
   I51_SPACE_DIRECT (elf32-i51.c:998). The user sees only a later "R_I51_8_B2B ... 0x8 is not bit addressable".
10. **A section name used before its `.section` gets a folded symbol of its own** (tc-i51.c:544-547 checks only whether the
    section already exists). `' mov dptr,#.mysec\n .section .mysec,"a"\n .byte 1\n .text\n mov dptr,#.mysec\n'`
    gives `R_I51_16 .MYSEC` (undefined at link) and then `R_I51_16 .mysec`.
11. **A `.pcode` operand in parentheses cannot follow the address.** The scrubber drops the space before `(`, and the
    address scanner (tc-i51.c:2151-2164) then takes `0x200(1)` as the address. `.pcode 0x200 (1)` gives "junk in pcode
    address: `(1)'". The same happens for `.pcode X (Y)`. The reverse direction is lax: `.pcode 0x200@1`, `.pcode 0x200#1`
    and `.pcode (0x200)1` are accepted with no white space, which the manual requires.
12. **The bare pcode keywords hide symbols of the same name** (tc-i51.c:1942-1943). With `.equ WORD,0x1234`,
    `.pcode 0x200 WORD-1` assembles silently as keyword WORD with operand -1 (`02 00 c0 ff ff`), not 0x1233.
    BYTE, SWAP and SHL8 behave the same way.
13. **The bit/byte class of a built-in name is not kept the way an operator's class is.** i51_builtin_value
    (tc-i51.c:655-668) does not set `i51_operator_class`. So `mov a,#P1.1` gives `74 91` while `#0x90.1` and `#B2B(0x90,1)` are
    refused ("a bit address is not a number"). Likewise `mov a,P1.1+0` gives `e5 91` while `mov a,B2B(0x90,1)+0` is refused.
14. **Misleading linker diagnostic for a negative direct address.** i51_check_space receives the unsigned
    `relocation + r_addend` (elf32-i51.c:649), not the sign-extended value. `_START: mov RX-9,a / .rcomm RX,1` reports "RAM at
    0xffffffffffffffff is not directly addressable, 0x80 and above is the special function register page".
15. **The `__RB__` errors from i51_frob_symbol have no line number** (tc-i51.c:678-682). `.equ __RB__,5`, `.comm __RB__,4`
    and `.set __RB__,.` give "x.s: Error: ...". `.using 1 / .weak __RB__` gives the generic "can not be both weak and
    common" instead of the port's message.
16. **The `@` operand accepts white space inside the register name** (tc-i51.c:1030-1037). `mov a,@r 0` gives `e6`.
    This is cosmetic.
17. **Still present from r8 LOW 12 (upstream):** UBSAN in linker.c and elflink.c on a huge SHN_COMMON alignment. It was not hit this
    round, because the mutators drove space-common st_value into the new port check.

## Verification of r8-quality findings

| r8 | Status |
|---|---|
| HIGH-1 gas segfault on branch to `X - undefined` | Fixed. `sjmp .-y`, `jb 0x20.1,l-y`, `djnz r0,l-y` and `jnc fwd-bits` give the two "can't resolve" errors and rc 1, with no crash (guard at tc-i51.c:1503,1521-1523). |
| HIGH-2 `--gc-sections` drops `__RB__` | Fixed. With and without GC: `__RB__` at 0, RV at 0x10, `75 08 05 / 75 10 07`. Over-broad: see LOW 3. |
| HIGH-3 R_I51_8_DIR/BIT wrap mod 0x10000 | Fixed. K=0x10030 gives "relocation truncated to fit" for DIR and BIT. `sjmp K` is refused too (srel checks, elf32-i51.c:527-543). |
| HIGH-4 `.comm` in one object pulls `.xcomm` of another | Fixed for common against common, in both orders. Residue: M1 (common against a definition). |
| MEDIUM-1 `.lcomm`/`.tls_common` after `.xcomm` | Fixed: "declared a common of .xbss here and placed elsewhere" (the location given is the `.xcomm` line). |
| MEDIUM-2 negative absolute extern refused | Fixed. `.equ K,-1` extern: all five uses link (`74 ff 24 00 ff ff ff 74 ff`). |
| MEDIUM-3 `.pcode 0x200 -1` | Fixed: `02 00 c0 ff ff`. `+X` is an operand too. New residue: LOW 11 and 12. |
| LOW 1 SHL8X | Fixed. It is a symbol: `02 00 c0 12 34`. |
| LOW 2 `#SWAP`/`@SWAP` second operand | Fixed. Constant and symbol are both refused ("cannot be swapped"). |
| LOW 3 `@BYTE 0x100` constant vs forward | Fixed. Both give `82 00 40 ff`. |
| LOW 4 numeric `.N` binding | Fixed. `1+0x20.1`, `0x20.1+1` and `0x20 .1` are refused, as documented. NAME.N binding to the name is documented. |
| LOW 5 `0x20.8` diagnostic | Fixed: "bit number 8 is not 0..7". |
| LOW 6 i51_check_direct on a code label | Fixed. Only internal-RAM sections are checked in gas, and ld reports "cannot name code memory". |
| LOW 7 user common `__RB__` hijacked | Fixed. It is refused, but without a line number (LOW 15). |
| LOW 8 `.comm` default alignment | Mostly fixed (st_value 1). Residue: LOW 8. `__RB__` has st_value 1. |
| LOW 9 NOBITS + bit 31 becomes a common | Fixed for generation 1: only generation 0 objects are reinterpreted. In generation 1, bit 31 is plain SHF_EXCLUDE. |
| LOW 10 direct link vs `ld -r` path | Fixed. nm output is identical, and the RAM sections are NOBITS through the fake_sections hook. |
| LOW 11 `-b binary` refused | Unchanged ("initialized data in internal RAM"). This matches the documented rule. |
| LOW 12 upstream UBSAN | Unchanged upstream. Not hit this round. |

## Checked clean
- New pcode logic. The address scanner covers parentheses, a leading sign, `#`/`@`, operators inside parentheses,
  HIGH/LOW/B2B of constants, built-in names and NAME.N, and gives a clean error for every malformed form.
  Constant ranges (byte -255..255, `@BYTE` stored -255..255, word -65535..65535) match the fixups of the symbolic
  forms, except LOW 6 and 7. The presence rule of `@BYTE` (`0` left out, `1` stored as `00`, `0x100` stored as `ff`) is
  the same in pcode_byte and pcode_flags, and the flags and the bytes agree in all 3,000 differential cases.
- i51_names_used: built-in, ARn, `@Rn` and register uses, then a definition, are refused at the use line. NAME.N used
  and then defined is refused.
- i51_common_decls / i51_check_common: `.lcomm`, `.tls_common`, a label and `.set` after `.xcomm` are refused.
  `.local` + `.xcomm` allocation is accepted.
- The `__RB__` refusal paths: label, `.equ`, `=`, `.set`, `.equiv`, `.comm`, `.rcomm`, `.lcomm` and `.tls_common`, before and
  after `.using`, with no double report. A reference to `__RB__` still works.
- tc_canonicalize_symbol_name: section symbols, `.startof.`/`.sizeof.`, `.file` symbols and DWARF section
  symbols keep their case.
- dwarf2_emit_label through i51_frob_label: `-g`, `--gdwarf-3` and `--gdwarf-5` give line tables identical across the
  three options, and the same after the link.
- The `@` operand with spaces, `@A + DPTR` and `@ DPTR`, with clean errors for `@r2`, `@`, `@@r0` and `@r0+1`.
- The operator "whole operand" rule over 14 algebraic forms.
- bfd: the sign extension (srel), the DIR/BIT/IMM/H/16/16_CODE/7_PCREL/11/PCODE/B2B range checks, a weak target in the
  same section (correct displacement after the link), and e_flags (generation 0 accepted with alignment forced to 1,
  generation 2 and stray bits refused). The add_symbol_hook alignment check (0, 3, 0x20000 and 0x80000000 refused,
  0x10000 accepted) works on direct links and on `ld -r`. `ld -r` → `ld` gives the same nm as a direct link with
  seven kinds of space commons and `.using` 2/3 (`__RB__` 0x20). The fake_sections NOBITS hook works, and so does the documented
  `objcopy -j .eeprom` extraction.
- Disassembler: 151 inputs (all opcodes with truncation, plus 150 random blobs) × 3 VMAs (0, 0xfff0, 0xf7fe), with
  `--visualize-jumps=extended-color`. 0 sanitizer reports. AJMP across 0xFFFF wraps correctly.
- readelf: the EM_8051 RELA and abs-reloc predicates.

## Statistics
- gas grammar fuzz (ASAN/UBSAN). Every case was also run with `-alsmgn` and compared, then put through objdump, nm, readelf,
  `ld`, `ld -r` and `--gc-sections`. 16,000 cases (561 assembled): 0 crashes, 0 sanitizer reports, 0 listing
  differences.
- gas valid-program fuzz: 3,000 cases (1,310 assembled). Same tool chain, plus `ld -r` → `ld` compared with a direct
  link: 0 crashes. There was 1 listing "difference", a false positive (the hexdump ASCII column matched the file-name filter).
- Differential, constant against forward equate against extern: 2,800 triples over 41 contexts × 14 expression shapes × 36
  values, including negatives and values above 0xFFFF. 72 mismatches: 58 are the documented "constant zero byte left
  out" pcode encoding, 13 are `.bit` (LOW 5), and 4 are pcode extern negative addends (LOW 6).
- ld structure-aware mutation (relocs, symbols, st_shndx/st_value of space commons, sh_flags, e_flags, byte flips;
  `ld`, `ld -r`, `ld -r`→`ld`, `--gc-sections`, objdump, nm, readelf, objcopy): 3,000 objects, 0 findings.
- Manual probes: about 250 snippets.

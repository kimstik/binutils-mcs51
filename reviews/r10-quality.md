# r10-quality: correctness review of the MCS-51 port (binutils 2.47)

Tree: `work/modern/binutils-2.47`, copied to `review10/quality/src` (read only). ASAN/UBSAN build: `review10/quality/asan`.
Scripts are in `review10/quality/scripts`: `t.sh` (assemble one snippet), `gfuzz.py` (grammar fuzz, now also with
`-mcase-sensitive`, dot names and pcode address forms), `diff.py` (constant / forward / extern), `lfuzz2.py` (ELF mutation,
now with `.rodata` and a plain common). In the repros, `as`, `ld`, `nm` and `objdump` are the tools from either build, and `ld` uses its built-in script.

## CRITICAL

### C1. The first `.local X` + space common in a file switches the current section, and the code that follows is silently lost
The allocation path of `i51_common_parse` (tc-i51.c:1867) is
`bss_alloc_section (symbolP, size, align, i51_space_section (space))`. On the first call for a space,
`i51_space_section` (tc-i51.c:1772-1791) runs `subseg_new (name, 0)` (:1783), which **makes that section current**. The argument is
evaluated before `bss_alloc_section` saves `now_seg`, so the "restore" puts back the space section. Every following
statement is assembled into `.xbss` / `.ibss` / … subsection 0. Those sections are NOBITS, so instruction bytes are dropped
without a word (md_assemble has no bss check, see L5), and the linker's "initialized data" check skips them because they have no
SEC_HAS_CONTENTS. The construct is the documented one ("A symbol declared `.local` before any of the common directives…").

    h.s:  .global _START / .text / _START: mov a,#1 / .local BUF / .xcomm BUF,4 /
          mov dptr,#BUF / movx @dptr,a / sjmp .
    as h.s -o h.o      -> rc 0, no diagnostic;  .text size 2, .xbss size 0xa (ALLOC, RELOC), BUF at .xbss+6
    ld -o h.elf h.o    -> rc 0;  the image is `74 01 22`: the mov/movx/sjmp are gone
A label after the directive moves too: `LOOP: nop` after `.local B / .xcomm B,4` lands in `.xbss`, and `ajmp LOOP` is
then refused as "a branch target cannot name external RAM". Only the first such directive per space in a file does this,
because later calls return the cached segment. A plain `.comm`, which uses `bss_section`, is not affected.

## MEDIUM

### M1. With `-mcase-sensitive`, the "use a built-in name, then define it" rule misses every spelling except upper case
`i51_builtin_value`, the register path and the `@` path all record the use under the table spelling `n->name` (upper case)
(tc-i51.c:679, 1059, 1093). `i51_frob_symbol` looks the use up by `S_GET_NAME (sym)` (tc-i51.c:700). Without folding,
a symbol `es`, `r0` or `acc` is never found. The same text then assembles to two different things in one file, with rc 0:

    as -mcase-sensitive:  ' mov a,r0\n .rbss\nr0: .space 1\n .text\n mov a,r0\n'  -> e8 / e5 00 (R_I51_8_DIR .rbss)
                          ' mov a,acc\n .equ acc,0x30\n mov a,acc\n'            -> e5 e0 / e5 30
                          ' setb es\nes: nop\n setb es\n'                        -> d2 ac / d2 00 (R_I51_8_BIT .text+2)
Without the option, all three are refused as the manual describes. `T2CON.1` and similar names from the table behave the same way.
NAME.N names that are not in the table are recorded in their written case, so they are refused correctly (`setb tcon.4 / tcon.4:`).

## LOW

1. **Making a built-in name a symbol after its use, without a definition, is not refused.** `i51_frob_symbol` (tc-i51.c:697) returns
   for a symbol that is undefined and neither external nor weak. `.local`, `.type`, `.size` and `.hidden` create such a symbol:
   `' setb ES\n .local ES\n setb ES\n'` gives rc 0, `d2 ac d2 00 R_I51_8_BIT ES`. `.type ES,@object` and `.hidden ES` do the same.
   The link normally fails later with an undefined `ES`. With `.global`/`.weak`/`.extern` the case is fixed (r9 LOW 2).
2. **UBSAN signed overflow in `pcode_flags`.** `stored = v - 1` (tc-i51.c:2116), and `ex->X_add_number + adjust` in `pcode_byte`
   (:2038), overflow for `.pcode 0x200 @BYTE 0x8000000000000000` (or `-0x8000000000000000`). The `-fsanitize` build aborts.
   The release build only wraps. Found by gfuzz twice.
3. **`.bcomm X` can be satisfied by a definition in `.data`/`.rdata`/`.bdata`.** In `elf32_i51_check_common_space`
   (elf32-i51.c:1025), a space common against a definition is compared by space, and `.bbss`, `.rbss`, `.data` and `.bss` are all
   I51_SPACE_DIRECT. Two space commons must be of one directive (`.bcomm` against `.rcomm` is refused), but `.bcomm FLG,1` against
   `.data / FLG: .space 1` links (rc 0, FLG at 0x20 in this case, only by chance bit addressable). The same `.bcomm` against an `.rdata`
   definition fails only through a later `R_I51_8_B2B … 0x8 is not bit addressable`. This contradicts the manual: "nor can a common of one
   space be satisfied by a definition in another".
4. **Sections that the script puts in `.text` without SEC_CODE are still unchecked.** `.section .vectors` and `.section vectors` are
   KEEP'd into `.text` by the default script but get no flags from gas, so `i51_section_space` returns ANY.
   `_START: mov a,V / setb V / .section .vectors / V: ljmp 0` links with rc 0. `.init`, `.fini` and `.text.*` are refused. This is
   the residue of r9 M2.
5. **No check for code in a bss section.** `' .xbss\n mov a,#1\n'` and `' .bss\n mov a,#1\n'` give rc 0, and the bytes vanish. `.byte 1` there
   is refused ("attempt to store non-zero value"). This makes C1 silent. md_assemble (tc-i51.c:1393) could refuse when
   `seg_info (now_seg)->bss`.
6. **A bare pcode keyword silently changes meaning when the symbol is defined later.** `pcode_keyword` (tc-i51.c:1946) consults
   only symbols that already exist. `' .pcode 0x200 SWAP-1\n .equ SWAP,7\n'` gives keyword SWAP with operand -1 (`02 00 c2 ff ff`).
   The same lines in the other order give 6. Built-in names in this situation are refused. The manual's "where the program has one"
   does not say "has one yet".
7. **Still open from r9 LOW 11 (reverse direction):** `.pcode 0x200@1`, `.pcode 0x200#1` and `.pcode (0x200)1` are accepted without the
   white space the manual requires. `.pcode -(-0x200) 1` gives "Unary operator - ignored" + "missing pcode address", not a clear
   "address is one term" message. `.pcode -X 1` (X undefined) reports "can't resolve 0 - X" twice.
8. **Still open from r9 LOW 15:** `__RB__` errors from `i51_frob_symbol` have no line number (`.equ __RB__,5`, `.lcomm __RB__,4`),
   and `.using 1 / .weak __RB__` still gives the generic "can not be both weak and common".
9. **Upstream (r8 LOW 12):** UBSAN on a huge SHN_COMMON alignment in linker.c/elflink.c is unchanged. It was not hit this round.

## Verification of r9-quality findings

| r9 | Status |
|---|---|
| M1 `.comm` satisfied by a definition in another space | Fixed. `.comm X` against `.xdata X` is refused in both orders, including against an `ld -r -d` output (`COMMON`/`.bss`/`.xbss` definitions). Residue: LOW 3. |
| M2 `.rodata` escapes space checks | Fixed. `.rodata` and `.gnu.linkonce.r.` are CODE: DIR and BIT against them are refused. Residue: LOW 4 (`.vectors`). |
| L1 SFR.N use-then-define | Fixed (`TCON.4:` and `.equ PSW.3` refused at the use line). |
| L2 built-in then `.global`/`.weak` | Fixed for `.global`/`.weak`. Residue: LOW 1 (`.local`/`.type`/`.size`/`.hidden`), M1 (case-sensitive). |
| L3 `--gc-sections` keeps space commons | Fixed. RV/IV/XV/CV are removed when unreferenced, and `__RB__`/`.regbank` is kept (also after `ld -r`). |
| L4 R_I51_13_PCODE no space check | Fixed: "a branch target cannot name external RAM". |
| L5 `.bit` range only on literal | Fixed: `.bit` is constant-only ("a bit value is a constant 0 or 1"), as documented. |
| L6 pcode extern negative addend | Fixed. Extern K=0xf8: `@K-256` gives `f8`, and `@BYTE K-256` gives `f7`, the same as the constant forms. |
| L7 `#SWAP` range by form | Fixed. A constant is checked at -32768..65535, the same as R_I51_H. |
| L8 `.comm` default alignment | Fixed. `,"bss"`, `,0` and no alignment all give st_value 1. An explicit 8 is kept. |
| L9 manual vs linker on commons | Fixed (the manual now describes the plain `.comm` rule and same-directive rule). |
| L10 section name before `.section` | Fixed (dot names keep case: `R_I51_16 .mysec` both times). |
| L11 `.pcode` paren operand | Fixed (`.pcode 0x200 (1)` gives `02 00 40 01`, and `X (Y)` works). The reverse laxness remains: LOW 7. |
| L12 bare keyword hides symbol | Fixed for an existing symbol (`.equ WORD,0x1234` gives `12 33`). Residue: LOW 6 (forward). |
| L13 built-in bit class | Fixed (`#P1.1` and `P1.1+0` are refused). |
| L14 negative direct-address message | Fixed: plain "relocation truncated to fit". |
| L15 `__RB__` no line number | Partly. `.comm`/`.xcomm __RB__` now have a line number. The frob path does not: LOW 8. |
| L16 `@r 0` | Fixed: "invalid indirect operand". |
| L17 upstream UBSAN | Unchanged (upstream). |

## Checked clean
- `-mcase-sensitive`: names keep their case, `.using` `__RB__` keeps its name, ARn works, and NAME.N use-then-define is refused in the written case.
  Dot names (`.Lx`/`.LX`, `.startof.(.TEXT)`, `.mysec`) keep their case with and without the option, and non-dot section names resolve
  to the section symbol.
- Commons in gas: cross-space `.comm`/`.xcomm` in both orders, `.lcomm`/`.set`/label after `.xcomm`, `.weak`, size and
  alignment limits (0x10000 accepted, 0x20000 and 3 refused), and `__RB__` via `.comm`, `.xcomm` and `.local`+`.comm`.
- ld commons: plain/space/definition combinations in both orders, `ld -r -d` then `ld`, `.bcomm` against `.rcomm` refused, and
  `--gc-sections` with `.using 2` (`__RB__` kept, `75 11 05 75 18 07`).
- i51_value sign extension: a negative DIR value gets an overflow, not a bogus "RAM at 0xffff…" message.
- The datum overflow split: a constant or forward `.byte`/`.word` is checked by write.c, and an extern one by ld. The ranges agree (diff fuzz).
- The pcode address scanner with HIGH/LOW/B2B in parentheses, `(X)`, a leading sign and NAME.N, and the error paths for `,`, a missing
  operand and too many operands.
- The `@` operand: one token after scrubbing (`@r 0` refused, `@a + dptr` scrubbed to `@a+dptr`).
- i51_check_direct on `.lcomm` and `.local`+`.icomm` offsets of 0x80 and above.
- Disassembler, readelf, cpu-i51, opcode table, linker script, and the generic read.c/symbols.c/obj-elf.c changes are unchanged since r9
  (diffed), and r9 covered them clean.

## Statistics
- gas grammar fuzz under ASAN/UBSAN (each case also run with `-alsmgn`, then objdump, nm, readelf, `ld`, `ld -r`→`ld` and `--gc-sections`): 16,800 cases, 527
  assembled. Results: 2 UBSAN reports (both LOW 2), 1 listing difference (a "stray `\`" warning repeated inside `.rept`, generic), 0 crashes.
- Differential, constant against forward equate against extern: 900 triples, 9 mismatches. All 9 are the documented "constant zero byte left out"
  pcode encoding.
- ld ELF mutation (relocs, st_shndx/st_value of space commons, sh_flags, e_flags, byte flips; `ld`, `ld -r`→`ld`, `--gc-sections`, objdump,
  nm, readelf, objcopy): 1,400 objects, 0 findings.
- Manual probes: about 180 snippets.

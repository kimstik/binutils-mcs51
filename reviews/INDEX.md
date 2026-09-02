# Review catalogue

Every review report written about this port, in one place, named by round.
The reports are the reviewers' own words and are never edited here; where an
answer was written it sits beside its report as `<name>-answer.md'.

Each file below was byte-compared against the branch it came from before it
was copied here. `tb/fuzz/' is deliberately absent: it is code, not a report,
and it is decided separately.

| file | bytes | source | subject |
|------|------:|--------|---------|
| `r1-gas-opcodes.md` | 19403 | copy on disk only (source branch deleted before this catalogue) | Review: assembler + disassembler (i51) |
| `r1-bfd-ld.md` | 17600 | copy on disk only (source branch deleted before this catalogue) | BFD + linker review — binutils-mcs51 (i51/8051) |
| `r1-build-ci.md` | 7904 | copy on disk only (source branch deleted before this catalogue) | Build / CI / testbench review |
| `r2-audit-provenance.md` | 13335 | copy on disk only (source branch deleted before this catalogue) | Audit: can the 2001 reference blobs be trusted, and should they be in the repo? |
| `r2-audit-isa-gate.md` | 30254 | copy on disk only (source branch deleted before this catalogue) | Audit: the instruction-level gate and the simulator oracle |
| `r2-audit-green-honesty.md` | 16001 | copy on disk only (source branch deleted before this catalogue) | Audit: is the green real this time? |
| `r2-review-newcode.md` | 16230 | copy on disk only (source branch deleted before this catalogue) | Review: the delta `origin/main..origin/work/green` in `mcs51/` |
| `r2-review-integration.md` | 7932 | copy on disk only (source branch deleted before this catalogue) | Integration review: build plumbing, target identity, third-party buildability |
| `r2-rootcause-rom-delta.md` | 16787 | copy on disk only (source branch deleted before this catalogue) | Root cause of the ROM delta against the 2001 `.hex` |
| `r2-tests-mutation.md` | 16675 | copy on disk only (source branch deleted before this catalogue) | Mutation testing the MCS-51 port |
| `r2-integration.md` | 20385 | copy on disk only (source branch deleted before this catalogue) | Integration of the seven round-2 review branches |
| `r3-verify-green-2.md` | 27432 | claude/verify-green-2 @ 1c0a8ea3 | VERIFY-green-2 |
| `r3-close-holes.md` | 20489 | claude/close-holes @ 91653a3f | Three holes in the gate, reproduced and closed |
| `r3-gas-surface.md` | 22118 | claude/gas-surface @ d48b3fe5 | gas surface audit — everything except instruction encoding |
| `r3-tools.md` | 24477 | claude/binutils-tools @ c6bab63e | The rest of binutils on i51 |
| `r3-robustness.md` | 24446 | claude/robustness @ e58a22a2 | Robustness of the i51 port against hostile and malformed input |
| `r4-validate-merged.md` | 36353 | claude/validate-merged @ d42a49a6 | Validation of the four fix branches merged into `work/green` |
| `r4-review-execution.md` | 20846 | claude/review-execution @ b6c2fc23 | REVIEW-execution — the ten project ROMs, executed |
| `r4-review-testcode.md` | 24855 | claude/review-testcode @ 1792ce5b | REVIEW-testcode.md — the testbench read as code |
| `r4-review-docs-truth.md` | 18890 | claude/review-docs-truth @ b89f1ae9 | REVIEW: does the repository still tell the truth about itself? |
| `r4-review-unfinished.md` | 35352 | claude/review-unfinished @ 016b4877 | REVIEW-unfinished — what does nothing, what is half-built, what never fires |
| `r4-review-hosts.md` | 17712 | claude/review-hosts @ 9c0a5301 | Review: host portability and build reproducibility |
| `r4-review-memmodel.md` | 20954 | claude/review-memmodel @ 4461c505 | Review: the 8051 memory model, end to end |
| `r4-review-scale.md` | 20696 | claude/review-scale @ 4f15384c | REVIEW-scale.md — behaviour at scale and across many translation units |
| `r4-review-sdcc.md` | 23156 | claude/review-sdcc @ ff461089 | Review: can anyone actually use this port? |
| `r4-audit-green-delta.md` | 23597 | claude/audit-green-delta @ a4eb01b4 | Audit: `origin/claude/integrate-round2` (8c9a641) -> `origin/work/green` (afee4a5) |
| `em-standard.md` | 24511 | claude/em-standard @ 16ef6abd | e_machine for i51-elf: the answer is 165 |
| `em-challenge.md` | 27884 | claude/em-challenge @ 58e65cd4 | EM-CHALLENGE: prosecution of `EM_8051 = 165` |
| `em-field.md` | 36882 | claude/em-field @ e70b81ac | EM-FIELD — who really emits and consumes 8051 ELF |
| `em-legacy.md` | 19163 | claude/em-legacy @ 4c6d9210 | EM_I51: what the legacy value costs, and what happens to the 2001 objects |
| `em-verify.md` | 1419 | claude/em-verify @ 848ec49f | EM-VERIFY: e_machine = 165 on main @ 90ee2af |
| `r5-coldread.md` | 34475 | claude/r5-coldread @ ed5ca2e8 | R5 cold read: binutils-mcs51 on `main` (90ee2af) |
| `r5-openitems.md` | 31995 | claude/r5-openitems @ 22fec196 | R5: the twenty open items, re-run on main |
| `r5-elfhdr.md` | 48934 | claude/r5-elfhdr @ e8050e9f | R5-ELFHDR — `e_flags` and `EI_DATA` |
| `r5-rewrite.md` | 24581 | claude/r5-rewrite @ 03dd796d | R5: account for the rewrite |

35 reports.


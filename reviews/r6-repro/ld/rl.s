	.text
	.global _START
_START:
	.rept 32
	.byte 0
	.endr
	.reloc 0, R_I51_NONE, SYM
	.reloc 2, R_I51_R1, SYM
	.reloc 4, R_I51_R3, SYM
	.reloc 6, R_I51_7_PCREL, SYM
	.reloc 8, R_I51_11, SYM
	.reloc 10, R_I51_8_BIT, SYM
	.reloc 12, R_I51_8, SYM
	.reloc 14, R_I51_L, SYM
	.reloc 16, R_I51_H, SYM
	.reloc 18, R_I51_16, SYM
	.reloc 20, R_I51_8_B2B, SYM
	.reloc 22, R_I51_13_PCODE, SYM
	.reloc 24, R_I51_8_DIR, SYM
	.reloc 26, R_I51_8_IMM, SYM

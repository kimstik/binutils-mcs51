	.text
	.global _START
_START:
	mov a,@r0
	mov a,r0
	.reloc 0, R_I51_R1, SYM
	.reloc 1, R_I51_R3, SYM
	.reloc 1, R_I51_NONE, SYM

	.text
	.global _START
_START:
	lcall INLF
	ljmp LOC1
	.section .text.inl,"axG",@progbits,INLF,comdat
	.global INLF
INLF:	nop
LOC1:	ret

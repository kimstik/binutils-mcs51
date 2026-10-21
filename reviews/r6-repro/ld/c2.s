	.text
	.global G2
G2:	lcall INLF
	ljmp LOC1
	mov dptr,#LOC1+1
	.section .text.inl,"axG",@progbits,INLF,comdat
	.global INLF
INLF:	nop
	nop
LOC1:	ret

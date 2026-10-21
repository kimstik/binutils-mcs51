	.text
	.skip 3
	lcall Lf
	.section .text.f,"axG",@progbits,F,comdat
	.globl F
F:	nop
Lf:	ret

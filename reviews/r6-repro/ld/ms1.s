	.text
	.global _START
_START:
	mov dptr,#S1
	mov dptr,#S2
	lcall F
	.section .rodata.str1.1,"aMS",@progbits,1
S1:	.asciz "HELLO"
S2:	.asciz "WORLD"

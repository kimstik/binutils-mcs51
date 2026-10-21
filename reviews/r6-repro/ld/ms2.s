	.text
	.global F
F:	mov dptr,#S3
	mov dptr,#S4
	ret
	.section .rodata.str1.1,"aMS",@progbits,1
S3:	.asciz "XYZ"
S4:	.asciz "WORLD"

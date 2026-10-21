	.text
	.global _START
_START:
	mov sp,#STACK-1
	mov r0,#IV
	.idata
	.skip 0xdf
IV:	.byte 0

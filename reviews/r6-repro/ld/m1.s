	.text
	.global _START
_START:
	mov a,LD1
	setb B2B(LB1,2)
	mov dptr,#LX1
	sjmp LT2
	ajmp LT2
	mov a,#HIGH(LX1)
	setb LBIT1
	acall F2
	.section .text.two,"ax"
LT2:	nop
	ret
	.data
	.byte 0
LD1:	.byte 0
	.bdata
	.byte 0
LB1:	.byte 0
	.xdata
	.skip 0x123
LX1:	.byte 0
	.bitdata
	.byte 0,0,0
LBIT1:	.byte 0

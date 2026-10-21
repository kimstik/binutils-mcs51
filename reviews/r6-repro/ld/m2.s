	.text
	.global F2
	nop
F2:	mov a,LD2
	setb B2B(LB2,7)
	mov dptr,#LX2
	setb LBIT2
	sjmp F2
	ret
	.data
	.byte 0,0,0
LD2:	.byte 0
	.bdata
	.byte 0,0
LB2:	.byte 0
	.xdata
	.skip 0x10
LX2:	.byte 0
	.bitdata
	.byte 0,0
LBIT2:	.byte 0

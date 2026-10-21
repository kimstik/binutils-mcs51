	.text
	.global _START
_START:
	ljmp XV
	acall XV
	sjmp DV
	mov a,_START
	setb _START
	.xdata
	.skip 5
XV:	.byte 0
	.data
DV:	.byte 0

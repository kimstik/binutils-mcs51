	.text
	.global _START
_START:
	setb DV
	setb XV
	setb IV
	.data
DV:	.byte 0
	.xdata
	.skip 0x40
XV:	.byte 0
	.idata
IV:	.byte 0

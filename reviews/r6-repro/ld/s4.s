	.text
	.global _START
_START:
	mov dptr,#XV
	.xdata
	.skip 0xfffe
	.xbss
	.skip 1
XV:	.skip 1

	.text
	.global _START
_START:
	mov dptr,#XV
	.xdata
	.skip 0xfffe
	.xbss
	.skip 2
XV:	.skip 1

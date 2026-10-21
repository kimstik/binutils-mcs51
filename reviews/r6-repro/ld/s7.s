	.text
	.global _START
_START:
	ret
	.xdata
	.word _START, FARX
	.data
	.byte LOW(_START)

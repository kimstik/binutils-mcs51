	.text
	.global _START
_START:
	mov a,#HIGH(X)
	mov a,#LOW(X)
	mov a,#HIGH(X+0x10000)
	.byte HIGH(Y), LOW(Y)
	.byte X
	.word Y

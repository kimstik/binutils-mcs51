	.text
	.global _START
_START:
	mov dptr,#BUF
	movx a,@dptr
	.xcomm BUF,4

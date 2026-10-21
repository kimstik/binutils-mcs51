	.text
	.global _START
_START:
	mov a,BIGV
	mov a,RV
	.data
	.global BIGV
	.skip 0x78
BIGV:	.byte 0

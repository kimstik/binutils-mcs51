	.text
	.global _START
_START:
	setb B2B(RB,2)
	mov a,RB
	.regbank
	.global RB
RB:	.byte 0

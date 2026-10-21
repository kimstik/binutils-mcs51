	.text
	.global _START
_START:
	mov r0,#1
	mov a,r0
	.rbss
	.global RB
RB:	.skip 2
	.text
	mov RB,#5

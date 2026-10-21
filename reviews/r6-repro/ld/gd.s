	.section .text.start,"ax"
	.global _START
_START:
	sjmp _START
	.section .text.dead,"ax"
	.global DEADG
DEADG:	nop
DEADL:	ret
	.section .debug_ranges,"",@progbits
	.word DEADG
	.word DEADL
	.byte LOW(DEADL)
	.word _START

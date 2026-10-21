	.text
	.global _START
_START:
	sjmp T
	.section .text.b,"ax"
	.global T

	.text
	.global _START
_START:
	sjmp FOO
	ajmp FOO
	acall GBL
	sjmp GBL
	ljmp FOO
	.weak FOO
FOO:	ret
	.global GBL
GBL:	ret

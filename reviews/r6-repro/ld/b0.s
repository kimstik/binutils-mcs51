	.text
	.global _START
_START:
	setb B2B(W,3)
	setb B2B(W2,3)
	.weak WK
	setb B2B(WK,5)

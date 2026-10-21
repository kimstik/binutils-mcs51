	.text
	.global _START
_START:
	.skip 0x200
	sjmp TA
	cjne a,#5,TB
	djnz 0x30,TC
	jbc 0x20,TD

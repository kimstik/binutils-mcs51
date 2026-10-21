	.section .text.start,"ax"
	.global _START
_START:
	lcall USED
	mov dptr,#TBL
	sjmp _START
	.section .text.used,"ax"
	.global USED
USED:	ret
	.section .text.unused,"ax"
	.global UNUSED
UNUSED:	mov a,UV
	ret
	.section .text.viaptr,"ax"
VIAPTR:	ret
	.section .rodata.tbl,"a"
TBL:	.word VIAPTR
	.section .data.uv,"aw"
UV:	.byte 1
	.section .xdata.x,"aw"
XU:	.byte 5

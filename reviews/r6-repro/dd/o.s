	.text
_start: mov a,v
	mov dptr,#w
	ljmp _start
	.section .xram,"aw",@nobits
w: .skip 4
	.section .text.x,"ax"
v: nop
	.section .rodata.k,"a"
k: .byte 1

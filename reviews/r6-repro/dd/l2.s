	.globl g
	.text
g: mov counter,#2
	ret
	.local counter
	.comm counter,1

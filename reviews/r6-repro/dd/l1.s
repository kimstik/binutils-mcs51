	.text
_start: mov counter,#1
	lcall g
	sjmp _start
	.local counter
	.comm counter,1

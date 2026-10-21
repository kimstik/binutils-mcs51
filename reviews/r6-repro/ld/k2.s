	.text
	.global G
G:	mov dptr,#XC+3
	clr BC+2
	setb B2B(BBC,0)
	mov r1,#IC+1
	.xcomm XC,8
	.bitcomm BC,9
	.bcomm BBC,2
	.icomm IC,1
	.comm PC1,3
	.rcomm RCX,1

	.text
	.global _START
_START:
	mov dptr,#XC
	setb BC
	setb B2B(BBC,6)
	mov r0,#IC
	mov a,PC1
	mov a,RCX
	.xcomm XC,4
	.bitcomm BC,3
	.bcomm BBC,1
	.icomm IC,2
	.comm PC1,1
	.rcomm RCX,1

	.using 1
	.globl ext, start
start:	acall start
	add a,r3
	add a,@r1
	add a,0x30
	add a,#5
	anl c,/acc.7
	anl 0x30,#0x0f
	cjne a,#3,start
	cjne r2,#3,start
	cjne @r0,#3,start
	cjne a,0x40,start
	clr c
	setb p1.3
	setb 0x20.3
	setb B2B(0x21,4)
	setb B2B(bvar,2)
	djnz r7,start
	djnz 0x30,start
	jb acc.3,start
	jbc ext,start
	jmp @a+dptr
	lcall ext
	ljmp ext+3
	mov a,#HIGH(ext)
	mov a,#LOW(ext)
	mov dptr,#ext
	mov 0x30,0x31
	mov ar3,#1
	mov c,p3.2
	movc a,@a+pc
	movx @dptr,a
	sjmp ext
	ajmp ext
	.byte LOW(ext), HIGH(ext), 1
	.word ext, 0x1234
	.pcode 0x200 #BYTE 5, @BYTE ext, #SWAP ext
	.pcode ext WORD 0x1234
	.bit 1,0,1
	.rcomm rv,2
	.icomm iv,4,2
	.xcomm xv,16
	.bcomm bv,1
	.bitcomm btv,1
	.ecomm ev,3
	.comm cv,2
	.xdata
xd:	.byte 1,2
	.bdata
bvar:	.byte 0
	.eeprom
	.byte 5

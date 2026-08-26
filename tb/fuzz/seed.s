; Seed object for the robustness harness.  It is deliberately rich: one
; relocation of every type the port defines, a memory-space common of every
; space, a bit-addressable datum and a .pcode record, so that a single
; mutated copy of the resulting .o exercises as much of bfd/elf32-i51.c as
; one file can.
	.using	0

	.comm	cvar, 4
	.rcomm	rvar, 2
	.bcomm	bvar, 2
	.icomm	ivar, 2
	.xcomm	xvar, 2
	.ecomm	evar, 2
	.bitcomm bitvar, 1

	.text
	.global	start
start:
	nop
	sjmp	local1			; R_I51_7_PCREL, resolved
	sjmp	extfunc			; R_I51_7_PCREL, external
	ljmp	extfunc			; R_I51_16
	acall	extfunc			; R_I51_11
	ajmp	local1			; R_I51_11, resolved
	lcall	extfunc			; R_I51_16
local1:
	mov	a, #extdata		; R_I51_8
	mov	a, #LOW(extdata)	; R_I51_L
	mov	a, #HIGH(extdata)	; R_I51_H
	mov	a, extdata		; R_I51_8
	setb	extbit			; R_I51_8_BIT
	setb	B2B(extdata,3)		; R_I51_8_B2B
	jb	extbit, local1
	djnz	r7, local1
	cjne	a, #extdata, local1
	mov	dptr, #extdata
	mov	0x20, 0x21
	movx	@dptr, a
	ret

	.data
dvar:
	.byte	1, 2, 3, 4
	.word	0x1234
	.word	extdata

	.xdata
	.byte	0xaa, 0xbb

	.bitdata
	.bit	1, 0, 1, 1

	.pcode	extdata #0x1234, @0x40, #BYTE 0x12

	.text
	.global _START
_START:
	mov dptr,#EEV
	mov dptr,#ORPH
	.eeprom
	.skip 0xffff
	.skip 0x10
EEV:	.byte 1
	.section .mydata,"aw"
	.skip 4
ORPH:	.byte 2

	.text
	.global _START
_START:
	.pcode 0x200 @BYTE 0x35
	.pcode 0x200 @BYTE SYMB
	.pcode 0x200 #SWAP 0x1234
	.pcode 0x200 #SWAP SYMW
	.pcode PEX

	.text
	.global _START
_START:
	setb BS
	clr BS+1
	jb BS2,_START

.idata
iv: .byte 1
.xdata
xv: .byte 2
.text
mov a,iv
mov a,xv
mov a,#iv
mov r0,#iv
mov a,@r0

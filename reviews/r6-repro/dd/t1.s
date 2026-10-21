        .text
_start: mov a,ivar
        mov r0,#ivar
        mov dptr,#xvar
        ljmp _start
        .data
ivar:   .byte 5
        .xdata
xvar:   .word 0x1234

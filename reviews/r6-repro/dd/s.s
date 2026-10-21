        .text
_start: mov sp,#STACK
        lcall f
f:      ret
        .data
d:  .skip 0x50
        .idata
i:  .skip 0x90

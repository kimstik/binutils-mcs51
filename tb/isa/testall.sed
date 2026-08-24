# oc8051 testall.asm is written in Intel/ASEM-51 dialect; GNU as needs a few
# spellings changed. Only syntax is touched - no instruction is added, removed
# or reordered, so what is assembled is still the original program.

# 66h -> 0x66, on immediates and bare operands alike
s/\([#, ]\)\([0-9][0-9A-Fa-f]*\)[hH]\b/\10x\2/g

# db -> .byte
s/^\([ \t]*\)\(db\|DB\)\b/\1.byte/

# `end' has no GNU as equivalent
/^[ \t]*\(end\|END\)[ \t]*$/d

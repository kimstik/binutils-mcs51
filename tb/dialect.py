"""Intel/ASEM-51 spelling to GNU as spelling.

oc8051's testall.asm predates GNU as by two decades and is written the way the
Intel and ASEM-51 assemblers expect. Only spelling is rewritten here - no
instruction is added, removed or reordered, so what gets assembled is still the
original program.
"""

import re

RULES = [
    # 66h -> 0x66, on immediates and bare operands alike
    (re.compile(r'([#, ])([0-9][0-9A-Fa-f]*)[hH]\b'), r'\g<1>0x\g<2>'),
    # db -> .byte
    (re.compile(r'^([ \t]*)(?:db|DB)\b'), r'\g<1>.byte'),
    # `end' has no GNU as equivalent
    (re.compile(r'^[ \t]*(?:end|END)[ \t]*$'), ''),
]


def translate(source):
    out = []
    for line in source.splitlines():
        for pattern, repl in RULES:
            line = pattern.sub(repl, line)
        out.append(line)
    return '\n'.join(out)

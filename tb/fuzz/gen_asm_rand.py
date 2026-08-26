#!/usr/bin/env python3
"""Random assembler sources built from the port's own vocabulary.

Token soup, not valid programs: mnemonics, register and SFR names, the port's
directives and its HIGH()/LOW()/B2B() prefixes, glued together with random
punctuation and out-of-range numbers.  gas has to diagnose all of it and
none of it may crash.  Seeded, so every file is reproducible from its name.

  ./gen_asm_rand.py outdir/ [count]
"""
import os
import random
import sys

MNEM = """acall add addc ajmp anl cjne clr cpl da dec div djnz inc jb jbc jc
jmp jnb jnc jnz jz lcall ljmp mov movc movx mul nop orl pop push ret reti rl
rlc rr rrc setb sjmp subb swap xch xchd xrl""".split()

OPS = ["A", "AB", "C", "DPTR", "@A+DPTR", "@A+PC", "@DPTR", "@R0", "@R1",
       "/C", "R0", "R7", "AR0", "AR7", "ACC", "ACC.7", "B", "B.0", "P0",
       "P0.0", "PSW", "SP", "TCON", "CY", "EA", "T2CON.7"]

PREFIX = ["", "#", "/", "@", "#HIGH(", "#LOW(", "B2B(", "HIGH(", "LOW(",
          "#WORD", "#BYTE", "#SWAP", "#SHL8"]

NUMS = ["0", "1", "7", "0x20", "0x2f", "0x30", "0x7f", "0x80", "0xf8", "0xff",
        "0x100", "0xffff", "0x10000", "0x7fffffff", "0xffffffff",
        "0xffffffffffffffff", "-1", "-128", "-129", "-32769",
        "99999999999999999999", "0x20.0", "0x20.7", "0x20.9", "0xff.0",
        "0x2f.7", "0x30.0", "1/0", "1%0", "1<<99", "(1+", "1)", ".", "..",
        "$", "'a'", '"s"']

DIRECT = [".bit", ".local", ".equ", ".set", ".using", ".rcomm", ".bitcomm",
          ".comm", ".icomm", ".xcomm", ".ecomm", ".bcomm", ".bss", ".rbss",
          ".bbss", ".ibss", ".xbss", ".ebss", ".bitbss", ".rdata", ".bdata",
          ".idata", ".xdata", ".edata", ".bitdata", ".eeprom", ".pcode",
          ".byte", ".word", ".ascii", ".asciz", ".org", ".align", ".global",
          ".section", ".text", ".data", ".skip", ".fill", ".space"]

PUNCT = [",", " ", "\t", "(", ")", "#", "@", "/", "+", "-", "*", "~", "!",
         "'", '"', ";", "$", ":", "<", ">", "&", "|", "^", "%", "\\", "["]


def line(rng):
    kind = rng.randrange(10)
    if kind < 5:
        n = rng.randrange(0, 4)
        parts = [rng.choice(MNEM)]
        args = []
        for _ in range(n):
            args.append(rng.choice(PREFIX) + rng.choice(OPS + NUMS))
        parts.append(", ".join(args))
        return "\t" + " ".join(parts)
    if kind < 8:
        n = rng.randrange(0, 4)
        args = [rng.choice(NUMS + OPS) for _ in range(n)]
        return "\t" + rng.choice(DIRECT) + " " + ", ".join(args)
    if kind == 8:
        return "l%d:" % rng.randrange(100)
    return "".join(rng.choice(PUNCT + NUMS + OPS + MNEM)
                   for _ in range(rng.randrange(1, 20)))


def main():
    out = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    os.makedirs(out, exist_ok=True)
    for seed in range(count):
        rng = random.Random(seed)
        with open(os.path.join(out, "r%05d.s" % seed), "w") as f:
            for _ in range(rng.randrange(1, 30)):
                f.write(line(rng) + "\n")
    print("%d random sources in %s" % (count, out))


if __name__ == "__main__":
    main()

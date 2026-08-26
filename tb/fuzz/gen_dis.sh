#!/bin/sh
# Build the disassembler's adversarial corpus in $1.
#
# print_insn_i51 () reads its operand bytes one at a time through
# read_memory_func, so the interesting inputs are the ones where a
# multi-byte instruction starts within the last two bytes of a section:
# every one of the 256 opcodes is placed at the last byte, and at the
# second-to-last byte, of a section of its own.
set -u
OUT=$1
AS=$2
mkdir -p "$OUT"
WORK=$OUT/.work
mkdir -p "$WORK"

python3 - "$WORK" <<'PY'
import os, sys
w = sys.argv[1]
# every opcode as the final byte of .text
for op in range(256):
    with open(os.path.join(w, 'last_%02x.s' % op), 'w') as f:
        f.write('\t.text\n\t.byte 0x00\n\t.byte 0x%02x\n' % op)
# every opcode one byte before the end (a 3-byte insn runs off)
for op in range(256):
    with open(os.path.join(w, 'penult_%02x.s' % op), 'w') as f:
        f.write('\t.text\n\t.byte 0x%02x\n\t.byte 0xff\n' % op)
# empty section
with open(os.path.join(w, 'empty.s'), 'w') as f:
    f.write('\t.text\n\t.data\n\t.byte 1\n')
# all 256 opcodes back to back, then all of them padded
with open(os.path.join(w, 'all_dense.s'), 'w') as f:
    f.write('\t.text\n')
    f.write('\t.byte ' + ','.join('0x%02x' % i for i in range(256)) + '\n')
with open(os.path.join(w, 'all_padded.s'), 'w') as f:
    f.write('\t.text\n')
    for i in range(256):
        f.write('\t.byte 0x%02x,0,0\n' % i)
# pseudo-random streams, fixed seed so a crash is reproducible
import random
for seed in range(8):
    random.seed(seed)
    b = [random.randrange(256) for _ in range(4096)]
    with open(os.path.join(w, 'rand_%d.s' % seed), 'w') as f:
        f.write('\t.text\n')
        for i in range(0, len(b), 16):
            f.write('\t.byte ' + ','.join('0x%02x' % x for x in b[i:i+16]) + '\n')
PY

for s in "$WORK"/*.s; do
  b=$(basename "$s" .s)
  $AS -o "$OUT/$b.o" "$s" 2>/dev/null
done
echo "$(ls "$OUT" | wc -l) disassembler inputs"

#!/bin/sh
# The two crashes tb/fuzz found in the port's own code, and the one it found
# in upstream gas.  Run against any build:
#
#   BUILD=<binutils build dir> ./repro.sh
#
# Against a build without -fsanitize=address the first two are a silent wild
# read and a wild write; the linker usually survives them and produces a
# wrong object.  With ASAN they abort with a report naming
# bfd/elf32-i51.c:i51_final_link_relocate.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=${BUILD:?set BUILD to a binutils build directory}
LD=$BUILD/ld/ld-new
AS=$BUILD/gas/as-new
export ASAN_OPTIONS=detect_leaks=0

run () {
  echo "================ $1"
  shift
  timeout -s KILL 30 "$@"
  echo "rc=$?"
}

# 1. r_offset out of range.  .rela.text reloc 1 (R_I51_16, 2 bytes) has its
#    r_offset set to 0xffff; .text is 0x2b bytes.  Wild WRITE through
#    bfd_putb16 () at bfd/elf32-i51.c:407.
run "oob-write-r_offset.o (wild write)" \
    "$LD" -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 --defsym EXTBIT=0x20 \
    -o /dev/null "$HERE/oob-write-r_offset.o"

# 2. sh_size shrunk.  .text sh_size is 1, so every relocation in .rela.text
#    now points past the contents buffer.  Wild READ through bfd_getb16 ()
#    at bfd/elf32-i51.c:358.
run "oob-read-sh_size.o (wild read)" \
    "$LD" -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 --defsym EXTBIT=0x20 \
    -o /dev/null "$HERE/oob-read-sh_size.o"

# 3. Not the port: gas's recursive-descent expression parser blows the stack
#    on deeply nested parentheses.  Stock x86 gas 2.42 segfaults on the same
#    input at the same depth; see ROBUSTNESS.md.
run "upstream-gas-deep-parens.s (upstream, not the port)" \
    "$AS" -o /dev/null "$HERE/upstream-gas-deep-parens.s"

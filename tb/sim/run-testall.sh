#!/bin/sh
# Execute testall.asm in the ucsim 8051 simulator and read the verdict.
#
# testall.asm is oc8051's self-checking instruction test: every failing
# test writes its number to P1 and jumps to `failed'; full success writes
# 127 there.  Either way the program parks in an infinite loop at `failed',
# so we break there, read the P1 latch (SFR 0x90) and judge.
#
#   usage: run-testall.sh BUILD-DIR
#
#   BUILD-DIR   binutils build tree: gas/as-new, binutils/objcopy,
#               binutils/nm-new (as produced by `make -C tb build')
#   S51         simulator binary to use (default: s51 from PATH)
#   S51_TIMEOUT wall-clock limit in seconds for the simulation (default 60)
#
# exit: 0 pass, 1 an instruction test failed, 2 bad usage/toolchain,
#       3 simulator not installed, 4 harness failure (tools, timeout, parse)

set -u

die()  { echo "run-testall: $*" >&2; exit 4; }

BUILD=${1-}
[ -n "$BUILD" ] || { echo "usage: run-testall.sh BUILD-DIR" >&2; exit 2; }
AS=$BUILD/gas/as-new
LD=$BUILD/ld/ld-new
OBJCOPY=$BUILD/binutils/objcopy
NM=$BUILD/binutils/nm-new
for t in "$AS" "$LD" "$OBJCOPY" "$NM"; do
    [ -x "$t" ] || { echo "run-testall: missing tool $t" >&2; exit 2; }
done

S51=${S51:-s51}
command -v "$S51" >/dev/null 2>&1 || {
    echo "run-testall: simulator '$S51' not found - install sdcc-ucsim" >&2
    echo "  (Ubuntu: apt-get install sdcc-ucsim; or set S51=/path/to/s51)" >&2
    exit 3
}
# The simulator later runs with a different cwd; pin a relative S51 down.
case $S51 in
    */*) S51=$(CDPATH= cd -- "$(dirname -- "$S51")" && pwd)/${S51##*/} ;;
esac

TB=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ASM=$TB/isa/testall.asm
[ -f "$ASM" ] || die "missing $ASM"

W=$(mktemp -d) || die "mktemp failed"
trap 'rm -rf "$W"' EXIT INT TERM

# Corrections to defects in the vendored test itself, then
# Intel/ASEM-51 spelling -> GNU as spelling, then assemble.
cp "$ASM" "$W/testall.asm"
# --batch: on a mismatch GNU patch would otherwise try to prompt, and the patch
# itself is on stdin, so the prompt reads from a /dev/tty a container has not
# got.  Fail cleanly instead.
patch -s --batch -d "$W" -p1 < "$TB/isa/testall-fixes.patch" || die "testall-fixes.patch did not apply"
ASM=$W/testall.asm
python3 -c 'import sys
sys.path.insert(0, sys.argv[1])
import dialect
sys.stdout.write(dialect.translate(open(sys.argv[2], encoding="latin-1").read()) + "\n")' \
    "$TB" "$ASM" > "$W/testall.s" || die "dialect translation failed"

"$AS" -o "$W/testall.o" "$W/testall.s" || die "as-new failed"

# Absolute operands (ljmp/acall/mov dptr,#label) stay as RELA relocations
# in the object, so the image must be linked before it can run.
"$LD" -e 0 -T "$TB/sim/link.ld" -o "$W/testall.elf" "$W/testall.o" \
    || die "ld-new failed"

# Address of the terminal loop, from the linked image.
FAILED=$("$NM" "$W/testall.elf" | tr -d '\r' \
         | awk 'tolower($NF) == "failed" { print "0x" $1; exit }')
[ -n "$FAILED" ] || die "symbol 'failed' not found in testall.elf"

"$OBJCOPY" -O ihex --only-section=.text "$W/testall.elf" "$W/testall.hex" \
    || die "objcopy failed"

# Batch-drive the simulator: break on the loop, run, print 100000+P1 as
# a marker line (dump kept as fallback for ucsim builds without expr).
{
    printf 'break %s\n' "$FAILED"
    printf 'run\n'
    printf 'expr /u 100000+sfr[0x90]\n'
    printf 'dump sfr 0x90 0x90\n'
    printf 'dump rom 0x0 0x1f\n'
    printf 'quit\n'
} > "$W/cmds"

# ucsim parses ':' in a file argument as an offset separator, which breaks
# absolute Windows paths - run from the work dir with a relative name.
TMO=${S51_TIMEOUT:-60}
if command -v timeout >/dev/null 2>&1; then
    ( cd "$W" && exec timeout "$TMO" "$S51" -t C51 testall.hex \
                      < cmds > out 2>&1 )
else
    ( cd "$W" && exec "$S51" -t C51 testall.hex < cmds > out 2>&1 )
fi
rc=$?
tr -d '\r' < "$W/out" > "$W/out.lf"
if [ $rc -eq 124 ]; then
    echo "run-testall: no verdict within ${TMO}s - execution never reached 'failed' ($FAILED)" >&2
    sed -n '$p' "$W/out.lf" >&2
    exit 4
fi

# Marker line from expr; else the P1 dump line, smart or classic format:
#   0x90 P1:                  0b01111111 0x7f '.' 127
#   0x90 7f .
P1=$(awk '/^100[0-9][0-9][0-9]$/ { print $0 - 100000; exit }' "$W/out.lf")
if [ -z "$P1" ]; then
    hx=$(awk '/^0x90 /{ v = ""
                        if ($2 ~ /^[0-9a-fA-F][0-9a-fA-F]$/) v = $2
                        else for (i = 2; i <= NF; i++)
                                 if ($i ~ /^0x[0-9a-fA-F][0-9a-fA-F]$/) v = substr($i, 3)
                        if (v != "") { print v; exit } }' "$W/out.lf")
    [ -n "$hx" ] && P1=$(printf '%d' "0x$hx")
fi
[ -n "$P1" ] || { cat "$W/out.lf" >&2; die "could not read P1 from simulator output"; }

if [ "$P1" -eq 127 ]; then
    echo "PASS: testall ran to completion, all instruction tests passed (P1=127)"
    exit 0
fi
if [ "$P1" -eq 0 ]; then
    echo "FAIL: P1=0 - instruction test 1 failed (its fail path reports via RAM[1], cleared to 0)"
else
    echo "FAIL: instruction test $P1 failed (P1=$P1)"
fi
echo "-- first code bytes as the simulator saw them:" >&2
awk '/^0x0000/, /^0x0018/' "$W/out.lf" >&2
exit 1

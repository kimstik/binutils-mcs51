#!/bin/sh
# Link a minimal program with the DEFAULT emulation of ld-new - no -T,
# no --no-check-sections - and verify the layout the built-in linker
# script produces.
#
# The probe touches one section of every address space the port emits:
# code in .text, initialized bytes in .xdata and .eeprom, a byte in the
# bit-addressable .bdata area (reached through a B2B relocation, which
# only resolves against true on-chip addresses), a named bit in
# .bitdata, and a call through __gsinit_startup left undefined on
# purpose: the assembler folds it to __GSINIT_STARTUP and the default
# script must bind it to its RET stub instead of failing the link or
# aiming the call at the reset vector.
#
#   usage: run-defaultlink.sh BUILD-DIR
#
#   BUILD-DIR   binutils build tree: gas/as-new, ld/ld-new,
#               binutils/objcopy, binutils/readelf, binutils/nm-new
#
# exit: 0 pass, 1 link or layout check failed, 2 bad usage/toolchain

set -u

BUILD=${1-}
[ -n "$BUILD" ] || { echo "usage: run-defaultlink.sh BUILD-DIR" >&2; exit 2; }
AS=$BUILD/gas/as-new
LD=$BUILD/ld/ld-new
OBJCOPY=$BUILD/binutils/objcopy
READELF=$BUILD/binutils/readelf
NM=$BUILD/binutils/nm-new
for t in "$AS" "$LD" "$OBJCOPY" "$READELF" "$NM"; do
    [ -x "$t" ] || { echo "run-defaultlink: missing tool $t" >&2; exit 2; }
done

W=$(mktemp -d) || { echo "run-defaultlink: mktemp failed" >&2; exit 2; }
trap 'rm -rf "$W"' EXIT INT TERM

cat > "$W/probe.s" <<'EOF'
; default-link probe: one section from every port address space

        .text
        .global _START
_START: lcall   __gsinit_startup ; undefined on purpose -> RET stub
        mov     dptr,#XVAR2      ; 16-bit xdata address
        movx    a,@dptr
        setb    BFLAG            ; named bit from .bitdata
        setb    B2B(BDVAR,1)     ; bit 1 of a bit-addressable byte
        mov     0x81,#STACK      ; SP <- provided stack bottom
        ljmp    _START

        .xdata
        .global XVAR
XVAR:   .byte   0x55
        .global XVAR2
XVAR2:  .byte   0xAA

        .eeprom
        .global EVAR
EVAR:   .byte   0x01

        .bdata
        .global BDVAR
BDVAR:  .byte   0x00

        .bitdata
        .global BFLAG
BFLAG:  .bit    0
EOF

"$AS" -o "$W/probe.o" "$W/probe.s" || { echo "run-defaultlink: as-new failed" >&2; exit 1; }

# The whole point: default emulation, no script, no flag to pacify the
# overlap check.  This must just work.
if ! "$LD" -o "$W/probe.elf" "$W/probe.o" 2> "$W/ld.err"; then
    echo "run-defaultlink: default link FAILED" >&2
    cat "$W/ld.err" >&2
    exit 1
fi
if grep -qi 'overlap' "$W/ld.err"; then
    echo "run-defaultlink: default link warns about overlaps" >&2
    cat "$W/ld.err" >&2
    exit 1
fi
[ -s "$W/ld.err" ] && { echo "== ld stderr (non-fatal):"; cat "$W/ld.err"; }

st=0
fail() { echo "FAIL: $*"; st=1; }

# Every address below follows deterministically from the probe and the
# default script: xdata and eeprom count from 0 in their own spaces,
# BDVAR is the first bit-addressable byte, BFLAG the first named bit
# after it (bit 8 = byte 0x21 bit 0), data resumes at 0x22 and nothing
# else is allocated, so the stack bottom is 0x22 as well.
sym() { "$NM" "$W/probe.elf" | tr -d '\r' | awk -v s="$1" '$NF == s { print $1; exit }'; }
expect_sym() {
    v=$(sym "$1")
    [ -n "$v" ] || { fail "symbol $1 not found"; return; }
    [ $((0x$v)) -eq $(($2)) ] || fail "$1 = 0x$v, expected $2"
}
expect_sym XVAR   0x0000
expect_sym XVAR2  0x0001
expect_sym EVAR   0x0000
expect_sym BDVAR  0x0020
expect_sym BFLAG  0x0008
expect_sym STACK  0x0022
expect_sym _ETEXT 0x0012

# The unresolved hook must resolve to the RET stub inside .text.
RET=$(sym __I51_RET)
HOOK=$(sym __GSINIT_STARTUP)
if [ -z "$RET" ] || [ -z "$HOOK" ]; then
    fail "RET stub or hook symbol missing"
elif [ $((0x$HOOK)) -ne $((0x$RET)) ] || [ $((0x$HOOK)) -ne 17 ]; then
    fail "__GSINIT_STARTUP = 0x$HOOK, __I51_RET = 0x$RET, expected both 0x11"
fi

# Sections: .text allocated in the image; every RAM space present at its
# true in-space address and not allocated (no A flag, no overlap check).
secline() { "$READELF" -S --wide "$W/probe.elf" | tr -d '\r' \
            | sed 's/^ *\[ *[0-9]*\] *//' | awk -v s="$1" '$1 == s { print; exit }'; }
expect_sec() {  # name addr alloc|noalloc
    line=$(secline "$1")
    [ -n "$line" ] || { fail "section $1 not in output"; return; }
    addr=$(echo "$line" | awk '{ print $3 }')
    [ $((0x$addr)) -eq $(($2)) ] || fail "$1 at 0x$addr, expected $2"
    flg=$(echo "$line" | awk '{ print $7 }')
    case "$3:$flg" in
        alloc:*A*)   ;;
        alloc:*)     fail "$1 is not allocated (flags '$flg')" ;;
        noalloc:*A*) fail "$1 is allocated (flags '$flg')" ;;
        noalloc:*)   ;;
    esac
}
expect_sec .text   0x0000 alloc
expect_sec .bdata  0x0020 noalloc
expect_sec .bit    0x0008 noalloc
expect_sec .xdata  0x0000 noalloc
expect_sec .eeprom 0x0000 noalloc

# The ROM image: probe code, hook call aimed at the trailing RET.
"$OBJCOPY" -O binary --only-section=.text "$W/probe.elf" "$W/probe.bin" \
    || { echo "run-defaultlink: objcopy failed" >&2; exit 1; }
img=$(od -An -v -tx1 "$W/probe.bin" | tr -d ' \n')
want=120011900001e0d208d20175812202000022
[ "$img" = "$want" ] || fail "ROM image $img, expected $want"

if [ "$st" -ne 0 ]; then
    echo "== nm";         "$NM" "$W/probe.elf"
    echo "== sections";   "$READELF" -S --wide "$W/probe.elf"
    exit 1
fi
echo "run-defaultlink: PASS (default emulation links and lays out all spaces)"

#!/bin/sh
# Check that the tree `make dist' installed is one somebody can actually
# assemble and link an 8051 program with, before it is packed into a release
# archive and published.  Nothing else in the repository looks at the installed
# toolchain: every gate stage runs the binaries straight out of the build tree,
# so `install' could drop a tool, or the linker script, and every stage would
# still be green.
#
#   usage: dist_check.sh PREFIX TARGET MODE
#
#   PREFIX   install prefix (work/modern/toolchain)
#   TARGET   target alias the programs are prefixed with (i51-elf)
#   MODE     native  the installed binaries are this machine's - run them
#            wine    they are mingw binaries and wine is installed - run them
#            none    they cannot be run here - static checks only
#
# exit: 0 shippable, 1 not shippable, 2 bad usage

set -u

PREFIX=${1-}
TARGET=${2-}
MODE=${3-native}

[ -n "$PREFIX" ] && [ -n "$TARGET" ] || {
    echo "usage: dist_check.sh PREFIX TARGET MODE" >&2; exit 2; }
case "$MODE" in
    native|wine|none) ;;
    *) echo "dist_check: MODE must be native, wine or none, not '$MODE'" >&2; exit 2 ;;
esac
PREFIX=$(cd "$PREFIX" 2>/dev/null && pwd) || {
    echo "dist_check: no such install prefix: ${1-}" >&2; exit 2; }

st=0
fail() { echo "FAIL: $*"; st=1; }

# bin/<target>-<tool>, with or without the .exe a mingw host appends.
prog() {
    for c in "$PREFIX/bin/$TARGET-$1" "$PREFIX/bin/$TARGET-$1.exe"; do
        if [ -f "$c" ]; then echo "$c"; return 0; fi
    done
    return 1
}

echo "== programs in $PREFIX/bin"
# The six the testbench wires up plus objdump and readelf, which its probes
# read, plus ranlib, which an archive needs.  Anything else install-binutils
# leaves behind is a bonus and is only listed.
for t in as ld ar nm objcopy objdump readelf ranlib strip; do
    if p=$(prog "$t"); then
        printf '   %-8s %s\n' "$t" "${p##*/}"
    else
        fail "$TARGET-$t is not in $PREFIX/bin"
    fi
done
echo "   ---- everything installed:"
ls "$PREFIX/bin" | sed 's/^/   /'

# The default linker script has to reach the user one of two ways: on disk under
# <prefix>/<target>/lib/ldscripts, where install-ld puts it, or compiled into ld
# itself, which is what genscripts does for the emulation named by the target's
# own configure.tgt entry.  tb/sim/run-defaultlink.sh links with no -T from a
# temporary directory that has no ldscripts anywhere near it, so on the build
# tree it is plainly the compiled-in copy that is being used - but that is a
# property of how the emulation was generated, not a promise, so both are looked
# for here and the archive is refused if neither is there.  An archive whose ld
# cannot link without an explicit -T is useless to the person who downloads it.
echo "== default linker script"
ondisk=no
[ -f "$PREFIX/$TARGET/lib/ldscripts/elf32i51.x" ] && ondisk=yes
builtin=no
LDPROG=$(prog ld) || LDPROG=
if [ -n "$LDPROG" ] && LC_ALL=C grep -a -q '__GSINIT_STARTUP' "$LDPROG"; then
    builtin=yes
fi
printf '   %-34s %s\n' "$TARGET/lib/ldscripts/elf32i51.x:" "$ondisk"
printf '   %-34s %s\n' "compiled into ld:" "$builtin"
if [ "$ondisk" = no ] && [ "$builtin" = no ]; then
    fail "no default linker script on disk and none inside ld: this toolchain cannot link without -T"
fi

# binutils is GPLv3 and its `make install' installs no licence text at all, so
# unless dist put one here the archive is a pile of GPL binaries nobody may
# redistribute.
echo "== licence and provenance"
set -- "$PREFIX"/COPYING*
if [ -f "$1" ]; then
    for f in "$@"; do printf '   %s\n' "${f##*/}"; done
else
    fail "no COPYING* in $PREFIX - GPL binaries may not be redistributed without one"
fi
if [ -f "$PREFIX/BUILD-INFO.txt" ]; then
    sed 's/^/   /' "$PREFIX/BUILD-INFO.txt"
else
    fail "no BUILD-INFO.txt in $PREFIX - the archive would not say what it is"
fi

# Assemble, link with ld's own default script and extract the ROM, using the
# INSTALLED programs.  One instruction is enough: `ljmp _START' at 0 is 02 00 00
# and the default script closes .text with __I51_RET = . ; BYTE(0x22), which is
# the same 02 00 00 22 that tb/sim/run-defaultlink.sh's larger image ends on.
if [ "$MODE" = none ]; then
    echo "== link probe SKIPPED (MODE=none: these binaries do not run on this machine)"
else
    echo "== link probe (MODE=$MODE)"
    AS=$(prog as)       || AS=
    LD=$(prog ld)       || LD=
    OBJCOPY=$(prog objcopy) || OBJCOPY=
    NM=$(prog nm)       || NM=
    if [ -z "$AS" ] || [ -z "$LD" ] || [ -z "$OBJCOPY" ] || [ -z "$NM" ]; then
        fail "link probe cannot run: one of as/ld/objcopy/nm is missing"
    else
        # BSD mktemp wants a template; GNU mktemp does not mind one.
        W=$(mktemp -d 2> /dev/null) || W=$(mktemp -d -t i51dist) \
            || { echo "dist_check: mktemp failed" >&2; exit 2; }
        trap 'rm -rf "$W"' EXIT INT TERM
        # Relative file names throughout, with $W as the working directory:
        # a mingw binary under wine resolves a unix absolute path against
        # whatever drive it happens to be on.
        {
            echo '; the smallest program that proves the shipped toolchain works.'
            echo '        .text'
            echo '        .global _START'
            echo '_START: ljmp    _START'
        } > "$W/probe.s"

        run() { if [ "$MODE" = wine ]; then wine "$@"; else "$@"; fi; }

        ( cd "$W" || exit 2
          run "$AS" -o probe.o probe.s ) || fail "$TARGET-as could not assemble the probe"
        # No -T, no -m, no --no-check-sections: the default emulation must work.
        ( cd "$W" || exit 2
          run "$LD" -o probe.elf probe.o ) || fail "$TARGET-ld could not link the probe with its default script"
        if [ -f "$W/probe.elf" ]; then
            ( cd "$W" || exit 2
              run "$OBJCOPY" -O binary --only-section=.text probe.elf probe.bin ) \
                || fail "$TARGET-objcopy could not extract the ROM"
        fi
        if [ -f "$W/probe.bin" ]; then
            img=$(od -An -v -tx1 "$W/probe.bin" | tr -d ' \n')
            want=02000022
            if [ "$img" = "$want" ]; then
                echo "   ROM image $img"
            else
                fail "ROM image $img, expected $want (ljmp _START, then the script's RET byte)"
            fi
        else
            fail "no ROM image was produced"
        fi
        if [ -f "$W/probe.elf" ]; then
            syms=$( ( cd "$W" || exit 2; run "$NM" probe.elf ) | tr -d '\r' )
            for pair in '_START 0' '__I51_RET 3' '_ETEXT 4'; do
                s=${pair% *}; wantv=${pair#* }
                v=$(printf '%s\n' "$syms" | awk -v s="$s" '$NF == s { print $1; exit }')
                # An undefined symbol prints `U' in the value column, and
                # $((0xU)) is a fatal arithmetic error, not a comparison that
                # fails - so the column is checked before it is read as a number.
                case "$v" in
                    '')
                        fail "$TARGET-nm does not report $s in the linked probe" ;;
                    *[!0-9a-fA-F]*)
                        fail "$s carries no address in nm's output: '$v'" ;;
                    *)
                        if [ $((0x$v)) -ne "$wantv" ]; then
                            fail "$s = 0x$v, expected $wantv"
                        else
                            printf '   %-12s 0x%s\n' "$s" "$v"
                        fi ;;
                esac
            done
        fi
    fi
fi

if [ "$st" -ne 0 ]; then
    echo "dist_check: NOT SHIPPABLE"
    exit 1
fi
echo "dist_check: PASS ($PREFIX assembles and links 8051 code)"

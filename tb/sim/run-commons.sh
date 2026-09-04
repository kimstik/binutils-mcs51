#!/bin/sh
# Memory-space commons: check that an external common keeps the address
# space it was declared in, all the way from the object file to the link.
#
# The port has one common directive per space (.rcomm .bcomm .bitcomm
# .icomm .xcomm .ecomm) next to plain .comm.  An external one is written
# out with a processor-specific section index - SHN_I51_RDATA_C 0xff01
# and friends - and readelf prints those numerically as PRC[0xff01].  A
# symbol that comes out as COM instead has lost its space: the linker
# then allocates it in byte-addressed .bss, and a bit common ends up
# carrying a byte address where a bit address is expected.
#
# Reading such a symbol back, bfd fabricates a common section named after
# the space it belongs to.  Further things are checked here:
#
#   - a relocatable link writes those commons out again itself, and the
#     linker hands every one of them to the backend as a plain
#     SHN_COMMON.  Only elf_backend_link_output_symbol_hook puts the
#     space index back; without it ld -r degrades every space common to
#     an ordinary one and the next link allocates a bit common in
#     byte-addressed .bss.
#   - an object may hold a REAL section of that name as well.  The
#     fabricated common section and the real one must stay separate, or
#     the SEC_IS_COMMON put on the common turns the real section into a
#     placeholder and the linker drops every byte it holds.
#   - the directive that names a space - .rbss, .xdata and the rest -
#     switches into the section of that name and creates it only when it
#     is not there yet.  A file that declared that section itself keeps
#     what it put in it, so a directive that resets the flags of a
#     section already full of data drops every byte of it.
#   - the space name is what a linker script places the common by.
#     Scripts written for this port name the spaces without a wildcard -
#     the 2001 web51 script has *(.regbank) and *(.ibss) - so the
#     fabricated section has to keep carrying the plain space name.
#
#   usage: run-commons.sh BUILD-DIR
#
#   BUILD-DIR   binutils build tree: gas/as-new, ld/ld-new,
#               binutils/readelf, binutils/objcopy
#
# exit: 0 pass, 1 a common lost its space, or a common or a directive
#       ate a real section, 2 bad usage/toolchain

set -u

BUILD=${1-}
[ -n "$BUILD" ] || { echo "usage: run-commons.sh BUILD-DIR" >&2; exit 2; }
AS=$BUILD/gas/as-new
LD=$BUILD/ld/ld-new
READELF=$BUILD/binutils/readelf
OBJCOPY=$BUILD/binutils/objcopy
for t in "$AS" "$LD" "$READELF" "$OBJCOPY"; do
    [ -x "$t" ] || { echo "run-commons: missing tool $t" >&2; exit 2; }
done

W=$(mktemp -d) || { echo "run-commons: mktemp failed" >&2; exit 2; }
trap 'rm -rf "$W"' EXIT INT TERM

# One external common per space, each with explicit alignment 1 so the
# sizes checked below are the sizes asked for and nothing else.
cat > "$W/commons.s" <<'EOF'
; one external common per memory space

        .text
        .global _START
_START: ret

        .rcomm   RCVAR,4,1     ; rdata      -> SHN_I51_RDATA_C   0xff01
        .bcomm   BCVAR,2,1     ; bdata      -> SHN_I51_BDATA_C   0xff02
        .icomm   ICVAR,8,1     ; idata      -> SHN_I51_IDATA_C   0xff03
        .xcomm   XCVAR,16,1    ; xdata      -> SHN_I51_XDATA_C   0xff04
        .ecomm   ECVAR,4,1     ; edata      -> SHN_I51_EDATA_C   0xff05
        .bitcomm BITVAR,1,1    ; bit space  -> SHN_I51_BITDATA_C 0xff06
        .comm    CVAR,3,1      ; direct RAM -> SHN_COMMON
EOF

"$AS" -o "$W/commons.o" "$W/commons.s" || { echo "run-commons: as-new failed" >&2; exit 1; }

st=0
fail() { echo "FAIL: $*"; st=1; }

# ---- the object: one section index per common ----------------------
# Each listing goes to a file of its own, so a later arm can read a
# second object and a second image without losing the first - the
# failure dump at the end prints all of them.
symlist() {  # FILE OUT, the symbol table as readelf prints it
    "$READELF" -s --wide "$1" | tr -d '\r' > "$2"
}
seclist() {  # FILE OUT, the section table with the [nn] index stripped
    "$READELF" -S --wide "$1" | tr -d '\r' \
        | sed 's/^ *\[ *[0-9]*\] *//' > "$2"
}

symlist "$W/commons.o" "$W/syms.txt"

ndx() { awk -v s="$2" '$NF == s { print $(NF-1); exit }' "$1"; }
expect_ndx() {  # WHAT SYMS-FILE SYMBOL NDX
    v=$(ndx "$2" "$3")
    [ -n "$v" ] || { fail "$1: symbol $3 not in the object"; return; }
    [ "$v" = "$4" ] || fail "$1: $3 has Ndx $v, expected $4"
}
expect_ndx object "$W/syms.txt" RCVAR  'PRC[0xff01]'
expect_ndx object "$W/syms.txt" BCVAR  'PRC[0xff02]'
expect_ndx object "$W/syms.txt" ICVAR  'PRC[0xff03]'
expect_ndx object "$W/syms.txt" XCVAR  'PRC[0xff04]'
expect_ndx object "$W/syms.txt" ECVAR  'PRC[0xff05]'
expect_ndx object "$W/syms.txt" BITVAR 'PRC[0xff06]'
expect_ndx object "$W/syms.txt" CVAR   COM

# ---- the link: every common allocated in its own space -------------
# The default script gives each space its own bss and the only thing in
# any of them is the one common declared for it, so the section sizes
# are the declared sizes.  A degraded common shows up as an empty space
# section and an oversized .bss.
if ! "$LD" -o "$W/commons.elf" "$W/commons.o" 2> "$W/ld.err"; then
    echo "run-commons: default link FAILED" >&2
    cat "$W/ld.err" >&2
    exit 1
fi
[ -s "$W/ld.err" ] && { echo "== ld stderr (non-fatal):"; cat "$W/ld.err"; }

seclist "$W/commons.elf" "$W/secs.txt"

expect_size() {  # WHAT SECS-FILE SECTION SIZE
    line=$(awk -v s="$3" '$1 == s { print; exit }' "$2")
    [ -n "$line" ] || { fail "$1: section $3 not in the image"; return; }
    sz=$(echo "$line" | awk '{ print $5 }')
    [ $((0x$sz)) -eq $(($4)) ] || fail "$1: $3 is 0x$sz bytes, expected $4"
}
expect_size "default link" "$W/secs.txt" .rbss   4
expect_size "default link" "$W/secs.txt" .bbss   2
expect_size "default link" "$W/secs.txt" .ibss   8
expect_size "default link" "$W/secs.txt" .xbss   16
expect_size "default link" "$W/secs.txt" .ebss   4
expect_size "default link" "$W/secs.txt" .bitbss 1
expect_size "default link" "$W/secs.txt" .bss    3

secfield() {  # FILE SECTION FIELD-INDEX, columns of readelf -S --wide
    "$READELF" -S --wide "$1" | tr -d '\r' \
        | sed 's/^ *\[ *[0-9]*\] *//' \
        | awk -v s="$2" -v f="$3" '$1 == s { print $f; exit }'
}
symval() {    # FILE SYMBOL
    "$READELF" -s --wide "$1" | tr -d '\r' \
        | awk -v s="$2" '$NF == s { print $2; exit }'
}
sechex() {    # FILE SECTION, lowercase hex of what the image holds there
    rm -f "$W/dump.bin"
    "$OBJCOPY" --dump-section "$2=$W/dump.bin" "$1" "$W/dump.elf" 2> /dev/null \
        || return 1
    od -An -v -tx1 "$W/dump.bin" | tr -d ' \n'
}

# ---- a relocatable link: the space survives the merge --------------
# ld -r leaves commons uninstantiated, so the merged object has to write
# them out itself.  It gets them from the linker hash table, where every
# one of them is a plain SHN_COMMON whatever space it came from, and
# only elf_backend_link_output_symbol_hook puts the index back - it is
# the one place in the port that knows the space from the name of the
# section the common arrived in.  Degrade a common here and nothing
# complains: the partial object links, and the space is gone by then.
#
# The commons are split over two objects, and RCVAR is declared in both,
# so the symbol that comes out of the merge is one the linker built from
# two inputs rather than one it copied through.
cat > "$W/parta.s" <<'EOF'
; the entry point, three spaces, and a common with no space at all

        .text
        .global _START
_START: ret

        .rcomm   RCVAR,4,1     ; declared again in partb.s
        .bcomm   BCVAR,2,1
        .icomm   ICVAR,8,1
        .comm    CVAR,3,1
EOF
cat > "$W/partb.s" <<'EOF'
; the other three spaces, and RCVAR a second time

        .rcomm   RCVAR,4,1     ; declared again in parta.s
        .xcomm   XCVAR,16,1
        .ecomm   ECVAR,4,1
        .bitcomm BITVAR,1,1
EOF

"$AS" -o "$W/parta.o" "$W/parta.s" \
    || { echo "run-commons: as-new failed on parta.s" >&2; exit 1; }
"$AS" -o "$W/partb.o" "$W/partb.s" \
    || { echo "run-commons: as-new failed on partb.s" >&2; exit 1; }

if ! "$LD" -r -o "$W/partial.o" "$W/parta.o" "$W/partb.o" 2> "$W/partial.err"; then
    echo "run-commons: relocatable link FAILED" >&2
    cat "$W/partial.err" >&2
    exit 1
fi
[ -s "$W/partial.err" ] && { echo "== ld stderr (partial, non-fatal):"; cat "$W/partial.err"; }

symlist "$W/partial.o" "$W/psyms.txt"
expect_ndx "partial object" "$W/psyms.txt" RCVAR  'PRC[0xff01]'
expect_ndx "partial object" "$W/psyms.txt" BCVAR  'PRC[0xff02]'
expect_ndx "partial object" "$W/psyms.txt" ICVAR  'PRC[0xff03]'
expect_ndx "partial object" "$W/psyms.txt" XCVAR  'PRC[0xff04]'
expect_ndx "partial object" "$W/psyms.txt" ECVAR  'PRC[0xff05]'
expect_ndx "partial object" "$W/psyms.txt" BITVAR 'PRC[0xff06]'
# A common that never had a space must not pick one up here.
expect_ndx "partial object" "$W/psyms.txt" CVAR   COM

# Linking the merged object allocates the same spaces the same sizes as
# linking the two inputs straight would.  A common that lost its space
# leaves its space section empty and shows up in .bss instead, so these
# sizes catch a hook that ran and got the space wrong as well as one
# that did not run.
if ! "$LD" -o "$W/partial.elf" "$W/partial.o" 2> "$W/plink.err"; then
    echo "run-commons: link of the partial object FAILED" >&2
    cat "$W/plink.err" >&2
    exit 1
fi
[ -s "$W/plink.err" ] && { echo "== ld stderr (partial link, non-fatal):"; cat "$W/plink.err"; }

seclist "$W/partial.elf" "$W/psecs.txt"
expect_size "partial link" "$W/psecs.txt" .rbss   4
expect_size "partial link" "$W/psecs.txt" .bbss   2
expect_size "partial link" "$W/psecs.txt" .ibss   8
expect_size "partial link" "$W/psecs.txt" .xbss   16
expect_size "partial link" "$W/psecs.txt" .ebss   4
expect_size "partial link" "$W/psecs.txt" .bitbss 1
expect_size "partial link" "$W/psecs.txt" .bss    3

# ---- a real section and a common in the same space -----------------
# Reading a memory-space common back, bfd fabricates a common section
# named after the space.  Here the same object also holds a real section
# of that name, with bytes in it.  The two have to stay separate: a
# fabrication that lands on the real section marks it SEC_IS_COMMON, and
# the linker then treats a section full of data as a size-only
# placeholder - the bytes are dropped, the link succeeds, nothing is
# said.
cat > "$W/mixed.s" <<'EOF'
; real data and an external common in one space, in one object

        .text
        .global _START
_START: ret

        .section .rbss,"aw",@progbits
        .global RREAL
RREAL:  .byte 0x11,0x22,0x33,0x44
        .rcomm RCVAR,4,1        ; external -> fabricated .rbss common

        .section .bitbss,"aw",@progbits
        .global BITREAL
BITREAL:
        .byte 0x5A
        .bitcomm BITVAR,1,1     ; external -> fabricated .bitbss common
EOF

"$AS" -o "$W/mixed.o" "$W/mixed.s" \
    || { echo "run-commons: as-new failed on mixed.s" >&2; exit 1; }

if ! "$LD" -o "$W/mixed.elf" "$W/mixed.o" 2> "$W/mixed.err"; then
    echo "run-commons: mixed link FAILED" >&2
    cat "$W/mixed.err" >&2
    exit 1
fi
[ -s "$W/mixed.err" ] && { echo "== ld stderr (mixed, non-fatal):"; cat "$W/mixed.err"; }

expect_mixed() {  # SECTION SIZE HEAD-BYTES COMMON-SYMBOL COMMON-ADDRESS
    sz=$(secfield "$W/mixed.elf" "$1" 5)
    [ -n "$sz" ] || { fail "mixed: section $1 not in the image"; return; }
    [ $((0x$sz)) -eq $(($2)) ] || fail "mixed: $1 is 0x$sz bytes, expected $2"
    if ! bytes=$(sechex "$W/mixed.elf" "$1"); then
        fail "mixed: $1 has no contents in the image - the real section was taken for a common"
        return
    fi
    case "$bytes" in
        "$3"*) ;;
        *)     fail "mixed: $1 holds '$bytes', expected it to start with '$3'" ;;
    esac
    v=$(symval "$W/mixed.elf" "$4")
    [ -n "$v" ] || { fail "mixed: symbol $4 not in the image"; return; }
    [ $((0x$v)) -eq $(($5)) ] || fail "mixed: $4 = 0x$v, expected $5"
}
# Four real bytes at the start of the space, the four-byte common after.
expect_mixed .rbss   8 11223344 RCVAR  4
# One real byte in the bit space, the one-bit common after it.
expect_mixed .bitbss 2 5a       BITVAR 1

# The same two things split over two objects.  Nothing collides inside
# one object here, so this passes either way; it pins the other half of
# the arrangement - real bytes first, then the common of the same space
# from the next object - so a fix for the collision cannot quietly
# reorder or drop one of them.
cat > "$W/real.s" <<'EOF'
; real data in a space, and the entry point

        .text
        .global _START
_START: ret

        .section .rbss,"aw",@progbits
        .global AREAL
AREAL:  .byte 0xAA,0xBB
EOF
cat > "$W/com.s" <<'EOF'
; the common of that space, in a second object

        .rcomm BCVAR,2,1
EOF

"$AS" -o "$W/real.o" "$W/real.s" \
    || { echo "run-commons: as-new failed on real.s" >&2; exit 1; }
"$AS" -o "$W/com.o" "$W/com.s" \
    || { echo "run-commons: as-new failed on com.s" >&2; exit 1; }

if ! "$LD" -o "$W/split.elf" "$W/real.o" "$W/com.o" 2> "$W/split.err"; then
    echo "run-commons: split link FAILED" >&2
    cat "$W/split.err" >&2
    exit 1
fi
[ -s "$W/split.err" ] && { echo "== ld stderr (split, non-fatal):"; cat "$W/split.err"; }

sz=$(secfield "$W/split.elf" .rbss 5)
if [ -z "$sz" ]; then
    fail "split: .rbss not in the image"
elif [ $((0x$sz)) -ne 4 ]; then
    fail "split: .rbss is 0x$sz bytes, expected 4"
fi
if ! bytes=$(sechex "$W/split.elf" .rbss); then
    fail "split: .rbss has no contents in the image"
else
    case "$bytes" in
        aabb*) ;;
        *)     fail "split: .rbss holds '$bytes', expected it to start with 'aabb'" ;;
    esac
fi
v=$(symval "$W/split.elf" BCVAR)
if [ -z "$v" ]; then
    fail "split: symbol BCVAR not in the image"
elif [ $((0x$v)) -ne 2 ]; then
    fail "split: BCVAR = 0x$v, expected 2"
fi

# ---- a real section and the directive that names the same space ----
# A memory-space directive creates the section it switches to the first
# time a file uses it.  The file may have created that section already,
# with .section and real bytes in it; the directive then has to switch
# into what is there and leave it alone.  Handing it the flags of a
# fresh section instead takes SEC_LOAD off a section full of data and
# marks it contentless: the bytes never reach the object, the assembler
# exits 0 and the link succeeds.
cat > "$W/spaces.s" <<'EOF'
; real bytes in a space, then the directive naming that same space

        .text
        .global _START
_START: ret

        .section .rbss,"aw",@progbits
        .global RKEEP
RKEEP:  .byte 0x11,0x22,0x33,0x44

        .rbss                   ; first use of the directive in this file

        .text
        nop
EOF

"$AS" -o "$W/spaces.o" "$W/spaces.s" \
    || { echo "run-commons: as-new failed on spaces.s" >&2; exit 1; }

expect_bytes() {  # WHAT FILE SECTION HEAD-BYTES
    if ! b=$(sechex "$2" "$3"); then
        fail "$1: $3 has no contents - a real section was marked a placeholder"
        return
    fi
    case "$b" in
        "$4"*) ;;
        *)     fail "$1: $3 holds '$b', expected it to start with '$4'" ;;
    esac
}

expect_bytes "spaces object" "$W/spaces.o" .rbss 11223344

if ! "$LD" -o "$W/spaces.elf" "$W/spaces.o" 2> "$W/spaces.err"; then
    echo "run-commons: spaces link FAILED" >&2
    cat "$W/spaces.err" >&2
    exit 1
fi
[ -s "$W/spaces.err" ] && { echo "== ld stderr (spaces, non-fatal):"; cat "$W/spaces.err"; }

sz=$(secfield "$W/spaces.elf" .rbss 5)
if [ -z "$sz" ]; then
    fail "spaces: .rbss not in the image"
elif [ $((0x$sz)) -ne 4 ]; then
    fail "spaces: .rbss is 0x$sz bytes, expected 4"
fi
expect_bytes "spaces image" "$W/spaces.elf" .rbss 11223344

# Bytes written after the switch land in the same section.  A section
# marked contentless refuses them instead, so this half of it is loud.
cat > "$W/spacesw.s" <<'EOF'
; real bytes in a space, the directive, then more bytes through it

        .text
        .global _START
_START: ret

        .section .rbss,"aw",@progbits
        .global RKEEP
RKEEP:  .byte 0x11,0x22,0x33,0x44

        .text
        nop

        .rbss                   ; first use of the directive in this file
        .global RMORE
RMORE:  .byte 0x55,0x66
EOF

if "$AS" -o "$W/spacesw.o" "$W/spacesw.s" 2> "$W/spacesw.err"; then
    expect_bytes "spaces written through the directive" \
        "$W/spacesw.o" .rbss 112233445566
else
    fail "spaces: bytes written through the .rbss directive were refused"
    cat "$W/spacesw.err"
fi

# A memory-space common declared local would be allocated in the space's
# section directly, the way .lcomm is allocated in .bss, and would meet
# the same real section.  It never is: .local in this port drops a
# built-in operand name from the hash table so user code can redefine a
# register name with .equ, and nothing else marks a symbol local, so a
# common stays external whatever precedes it.  Pinned here, because a
# .local that started marking symbols local instead would route commons
# through a path nothing else in this file reaches.
cat > "$W/localcom.s" <<'EOF'
; real bytes in a space, then a common of that space declared .local

        .text
        .global _START
_START: ret

        .section .rbss,"aw",@progbits
        .global RHOLD
RHOLD:  .byte 0xDE,0xAD

        .local  LCVAR
        .rcomm  LCVAR,4,1
EOF

"$AS" -o "$W/localcom.o" "$W/localcom.s" \
    || { echo "run-commons: as-new failed on localcom.s" >&2; exit 1; }

sz=$(secfield "$W/localcom.o" .rbss 5)
if [ -z "$sz" ]; then
    fail "localcom: .rbss not in the object"
elif [ $((0x$sz)) -ne 2 ]; then
    fail "localcom: .rbss is 0x$sz bytes, expected 2"
fi
expect_bytes "localcom" "$W/localcom.o" .rbss dead
lndx=$("$READELF" -s --wide "$W/localcom.o" | tr -d '\r' \
       | awk '$NF == "LCVAR" { print $(NF-1); exit }')
if [ -z "$lndx" ]; then
    fail "localcom: symbol LCVAR not in the object"
elif [ "$lndx" != 'PRC[0xff01]' ]; then
    fail "localcom: LCVAR has Ndx $lndx, expected PRC[0xff01] - .local now marks symbols local, and the local-common path needs a probe of its own"
fi

# The data-space directives take the same route.  This space section is
# read-only - "a" without "w" - so a reset of its flags shows in the
# object even where the bytes survive: SEC_READONLY goes and the section
# comes out writable.
cat > "$W/xspace.s" <<'EOF'
; read-only bytes in the xdata space, then the .xdata directive

        .text
        .global _START
_START: ret

        .section .xdata,"a",@progbits
        .global XKEEP
XKEEP:  .byte 0x77,0x88

        .text
        nop

        .xdata                  ; first use of the directive in this file
        .global XMORE
XMORE:  .byte 0x99
EOF

"$AS" -o "$W/xspace.o" "$W/xspace.s" \
    || { echo "run-commons: as-new failed on xspace.s" >&2; exit 1; }

expect_bytes "xspace" "$W/xspace.o" .xdata 778899
flg=$(secfield "$W/xspace.o" .xdata 7)
[ "$flg" = A ] || fail "xspace: .xdata has flags '$flg', expected 'A' - its flags were reset"

# ---- the name a linker script places a common by -------------------
# A common is placed by the name of the section it arrives in.  Scripts
# written for this port name the spaces with no wildcard - the 2001
# web51 script has *(.regbank) and *(.ibss), and every project linked
# against it has __RB__ register-bank commons and indirect-RAM commons
# to place.  A fabricated common section carrying anything but the plain
# space name falls out of those patterns and is placed as an orphan,
# moving every address behind it.
cat > "$W/named.ld" <<'EOF'
ENTRY(_START)
SECTIONS
{
  .text 0x0000 : { *(.text) }
  .reg  0x0000 (INFO) : { *(.regbank) __PROBE_REG_END = . ; }
  .ibss 0x0090 (INFO) : { *(.ibss)    __PROBE_IBSS_END = . ; }
  .data 0x0030 (INFO) : { *(.data) *(.bss) *(COMMON) }
}
EOF

cat > "$W/named.s" <<'EOF'
; a register bank in use and one indirect-RAM common

        .text
        .global _START
_START: .using 0
        ret

        .icomm ICVAR,8,1
EOF

"$AS" -o "$W/named.o" "$W/named.s" \
    || { echo "run-commons: as-new failed on named.s" >&2; exit 1; }

if ! "$LD" -T "$W/named.ld" -o "$W/named.elf" "$W/named.o" 2> "$W/named.err"; then
    echo "run-commons: named-pattern link FAILED" >&2
    cat "$W/named.err" >&2
    exit 1
fi
[ -s "$W/named.err" ] && { echo "== ld stderr (named, non-fatal):"; cat "$W/named.err"; }

expect_named() {  # SYMBOL VALUE
    v=$(symval "$W/named.elf" "$1")
    [ -n "$v" ] || { fail "named: symbol $1 not in the image"; return; }
    [ $((0x$v)) -eq $(($2)) ] || fail "named: $1 = 0x$v, expected $2"
}
# .using 0 claims one register bank, so __RB__ is eight bytes and
# *(.regbank) has to grow .reg to 8.  ICVAR is eight bytes at 0x90.
expect_named __PROBE_REG_END  8
expect_named ICVAR            0x90
expect_named __PROBE_IBSS_END 0x98

if [ "$st" -ne 0 ]; then
    echo "== symbols in the object";        cat "$W/syms.txt"
    echo "== sections in the linked image"; cat "$W/secs.txt"
    echo "== symbols in the partial object";       cat "$W/psyms.txt"
    echo "== sections after linking the partial";  cat "$W/psecs.txt"
    echo "== sections, real section plus common";
    "$READELF" -S --wide "$W/mixed.elf"
    echo "== symbols, real section plus common";
    "$READELF" -s --wide "$W/mixed.elf"
    echo "== sections, real section plus the directive of its space";
    "$READELF" -S --wide "$W/spaces.o"
    echo "== sections, real section plus a local common of its space";
    "$READELF" -S --wide "$W/localcom.o"
    echo "== sections, read-only xdata plus the .xdata directive";
    "$READELF" -S --wide "$W/xspace.o"
    echo "== symbols, script-named spaces";
    "$READELF" -s --wide "$W/named.elf"
    exit 1
fi
echo "run-commons: PASS (commons keep their space through a relocatable link, space directives keep their name, and the real sections beside them keep their bytes)"

B=/tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/work/modern/build
AS=$B/gas/as-new; LD=$B/ld/ld-new; OD=$B/binutils/objdump; RE=$B/binutils/readelf; NM=$B/binutils/nm-new; AR=$B/binutils/ar; OC=$B/binutils/objcopy
txt() { $OC -O binary -j .text "$1" /tmp/claude-0/-home-user/db7d4289-e9f3-5310-8ce9-42cf719f783e/scratchpad/review/ld/_t.bin && od -An -tx1 _t.bin | tr -d "\n"; echo; }

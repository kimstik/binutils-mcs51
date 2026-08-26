#!/bin/sh
# One work item for run.sh: $1 is the class (elf/ar/dis/as), $2 the input.
# Runs the tools that class calls for and appends a line to findings.txt for
# every signal, hang or sanitizer report.
set -u
CLASS=$1
IN=$2
OUT=$I51_OUT
B=$(basename "$IN" | sed 's/\.[^.]*$//')
SCRATCH=$OUT/scratch/$$
mkdir -p "$SCRATCH"

report () {
  printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" >> "$OUT/findings.txt"
  printf 'FINDING %-10s %-40s %s\n' "$1" "$2" "$3"
}

probe () {
  label=$1; shift
  log=$OUT/logs/$(echo "$label" | tr '/ ' '__').log
  timeout -s KILL "$I51_TIMEOUT" "$@" > "$log" 2>&1
  rc=$?
  tool=$(basename "$1")
  if [ "$rc" -eq 137 ]; then
    report "$tool" "$label" "TIMEOUT" "$log"
  elif [ "$rc" -ge 128 ]; then
    report "$tool" "$label" "SIGNAL $((rc - 128))" "$log"
  elif grep -qE 'AddressSanitizer|runtime error:|SEGV|[Aa]ssertion fail|internal error, aborting|Aborted' "$log"; then
    why=$(grep -m1 -hoE 'ERROR: AddressSanitizer: [a-z_-]+|runtime error: .*|[Aa]ssertion fail[^ ]*|internal error, aborting[^,]*' "$log" | head -1)
    report "$tool" "$label" "SAN: $why" "$log"
  else
    rm -f "$log"
  fi
}

case $CLASS in
elf)
  probe "nm/$B"        "$NM" "$IN"
  probe "objdumpx/$B"  "$OBJDUMP" -x "$IN"
  probe "objdumpD/$B"  "$OBJDUMP" -D "$IN"
  probe "objdumpr/$B"  "$OBJDUMP" -r "$IN"
  probe "readelf/$B"   "$READELF" -a "$IN"
  probe "objcopy/$B"   "$OBJCOPY" "$IN" "$SCRATCH/copy.o"
  probe "objcopyhex/$B" "$OBJCOPY" -O ihex "$IN" "$SCRATCH/copy.hex"
  probe "objcopybin/$B" "$OBJCOPY" -O binary "$IN" "$SCRATCH/copy.bin"
  probe "strip/$B"     "$STRIP" -o "$SCRATCH/strip.o" "$IN"
  probe "ldr/$B"       "$LD" -r -o "$SCRATCH/link.o" "$IN"
  probe "ld/$B"        "$LD" -e 0 --defsym EXTFUNC=0x100 --defsym EXTDATA=0x30 \
                             --defsym EXTBIT=0x20 -o "$SCRATCH/link.elf" "$IN"
  ;;
ar)
  probe "art/$B"       "$AR" t "$IN"
  probe "arp/$B"       "$AR" p "$IN"
  probe "nmar/$B"      "$NM" "$IN"
  probe "ldar/$B"      "$LD" -r -o "$SCRATCH/link.o" "$IN"
  probe "objdumpar/$B" "$OBJDUMP" -x "$IN"
  ;;
dis)
  probe "dis/$B"       "$OBJDUMP" -D "$IN"
  probe "disS/$B"      "$OBJDUMP" -d -j .text "$IN"
  ;;
as)
  probe "as/$B"        "$AS" -o "$SCRATCH/as.o" "$IN"
  ;;
esac
rm -rf "$SCRATCH"

#!/bin/sh
# Robustness harness for the i51 port.
#
#   BUILD=<binutils build dir> ./run.sh [outdir]
#
# Builds tb/fuzz/seed.s, mutates the object every way tb/fuzz/elfmangle.py
# knows, and feeds every mutant to nm, objdump, readelf, objcopy, strip and
# ld.  Then the archive mutants, then adversarial byte streams through the
# disassembler, then the hostile assembler corpus through gas.
#
# A finding is a tool that dies on a signal, emits a sanitizer report, or
# does not terminate.  Everything else - a diagnostic, a non-zero exit,
# "file format not recognized" - is the tool doing its job.
#
# Point BUILD at a build configured with
#   -fsanitize=address,undefined -fno-sanitize-recover=all
# or the silent out-of-bounds reads stay silent.

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD=${BUILD:?set BUILD to a binutils build directory}
OUT=${1:-/tmp/i51fuzz}
JOBS=${JOBS:-4}
export I51_TIMEOUT=${TIMEOUT:-20}
export ASAN_OPTIONS=detect_leaks=0:abort_on_error=0
export UBSAN_OPTIONS=print_stacktrace=1

export AS=$BUILD/gas/as-new
export LD=$BUILD/ld/ld-new
export NM=$BUILD/binutils/nm-new
export OBJDUMP=$BUILD/binutils/objdump
export READELF=$BUILD/binutils/readelf
export OBJCOPY=$BUILD/binutils/objcopy
export STRIP=$BUILD/binutils/strip-new
export AR=$BUILD/binutils/ar
export I51_OUT=$OUT

rm -rf "$OUT"
mkdir -p "$OUT/mutants" "$OUT/logs" "$OUT/scratch"
: > "$OUT/findings.txt"

echo "== seed"
"$AS" -o "$OUT/seed.o" "$HERE/seed.s" || exit 1

echo "== elf mutants"
python3 "$HERE/elfmangle.py" "$OUT/seed.o" "$OUT/mutants"

echo "== archives"
mkdir -p "$OUT/ar"
cp "$OUT/seed.o" "$OUT/ar/a.o"
( cd "$OUT/ar" && "$AR" rcs good.a a.o >/dev/null 2>&1 )
python3 "$HERE/armangle.py" "$OUT/ar/good.a" "$OUT/ar/mut"

echo "== disassembler inputs"
sh "$HERE/gen_dis.sh" "$OUT/dis" "$AS"

echo "== assembler inputs"
sh "$HERE/gen_asm.sh" "$OUT/asm"
python3 "$HERE/gen_asm_rand.py" "$OUT/asmrand" "${RAND:-2000}"

echo "== running"
{
  for m in "$OUT"/mutants/*.o;  do echo "elf $m"; done
  for m in "$OUT"/ar/mut/*.a;   do echo "ar $m"; done
  for m in "$OUT"/dis/*.o;      do echo "dis $m"; done
  for s in "$OUT"/asm/*.s;      do echo "as $s"; done
  for s in "$OUT"/asmrand/*.s;  do echo "as $s"; done
} | xargs -P "$JOBS" -n 2 sh "$HERE/probe.sh"

echo
n=$(wc -l < "$OUT/findings.txt")
echo "== $n findings; see $OUT/findings.txt and $OUT/logs/"
sort -t'	' -k3 "$OUT/findings.txt" | awk -F'\t' '{print $1"\t"$3}' | sort | uniq -c | sort -rn | head -40

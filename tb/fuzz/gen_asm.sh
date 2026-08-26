#!/bin/sh
# Generate the hostile assembler corpus into $1 (default tb/fuzz/asm).
# Everything here is input gas must diagnose without crashing, hanging or
# asserting.  Nothing here is expected to assemble.
set -e
OUT=${1:-$(dirname "$0")/asm}
mkdir -p "$OUT"
cd "$OUT"

# --- empty and binary --------------------------------------------------
: > empty.s
printf 'x' > one_byte.s
head -c 4096 /dev/urandom > binary_garbage.s
printf '\0\0\0\0\0\0\0\0' > nul_bytes.s
printf 'nop' > no_trailing_newline.s

# --- directives with wrong/missing/extra arguments ---------------------
for d in bit local using rcomm rcommon bitcomm bitcommon comm common \
         icomm icommon xcomm xcommon ecomm ecommon bcomm bcommon \
         bss rbss bbss ibss xbss ebss bitbss rdata bdata idata xdata \
         edata bitdata eeprom pcode; do
  printf '\t.%s\n' "$d"                        > "dir_${d}_none.s"
  printf '\t.%s ,\n' "$d"                      > "dir_${d}_comma.s"
  printf '\t.%s ,,,,,,,,\n' "$d"               > "dir_${d}_commas.s"
  printf '\t.%s @@@\n' "$d"                    > "dir_${d}_garbage.s"
  printf '\t.%s -1\n' "$d"                     > "dir_${d}_neg.s"
  printf '\t.%s 99999999999999999999\n' "$d"   > "dir_${d}_huge.s"
  printf '\t.%s x, -1\n' "$d"                  > "dir_${d}_negsize.s"
  printf '\t.%s x, 0x7fffffff\n' "$d"          > "dir_${d}_hugesize.s"
  printf '\t.%s x, 4, 3\n' "$d"                > "dir_${d}_badalign.s"
  printf '\t.%s x, 4, -8\n' "$d"               > "dir_${d}_negalign.s"
  printf '\t.%s "\n' "$d"                      > "dir_${d}_openquote.s"
done

# --- .using with garbage ----------------------------------------------
cat > using_none.s <<'E'
	.using
E
cat > using_4.s <<'E'
	.using 4
E
cat > using_eof.s <<'E'
	.using
E
printf '\t.using' > using_noeol.s
cat > using_expr.s <<'E'
	.using 1+1
E
cat > using_neg.s <<'E'
	.using -1
E
cat > using_sym.s <<'E'
	.using foo
E
cat > using_many.s <<'E'
	.using 0
	.using 1
	.using 2
	.using 3
	.using 9
	mov a, ar0
E
cat > using_missing.s <<'E'
	mov a, ar7
E

# --- bit addressing ----------------------------------------------------
cat > bit_0x20_99.s <<'E'
	setb 0x20.99
E
cat > bit_0xff_0.s <<'E'
	setb 0xff.0
E
cat > bit_0x00_0.s <<'E'
	setb 0x00.0
E
cat > bit_dot_eol.s <<'E'
	setb 0x20.
E
cat > bit_neg.s <<'E'
	setb -1.0
E
cat > bit_huge.s <<'E'
	setb 0x7fffffffffff.7
E
cat > bit_directive_nonbit.s <<'E'
	.bitdata
	.bit 2
	.bit -1
	.bit 0x7fffffff
	.bit
	.bit ,
E
cat > b2b_noclose.s <<'E'
	setb B2B(0x20,3
E
cat > b2b_nocomma.s <<'E'
	setb B2B(0x20)
E
cat > b2b_negoff.s <<'E'
	setb B2B(0x20,-1)
E
cat > b2b_hugeoff.s <<'E'
	setb B2B(0x20,99999)
E
cat > b2b_nonbit.s <<'E'
	setb B2B(0x31,1)
E

# --- expressions -------------------------------------------------------
python3 - <<'E'
open('expr_deep_parens.s','w').write('\tmov a, #' + '('*20000 + '1' + ')'*20000 + '\n')
open('expr_deep_unbalanced.s','w').write('\tmov a, #' + '('*20000 + '1\n')
open('expr_deep_unary.s','w').write('\tmov a, #' + '-'*20000 + '1\n')
open('expr_deep_not.s','w').write('\tmov a, #' + '~'*20000 + '1\n')
open('expr_long_chain.s','w').write('\tmov a, #' + '+'.join(['1']*50000) + '\n')
open('sym_long_name.s','w').write('a'*100000 + ':\n\tnop\n')
open('line_long.s','w').write('\tnop ' + ' '*1000000 + '\n')
open('op_long.s','w').write('\t' + 'a'*100000 + ' 1,2\n')
open('label_many.s','w').write(''.join('l%d:\n' % i for i in range(50000)))
E
cat > expr_div_zero.s <<'E'
	mov a, #(1/0)
E
cat > expr_mod_zero.s <<'E'
	mov a, #(1%0)
E
cat > expr_huge_const.s <<'E'
	mov a, #0xffffffffffffffffffffffff
	ljmp 0xffffffffffffffff
	.long 0x123456789abcdef0123
E
cat > expr_shift_huge.s <<'E'
	mov a, #(1 << 9999)
E
cat > expr_neg_operand.s <<'E'
	mov a, #-99999999
	sjmp -99999999
	ljmp -99999999
	acall -99999999
E
cat > string_unterminated.s <<'E'
	.ascii "abcdef
E
cat > string_unterminated2.s <<'E'
	.asciz "abc\
E
cat > quote_only.s <<'E'
"
E

# --- operand parsing ---------------------------------------------------
cat > op_at_prefix.s <<'E'
	mov @foo, a
E
cat > op_hash_only.s <<'E'
	mov a, #
E
cat > op_slash_only.s <<'E'
	anl c, /
E
cat > op_high_noclose.s <<'E'
	mov a, #HIGH(1
E
cat > op_low_noclose.s <<'E'
	mov a, #LOW(1
E
cat > op_trailing_comma.s <<'E'
	mov a, r0,
E
cat > op_extra_operand.s <<'E'
	nop 1, 2, 3
	ret a
	mov a, r0, r1, r2
E
cat > op_missing.s <<'E'
	mov
	mov a,
	cjne a, #1
	djnz
E
cat > op_unknown.s <<'E'
	zzzz
	.byte 1
	qqqqqqqqqqqqqqqqqqqqqqq a, b
E
cat > pcode_short.s <<'E'
	.pcode
	.pcode 1
	.pcode 1,
	.pcode 1,,,,
	.pcode 0x100, #WORD, @, #SWAP
	.pcode -1, -1, -1, -1
	.pcode 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff
E
cat > local_garbage.s <<'E'
	.local
	.local ,
	.local A, B, C, ACC, R0, @R0, @A+DPTR, nonexistent
	.local "quoted"
	mov a, r0
E
echo "generated $(ls | wc -l) files in $OUT"

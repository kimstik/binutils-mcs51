# R5: account for the rewrite

Owner threw away history. `work/green` gone, `main` fresh squash. Question:
did anything fall out, and what changed besides EM_8051.

Answer up front: **nothing that runs was lost. Three documents were dropped on
purpose. One hash block in `tb/base2001.PROVENANCE` went stale and nobody
noticed.** `tb/fuzz/` still not here.

---

## 0. Baseline is real, not guessed

Old head 0f45319 is not dangling. It is still an object in this repo, parent of
every review branch.

```
$ git rev-parse --verify 0f45319^{commit}
0f45319ae5774231b651f53675f3121f74fd12bc

$ git log --oneline -2 claude/review-testcode
1792ce5 REVIEW-testcode.md: read the testbench's own code as code
0f45319 bfd: bounds-check r_offset before relocating

$ git log --oneline -2 claude/review-unfinished
016b487 review: inventory of unfinished, dead and never-firing code
0f45319 bfd: bounds-check r_offset before relocating

$ git log --oneline -2 claude/review-docs-truth
b89f1ae review: check every documented claim against the tree as it stands
0f45319 bfd: bounds-check r_offset before relocating

$ git log --oneline -2 claude/review-execution
b6c2fc2 review: execute the ten project ROMs in ucsim
0f45319 bfd: bounds-check r_offset before relocating

$ git log --oneline -2 claude/validate-merged
d42a49a tb: validate the four merged fix branches by execution
0f45319 bfd: bounds-check r_offset before relocating
```

Five branches, one parent. Baseline confirmed. All five diff below use it.

---

## 1. The whole delta

```
$ git diff --stat 0f45319 origin/main
 .github/workflows/gate.yml                |   2 +-
 README.md                                 |   3 +-
 mcs51/additions.patch                     |  32 +--
 mcs51/modifications.patch                 |  14 +-
 tb/Makefile                               |   3 -
 tb/base.7z                                | Bin 140018 -> 139839 bytes
 tb/base2001.PROVENANCE                    |  10 +-
 tb/frozen-report.md                       | 394 ------------------------------
 tb/hexoracle.py                           |   3 +-
 tb/i51elf_le2be.py                        |   6 +-
 tb/objects-report/PROVENANCE              | 214 ----------------
 tb/objects-report/REPORT.md               | 188 --------------
 tb/objects-report/staged/cgi/bd.obj       | Bin 2788 -> 0 bytes
 ... 27 more staged/*.obj, all -> 0 bytes ...
 40 files changed, 23 insertions(+), 846 deletions(-)

$ git ls-tree -r --name-only 0f45319 | wc -l
73
$ git ls-tree -r --name-only origin/main | wc -l
42
```

73 files in. 42 out. 31 gone. 9 touched.

Classify every one:

| file | class | what |
|---|---|---|
| `mcs51/additions.patch` | EM re-stamp | drop `ELF_MACHINE_ALT1`, drop `EM_I51_OLD`, drop `bfd_elf_i51_final_write_processing` |
| `mcs51/modifications.patch` | EM re-stamp | drop 3 `EM_I51_OLD` cases in readelf |
| `tb/base.7z` | EM re-stamp | 221 ELF headers 0x1051 -> 0x00a5 |
| `tb/i51elf_le2be.py` | EM re-stamp | writes 165, not 0x1051 |
| `README.md` | EM re-stamp | drop "0x1051 still accepted on input" claim |
| `.github/workflows/gate.yml` | intended fix | drop pointer to file that never existed |
| `tb/Makefile` | intended fix | same, 2 pointers |
| `tb/hexoracle.py` | intended fix | same, 2 pointers. comment only |
| `tb/base2001.PROVENANCE` | intended fix + **DEFECT** | prose repointed. hashes NOT updated |
| `tb/frozen-report.md` | dropped content | 394 lines, gone |
| `tb/objects-report/*` (30 files) | dropped content | report + provenance + 28 staged .obj |

Nothing unexplained. Every changed byte accounted for.

### The re-stamp is exactly a re-stamp

Not a rebuild. Not new inputs. Checked byte by byte, all 36 differing members of
`base.7z`:

```
total differing bytes: 442
e_machine 0x1051->0x00a5 pairs: 221 (=442 bytes)
unexplained differing bytes: 0
```

Every file same length. Archive shrank 140018 -> 139839 only because LZMA
repacked. One member spelled out:

```
cgi/bd.obj size 2788 2788  diff offsets [18, 19]
  off 18: 51 -> a5
  off 19: 10 -> 00
old e_machine 1051  new e_machine 00a5
old EI_DATA 1 new EI_DATA 1
```

Offset 18 is `e_machine`. Nothing else moved.

### The pointers that were removed pointed at nothing

`ROOTCAUSE-rom-delta.md` was never a file. Baseline referenced it three times:

```
$ git grep -n "ROOTCAUSE-rom-delta" 0f45319
0f45319:.github/workflows/gate.yml:88:      # recorded one. See ROOTCAUSE-rom-delta.md.
0f45319:tb/Makefile:296:# ROOTCAUSE-rom-delta.md derives all of this.
0f45319:tb/hexoracle.py:55:their bytes are not classified.  See ROOTCAUSE-rom-delta.md.

$ git ls-tree -r --name-only 0f45319 | grep -i rootcause
ABSENT
```

Three dangling references removed. Good. Tree now has zero:

```
$ grep -rn "frozen-report\|objects-report\|ROOTCAUSE" . --exclude-dir=.git --exclude-dir=work
NONE
```

### The dropped documents

`frozen-report.md` was the write-up of `make check-frozen` — 2.11.2 toolchain
against the current reference ROMs. `objects-report/` was the provenance hunt
for the missing precompiled objects, plus 28 staged copies of them.

Those 28 staged `.obj` were a second, independent copy of base.7z members:

```
staged objects identical to OLD base.7z members: 28 ; differing: 0
```

So no unique bytes died with them. What died is the corroboration — the
independent copy that let you check base.7z against something.

Nothing in the build or the gate reads any of the three. All three are prose.
The numbers they derived still live in `tb/frozen.expect`, `tb/hexoracle.py`
and `tb/Makefile`, all unchanged. Loss is real but it is documentation loss.

### DEFECT the rewrite introduced

`tb/base2001.PROVENANCE` section 3 records sha256 of seven `base.7z` members.
base.7z got re-stamped. The hashes did not.

Recorded:

```
ed9a9d70a14af5d7dabc24e94e02018c7556c696911aa0f0db617bac2ba70158   45166  lib/libk23.a
6c16cb145933d2ac1030f860473e5cc04213ec96ce4e5f2c8faae7db22ddeaa2   42638  lib/libk80.a
1d7c810e130f723de3c3af74579f96ce03365612c2a92a683c0bd85e8437c5c9   78576  lib/libw23.a
8065c61fdeef0bab337aef57014bffbfe1a8ecf472f6da1f6a14204ff456b8a6   78576  lib/libw80.a
a00bb9ecd9ad9e7c58d9f9c4efa407b92ba129d0535c80aef7f13a840b09b71e   10708  lib/web51_23.obj
ff0c60de66ebcd6a08ab7346039f1499fa5dcc29edb365213298065ca0e4b0a1   10280  lib/web51_80.obj
dae56bcbf5f68928779f6e9c2bdc8edd055694558603ab42d9e746d1c08cf2ea   55332  cgi/libcgi.a
```

Actual, from the shipped `base.7z`:

```
$ sha256sum lib/libk23.a lib/libk80.a lib/libw23.a lib/libw80.a \
            lib/web51_23.obj lib/web51_80.obj cgi/libcgi.a
fda60a93589a0c30e8d731593071f2a82f777c436ec8aeab79d32f1fa0b6f96c  lib/libk23.a
5c4af50d95a654b868ba189d1dfe281be67fa28bb41ae6f842a88b82cd28f42a  lib/libk80.a
00c2b7a6d17b76ceb5910a66956938fb6d69236ca0503473790632ce5c622a84  lib/libw23.a
51f64f826c35a449e0185324b036220d62199a4073c9e1bc22b57e8887bbf927  lib/libw80.a
f18aadd95ea4878b6a15fc43f4dec708687099316c11c4f483ba7bb558f8493c  lib/web51_23.obj
fee841e7329e4b5e6e4b2fa8a6fc2adc994f5505643b1c1b7ddbcfd8b6c0ba4c  lib/web51_80.obj
14077543bf5647187fd03a75d360a42a3c81c2245d0fa99501c963cc1a7c333e  cgi/libcgi.a
```

Seven for seven wrong. Sizes still right (the re-stamp preserves length), which
is why it hides:

```
$ stat -c '%s %n' ...
45166 lib/libk23.a
42638 lib/libk80.a
78576 lib/libw23.a
78576 lib/libw80.a
10708 lib/web51_23.obj
10280 lib/web51_80.obj
55332 cgi/libcgi.a
```

Nothing verifies these, so nothing went red:

```
$ grep -rn "PROVENANCE" tb/Makefile .github/workflows/
tb/Makefile:45:# file is and where it came from: base2001.PROVENANCE.
```

Not a build break. Is a truth break. The same document also still says the 26
`cgi/*.obj` hashes match the "STAGED OUTPUTS" block of the objects report — a
document this commit deleted, whose hashes were the pre-re-stamp bytes anyway.

---

## 2. The named fixes. All fifteen still there.

Each grepped out of `mcs51/*.patch` on `origin/main`.

**howto sizes as byte counts** — `grep -n "HOWTO (R_I51" -A2 mcs51/additions.patch`

```
97:+  HOWTO (R_I51_NONE,   ... 99-+  0,  /* size in bytes */
112:+  HOWTO (R_I51_R1,     ... 114-+ 1,  /* size in bytes */
157:+  HOWTO (R_I51_11,     ... 159-+ 2,  /* size in bytes */
232:+  HOWTO (R_I51_16,     ... 234-+ 2,  /* size in bytes */
262:+  HOWTO (R_I51_13_PCODE, . 264-+ 2,  /* size in bytes */
```

Byte counts, not log2. PRESENT.

**bfd_getb16/putb16** — PRESENT, 12 hits.

```
426:+      x = bfd_getb16 (contents);
428:+      bfd_putb16 (x, contents);
475:+      bfd_putb16 ((bfd_vma) srel & 0xFFFF, contents);
1947:+	  insn = bfd_getb16 (where) & 0x1F00;
4425:+  return bfd_getb16(buffer);
```

**howto index bounds check** — PRESENT, both sites.

```
342:+  if (r_type >= (unsigned int) R_I51_max)
343:+    { _bfd_error_handler (_("%pB: invalid relocation type %d"), abfd, r_type);
348:+  cache_ptr->howto = &elf_i51_howto_table[r_type];

542:+      if (r_type < 0 || r_type >= (int) R_I51_max)
549:+      howto  = elf_i51_howto_table + r_type;
```

**bfd_reloc_offset_in_range at i51_final_link_relocate entry** — PRESENT, and it
is the first statement, before the switch.

```
383:+i51_final_link_relocate (reloc_howto_type *howto, ...
391:+  if (!bfd_reloc_offset_in_range (howto, input_bfd, input_section,
392:+				  rel->r_offset
393:+				  * bfd_octets_per_byte (input_bfd,
394:+							 input_section)))
395:+    return bfd_reloc_outofrange;
397:+  switch (howto->type)
```

**ACALL/AJMP page checks** — PRESENT, both sides, and they say so.

bfd:
```
+      if (((srel ^ (rel->r_offset + input_section->output_section->vma
+		    + input_section->output_offset + 2)) & 0x0000F800l) != 0)
+	return bfd_reloc_overflow;
```
gas:
```
+	    long pc = (fixp->fx_frag->fr_address + fixp->fx_where + 2);
+	    if (((value ^ pc) & 0xF800) != 0)
+	      as_bad_where (... "ACALL/AJMP target 0x%lx is not in the same 2K page as 0x%lx"
```

**disassembler `mov direct,direct` order** — PRESENT.

```
4625:+	  /* MOV direct,direct (0x85) is the one insn that encodes the
     +	     source byte first, so the operands come out swapped.  */
     +	  if (opcode->args[0] == 'D')
     +	    { char tmp[16]; strcpy (tmp, op1); strcpy (op1, op2); strcpy (op2, tmp); }
```

**disassembler `anl/orl C,/bit`** — PRESENT.

```
4606:+	case '/':	// /bit
     +	  opdata = i51dis_opcode (addr, info);
     +	  sprintf (op2,"/0x%02X",opdata);
4473:+    case '/':	return dis_style_address;
```

**disassembler 0x7E/0x7F sign** — PRESENT, both `J` branches.

```
+	  /* Sign-extend the encoded displacement before deciding its sign:
+	     testing bit 7 of (displacement + insn length) turns the largest
+	     forward branches into backward ones.  */
+	  disp = ((opdata ^ 0x80) & 0xFF) - 0x80;
```

**B2B bounds 0x80..0xF8 step 8** — PRESENT, literally in gas:

```
+	    else if (value >= 0x80 && value <= 0xF8 && (value & 7) == 0)
+	      where[0] = (bfd_byte) (value + off);
+	    else
+	      as_bad_where (... "0x%lx is not bit addressable"
```

bfd mirrors it:

```
+      if (srel >= 0x100) return bfd_reloc_outofrange;
+      if (srel < 0x20) return bfd_reloc_outofrange;
+      if ((srel < 0x30) && (((srel - 0x20) * 8 + x) >= 0x80)) return bfd_reloc_overflow;
+      if ((srel >= 0x30) && ((srel < 0x80) || (srel & 7) != 0)) return bfd_reloc_outofrange;
```

**elf32_i51_link_output_symbol_hook** — PRESENT, defined and wired.

```
990:+elf32_i51_link_output_symbol_hook (struct bfd_link_info *info ...
1005:+  if (strcmp (sname, ".regbank") == 0)  sym->st_shndx = SHN_I51_REGBANK;
1007:+  else if (strcmp (sname, ".rbss") == 0)  sym->st_shndx = SHN_I51_RDATA_C;
1042:+#define elf_backend_link_output_symbol_hook	elf32_i51_link_output_symbol_hook
```

**default script ADDR(prev)+SIZEOF(prev) chaining** — PRESENT, in
`ld/scripttempl/elf32i51.sc`, 12 arms chained:

```
4186:+  .rdata (ADDR (.regbank) + SIZEOF (.regbank)) (INFO) :
4192:+  .rbss (ADDR (.rdata) + SIZEOF (.rdata)) (INFO) :
4200:+  .bdata MAX (0x20, ADDR (.rbss) + SIZEOF (.rbss)) (INFO) :
4206:+  .bbss (ADDR (.bdata) + SIZEOF (.bdata)) (INFO) :
4217:+  .bit ((ADDR (.bbss) + SIZEOF (.bbss) - 0x20) * 8) (INFO) :
4223:+  .bitbss (ADDR (.bit) + SIZEOF (.bit)) (INFO) :
4239:+  .bss (ADDR (.data) + SIZEOF (.data)) (INFO) :
4251:+  .idata (ADDR (.bss) + SIZEOF (.bss)) (INFO) :
4257:+  .ibss (ADDR (.idata) + SIZEOF (.idata)) (INFO) :
4275:+  .xbss (ADDR (.xdata) + SIZEOF (.xdata)) (INFO) :
4289:+  .ebss (ADDR (.edata) + SIZEOF (.edata)) (INFO) :
```

Plus the two ASSERTs still guard `.bdata`/`.bit`.

**O_max / had_errors() guard in gas** — PRESENT.

```
1695:+  int errors_before = had_errors ();
1700:+  op_expr1.X_op = O_max;
1701:+  op_expr2.X_op = O_max;
...
1795:+      if (had_errors () != errors_before)
1796:+	return;
1798:+      if ((op1mode == opcode->args[0]) && (op2mode == opcode->args[1]))
1800:+	  i51_build_ins (opcode, regno, &op_expr1, &op_expr2);
```

**--defsym binding fix** — PRESENT. Still moved to `tc_init_after_args`.

```
1598:+   rather than from md_begin: gas_init () defines the --defsym symbols
1599:+   before md_begin () runs, so setting it any later leaves those names
1600:+   unfolded and unreachable from the source.  */
1603:+i51_init_after_args (void)
1605:+  symbols_case_sensitive = 0;
3843:+#define tc_init_after_args() i51_init_after_args ()
```

**print_address_func + fprintf_styled_func + i51_symbol_is_valid** — all three
PRESENT.

```
mcs51/additions.patch:4443:+i51_symbol_is_valid (asymbol *sym, struct disassemble_info *info)
mcs51/additions.patch:4488:+  fprintf_styled_ftype prin = info->fprintf_styled_func;
mcs51/additions.patch:4721:+      if (op1_is_code_addr && info->print_address_func != NULL)
mcs51/additions.patch:4722:+	(*info->print_address_func) (code_target, info);
mcs51/modifications.patch:577:+      info->symbol_is_valid = i51_symbol_is_valid;
mcs51/modifications.patch:593:+extern bool i51_symbol_is_valid	(asymbol *, struct disassemble_info *);
```

**EM_8051 with no ALT1** — PRESENT and clean.

```
$ grep -n "EM_8051\|ELF_MACHINE_ALT1\|EM_I51_OLD\|0x1051" mcs51/additions.patch mcs51/modifications.patch
mcs51/additions.patch:1024:+#define ELF_MACHINE_CODE	EM_8051
mcs51/additions.patch:3875:+/* The machine number is the registered EM_8051 (165), defined in
mcs51/modifications.patch:342:+    case EM_8051:
mcs51/modifications.patch:350:+	case EM_8051:
```

Zero `ELF_MACHINE_ALT1`. Zero `EM_I51_OLD`. Zero `0x1051`. Four hits total, all
`EM_8051`. Fifteen for fifteen.

### One thing the rewrite deleted that reviewers should look at

`bfd_elf_i51_final_write_processing` is gone. It was the function that stamped
`e_machine = EM_8051`. Removing it looks risky. It is not — `prep_headers()` in
`bfd/elf.c` sets `e_machine` from `ELF_MACHINE_CODE`. Proved by building and
asking:

```
$ work/modern/build/gas/as-new -o t.o t.s
$ work/modern/build/binutils/readelf -h t.o
  Class:                             ELF32
  Data:                              2's complement, little endian
  Machine:                           Intel 8051 and variants
  Flags:                             0x0
```

Still 165. Safe deletion.

### And one thing the rewrite really did break, on purpose

Legacy `0x1051` objects are no longer readable. That is the whole point of
dropping ALT1, and it is why `base.7z` had to be re-stamped. Demonstrated on the
two copies of the same file:

```
$ objdump -f b7/xold/cgi/bd.obj      # e_machine 0x1051
  file format elf32-little
  architecture: UNKNOWN!, flags 0x00000011

$ objdump -f b7/xnew/cgi/bd.obj      # e_machine 165
  file format elf32-i51
  architecture: i51, flags 0x00000011
```

README was updated honestly to stop claiming otherwise. No complaint. Just note
that any 2001-lineage object still out in the world now needs
`tb/i51elf_le2be.py` run over it first.

---

## 3. Testbench: intact

Blob hashes, baseline vs main:

```
SAME     tb/frozen.expect
SAME     tb/reference.md5
SAME     tb/romdiff.py
SAME     tb/sim/run-script.py
SAME     tb/mutation/gen.py
SAME     tb/mutation/run.py
SAME     tb/mutation/report.py
CHANGED  tb/hexoracle.py
CHANGED  tb/base.7z
SAME     tb/ref.7z
SAME     tb/base2001.7z
SAME     tb/dialect.py
SAME     tb/fixhunks.py
SAME     tb/isa_check.py
SAME     tb/i51elf_ar.py
SAME     tb/i51elf_sym_uc.py
SAME     tb/isa/testall.asm
SAME     tb/isa/8051.txt
SAME     tb/sim/link.ld
SAME     tb/sim/run-bits.py
SAME     tb/sim/run-branch.py
SAME     tb/sim/run-commons.sh
SAME     tb/sim/run-defaultlink.sh
SAME     tb/sim/run-reloc.py
SAME     tb/sim/run-testall.sh
```

Everything asked about survived byte-identical except two:

- `tb/hexoracle.py` — 3 lines, comment only, the dangling `ROOTCAUSE` pointers.
  No logic touched.
- `tb/base.7z` — the re-stamp, proved above to be `e_machine` and nothing else.

`tb/mutation/*` untouched. `tb/frozen.expect` and `tb/reference.md5` untouched,
which matters: the re-stamp did not force a reference update, because the
re-stamp is input-side only and the ROMs come out the same.

---

## 4. tb/fuzz/ — NO

Still not in the tree. Third rewrite in a row it has missed.

```
$ git ls-tree -r --name-only claude/robustness | grep fuzz
tb/fuzz/armangle.py
tb/fuzz/elfmangle.py
tb/fuzz/gen_asm.sh
tb/fuzz/gen_asm_rand.py
tb/fuzz/gen_dis.sh
tb/fuzz/probe.sh
tb/fuzz/repro/.gitignore
tb/fuzz/repro/oob-read-sh_size.o
tb/fuzz/repro/oob-write-r_offset.o
tb/fuzz/repro/repro.sh
tb/fuzz/run.sh
tb/fuzz/seed.s
tb/fuzz/repro/upstream-gas-deep-parens.s

$ git ls-tree -r --name-only origin/main | grep fuzz
(nothing)
$ git ls-tree -r --name-only 0f45319 | grep fuzz
(nothing)
```

So this is not a rewrite loss — `tb/fuzz/` was never on green. It is still
stranded on `claude/robustness` (e58a22a). The *fix* that branch found did land
(`bfd_reloc_offset_in_range`, section 2). The harness that found it did not, and
neither did the two crash repros `oob-read-sh_size.o` and
`oob-write-r_offset.o`. The regressions have no test.

---

## 5. Build from pristine 2.47, fuzz 0, full gate

`make -C tb build` — downloads the tarball, checksums it, `git init` a pristine
commit, applies both patches at `--fuzz 0`, refuses any hunk that slid.

```
154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff  binutils-2.47.tar.xz
binutils-2.47.tar.xz: OK
== applying mcs51/additions.patch
== applying mcs51/modifications.patch
-rwxr-xr-x 686728 work/modern/build/gas/as-new
-rwxr-xr-x 1031984 work/modern/build/ld/ld-new
```

Apply logs: 9 files patched + 28 files patched, and:

```
$ grep -i "offset\|fuzz\|fail" work/modern/*.apply.log
NO offset/fuzz/fail in apply logs
```

Zero fuzz, zero offset, zero rejects. Patches are in sync with 2.47.

Then `make -C tb gate BUILD=work/modern/build`. Every stage:

| stage | result | detail |
|---|---|---|
| isa | PASS | 280 instructions + testall.asm; 3 instructions |
| roundtrip | PASS | 280, 3, 18 instructions |
| branch | PASS | 24 cases |
| bits | PASS | 50 cases |
| reloc | PASS | 36 checks |
| sim | PASS | testall ran to completion in ucsim, P1=127 |
| defaultlink | PASS | default emulation lays out all spaces |
| commons | PASS | commons keep space, name, neighbours |
| script | PASS | 146 arms covered, 319 checks, 38 unreachable |
| check | PASS | 10/10 projects match reference md5 |
| oracle | PASS | 10/10 agree with the 2001 .hex |

```
gate: PASS (isa roundtrip branch bits reloc sim defaultlink commons script check oracle)
```

The ten ROMs, hashed:

```
PASS diag     1267 84779b2386ba64a0347e227ac09cf18a
PASS ds1620   6284 5bd93daf7609853f6c3db6541060c420
PASS ds1822   6078 733b5d0483c7cd324156cd36da1743a6
PASS lcd      5754 7c0f4fccb4e9ee7305c1f8c8fe7bee1e
PASS led1     5173 bd336522c8c54be539f2e45d5bbe7888
PASS led2     5010 97e9cf0cf06ebf6ff10e98a6420f6f63
PASS led3     5200 470097b25def9f33cde74fdb4c6264f1
PASS serial   8128 94c14915a302c599ff91b88244319f4d
PASS welcome  4812 0244913c2585c0dc9995a5e6a2e95d6d
PASS wjava    4812 bbdbcb2b80d62a384aa8f3ec9d407315
```

Oracle closed with both size deltas still explained and budgeted:

```
note: diag: +3 bytes, explained - 2001 linked diag with ld's built-in i51 script...
note: serial: -1519 bytes, explained - 2001 built index.html and setup.html with
      html2db.pl -cpurom and without -index 0...
all 10 projects agree with the 2001 oracle: recorded size delta, and every one
of addr16/acall11/word16/pcode13/zero8/residual at its recorded count
```

`check-canary` too, which gate.yml runs but `GATE` does not list:

```
== canary: check with a sabotaged assembler
CANARY PASS: check exited nonzero, 10 project(s) reported FAIL
```

Gate is honest — it goes red when the toolchain is broken.

---

## 6. The two open items from the EM work

**Is `e_flags` set anywhere now? NO. Still open.**

```
$ grep -n "e_flags\|EF_I51\|elf_elfheader" mcs51/additions.patch mcs51/modifications.patch
(nothing)
```

Zero hits, in either patch. Note it got *worse*, structurally: `elf_elfheader`
had exactly one user, `bfd_elf_i51_final_write_processing`, and this rewrite
deleted that function. So there is no longer any code in the port that touches
the ELF header at write time — no hook is even sitting there to hang an
`e_flags` on. Confirmed on the built object:

```
  Flags:                             0x0
```

**Is `EI_DATA` still LSB? YES. Still open.**

```
$ grep -n "ELFDATA2\|TARGET_BIG_SYM\|TARGET_LITTLE_SYM\|EI_DATA" mcs51/*.patch
mcs51/additions.patch:1027:+#define TARGET_LITTLE_SYM	i51_elf32_vec
mcs51/additions.patch:3876:+   elf/common.h.  Objects are ELFDATA2LSB; the 16-bit fields inside
```

`TARGET_LITTLE_SYM` only, no `TARGET_BIG_SYM`. Readelf agrees:

```
  Data:                              2's complement, little endian
```

The rewrite did do one good thing here: the new `include/elf/i51.h` comment now
states the split honestly instead of leaving it implicit —

```
+/* The machine number is the registered EM_8051 (165), defined in
+   elf/common.h.  Objects are ELFDATA2LSB; the 16-bit fields inside
+   instruction encodings (LJMP/LCALL addr16, MOV DPTR,#data16) are stored
+   high byte first, as the instruction set defines them, and R_I51_L /
+   R_I51_H address the two halves of a 16-bit value explicitly.  */
```

Container is LSB, instruction immediates are big-endian, and the reloc types
name which half. That was the confusing part. It is written down now. The item
is still open, but it is documented rather than lurking.

---

## Verdict table

| file | verdict |
|---|---|
| `.gitattributes` | survived |
| `.github/workflows/build.yml` | survived |
| `.github/workflows/frozen.yml` | survived |
| `.github/workflows/gate.yml` | changed — dangling pointer removed |
| `.gitignore` | survived |
| `README.md` | changed — EM claim corrected |
| `mcs51/additions.patch` | changed — ALT1 + legacy EM dropped |
| `mcs51/modifications.patch` | changed — 3 readelf legacy cases dropped |
| `tb/Makefile` | changed — 2 dangling pointers removed |
| `tb/base.7z` | changed — 221 headers re-stamped, nothing else |
| `tb/base2001.7z` | survived |
| `tb/base2001.PROVENANCE` | changed — prose ok, **7 hashes now stale** |
| `tb/dialect.py` | survived |
| `tb/fixhunks.py` | survived |
| `tb/frozen-report.md` | **dropped** (394 lines) |
| `tb/frozen.expect` | survived |
| `tb/hexoracle.py` | changed — comment only |
| `tb/i51elf_ar.py` | survived |
| `tb/i51elf_le2be.py` | changed — emits 165 |
| `tb/i51elf_sym_uc.py` | survived |
| `tb/isa/*` (8 files) | survived |
| `tb/isa_check.py` | survived |
| `tb/mutation/gen.py` | survived |
| `tb/mutation/run.py` | survived |
| `tb/mutation/report.py` | survived |
| `tb/objects-report/PROVENANCE` | **dropped** (214 lines) |
| `tb/objects-report/REPORT.md` | **dropped** (188 lines) |
| `tb/objects-report/staged/*.obj` (28) | **dropped** (duplicates of base.7z) |
| `tb/ref.7z` | survived |
| `tb/reference.md5` | survived |
| `tb/romdiff.py` | survived |
| `tb/sim/*` (8 files) | survived |
| `tb/fuzz/*` (13) | never arrived — still only on `claude/robustness` |

---

## Did the rewrite lose anything

No executable content, no test, no reference and no fix was lost — the re-stamp
is provably nothing but `e_machine`, all fifteen named fixes are present, and a
pristine 2.47 build applies at fuzz 0 and passes all eleven gate stages plus the
canary — but three provenance documents (596 lines) were deleted, the seven
`base.7z` hashes in `tb/base2001.PROVENANCE` were left describing the
pre-re-stamp bytes and now match nothing, and `tb/fuzz/` still has not come
across, so the two bounds bugs it found remain fixed but untested.

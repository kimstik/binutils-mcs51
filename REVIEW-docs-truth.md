# REVIEW: does the repository still tell the truth about itself?

Branch reviewed: `origin/work/green` @ 0f45319. Method: every number, hash, byte
count and behavioural claim in the prose was recomputed on this host, not read
and believed. The port was built from `mcs51/*.patch` on binutils 2.47
(`make -C tb build`, green), the full gate was run (`isa` 280/280+3/3,
`roundtrip`, `branch` 24/24, `bits`, `reloc`, `sim` P1=127, `defaultlink`,
`commons`, `script`, `check` 10/10 PASS, `check-canary` PASS, `oracle` all-ok),
the archives were unpacked and re-hashed, the conversion pipelines re-run, and
binutils-2.11.2 sources were fetched to check the claims made about them.

Verdict up front: **12 false statements** (5 never true, 7 stale), **2 broken
document pointers**, 3 minor overstatements. Everything else checked — and most
of the tree's numbers are correct to the byte; the list of verified claims is at
the end so the next audit does not re-litigate them.

---

## A. Never was true

### A1. README: "Migrated from 'elf' to 'generic' template"

> `README.md` — "## Key Changes: - Migrated from 'elf' to 'generic' template"

No migration ever happened. The 2001 port already used the generic emulation
template, and every version of this repo does too:

```
$ 7z x tb/ref.7z; grep -n 'TEMPLATE_NAME' i51.patch.112n
4098:+ TEMPLATE_NAME=generic          # ld/emulparams/elf32_i51.sh, Dec 2001
$ git show 1563588:mcs51/additions.patch | grep TEMPLATE_NAME
+ TEMPLATE_NAME=generic              # first commit of this repo
$ grep -A1 TEMPLATE_NAME mcs51/additions.patch   # today
+TEMPLATE_NAME=generic
+EXTRA_EM_FILE=genelf
```

Corrected statement: "the ld emulation uses the `generic` template
(`TEMPLATE_NAME=generic`, `EXTRA_EM_FILE=genelf`), as the 2001 port always did."
It is a property, not a change, and does not belong under "Key Changes".

### A2. README + patch comment + readelf string: 0x1051 attributed to the 2001 lineage

> `README.md` — "the unregistered `0x1051` that the 2001 lineage used is still
> accepted on input (`EM_I51_OLD`)"

> `mcs51/additions.patch` (include/elf/i51.h) — "Objects from the 2001
> web51.hw.cz lineage carry the unregistered value 0x1051; it is still accepted
> on input."

> `mcs51/modifications.patch` (binutils/readelf.c) —
> `case EM_I51_OLD: return "MCS-51 8-bit microcontroller (legacy web51 value)"`

The 2001 lineage never used 0x1051. The 2001 patch defines the machine as
0x7262, and the 2001 objects carry it, big-endian:

```
$ grep 'define EM_I51' ref.7z:i51.patch.112p
+ #define EM_I51                  0x7262
$ python3 - # e_machine of gnu13's own lib/web51_80.obj (from tb/base2001.7z)
lib/web51_80.obj 0x7262 BE
$ work/modern/build/binutils/objdump -f <2001 object>
architecture: UNKNOWN!          # the current port cannot even open it
```

0x1051 is this repo's **own** invention, introduced at the 2.45.1 step:

```
$ git show 15b928d:mcs51/additions.patch | grep '0x1051'
+#define EM_I51 0x1051
```

The current port emits EM_8051 (165 = 0xA5, verified: `readelf -h` on fresh gas
output says "Intel 8051 and variants", raw e_machine 0xa5) and accepts 0x1051
on input (verified: objdump reads base.7z's 0x1051 objects as elf32-i51).
Corrected statement: "the unregistered `0x1051` that earlier revisions of this
port (through 2.45.1/2.47 before the EM_8051 switch) wrote — and that the
testbench's conversion of the 2001 objects stamps — is still accepted on input;
the true 2001 objects are big-endian with e_machine 0x7262 and are readable
only after conversion through `tb/i51elf_le2be.py`."

### A3. tb/Makefile: "oracle … does not fail a project that will not build"

> `tb/Makefile` (GATE/MUTGATE comment, lines 84-87) — "It does not also add
> oracle - oracle builds the same ten projects with the same tools and, unlike
> check, does not fail a project that will not build, so it can only be the
> weaker of the two."

False in the same commit that wrote it. f109a44 rewrote this comment AND
rewrote the oracle recipe so a build failure is fatal:

```
$ sed -n '317,329p' tb/Makefile
	@cd $(WORK)/oracle/projekt && rc=0; for p in $(PROJECTS); do \
		...
		else \
			echo "FAIL $$p: build failed"; ... rc=1; \
		fi; \
	done; \
	if [ $$rc -ne 0 ]; then \
		echo "oracle: a project that does not build cannot be compared"; \
		exit 1; \
	fi
```

Corrected statement: oracle now fails a project that will not build, exactly
like check. The reason MUTGATE omits oracle has to be restated (e.g. "oracle
compares against the frozen 2001 layout, not against the current reference
ROMs, so on top of check it only re-runs the same build") — the stated premise
is gone.

### A4. gate.yml: "oracle below would let it pass"

> `.github/workflows/gate.yml` (comment on the check step) — "A project that
> fails to build is a failure here; oracle below would let it pass."

Same falsehood, same commit (f109a44 added this comment and the oracle
`exit 1` in one diff). Oracle does not let a non-building project pass:
`git diff afee4a5 f109a44` shows both changes together. Corrected statement:
delete the second clause, or say "oracle below fails it too, but classifies
bytes instead of hashing against the reference".

### A5. base2001.PROVENANCE: "the format the current port emits - … e_machine 0x1051"

> `tb/base2001.PROVENANCE` (header) — "base.7z ships the same 33 paths in the
> format the current port emits - little-endian ELF, e_machine 0x1051, symbols
> uppercased by the assembler."

The current port emits e_machine 0xA5 (EM_8051), not 0x1051 — verified on a
fresh `as-new` object. 0x1051 is what the port *accepts* (EM_I51_OLD) and what
`tb/i51elf_le2be.py` deliberately writes (its own line 39:
`struct.pack('<H', 0x1051)`). This file was created in 93270ae, after the
EM_8051 switch (c907fad), so it was wrong when committed. Corrected statement:
"…in the converted legacy format the current port accepts on input:
little-endian ELF, e_machine 0x1051 (`EM_I51_OLD`), symbols uppercased."

---

## B. Stale — was true, the tree moved under it

All six of these describe the state before commit 93270ae repacked
`tb/base.7z`/`tb/base2001.7z` with `*(reset_network)` restored in
`lib/www51.sc` — and four of them sit in files that 93270ae itself created or
last touched, so nothing since has been allowed to correct them.

### B1. base2001.PROVENANCE: its own archive hash and size

> "Archive sha256: 03399d746b3909d471548fefc7b4f3b66341c32521c2d5d4133e7f27bdf3ea13
>  Archive size:   27907 bytes"

```
$ sha256sum tb/base2001.7z
056aed4d13749893182f9a1c4e48544ce6ce42f0e1cb85c7c6c5cf88c7d3c2ef  (27900 bytes)
```

03399d…/27907 is the archive as it stood one commit earlier (verified:
`git show a1989a8:tb/base2001.7z | sha256sum` = 03399d…). 93270ae repacked the
archive (www51.sc: reset_network restored) and updated this PROVENANCE in the
same commit without updating its self-hash. All 33 object hashes inside the
file are still correct (recomputed, 33/33 match); only the archive-level pair
and the www51.sc entries moved.

### B2. base2001.PROVENANCE §2/§6: lib/www51.sc hashes and size

> §2: "aeb3d964ab51a63ebec33fbc9d4d570c75ef7ccd65f1efec08b95ec5374c85b4    5629  lib/www51.sc"
> §6: "base.7z    b4b89651…e548099 / overlay    aeb3d964…374c85b4 / both 5629 bytes, 265 LF-terminated lines"

Actual, today:

```
base.7z:lib/www51.sc    3dc717e79adee15e04b03d091964a9e780f6e08615a4a5c6be9638f3d342cb1f  5623
base2001.7z:lib/www51.sc 1c5cfb4c8c90ef72a5875a307d8c7ee17b569a08dd91bcdaf2e901dce77655cb 5623
```

Both 5623 bytes now (six bytes of comment markers gone with the restore); 265
lines still. The **derivation itself still holds** — replacing `_RETI_` with
`_reti_` in base.7z's script reproduces the overlay's byte-for-byte (verified
programmatically). Only the recorded hashes/sizes are stale.

### B3. base2001.PROVENANCE §5: "lib/www51.sc comments out *(reset_network)"

> "- lib/www51.sc comments out *(reset_network), uppercases the interrupt
>    trampoline symbol to _RETI_, …"

```
$ 7z x tb/base.7z; grep -n 'reset_network' lib/www51.sc
82:    *(reset_network)        # live, not commented
```

The uppercase-_RETI_ and INTIE0/STACK-alias deltas are still real; the
reset_network delta between base.7z and gnu13 no longer exists.

### B4. base2001.PROVENANCE §6: the rationale for not using gnu13's script

> "gnu13's own lib/www51.sc was not used. It still has *(reset_network) live,
> where base.7z's has it commented out, so it would place a section that the
> reference ROMs were linked without."

Inverted by 93270ae: base.7z's script now has the line live and the current
reference ROMs were linked WITH reset_network (sizes 1267/6284/… vs the
pre-restore 1264/6281/…; `make check` green against them on this host). The
"one variable between the two lines" conclusion happens to survive — both
scripts now place the section — but the stated reason is dead.

### B5. base2001.PROVENANCE §4: "lib/web51.obj (a duplicate of base.7z's lib/web51_80.obj)"

```
$ sha256sum base.7z:lib/web51.obj    2f2191c2…c08239e7   # pre-repair re-assembled copy
$ sha256sum base.7z:lib/web51_80.obj ff0c60de…b0a1       # converted 2001 original
```

Not duplicates since the §5 repair in the sibling document replaced
web51_80.obj. `tb/objects-report/PROVENANCE` §5 states it correctly
("byte-copies of the two _80 inputs **from before the repair**") — the two
PROVENANCE files contradict each other on the same fact. Corrected statement:
"lib/web51.obj (a byte-copy of the re-assembled web51_80.obj that the repair
replaced; hash 2f2191c2…, the §3 'what they replaced' entry)."

### B6. objects-report/PROVENANCE §6: the "md5 (now)" reference-ROM table

> "project   size   md5 (was)   md5 (now)
>  diag      1264   ade88d9d…   c3ba924a3c3b39f0818f0d6114e3c126
>  ds1620    6281   ad375c7f…   87082cbd4c11b70f99b8144ce3986648  …"

None of the "(now)" column is now. base.7z ships (recomputed, = tb/reference.md5):

```
diag 1267 84779b2386ba64a0347e227ac09cf18a    ds1620 6284 5bd93daf7609853f6c3db6541060c420
ds1822 6078 733b5d04…    lcd 5754 7c0f4fcc…   led1 5173 bd336522…   led2 5010 97e9cf0c…
led3 5200 470097b2…      serial 8128 94c14915… welcome 4812 0244913c… wjava 4812 bbdbcb2b…
```

The table records the post-repair/pre-restore generation — two generations
ago. It needs a third column or a note that 93270ae superseded it (the
supersession IS documented in frozen-report.md and reference.md5, but this
file claims "now" and is wrong).

### B7. tb/Makefile oracle comment: "Two repairs are made to the extracted tree before building"

> "Two repairs are made to the extracted tree before building, both of them in
> base.7z's own copy of the 2001 inputs …
>   1. lib/www51.sc ships with `*(reset_network)` commented out. … Restoring
>      the line puts eight of the ten projects back on the 2001 ROM's exact length.
>   2. projekt/diag/Makefile is left alone: …"

The oracle recipe performs **no repair**: it extracts base.7z, moves the .hex
files aside, builds, and runs hexoracle.py — there is no sed, no script edit
(read the recipe, lines 297-331). And base.7z ships www51.sc with the line
live (B3), so repair 1 describes a state that base.7z left behind in the very
commit this comment was written in; "repair" 2 is by its own words not a
repair. Filed under stale because the *facts* it narrates (why the sizes
differ) were once the live derivation. Corrected statement: "base.7z already
carries both decisions: lib/www51.sc with *(reset_network) restored (commit
93270ae), and projekt/diag/Makefile with --script, which is why diag comes out
3 bytes longer than the 2001 oracle — hexoracle.py records that."

---

## C. Broken pointers — documents cited that are not in the tree

1. **ROOTCAUSE-rom-delta.md** is cited three times on work/green —
   `tb/Makefile:296` ("ROOTCAUSE-rom-delta.md derives all of this"),
   `tb/hexoracle.py:55` ("See ROOTCAUSE-rom-delta.md"),
   `.github/workflows/gate.yml:88` ("See ROOTCAUSE-rom-delta.md") — and exists
   on no branch of origin (`git ls-tree -r origin/... | grep -i rootcause`:
   nothing; it lives only on the unpushed local branch
   `claude/rootcause-rom-delta`). A reader of this repository cannot follow
   the citation.
2. **AUDIT-green-honesty.md** — `tb/objects-report/PROVENANCE` (CORRECTION
   paragraph): "Those 2001 hashes are recorded in AUDIT-green-honesty.md so
   the oracle is not lost again." The file exists only on the unpushed local
   branch `claude/audit-green-honesty`; on origin it is nowhere. The 2001
   hashes are therefore NOT recorded anywhere a reader of work/green can see —
   the sentence defeats its own purpose. (The oracle itself is safe: the .hex
   files are in base.7z and hexoracle.py pins their decoded sizes; and this
   review re-verified the CORRECTION's substance — at 1563588 all ten
   www8051.hex decode byte-for-byte to the shipped www8051.rom, and from
   91a9476 on, none do.)

Fix: either commit the two documents to the branch that cites them, or inline
the load-bearing facts (the six defect classes, the 2001 ROM hashes) where
they are cited.

---

## D. Minor overstatements

1. `README.md`: "`tb/Makefile` (`make build`) automates exactly this". Not
   exactly: build additionally passes `--disable-nls --disable-werror
   --disable-shared`, `CFLAGS="-Os -flto -march=haswell"`, gcc-ar/gcc-ranlib,
   git-inits the tree, and rejects any patch hunk applied at an offset. The
   spirit (download, checksum, patch, configure `--target=i51-elf
   --disable-gdb`, make) is right.
2. `.github/workflows/build.yml` header: "built for each host, then verified
   against the testbench." The two wine hosts get `as-new.exe --version` /
   `ld-new.exe --version` only; the testbench runs on the three native hosts.
   The step names inside the file are honest about this.
3. `README.md` references: "sdcc-adjacent work referenced by the 2.45.1
   release". This repository has no releases (`gh api releases` → empty) and
   nothing in the tree at the 2.45.1 step references that repo; the link
   target (volumit/sdcc_aurix_scr_42, "sdcc+binutils for SCR Aurix (mcs51)")
   does exist. Unverifiable attribution, not provably false.

---

## E. Claims recomputed on this host and found TRUE

So the next round does not redo the work — each of these was checked by
command, not by reading:

- README startup hooks: `elf32i51.sc` PROVIDEs `__GSINIT_STARTUP`,
  `__EXTERNAL_STARTUP`, `__INIT_DATA` = `__I51_RET`; probe link puts all three
  at 0x0A and the byte there is 0x22 (RET). The old false "weak symbols
  __gsinit_startup" bullet is gone from README — fixed in a prior round.
- README target identity: `config.sub i51-elf` → `i51-unknown-elf`; bare `i51`
  → `i51-unknown-none`, matched by the `i51-*-*` stanzas in bfd/gas/ld; gas
  output e_machine = 0xA5 = EM_8051, stock readelf prints "Intel 8051 and
  variants"; emulation `elf32i51`; format `elf32-i51`. Out-of-tree build:
  `make build` itself builds in `work/modern/build` (green). A second
  configure with `--enable-targets=all` also builds (see note at end).
- `tb/reference.md5` = sizes+md5 of the ten `www8051.rom` in today's base.7z,
  10/10 exact; `make check` on a fresh local build: 10/10 PASS.
- `tb/frozen.expect`: three columns; sizes 6284/6078/5754/5173/5010/5200/8128/
  4812/4812 match today's base.7z ROMs; `romdiff.py` really rejects a
  two-column file (code path present with its own error string).
- `tb/frozen-report.md`: re-derived table sizes match base.7z; the 2.11.2
  `ldexp.c` claim is true (fetched binutils-2.11.2: `case etree_provide:`
  folds `tree->assign.src` before `bfd_link_hash_lookup`, so a PROVIDE's RHS
  must resolve even if unwanted — diag's `_reti_` failure follows); the quoted
  `ldlang.c` i51 common-alignment hunk is verbatim in ref.7z's i51.patch.112p;
  the SHN census tables (ff00:7/ff02:1/ff03:2/ff06:15/COMMON:17 for libk80.a
  etc.) reproduce exactly from the archives in the tree, and base.7z's
  repaired inputs now census identical to the 2001 originals; `web51.obj`
  (unrepaired, by design) censuses as COMMON×9 — exactly the pre-fix shape the
  report describes.
- Conversion pipeline claims: `i51elf_le2be.py`+`i51elf_sym_uc.py` reproduce
  base.7z's `web51_80.obj`/`web51_23.obj`/`cgi/bd.obj` from the 2001 originals
  byte-for-byte; `i51elf_ar.py` reproduces `libk80.a`, `libw80.a`, `libk23.a`,
  `libw23.a` byte-for-byte. Overlay `libk23.a`/`libw23.a` are byte-identical
  to base.7z's `lib/lib23_old/` copies.
- `tb/objects-report/PROVENANCE` §1/§2/§3/§5: all 33 source hashes and all 28
  staged hashes recomputed, 100% match; staged/cgi = base.7z cgi, 26/26.
- `tb/objects-report/REPORT.md` post-commit integrity: 28/28 staged blobs
  still hash to the recorded values.
- `tb/isa/PROVENANCE`: 8051.txt and testall.asm are byte-identical
  (sha256+size) to the upstream files at the pinned commits — fetched from
  GitHub raw and compared; 280 table lines; testall.asm's own header says
  "tests all instructions except: MOVX(1-4) and RETI".
- `tb/hexoracle.py` EXPECT: live `make oracle` reproduces every recorded
  count — six classes, ten projects, diag +3 explained, serial -1519
  explained; the ten shipped .hex decode to 1264/6284/6078/5754/5173/5010/
  5200/9647/4812/4812 and are byte-identical to the first commit's .hex AND to
  the first commit's .rom (the CORRECTION paragraph's substance holds).
- Memory-space commons on disk: fresh gas output shows `PRC[0xff01]`…
  `PRC[0xff06]` for the six space commons and `COM` for plain `.comm` — the
  `SHN_LORESERVE + n` comment in include/elf/i51.h now tells the truth
  ("written to and read from an object file as 0xff00..0xff06"); the old
  lying version is gone.
- Workflow history comments: gate.yml really did carry
  `branches-ignore: [main]` with no `pull_request` (93270ae version), and
  frozen.yml really was monthly (`cron: '0 3 1 * *'`) with the comparison
  never gated; gate.yml's step list is $(GATE) in order (isa roundtrip branch
  bits reloc sim defaultlink commons script check [canary] oracle);
  frozen.yml's testbench step carries `continue-on-error: true` and the
  compare step does not, exactly as frozen-report's Status section says.
- `tb/Makefile` header: every listed target exists and its one-line
  description matches its recipe (check's hash-then-delete of shipped ROMs
  verified in the recipe; canary verified by running it: sabotaged assembler →
  check exits nonzero, 10 FAIL).

Note on `--enable-targets=all`: verified. A separate out-of-tree configure
with `--target=i51-elf --enable-targets=all --disable-gdb` built
bfd/opcodes/gas/ld to completion (exit 0); the resulting `as-new` assembles
and `ld-new` links an i51 probe. The README's "--enable-targets=all and
out-of-tree build dirs work" is true.

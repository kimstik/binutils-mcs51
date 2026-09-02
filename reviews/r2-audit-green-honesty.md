# Audit: is the green real this time?

Adversarial re-audit of `work/green` (5d02910). Scope: the testbench only.
Every claim below is backed by a command that was run in this container and its
output. Nothing here is inferred from reading code alone.

Environment: Linux 6.18, 4 cores, gcc 13, GNU patch 2.7.6, p7zip 23.01,
sdcc-ucsim 4.2.0, texinfo 7.1. Toolchain built from `mcs51/*.patch` on
binutils 2.47 by this container, not downloaded from CI.

## Verdict

**The harness mechanics are honest. The reference it compares against is not.**

The 2001 fraud is gone: `make check` really builds all ten projects with the
port, really byte-compares, and really goes red when anything is wrong (proved
five separate ways below). What replaced it is a subtler problem: every golden
`www8051.rom` in `tb/base.7z` was overwritten with the port's own output, so a
green `make check` proves reproducibility, not correctness. Against the only
reference in this repository the port did not produce, **0 of 10 projects
match**, and at least one concrete defect has already been baked into the new
goldens.

---

## S1 - The golden ROMs are the port's own output

`tb/base.7z` has been rewritten four times. All ten reference ROMs were
replaced:

```
$ git log --oneline --all -- tb/base.7z
5d02910 tb: commons probe, repaired 2001-converted inputs, regenerated references
1d27c52 tb: reference ROMs from the fixed toolchain and repaired inputs
53e4758 tb: repair the three re-assembled inputs from the 2001 originals
91a9476 tb: honest check with canary, reference objects and roms
1563588 i51 binutils: patches, testbench, CI
```

Extracting `base.7z` from 1563588 and from HEAD and diffing the contents:

```
=== files present in both but changed ===
CHANGED ./lib/libw80.a
CHANGED ./projekt/{diag,ds1620,ds1822,lcd,led1,led2,led3,serial,welcome,wjava}/www8051.rom
```

Divergence between the ROM originally shipped and the ROM now used as the
reference:

```
diag    orig=1264 new=1264 differing_bytes=150
ds1620  orig=6284 new=6281 differing_bytes=5927
ds1822  orig=6078 new=6075 differing_bytes=5719
lcd     orig=5754 new=5720 differing_bytes=5455
led1    orig=5173 new=5170 differing_bytes=4836
led2    orig=5010 new=5007 differing_bytes=4717
led3    orig=5200 new=5197 differing_bytes=4883
serial  orig=9647 new=8125 differing_bytes=7487
welcome orig=4812 new=4809 differing_bytes=4524
wjava   orig=4812 new=4809 differing_bytes=4524
```

`tb/objects-report/PROVENANCE` section 6 states the provenance plainly - the
replacements come from CI run 32876629391 of the port itself - and
`.github/workflows/frozen.yml` repeats it in a comment. So this is disclosed,
not concealed. But disclosure does not make it an oracle. `make check` is now a
**regression and cross-platform-reproducibility test**. It cannot detect a
wrong-code bug, because a wrong-code bug is what produced the goldens.

This is the exact trap named in the previous review round, re-entered one level
deeper.

## S1 - The stated reason for discarding the 2001 oracle is false

`tb/objects-report/PROVENANCE` justified overwriting the ROMs with:

> decoding the shipped .hex has never reproduced the shipped .rom, for any
> project, at any point in this archive's history.

Decoding every `projekt/*/www8051.hex` out of `base.7z` at 1563588 and
comparing to the `www8051.rom` beside it:

```
diag     hexlen=1264 romlen=1264 identical=True diffbytes=0
ds1620   hexlen=6284 romlen=6284 identical=True diffbytes=0
ds1822   hexlen=6078 romlen=6078 identical=True diffbytes=0
lcd      hexlen=5754 romlen=5754 identical=True diffbytes=0
led1     hexlen=5173 romlen=5173 identical=True diffbytes=0
led2     hexlen=5010 romlen=5010 identical=True diffbytes=0
led3     hexlen=5200 romlen=5200 identical=True diffbytes=0
serial   hexlen=9647 romlen=9647 identical=True diffbytes=0
welcome  hexlen=4812 romlen=4812 identical=True diffbytes=0
wjava    hexlen=4812 romlen=4812 identical=True diffbytes=0
```

Ten of ten, byte-for-byte. The same test on `base.7z` at 91a9476 - the first
commit that overwrote the ROMs - gives `identical=False` for all ten. The .hex
and .rom stopped agreeing *because the .rom was replaced*, and that fact was
then cited as evidence the pair was never consistent.

The 2001 `.hex`/`.rom` pair is a self-consistent, independently produced
artifact set. It is the only thing in this repository that qualifies as an
oracle, and it was thrown away on a false premise. `tb/objects-report/PROVENANCE`
has been corrected on this branch.

**The 2001 oracle, recorded here so it cannot be lost again**
(`md5 size` of `projekt/*/www8051.rom` in `tb/base.7z` at commit 1563588;
`bin2hex` of each reproduces the `www8051.hex` beside it):

```
diag     1264   66cb267cc8485b84f2aea3847c41d156
ds1620   6284   73c85bd0dfeabadcb637d9adf407af84
ds1822   6078   37c9288994424d91cd57fe89d841b237
lcd      5754   8467c5bd46106987f1f674796b72b786
led1     5173   6c5793047cf6943539c0ba985f623dcf
led2     5010   756dc87c5851d03abbd58aa2ca256754
led3     5200   ac30cc9bd0cf3c83d7bc66ac24a327ec
serial   9647   eb3036827434f4a4a4843457f4e71672
welcome  4812   37d154bafbee6604073b8752882b1951
wjava    4812   c8e24a730c6ab2754b03b28036f352c0
```

## S1 - Against the real oracle: 0 of 10

`tb/romdiff.py --reference <base.7z@1563588> --produced work/tb` on the output
of a green `make check`:

```
| project | reference | produced | differing bytes |
| diag    | 1264 B    | 1264 B   | 150,  from 0x0 |
| ds1620  | 6284 B    | 6281 B   | 5930, from 0x1 |
| ds1822  | 6078 B    | 6075 B   | 5722, from 0x1 |
| lcd     | 5754 B    | 5720 B   | 5489, from 0x1 |
| led1    | 5173 B    | 5170 B   | 4839, from 0x1 |
| led2    | 5010 B    | 5007 B   | 4720, from 0x1 |
| led3    | 5200 B    | 5197 B   | 4886, from 0x1 |
| serial  | 9647 B    | 8125 B   | 9009, from 0x1 |
| welcome | 4812 B    | 4809 B   | 4527, from 0x1 |
| wjava   | 4812 B    | 4809 B   | 4527, from 0x1 |

identical 0, different 10, missing 0
```

`tb/frozen-report.md` argues the differences are "one variable layout
relabelled into another, not different code". That argument is about the
*frozen 2.11.2 rebuild*, whose ROMs have exactly the reference length. It does
not cover the divergence above: nine of ten produced ROMs are **shorter** than
the 2001 artifact. Length differences are not relabelling.

## S2 - A real defect already laundered into the goldens: `reset_network`

`objdump -h` on the port's own `www8051.o`, next to the 2001 length delta:

```
== led1  2001=5173  port=5170  delta=3
   .text          size=0x00001432 vma=0x00000000
   reset_network  size=0x00000003 vma=0x00001432   <- immediately after .text
== lcd   2001=5754  port=5720  delta=34
   .text          size=0x00001658 vma=0x00000000
   reset_network  size=0x00000022 vma=0x00001658   <- 0x22 == 34
```

`work/tb/projekt/led1/map`:

```
reset_network   0x00001432        0x3
 reset_network  0x00001432        0x3 ../../lib/libw80.a(packet.obj)
```

`lib/www51.sc` has `/* *(reset_network) */` commented out (unchanged from 2001;
`diff` against the 1563588 copy is empty), so the section is an orphan. binutils
2.11.2 folded that orphan into the `.text` **output** section, so
`objcopy -j .text -O binary` picked it up; modern ld gives it an output section
of its own, so `objcopy -j .text` drops it. The ROM is missing real linked bytes
from `libw80.a(packet.obj)` in at least eight of the ten projects, and the delta
matches the section size exactly.

That is precisely the class of bug the golden files existed to catch, and it is
now *inside* them. `serial` is short by 1522 B, which `reset_network` (3 B) does
not explain and which nothing in the repo does; not chased further - out of
scope.

## S2 - `frozen.yml` can never go red

```yaml
      - name: Run the testbench on the 2001 objects
        id: check
        continue-on-error: true
        run: make -C tb check-frozen
...
      - name: Verdict
        if: always()
        run: |
          if [ "$outcome" != success ]; then
            echo "::warning title=frozen testbench::$outcome - ${counts:-no comparison}"
          fi
```

Every step is `continue-on-error` or `if: always()`, and the only escalation is
`::warning`. No path through this workflow returns a nonzero job status. It is
the one workflow that would surface port-vs-2001 divergence and it is
structurally incapable of reporting it as a failure. It is also schedule-only
(`cron: 0 3 1 * *`) - monthly - so no push or PR ever exercises it.

## S3 - Is a red gate actually blocking?

```yaml
# .github/workflows/gate.yml
on:
  workflow_dispatch:
  push:
    branches-ignore: [main]
```

- No `pull_request` trigger. Enforcement therefore depends entirely on GitHub
  branch protection / rulesets naming `isa` as a required status check. That is
  repository configuration, not repository content: **I could not inspect it** -
  `api.github.com` returns 403 in this session ("GitHub access is not enabled for
  this session"). Unverified either way. If no required check is configured,
  gate.yml is decorative.
- `branches-ignore: [main]` means the ISA / branch / simulator / defaultlink /
  commons gates **never run on `main` itself**. Post-merge `main` is ungated.
- A PR from a fork produces no `push` event in the base repo, so a fork PR gets
  no gate run at all.
- `make -C tb check` (the project testbench) is not in gate.yml. Only build.yml
  runs it, and build.yml is `paths:`-filtered to `mcs51/**`, `tb/**`,
  `.github/workflows/build.yml`.

## S3 - `make check` is mostly a linker test

Summing `.text` contributions per input from each project's map:

```
diag     port-assembled  342 B   prebuilt-2001  1009 B   port share 25.3%
led1     port-assembled  924 B   prebuilt-2001  5368 B   port share 14.7%
lcd      port-assembled  459 B   prebuilt-2001  5857 B   port share  7.3%
serial   port-assembled 2920 B   prebuilt-2001  7460 B   port share 28.1%
wjava    port-assembled  825 B   prebuilt-2001  5343 B   port share 13.4%
```

72-93% of every reference ROM comes from 2001 `.obj`/`.a` files that the port
only relinks. The assembler is covered by the ISA/branch/simulator gates
instead, which is fine - but "10/10 projects match" should not be read as
assembler coverage.

## S4 - Smaller masking surfaces

| where | what | note |
|---|---|---|
| `build.yml:117` | `if-no-files-found: ignore` | **fixed on this branch** -> `warn` |
| `build.yml:113` | artifact `i51-binutils-<name>` uploaded `if: always()` | on a red run it contains only logs but carries a release-shaped name |
| `tb/Makefile:288` | `strip ... \|\| true` in `dist` | release path; a failed strip ships an unstripped binary silently. Left alone - some hosts legitimately fail on non-ELF files in `bin/`. |
| `tb/Makefile:100` | comment claims patches "must apply with zero fuzz and zero offsets" | `--fuzz 0` bounds fuzz only; `patch` still succeeds with line offsets and nothing checks for them. Empirically there are none today (dry-run: 0 "offset", 0 "fuzz" lines in both patches). |
| `frozen.yml:63,76` | `exit 0` / `\|\| true` | disassembly reporting only, not a verdict |
| workflow `run:` steps | GitHub's default shell is `bash -e {0}`, no `pipefail` | only `build.yml`'s wine smoke test pipes into `head`, and it sets `set -o pipefail` explicitly. No real exposure. |

Searched for and **did not** find: any `\|\| true` in the `check` path, any
ignored exit code in the project loop, any comparison of a file against itself,
any stale output surviving a run (`check` does `rm -rf $(WORK)/tb` and
re-extracts, and deletes the shipped `.rom`/`.hex`/`.o` after hashing).

---

## What is genuinely fixed - executed, not read

### The build is real

```
$ make -C tb build          # binutils 2.47 + mcs51/*.patch, ~5 min on 4 cores
BUILD EXIT=0
-rwxr-xr-x 690824 work/modern/build/gas/as-new
-rwxr-xr-x 1031984 work/modern/build/ld/ld-new
-rwxr-xr-x 634816 work/modern/build/binutils/objcopy
```

Both patches apply with zero fuzz and zero offsets (verified by `--dry-run`
against the pristine tree).

### The check is real

```
$ make -C tb check BUILD=$PWD/work/modern/build
PASS diag     1264 c3ba924a3c3b39f0818f0d6114e3c126
... 10 lines ...
all 10 projects match the reference
CHECK EXIT=0
```

Ten projects built from source on this machine reproduce the CI-produced
goldens bit-exactly - the port is deterministic across hosts. `mcs51-as` was
invoked 40 times, `mcs51-ld` 10 times, `mcs51-objcopy` 19 times. Wall time 1.3 s,
which is fast but real: every falsification below flips it red.

### It can fail - five independent proofs

| # | sabotage | result |
|---|---|---|
| T1 | `make check-canary` (shipped: assembler that always exits 1) | `CANARY PASS: check exited nonzero, 10 project(s) reported FAIL` |
| T2 | objcopy wrapper flips **one bit of one byte** at ROM offset 0x100 | `10 of 10 projects failed`, exit 2 |
| T3 | canary's "sabotaged" assembler swapped for a working one (negative control) | check exits 0, 10 PASS -> the shipped rule would print `CANARY FAIL` and exit 1. The canary is falsifiable, not a rubber stamp. |
| T10a | only `ld-new` broken, everything else real | `10 of 10 projects failed`, exit 2 |
| T10b | whole toolchain replaced by host `/usr/bin/{as,ld,objcopy,ar,nm,strip}` | `10 of 10 projects failed`, exit 2 |

### The gates are real and each can fail

All five gate targets pass here against my own build:

```
isa         280/280 assemble, 280/280 decode, testall assembles (3350 B); extra 3/3
branch      24/24
sim         PASS: testall ran to completion, all instruction tests passed (P1=127)
defaultlink PASS (default emulation links and lays out all spaces)
commons     PASS (every external common keeps its address space)
```

Falsified:

| sabotage | result |
|---|---|
| flip one golden byte in `isa/8051.txt` (`B405FD47` -> `B505FD46`) | `assemble: 279/280`, `FAIL: 1`, exit 1 |
| isa gate pointed at host `as`/`objdump` | `FAIL: 560`, exit 1 |
| branch gate against host `as`/`ld` | `FAIL: 19`, exit 1 |
| simulator oracle against host toolchain | `run-testall: as-new failed`, exit 4 |
| toolchain that assembles cleanly but emits one wrong code byte at `.text` 0x100 / 0x400 / 0x800 | ucsim verdict goes **FAIL** |

Coverage limit worth knowing: the same one-byte corruption at `.text` 0x03,
0x40 and 0xc00 still reports `P1=127`. Those offsets are vectors/padding/trailing
data that `testall` never executes. The simulator oracle is a genuine oracle
with genuine dead zones - it is not a proof of byte-exactness.

The vendored corpora match their recorded upstream hashes:

```
a597813a2fcd00162863cee1511b18261a3469d25ad0931908db8c781207884c  tb/isa/8051.txt
7869c57e4ef7946cb49f87350819ff92cb6e7f732046f7906a93171d0385c583  tb/isa/testall.asm
```

Both agree with `tb/isa/PROVENANCE`, which cites naken_asm and oc8051 with
pinned commits. `8051.txt`'s golden column comes from c51asm, an unrelated
assembler. This is the one part of the testbench with a truly independent
oracle, and it holds up.

---

## What would make the green mean something

1. Stop shipping port-produced ROMs as `reference`. Restore the 2001
   `www8051.rom` set (hashes above) as `tb/reference-2001.md5`, keep the
   port-produced set under an honest name such as `baseline.md5`, and report
   both: `matches baseline` (regression) and `matches 2001` (correctness).
2. Explain the length deltas before re-baking anything. `reset_network` accounts
   for eight of them exactly; `serial`'s 1522 B does not.
3. Make `frozen.yml` able to fail, or stop describing it as a check.
4. Add `pull_request` to `gate.yml` and confirm a required status check exists.

## Changes made on this branch

- `tb/objects-report/PROVENANCE` - corrected the false ".hex has never
  reproduced the .rom" claim with the disproving evidence and a pointer here.
- `.github/workflows/build.yml` - `if-no-files-found: ignore` -> `warn`.
- `.gitignore` - ignore `__pycache__/`.

No change was made to `tb/base.7z`, to any patch, or to any check logic.

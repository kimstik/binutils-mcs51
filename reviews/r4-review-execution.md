# REVIEW-execution — the ten project ROMs, executed

Branch `claude/review-execution`, head `0f45319`. Review only; nothing in
`mcs51/`, `tb/` or `.github/` was modified. Every claim below is a command and
its output.

## Verdict

**Ten of ten execute.** All ten reach their reset entry, run initialisation to
completion, call `network_init`, enter their main loop, and are still cycling
in it after millions of instructions with the PC inside the image and the stack
pointer inside its allotted range.

The ten 2001 `.hex` images shipped alongside them are **zero of ten**: every one
leaves its own ROM on the *first* instruction executed and never returns.

One divergence between the byte comparison and execution, in `diag` — see
§6. It is not fatal, but the byte comparison is structurally blind to it.

## 1. Setup

```
$ make -C tb build                      # binutils 2.47 + mcs51/*.patch
$ work/modern/build/gas/as-new --version | head -1
GNU assembler (GNU Binutils) 2.47.20260726
$ s51 -v
s51: 0.6.4
```

Byte gate first, so execution is judged on the images the gate certifies:

```
$ make -C tb check BUILD=$PWD/work/modern/build
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
all 10 projects match the reference
```

Those exact `www8051.rom` files, converted to Intel hex byte-for-byte, are what
was executed. Simulator: `s51 -t C52 -R <seed>` (C52 because the AT89S8252 has
256 bytes of IRAM and the reset code clears all of it via `MOV @R0` with
R0 = 0…255; on a 128-byte C51 core half of that loop has nowhere to go).

## 2. What "runs" means here

Nine of the ten are web51 firmware for an AT89S8252 with an RTL8019AS on an
ISA-style bus. ucsim models neither the NIC nor the AT89S8252's `WMCON`
watchdog/EEPROM SFR. So the criterion is not "the web server serves a page".
It is the reset path plus liveness, and each part is a separate breakpoint:

| landmark | what it proves |
|---|---|
| `RESET` (`0x0026` in nine, `0x0003` in `diag`) | the reset vector decodes and transfers control to real code |
| `NETWORK_INIT` | the whole init chain — `reset_begin` delay loop, port setup, `MOV SP,#stack`, IRAM clear, timer setup, `reset_device` — completed and fell through to `reset_network` |
| `MAIN` / `MAINLOOP` | `reset_end` completed, the main loop was entered |
| `MAIN` hit **1000 times** | the loop is live, not a one-shot fall-through into blank ROM |

`network_init` is bounded even with no NIC present: `Reset_ISA` and `longpause`
are counted delay loops, and `rcv_pkt` reads `EN0_ISR` and `RET`s when it reads
zero. Nothing in the init path spins on a hardware ready bit, so a missing
RTL8019AS does not by itself hang these images — which is what makes this test
meaningful rather than a test of ucsim's NIC.

## 3. The ten ROMs, executed

Breakpoint on each landmark, then `step 4000000` from reset (deterministic —
no wall-clock timeout is involved in the verdict):

```
$ sh reach.sh work/tb fixed
diag      NI=0x00000304 -> [Stop at 0x000304: (104) Breakpoint]  MAIN=0x00000058 -> [Stop at 0x000058: (104) Breakpoint]
ds1620    NI=0x00001577 -> [Stop at 0x001577: (104) Breakpoint]  MAIN=0x000000fd -> [Stop at 0x0000fd: (104) Breakpoint]
ds1822    NI=0x000014f7 -> [Stop at 0x0014f7: (104) Breakpoint]  MAIN=0x000000ee -> [Stop at 0x0000ee: (104) Breakpoint]
lcd       NI=0x00001352 -> [Stop at 0x001352: (104) Breakpoint]  MAIN=0x0000010a -> [Stop at 0x00010a: (104) Breakpoint]
led1      NI=0x000011bf -> [Stop at 0x0011bf: (104) Breakpoint]  MAIN=0x000000eb -> [Stop at 0x0000eb: (104) Breakpoint]
led2      NI=0x0000111c -> [Stop at 0x00111c: (104) Breakpoint]  MAIN=0x000000eb -> [Stop at 0x0000eb: (104) Breakpoint]
led3      NI=0x000011da -> [Stop at 0x0011da: (104) Breakpoint]  MAIN=0x000000eb -> [Stop at 0x0000eb: (104) Breakpoint]
serial    NI=0x00001d4a -> [Stop at 0x001d4a: (104) Breakpoint]  MAIN=0x0000019d -> [Stop at 0x00019d: (104) Breakpoint]
welcome   NI=0x00001056 -> [Stop at 0x001056: (104) Breakpoint]  MAIN=0x000000eb -> [Stop at 0x0000eb: (104) Breakpoint]
wjava     NI=0x00001056 -> [Stop at 0x001056: (104) Breakpoint]  MAIN=0x000000eb -> [Stop at 0x0000eb: (104) Breakpoint]
```

Liveness — `break MAIN 1000`, i.e. stop on the thousandth pass through the top
of the main loop:

```
$ sh loop.sh                                  # s51 -t C52 -R 1
diag     main=0x00000058 rc=0   CPU state= OK PC= 0x000058 Inst= 1295588
ds1620   main=0x000000fd rc=0   CPU state= OK PC= 0x0000fd Inst= 1471424
ds1822   main=0x000000ee rc=0   CPU state= OK PC= 0x0000ee Inst= 1474046
lcd      main=0x0000010a rc=0   CPU state= OK PC= 0x00010a Inst= 1501896
led1     main=0x000000eb rc=0   CPU state= OK PC= 0x0000eb Inst= 1471280
led2     main=0x000000eb rc=0   CPU state= OK PC= 0x0000eb Inst= 1471280
led3     main=0x000000eb rc=0   CPU state= OK PC= 0x0000eb Inst= 1471510
serial   main=0x0000019d rc=0   CPU state= OK PC= 0x00019d Inst= 1481152
welcome  main=0x000000eb rc=0   CPU state= OK PC= 0x0000eb Inst= 1471280
wjava    main=0x000000eb rc=0   CPU state= OK PC= 0x0000eb Inst= 1471280
```

Ten of ten stop on the thousandth hit; none times out. In the nine web51
projects most of that instruction count is the `reset_begin` ISP delay
(`20 × 255 × 255` DJNZ) — the firmware's own 650 ms power-on wait, executed for
real; `welcome` reaches its `reset_network` stub at instruction 1 313 179.
`diag` has no `reset_begin`; its count is dominated by the two `network_init`
calls (§6) and their `waitbus`/`longpause` loops.

ucsim seeds unmapped external memory pseudo-randomly, so `MOVX` reads of the
absent RTL8019AS return seed-dependent garbage and the main loop takes
different branches on different seeds. Repeated with a different seed, same
result:

```
$ SEED=4242 sh loop.sh
diag     main=0x00000058 rc=0   CPU state= OK PC= 0x000058 Inst= 1295579
ds1620   main=0x000000fd rc=0   CPU state= OK PC= 0x0000fd Inst= 1471424
...
wjava    main=0x000000eb rc=0   CPU state= OK PC= 0x0000eb Inst= 1471280
```

Stack high-water marks over those runs, from ucsim's own counter. Every one is
below `0x90`, where the `.ibss` receive buffer `buf` starts — the linker script's
`PROVIDE (stack = .)` gave each project enough room:

```
diag     Max SP= 0x65, avg 0x59      led2     Max SP= 0x74, avg 0x69
ds1620   Max SP= 0x75, avg 0x6a      led3     Max SP= 0x74, avg 0x69
ds1822   Max SP= 0x82, avg 0x75      serial   Max SP= 0x79, avg 0x6e
lcd      Max SP= 0x74, avg 0x69      welcome  Max SP= 0x74, avg 0x69
led1     Max SP= 0x74, avg 0x69      wjava    Max SP= 0x74, avg 0x69
```

## 4. The 2001 `.hex` images: dead on the first instruction

The static claim (`MOV SP,#0` = `75 81 00`, and reset vector `02 26 00` =
`LJMP 0x2600` instead of `02 00 26` = `LJMP 0x0026`) holds in all ten:

```
              2001 .hex          our .rom
diag     hex: 32 00 00 ...  rom: 12 03 04 01 35 ...
ds1620   hex: 02 26 00 ...  rom: 02 00 26 02 01 cd ...
ds1822   hex: 02 26 00 ...  rom: 02 00 26 02 01 be ...
lcd      hex: 02 26 00 ...  rom: 02 00 26 02 01 da ...
led1/2   hex: 02 26 00 ...  rom: 02 00 26 02 01 bb ...
led3     hex: 02 26 00 ...  rom: 02 00 26 02 02 30 ...
serial   hex: 02 26 00 ...  rom: 02 00 26 02 02 eb ...
welcome  hex: 02 26 00 ...  rom: 02 00 26 02 01 bb ...
wjava    hex: 02 26 00 ...  rom: 02 00 26 02 01 bb ...

MOV SP,#imm  (75 81 xx)      2001 .hex        our .rom
diag         at 0x3e / 0x41  imm = 0          imm = 0x59
ds1620..wjava  at 0x3e       imm = 0          imm = 0x6a / 0x75 / 0x69 / 0x6e
```

Now executed. This is the part that turns the argument into a demonstration:

```
$ sh run2001.sh                # s51 -t C52 -R 1 on base.7z's own www8051.hex
diag     romlen=1264   PC after 1 instr = 0x004854   after 200k = 0x00c1ea
ds1620   romlen=6284   PC after 1 instr = 0x002600   after 200k = 0x00a53d
ds1822   romlen=6078   PC after 1 instr = 0x002600   after 200k = 0x00a53d
lcd      romlen=5754   PC after 1 instr = 0x002600   after 200k = 0x00a53d
led1     romlen=5173   PC after 1 instr = 0x002600   after 200k = 0x00a53d
led2     romlen=5010   PC after 1 instr = 0x002600   after 200k = 0x00a53d
led3     romlen=5200   PC after 1 instr = 0x002600   after 200k = 0x00a53d
serial   romlen=9647   PC after 1 instr = 0x002600   after 200k = 0x00a53d
welcome  romlen=4812   PC after 1 instr = 0x002600   after 200k = 0x00a53d
wjava    romlen=4812   PC after 1 instr = 0x002600   after 200k = 0x00a53d
```

`0x2600` is past the end of all nine images. What the simulator finds there:

```
0x0000    02 26 00 LJMP   0x2600
0x2600    ff       MOV    R7,A          <- unprogrammed ROM
0x2601    ff       MOV    R7,A
0x2602    ff       MOV    R7,A
```

The CPU slides through blank ROM at one byte per instruction until it wraps.
`diag` is worse still — its first byte is a bare `32`:

```
0x0000    <.reset>:
0x0000    32       RETI
```

`RETI` at power-on pops an address off an uninitialised stack: PC = `0x4854`,
outside a 1264-byte image, on instruction one.

So: **none of the ten 2001 images executes**, and the failure is not subtle —
it is instruction one in all ten. `tb/hexoracle.py` compares against these
images; that comparison is still worth having as a record of what the 2001 port
emitted, but the images themselves are not a working reference and nothing
should ever be "corrected" toward them.

The same probe run against the 2001 `welcome` image with *our* landmark
addresses is the negative control for §3's method — nothing is ever reached:

```
$ break 0x1056 ; break 0x00eb ; step 4000000
Stop at 0x00b8b8: (109) stepped 48000864 ticks     <- budget exhausted, no breakpoint
```

## 5. `reset_network`: the fix, proved by execution

The claim under test: `*(reset_network)` was commented out in `lib/www51.sc`,
which orphaned `lib/packet.asm`'s three-byte `LCALL network_init` stub and made
`objcopy -j .text` drop it, so nine of ten ROMs never initialised the NIC. It
has since been restored.

**The restored stub is executed.** Address from each project's own link map,
`break` on it, `step 4000000` from reset:

```
$ sh stub.sh
ds1620   stub=0x000000f2  0x00f2 12 15 77 LCALL 0x1577 | Stop at 0x0000f2: Breakpoint
ds1822   stub=0x000000e3  0x00e3 12 14 f7 LCALL 0x14f7 | Stop at 0x0000e3: Breakpoint
lcd      stub=0x000000e0  0x00e0 12 15 a4 LCALL 0x15a4 | Stop at 0x0000e0: Breakpoint
led1     stub=0x000000e0  0x00e0 12 11 bf LCALL 0x11bf | Stop at 0x0000e0: Breakpoint
led2     stub=0x000000e0  0x00e0 12 11 1c LCALL 0x111c | Stop at 0x0000e0: Breakpoint
led3     stub=0x000000e0  0x00e0 12 11 da LCALL 0x11da | Stop at 0x0000e0: Breakpoint
serial   stub=0x0000018e  0x018e 12 1d 4a LCALL 0x1d4a | Stop at 0x00018e: Breakpoint
welcome  stub=0x000000e0  0x00e0 12 10 56 LCALL 0x1056 | Stop at 0x0000e0: Breakpoint
wjava    stub=0x000000e0  0x00e0 12 10 56 LCALL 0x1056 | Stop at 0x0000e0: Breakpoint
```

Each target is that project's `NETWORK_INIT`, except `lcd`, whose `0x00e0` is
its own `reset_network` section from `projekt/lcd/www8051.asm` (`LCALL d_init`,
the LCD greeting); the `packet.obj` stub follows it and `lcd` reaches
`NETWORK_INIT` at `0x1352` in §3 all the same.

**Without the fix they do not.** The pre-fix state was reproduced under `/tmp`
only — `work/tb` copied, `*(reset_network)` commented out in the *copy's*
`lib/www51.sc`, ten projects relinked. Nothing in the repository was touched:

```
$ sed -i 's|\*(reset_network)|/* & */|' /tmp/.../prefix/lib/www51.sc
82:    /* *(reset_network) */
$ (rebuild)
diag 1264   ds1620 6281   ds1822 6075   lcd 5720   led1 5170
led2 5007   led3 5197     serial 8125   welcome 4809   wjava 4809
```

Three bytes shorter than the reference in nine of them; `lcd` loses 34 (its own
`reset_network` block plus the stub); `diag` comes out at 1264, exactly the size
of the 2001 `diag` image. Executed with the same bounded probe:

```
$ sh reach.sh /tmp/.../prefix prefix
diag      NI=0x0301 -> [Stop at 0x000301: Breakpoint ]  MAIN=0x0055 -> [Stop at 0x000055: Breakpoint]
ds1620    NI=0x1574 -> [Stop at 0x000105: stepped    ]  MAIN=0x00fa -> [Stop at 0x0000fa: Breakpoint]
ds1822    NI=0x14f4 -> [Stop at 0x000113: stepped    ]  MAIN=0x00eb -> [Stop at 0x0000eb: Breakpoint]
lcd       NI=0x1330 -> [Stop at 0x0013d6: stepped    ]  MAIN=0x00e8 -> [Stop at 0x0000e8: Breakpoint]
led1      NI=0x11bc -> [Stop at 0x001250: stepped    ]  MAIN=0x00e8 -> [Stop at 0x0000e8: Breakpoint]
led2      NI=0x1119 -> [Stop at 0x0011b2: stepped    ]  MAIN=0x00e8 -> [Stop at 0x0000e8: Breakpoint]
led3      NI=0x11d7 -> [Stop at 0x0000eb: stepped    ]  MAIN=0x00e8 -> [Stop at 0x0000e8: Breakpoint]
serial    NI=0x1d47 -> [Stop at 0x001606: stepped    ]  MAIN=0x019a -> [Stop at 0x00019a: Breakpoint]
welcome   NI=0x1053 -> [Stop at 0x0011a2: stepped    ]  MAIN=0x00e8 -> [Stop at 0x0000e8: Breakpoint]
wjava     NI=0x1053 -> [Stop at 0x0010f2: stepped    ]  MAIN=0x00e8 -> [Stop at 0x0000e8: Breakpoint]
```

`stepped` = the 4 000 000-instruction budget ran out with the breakpoint never
hit. **Nine of ten never enter `network_init`; `diag` does**, at `0x0301`, via
its own `lcall network_init` in `RESET_CONT` — exactly the nine/one split
`tb/Makefile` describes. All ten still reach `MAIN`, which is precisely why the
regression was invisible: the firmware boots and loops happily, it just never
talks to the NIC. No byte-level gate stage could tell the two apart, because
the reference ROM in `base.7z` was itself regenerated after the fix.

This is the one thing in the repository where "the fix works" is now shown
rather than argued.

## 6. Where execution and the byte comparison disagree: `diag`

`diag` passes `make check` byte-for-byte. Executed, its reset vector is not its
own reset:

```
$ grep -E '^ (reset_network|\.text) ' work/tb/projekt/diag/map
 reset_network  0x00000000        0x3 ../../lib/libw80.a(packet.obj)
 .text          0x00000003      0x10c www8051.obj

$ dc 0 0x12                                   # in s51, on the certified ROM
0x0000    12 03 04 LCALL  0x0304        <- lib/packet.asm's reset_network stub
0x0003    01 35    AJMP   0x0035        <- diag's own `reset'
0x0005 ?  00       NOP
...
0x000b ?  00       NOP                  <- 8051 timer-0 vector: NOP
0x000c ?  00       NOP
0x000d ?  00       NOP
0x000e ?  01 24    AJMP   0x0024        <- diag's I_TF0, displaced by 3
```

`diag` is the one project that does not link `lib/web51_80.obj`, so it has no
`vectors` section and `*(reset_network)` is the first non-empty arm of `.text`
in `www51.sc`. The library stub therefore lands **on the reset vector**.

Three consequences, all measured:

1. **`network_init` runs before the stack pointer exists.** At power-on
   `SP = 0x07`; the `LCALL` at address 0 pushes into IRAM `0x08/0x09` — register
   bank 1 — and the whole of `network_init` then runs on that stack:

   ```
   $ break 0x35 ; run ; state          # 0x35 = RESET_CONT, i.e. `MOV SP,#stack'
   Stop at 0x000035: Breakpoint
   Inst= 135343
   Max value of stack pointer= 0x000010, avg= 0x000007
   ```

   135 343 instructions of NIC initialisation execute before `MOV SP,#stack`,
   touching IRAM `0x08`–`0x10` (banks 1 and 2), and before `MOV P0,#-1` /
   `MOV P1,#0` / … set the port latches. On real hardware the RTL8019AS is
   driven once with the ports still at their power-on all-ones state. Compare
   `welcome`, where `SP` is already `0x69` when its stub runs:

   ```
   $ break 0x00e0 ; run ; state        # welcome's reset_network stub
   Max value of stack pointer= 0x00006d, avg= 0x000069
   ```

2. **`network_init` runs twice.** The stub's `RET` lands on `0x0003`, which is
   `AJMP RESET_CONT`, which contains `diag`'s own `lcall network_init`. Exactly
   twice, never a third time:

   ```
   $ break 0x304 2 ; step 4000000   ->  Stop at 0x000304: Breakpoint
   $ break 0x304 3 ; step 4000000   ->  Stop at 0x000287: stepped   (never hit)
   ```

3. **`diag`'s hand-built interrupt vector is displaced by 3 bytes.** Its source
   uses `.org 0x0B` inside its own `.text`; with `.text` now starting at `0x0003`
   that `AJMP IntTF0` sits at ROM `0x000E`, and the hardware timer-0 vector at
   `0x000B` holds three `NOP`s. **Latent, not live**: no instruction in the
   image writes `IE` or `IP` or sets `EA`, so no interrupt can ever be taken —

   ```
   $ scan diag/www8051.rom for 75 a8 / 43 a8 / d2 af / f5 a8 / 75 b8
   diag:     (none found)
   welcome:  0x0058 MOV IE,#imm   0x00e3 ORL IE,#imm
   ```

   — but the three `NOP`s at `0x000B` do fall through into `AJMP IntTF0` at
   `0x000E`, so even if interrupts were enabled it would still work, by accident.

None of this is a defect in the port: `as`, `ld` and `objcopy` all did what
`lib/www51.sc` and `projekt/diag/Makefile` asked. It is a defect in the project
inputs that only execution can see. **A fix would go in `tb/base.7z`**, in one
of three places — `projekt/diag/Makefile` (link `lib/web51_80.obj`, or link with
ld's built-in script as `tb/Makefile`'s own comment says 2001 did), or
`projekt/diag/www8051.asm` (put its `reset`/`.org 0x0B` block in a `vectors`
section), or `lib/www51.sc`. Not made here. Note that any of them changes
`diag`'s bytes, so `tb/reference.md5` moves with it.

One cosmetic item in the same area, also in `base.7z` and also not touched:
`lib/packet.asm:787` declares `.section reset_network, "a"` — allocatable but
not executable — where every neighbouring section (`reset_begin`,
`reset_device`, `reset_end`, and `lcd`'s own `reset_network`) uses `"ax"`. It
lands in `.text` and executes regardless; it is an inconsistency, not a bug.

## 7. What the simulator cannot answer

Stated so no false confidence is taken from the above.

- **No RTL8019AS.** ucsim has no NE2000. `MOVX` reads of the NIC's ISA window
  return pseudo-random bytes seeded by `-R`. So "the ROM initialises the NIC"
  is proved only as far as "it executes the whole of `network_init` and returns
  to `reset_end`". Whether the register sequence would bring a real RTL8019AS up
  cannot be answered here — it needs a NE2000 model attached to the external bus,
  or hardware.
- **No AT89S8252 `WMCON`.** The watchdog, and the EEPROM-enable bit
  `network_init` toggles around `flash_my_ether`, are a plain SFR cell in ucsim.
  A real part with the watchdog running would reset if the main loop ever
  stalled between `MOV WMCON,#RESTARTWATCHDOG` writes; that failure mode is
  invisible here. The `movx` read of `flash_my_ether` likewise returns garbage
  rather than the board's MAC.
- **No peer.** `serial`'s UART, driven for 8 M instructions with
  `-S out=uart.txt`, emitted a single `\0`: the transmit path is reachable but
  there is nothing to converse with. No HTTP request can be delivered, so the
  `cgi/` and `http.asm` paths are never entered from a real stimulus.
- **"Never fetched outside the image" is NOT proved.** I tried both
  `break rom r <end>` and `statistic rom <end> 0xffff`; neither counts
  instruction fetches in ucsim 0.6.4 — the 2001 `welcome` image sits at
  PC `0xb8b8`, far outside its 4812 bytes, and both probes report zero. So that
  control was discarded. What *is* shown is weaker and honest: after 4 M
  instructions every one of the ten has its PC inside its own image, and each
  passes `main` 1000 times. Proving the stronger property needs a ucsim build
  with fetch tracing, or a `-t` trace log post-processed for out-of-range PCs.
- **Timing is not checked.** ucsim counts cycles but nothing here asserts the
  650 ms ISP delay or the 1 ms `SysTik` reload against real time.

## 8. Reproducing

```
make -C tb build
make -C tb check BUILD=$PWD/work/modern/build
# then, per project, with s51 0.6.4:
#   objcopy the .rom to Intel hex (or bin2hex), addresses from
#   work/modern/build/binutils/nm-new work/tb/projekt/<p>/www8051.o
#   and section placement from work/tb/projekt/<p>/map
s51 -t C52 -R 1 <p>.hex <<'EOF'
break <NETWORK_INIT>
break <MAIN>
step 4000000
state
quit
EOF
```

The driver scripts used (`reach.sh`, `loop.sh`, `stub.sh`, `run2001.sh`,
`prefix.sh`) were throwaway files under `/tmp`, deliberately not added to the
repository — this is a review, not a new gate stage. If any of it is worth
keeping, the natural home is a new `tb/sim/run-projects.sh` beside
`tb/sim/run-testall.sh`, wired into `TOOLGATE`; that would make the merge gate
the first one in this repository's history to execute a project ROM.

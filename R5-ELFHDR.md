# R5-ELFHDR — `e_flags` and `EI_DATA`

Review round 5. **Review only; nothing in `mcs51/` was patched.** Both questions
below are design decisions for the owner; each section ends in a recommendation.

`e_machine = 165` is settled and is not reopened here.

## Method

Everything below was measured, not recalled.

- Toolchain: `binutils-2.47` + `mcs51/additions.patch` + `mcs51/modifications.patch`
  at `90ee2af`, configured `--target=i51-elf`, built with `OPTFLAGS="-O1" AR_WRAP=`
  (LTO off for build speed; it changes no emitted byte of a target object).
- Upstream sources quoted from the same pristine `binutils-2.47` tree.
- Probe objects, both endiannesses, and the ten-project gate results are in `/tmp/r5`.
- The gABI is quoted from <https://www.sco.com/developers/gabi/latest/ch4.eheader.html>.

---

# A. `e_flags`

## A.1 What the port does today: nothing

The field is never written, never read, never checked.

```
$ grep -c e_flags mcs51/additions.patch mcs51/modifications.patch
mcs51/additions.patch:0
mcs51/modifications.patch:0
```

Confirmed on a real object:

```
$ as-new -o probe.o probe.s && readelf -h probe.o
  Machine:                           Intel 8051 and variants
  Flags:                             0x0
```

The port registers exactly one ELF backend hook that could bear on this, and it is
a stub:

```
$ grep -n "final_write_processing\|merge_private\|print_private\|elf_backend_object_p" mcs51/additions.patch
1035:+#define elf_backend_object_p		elf32_i51_object_p
```

```c
/* Set the right machine number.  */

static bool
elf32_i51_object_p (bfd *abfd ATTRIBUTE_UNUSED)
{
  return 1;
}
```

The comment is inherited; the body sets no machine number.

### A.1.1 The write hook is gone

There is no `final_write_processing` on main. There was one in the 2001 original
(`tb/ref.7z`, `i51.patch.112n`):

```c
static void
bfd_elf_i51_final_write_processing (abfd, linker)
     bfd *abfd;
     boolean linker ATTRIBUTE_UNUSED;
{
  unsigned long val;

  elf_elfheader (abfd)->e_machine = EM_I51;
}
```

Two things are worth reading off that. First, the orphaned `unsigned long val;`
with no use is the tell that this function was copied from AVR's
`bfd_elf_avr_final_write_processing` — whose body is exactly
`val = <mach>; e_flags &= ~EF_AVR_MACH; e_flags |= val;` — and that the original
author **deliberately deleted the mach-encoding body** while keeping the
declaration. The port has never encoded a machine in `e_flags`, by choice.

Second, all the surviving function did was force the private `e_machine`
(`EM_I51` = `0x7262`). That job is now done declaratively by
`#define ELF_MACHINE_CODE EM_8051`, so deleting the function lost nothing.
But it did remove **the natural hook point**: any `e_flags` proposal must
re-introduce `elf_backend_final_write_processing`, not merely add a line to an
existing one.

## A.2 What upstream puts in `e_flags`, and what a mismatch produces

Four backends, chosen to span the range of idioms.

### AVR — sub-machine only, no merge hook

`include/elf/avr.h`:

```c
/* Processor specific flags for the ELF header e_flags field.  */
#define EF_AVR_MACH 0x7F

/* If bit #7 is set, it is assumed that the elf file uses local symbols
   as reference for the relocations so that linker relaxation is possible.  */
#define EF_AVR_LINKRELAX_PREPARED 0x80

#define E_AVR_MACH_AVR1     1
#define E_AVR_MACH_AVR2     2
...
#define E_AVR_MACH_XMEGA7  107
```

Low seven bits are the ISA family; bit 7 is a *producer property* (this object was
assembled in a form that permits relaxation). Write side, `bfd/elf32-avr.c`:

```c
  elf_elfheader (abfd)->e_flags &= ~ EF_AVR_MACH;
  elf_elfheader (abfd)->e_flags |= val;
  return _bfd_elf_final_write_processing (abfd);
```

Read side:

```c
static bool
elf32_avr_object_p (bfd *abfd)
{
  unsigned int e_set = bfd_mach_avr2;

  if (elf_elfheader (abfd)->e_machine == EM_AVR
      || elf_elfheader (abfd)->e_machine == EM_AVR_OLD)
    {
      int e_mach = elf_elfheader (abfd)->e_flags & EF_AVR_MACH;
      switch (e_mach)
	{
	default:
	case E_AVR_MACH_AVR2:  e_set = bfd_mach_avr2;  break;
	...
```

AVR registers **no** `merge_private_bfd_data`:

```
$ grep -c "bfd_elf32_bfd_merge_private_bfd_data" bfd/elf32-avr.c
0
```

So `e_flags` feeds `bfd_get_mach()`, and *compatibility is decided by the arch
table*, `bfd/cpu-avr.c`:

```c
static const bfd_arch_info_type *
compatible (const bfd_arch_info_type * a, const bfd_arch_info_type * b)
{
  /* If a & b are for different architectures we can do nothing.  */
  if (a->arch != b->arch)
    return NULL;

  if (a->mach == b->mach)
    return a;

  /* avr-6 is compatible only with itself as its call convention is not
     compatible with other avr (the mcu saves the return address on 3 bytes
     instead of 2).  */
  if (a->mach == bfd_mach_avr6 || b->mach == bfd_mach_avr6)
    return NULL;
  ...
```

**This is the important structural point.** `e_flags` is not itself the gate; it is
the *transport* for a mach number, and the gate is the `compatible` callback.

### MSP430 — sub-machine in `e_flags`, ABI in build attributes

`include/elf/msp430.h`: `#define EF_MSP430_MACH 0xff`, values
`E_MSP430_MACH_MSP430x11 … E_MSP430_MACH_MSP430X`. Same `object_p` /
`final_write_processing` pattern as AVR. Its merge hook never rejects on `e_flags`:

```c
static bool
elf32_msp430_merge_private_bfd_data (bfd *ibfd, struct bfd_link_info *info)
{
  bfd *obfd = info->output_bfd;
  /* Make sure that the machine number reflects the most
     advanced version of the MSP architecture required.  */
#define max(a,b) ((a) > (b) ? (a) : (b))
  if (bfd_get_mach (ibfd) != bfd_get_mach (obfd))
    bfd_default_set_arch_mach (obfd, bfd_get_arch (obfd),
			       max (bfd_get_mach (ibfd), bfd_get_mach (obfd)));
#undef max

  return elf32_msp430_merge_msp430_attributes (ibfd, info);
}
```

Everything that can actually *fail* a link was moved out of `e_flags` and into
`.MSP430.attributes`:

```c
  /* The ISAs must be the same.  */
  if (in_msp_attr[OFBA_MSPABI_Tag_ISA].i != out_msp_attr[OFBA_MSPABI_Tag_ISA].i)
    {
      _bfd_error_handler
	(_("error: %pB uses %s instructions but %pB uses %s"), ...);
      result = false;
    }

  /* The code models must be the same.  */
  ...
  /* The data models must be the same.  */
```

### ARM — ABI version in the top byte, hard reject

`include/elf/arm.h`:

```c
#define EF_ARM_BE8	    0x00800000
#define EF_ARM_EABIMASK      0xFF000000
#define EF_ARM_EABI_VERSION(flags) ((flags) & EF_ARM_EABIMASK)
#define EF_ARM_EABI_VER1     0x01000000
...
#define EF_ARM_EABI_VER5     0x05000000
```

`bfd/elf32-arm.c`:

```c
  /* Complain about various flag mismatches.  */
  if (!elf32_arm_versions_compatible (EF_ARM_EABI_VERSION (in_flags),
				      EF_ARM_EABI_VERSION (out_flags)))
    {
      _bfd_error_handler
	(_("error: source object %pB has EABI version %d, but target %pB has EABI version %d"),
	 ibfd, (in_flags & EF_ARM_EABIMASK) >> 24,
	 obfd, (out_flags & EF_ARM_EABIMASK) >> 24);
      return false;
    }
```

And, decisive for our wild objects, ARM's rule for a zero input:

```c
  if (!elf_flags_init (obfd))
    {
      /* If the input has no flags set, then do not set the output flags.
	 This will allow future bfds to determine the desired output flags.
	 If no input bfds have any flags set, then neither will the output bfd.
	 ...  */
      if (in_flags == 0)
	return true;
```

### RISC-V — the clearest two-class discipline

`include/elf/riscv.h`: `EF_RISCV_RVC 0x1`, `EF_RISCV_FLOAT_ABI 0x6`,
`EF_RISCV_RVE 0x8`, `EF_RISCV_TSO 0x10`. `bfd/elfxx-riscv.c` splits them into
bits that **must match** and bits that **union**:

```c
  /* Disallow linking different float ABIs.  */
  if ((old_flags ^ new_flags) & EF_RISCV_FLOAT_ABI)
    {
      (*_bfd_error_handler)
	(_("%pB: can't link %s modules with %s modules"), ibfd,
	 riscv_float_abi_string (new_flags),
	 riscv_float_abi_string (old_flags));
      goto fail;
    }

  /* Disallow linking RVE and non-RVE.  */
  if ((old_flags ^ new_flags) & EF_RISCV_RVE)
    {
      (*_bfd_error_handler)
       (_("%pB: can't link RVE with other target"), ibfd);
      goto fail;
    }

  /* Allow linking RVC and non-RVC, and keep the RVC flag.  */
  elf_elfheader (obfd)->e_flags |= new_flags & EF_RISCV_RVC;

  /* Allow linking TSO and non-TSO, and keep the TSO flag.  */
  elf_elfheader (obfd)->e_flags |= new_flags & EF_RISCV_TSO;
```

### What a mismatch produces

Two distinct failure paths, both in `ld/ldlang.c`:

`compatible == NULL` from the arch table:

```c
      if (compatible == NULL)
	{
	  if (command_line.warn_mismatch)
	    einfo (_("%X%P: %s architecture of input file `%pB'"
		     " is incompatible with %s output\n"),
		   bfd_printable_name (input_bfd), input_bfd,
		   bfd_printable_name (link_info.output_bfd));
	}
```

`merge_private_bfd_data` returning false:

```c
	  if (!bfd_merge_private_bfd_data (input_bfd, &link_info))
	    {
	      if (command_line.warn_mismatch)
		einfo (_("%X%P: failed to merge target specific data"
			 " of file %pB\n"), input_bfd);
	    }
```

`%X` sets the failure exit code, so both are fatal to the link, and the backend's
own `_bfd_error_handler` message is printed first. Both are suppressible with
`--no-warn-mismatch`.

### A.2.1 What this port would inherit today

`bfd/cpu-i51.c` declares one machine and uses the default comparator:

```c
const bfd_arch_info_type bfd_i51_arch =
{
  8,				/* Bits per word.  */
  16,				/* Bits per address.  */
  8,				/* Bits per byte.  */
  bfd_arch_i51,			/* Architecture.  */
  0,				/* Machine number - 0 for default.  */
  ...
  bfd_default_compatible,	/* Architecture comparison function.  */
```

and `bfd_default_compatible` (`bfd/archures.c`) **cannot reject same-arch inputs**:

```c
bfd_default_compatible (const bfd_arch_info_type *a,
			const bfd_arch_info_type *b)
{
  if (a->arch != b->arch)
    return NULL;
  if (a->bits_per_word != b->bits_per_word)
    return NULL;
  if (a->mach > b->mach)
    return a;
  if (b->mach > a->mach)
    return b;
  return a;
}
```

So even if `e_flags` were decoded into distinct `bfd_mach_i51_*` values tomorrow,
the link would silently pick the higher one. Any rejection needs a *custom
`compatible`* (AVR's shape) or a *custom merge hook* (RISC-V's shape). This is the
single most-missed step, and it is the one AVR shows and MSP430 does not.

### A.2.2 Demonstration that nothing is checked now

```
$ as-new -o probe.o probe.s
$ as-new -o probe2.o probe2.s
$ python3 -c "...; f.seek(36); f.write(struct.pack('<I',0xDEADBEEF))"   # probe2.o
probe2.o e_flags := 0xDEADBEEF
$ ld-new -r -o merged.o probe.o probe2.o
$ echo $?
0
$ readelf -h merged.o | grep -iE "Flags|Machine"
  Machine:                           Intel 8051 and variants
  Flags:                             0x0
```

Contradictory `e_flags` link clean, and the value is not even propagated to the
output — it is dropped, because nothing writes it.

## A.3 Triage: what belongs where

| Candidate | Verdict | Why |
|---|---|---|
| 8051 vs 8052 (upper IDATA `0x80–0xFF` indirect, T2) | **`e_flags`** *(if a producer can set it)* | Real, and genuinely unchecked today — see A.3.1 |
| 80251 / 80151 extended cores | **`e_flags`, reserve only** | Different ISA. The port assembles 8051 only (`make roundtrip` covers 280 + 3 + 18 instructions, all 8051). Encoding a value for a core the assembler cannot emit is speculative; reserve the space, do not populate it |
| Vendor supersets (Dallas, SiLabs, Nordic, Infineon XC800 …) | **Nowhere** | These differ in SFR maps and peripherals, resolved by `.inc` files at assembly time. They have no linker consequence. AVR encodes `E_AVR_MACH_AVR5` for hundreds of parts and no part numbers; MSP430 likewise. A part-number field would be a combinatorial explosion with no consumer |
| Big-endian 16-bit instruction fields | **Nowhere — it is `EI_DATA`'s job** | Not an ABI choice this port makes; it is what the MCS-51 ISA mandates, and every 8051 assembler does it. See section B |
| Uppercased symbols | **`e_flags` ABI nibble** | A real, invisible, port-specific convention. See A.3.2 |
| Memory-space common scheme (`SHN_LORESERVE+0…6`, `SHF_CDATA`) | **`e_flags` ABI nibble** | The highest-value item. See A.3.3 |
| Anything above | **not `EI_OSABI`, not `EI_ABIVERSION`** | See A.3.4 |

### A.3.1 The 8051/8052 RAM distinction really is unchecked

It would be reasonable to assume the linker script catches RAM overrun. It does
not. `ld/scripttempl/elf32i51.sc` declares exactly one MEMORY region:

```
MEMORY
{
  /* Code space.  64K is the architectural limit; the smaller ROM of a
     concrete chip is a property of that chip, not of this script.  */
  rom (rx) : ORIGIN = 0x0000, LENGTH = 0x10000
}
```

and every RAM space is a non-alloc `(INFO)` section with a computed VMA and **no
`> region` clause**:

```
  .regbank 0x00 (INFO) :
  .rdata (ADDR (.regbank) + SIZEOF (.regbank)) (INFO) :
  .rbss  (ADDR (.rdata) + SIZEOF (.rdata)) (INFO) :
  ...
  .idata (ADDR (.bss) + SIZEOF (.bss)) (INFO) :
  .ibss  (ADDR (.idata) + SIZEOF (.idata)) (INFO) :
```

That is a deliberate and correct design (the script's own header explains it: the
spaces must keep true on-chip addresses, so they cannot be spread over disjoint
VMA windows). The side effect is that **no region overflow check exists for any
RAM space.** A build that runs `.ibss` past `0x7F` on a part with no upper IDATA
links silently and runs wrong.

So this is a genuine gap. But note carefully what would close it: a `LENGTH` on a
RAM region, or a script assertion, closes it *directly*. `e_flags` closes it only
*indirectly*, and only once a producer exists that knows which part it is
targeting — which today it does not (A.5.1).

### A.3.2 Uppercased symbols

```c
/* MCS-51 symbols are case insensitive (acc.7 is the same as Acc.7 and
   ACC.7), which gas implements by folding every symbol name to upper case
   as it is created. ... */
void
i51_init_after_args (void)
{
  symbols_case_sensitive = 0;
}
```

Visible in a real object — the source says `start`, the symbol table says `START`:

```
$ ld-new -r -o merged.o probe.o probe_flagged.o
ld-new: probe_flagged.o: in function `START':
(.text+0x0): multiple definition of `START'
```

Mixing folded and unfolded objects fails loudly today (undefined symbols), so this
is a *diagnostic-quality* improvement, not a correctness one. It rides along in the
ABI nibble for free; it does not justify the nibble by itself.

### A.3.3 The memory-space common scheme — the item with teeth

This is the one place where a silent mismatch produces a *wrong program* rather
than a failed link. A memory-space common travels as a reserved section index:

```c
#define SHN_I51_REGBANK SHN_LORESERVE        /* Register bank common */
#define SHN_I51_RDATA_C (SHN_LORESERVE + 1)  /* rdata common */
...
#define SHN_I51_BITDATA_C (SHN_LORESERVE + 6) /* bitdata common */
```

and the port's own source records that the section-header half of the scheme is
**unimplemented and cannot be implemented as currently shaped**:

```c
/* Section headers on the way out.

   This is where a memory-space code would be stamped into the top bits
   of sh_flags - SHF_RDATA on .rbss, SHF_BDATA on .bbss and so on - so
   that a consumer could tell one space from another from the section
   header alone.  Nothing is stamped, and nothing can be: ...
   The classification is unimplemented.  */
```

An acknowledged-incomplete, port-private scheme carried in reserved indices is
exactly the thing that will be revised. If it is revised without a version stamp,
an old object and a new linker will agree on the *numbers* and disagree on the
*meaning*, and a variable lands in the wrong address space. That failure is silent,
and on this target it is the worst failure available.

### A.3.4 Why not `EI_OSABI` / `EI_ABIVERSION`

gABI:

> Byte `e_ident[EI_OSABI]` identifies the OS- or ABI-specific ELF extensions used
> by this file. Some fields in other ELF structures have flags and values that have
> operating system and/or ABI specific meanings; the interpretation of those fields
> is determined by the value of this byte.

> Byte `e_ident[EI_ABIVERSION]` identifies the version of the ABI to which the
> object is targeted. This field is used to distinguish among incompatible versions
> of an ABI. The interpretation of this version number is dependent on the ABI
> identified by the `EI_OSABI` field.

Everything this port invents lives in **processor-specific** ranges, not
OS-specific ones: `SHN_I51_*` start at `SHN_LORESERVE` = `SHN_LOPROC` = `0xff00`
and stay inside `SHN_HIPROC` = `0xff1f`; `SHF_CDATA` = `0xE0000000` is inside
`SHF_MASKPROC` = `0xF0000000`. Those ranges are given meaning by `e_machine`,
which is already `EM_8051` and already unique. `EI_OSABI` would be redundant at
best; setting it non-zero would additionally tell every generic consumer that it
needs OS-specific knowledge it does not need, and `EI_ABIVERSION` is explicitly
defined as meaningless unless `EI_OSABI` is set. Both should stay `0`, as they are
in all 30 shipped objects.

## A.4 Concrete proposal

### Bit layout

```
   31                    16 15    12 11     8 7             0
  +------------------------+--------+--------+---------------+
  |     reserved (MBZ)     |  CAP   |  ABI   |     MACH      |
  +------------------------+--------+--------+---------------+
```

```c
/* Processor specific flags for the ELF header e_flags field.  */

/* Core family.  Reject class: two objects that name different cores may
   not be linked unless one of them is UNKNOWN.  */
#define EF_I51_MACH		0x000000ff
#define E_I51_MACH_UNKNOWN	0	/* not stated (pre-flags object)  */
#define E_I51_MACH_8051		1	/* base MCS-51: 128 B IDATA       */
#define E_I51_MACH_8052		2	/* + upper IDATA 0x80-0xFF, T2    */
#define E_I51_MACH_80251	51	/* reserved: MCS-251 core         */
#define E_I51_MACH_80151	52	/* reserved: MCS-151 core         */

/* Port ABI revision: symbol folding + memory-space common scheme.
   Reject class: differing non-zero values may not be linked.  */
#define EF_I51_ABI		0x00000f00
#define E_I51_ABI_UNKNOWN	0x00000000  /* not stated                 */
#define E_I51_ABI_WEB51_1	0x00000100  /* symbols folded upper case;
					       commons at SHN_LORESERVE+0..6 */

/* Producer capabilities.  Union class: OR-merged, never rejected.  */
#define EF_I51_CAP		0x0000f000
#define EF_I51_CAP_PCODE	0x00001000  /* object uses .pcode /
					       R_I51_13_PCODE            */
```

`MACH` follows AVR/MSP430 (low byte, small integers). `ABI` follows ARM's EABI
version idea, shrunk to a nibble because this port will not see 255 revisions.
`CAP` follows RISC-V's `RVC`/`TSO` union bits. The split into reject-class and
union-class fields is the RISC-V discipline and is the part worth copying.

### `bfd_mach_*` map

```c
#define bfd_mach_i51		 0	/* default; == E_I51_MACH_UNKNOWN */
#define bfd_mach_i51_8051	 1
#define bfd_mach_i51_8052	 2
#define bfd_mach_i51_80251	51
#define bfd_mach_i51_80151	52
```

with `bfd/cpu-i51.c` growing an `arch_info_struct[]` chain (AVR's shape) and,
critically, **its own `compatible`** — `bfd_default_compatible` cannot reject
(A.2.1):

```c
static const bfd_arch_info_type *
compatible (const bfd_arch_info_type *a, const bfd_arch_info_type *b)
{
  if (a->arch != b->arch)
    return NULL;
  if (a->mach == b->mach)
    return a;
  /* Unstated links with anything and takes the other side's identity.  */
  if (a->mach == bfd_mach_i51) return b;
  if (b->mach == bfd_mach_i51) return a;
  /* 8051 code runs on an 8052; the reverse is not true.  */
  if (a->mach == bfd_mach_i51_8051 && b->mach == bfd_mach_i51_8052) return b;
  if (a->mach == bfd_mach_i51_8052 && b->mach == bfd_mach_i51_8051) return b;
  /* The extended cores are compatible only with themselves.  */
  return NULL;
}
```

### What `merge_private_bfd_data` should reject

```
  ABI   : both non-zero and different            -> reject
          "object %pB uses i51 ABI revision %d, but %pB uses revision %d"
  MACH  : handled by `compatible` above; the merge hook only raises the
          output mach to the union result, MSP430-style
  CAP   : never rejected; OR-merged into the output
  reserved bits set (0xffff0000)                 -> reject
          "object %pB sets unknown i51 e_flags bits 0x%x"
```

The reserved-bit rejection is what makes the field extensible: it guarantees that
a future flag added by a newer assembler is *noticed* by an older linker rather
than ignored. Without it, a version stamp buys much less than it looks like.

### What zero must mean

**Zero means "not stated" and must never constrain the link.** ARM's rule,
verbatim:

```c
      /* If the input has no flags set, then do not set the output flags.
	 This will allow future bfds to determine the desired output flags. ... */
      if (in_flags == 0)
	return true;
```

This is not an academic concern here. Every object already in the wild has
`e_flags = 0`. All 30 precompiled objects `tb/base.7z` ships:

```
$ python3 findelf.py base
path                                       DATA   OSABI  ABIVER   type   machine  e_flags
cgi/bd.obj                                 1      0      0        1      165      0x00000000
...
lib/web51_80.obj                           1      0      0        1      165      0x00000000
total ELF files: 30
```

— 30/30 with `EI_DATA=1`, `OSABI=0`, `ABIVERSION=0`, `e_machine=165`,
`e_flags=0x00000000`. Plus every `.o` produced by the port to date. If zero were
rejected, or were treated as `E_I51_MACH_8051`, the shipped inputs would stop
linking or would start constraining links they have no business constraining.
`E_I51_MACH_UNKNOWN` / `E_I51_ABI_UNKNOWN` at value 0 makes the whole existing
corpus a permanent, silent no-op.

## A.5 Cost

### A.5.1 The prerequisite nobody can skip: gas has no options

```c
const struct option md_longopts[] =
{
  { NULL, no_argument, NULL, 0 }
};

int
md_parse_option (int c ATTRIBUTE_UNUSED, const char *arg ATTRIBUTE_UNUSED)
{
  return 0;
}
```

and `gas/config/tc-i51.h`:

```c
#define TARGET_MACH 0
```

There is no `-mmcu=`, no `-m8052`, nothing. **Every object the port can currently
produce would carry an identical `e_flags`.** A field with one possible value
checks nothing. So the `MACH` half of this proposal is not implementable as a
self-contained change: it requires `md_longopts` + `md_parse_option` +
`bfd_set_arch_mach` in gas first, and then a decision about what the *default*
is when `-mmcu=` is absent (it must be `UNKNOWN`, or every old-Makefile build
starts asserting a core it was never told about).

### A.5.2 Files that change

| File | Change |
|---|---|
| `include/elf/i51.h` | the `EF_I51_*` / `E_I51_*` block |
| `bfd/elf32-i51.c` | **re-add** `elf_backend_final_write_processing` (deleted; A.1.1); flesh out the `elf32_i51_object_p` stub; add `bfd_elf32_bfd_merge_private_bfd_data`; add `bfd_elf32_bfd_print_private_bfd_data` for `objdump -p` |
| `bfd/cpu-i51.c` | `arch_info_struct[]` chain + custom `compatible` (A.2.1) |
| `bfd/archures.c` | `bfd_mach_i51_*` values (patched region already exists in `modifications.patch`) |
| `gas/config/tc-i51.c` | `md_longopts`, `md_parse_option`, `md_show_usage`, `bfd_set_arch_mach` call |
| `gas/config/tc-i51.h` | `TARGET_MACH` |
| `binutils/readelf.c` | a `case EM_8051:` in `get_machine_flags ()` — there is none today, which is why `readelf -h` prints a bare `Flags: 0x0` |
| `ld/emulparams/elf32i51.sh` | nothing (`ARCH=i51` keeps resolving to the default mach) |
| `tb/` | a gate stage for the new rejection paths; `mutation/` entries |

Roughly a `MACH`-and-`ABI` change touches 8 files across 4 components, and cannot
land in one piece because gas must grow options first.

### A.5.3 Reference ROMs do not move — proven

`e_flags` is a header field; it is not in any section's contents, so no ROM can
depend on it. Proof, not assertion. Take the extracted testbench tree, stamp a
garbage `e_flags` into **every** ELF input including all 30 precompiled objects,
and rebuild all ten projects:

```
$ python3 /tmp/r5/stamp.py /tmp/r5/tb-eflags 0xDEADBEEF
stamped e_flags=0xdeadbeef into 80 objects

$ python3 findelf.py /tmp/r5/tb-eflags/lib
web51.obj      1  0  0  1  165  0xdeadbeef
web51_23.obj   1  0  0  1  165  0xdeadbeef
web51_80.obj   1  0  0  1  165  0xdeadbeef

$ sh /tmp/r5/rebuild.sh /tmp/r5/tb-eflags
diag      1267 84779b2386ba64a0347e227ac09cf18a
ds1620    6284 5bd93daf7609853f6c3db6541060c420
ds1822    6078 733b5d0483c7cd324156cd36da1743a6
lcd       5754 7c0f4fccb4e9ee7305c1f8c8fe7bee1e
led1      5173 bd336522c8c54be539f2e45d5bbe7888
led2      5010 97e9cf0cf06ebf6ff10e98a6420f6f63
led3      5200 470097b25def9f33cde74fdb4c6264f1
serial    8128 94c14915a302c599ff91b88244319f4d
welcome   4812 0244913c2585c0dc9995a5e6a2e95d6d
wjava     4812 bbdbcb2b80d62a384aa8f3ec9d407315
```

Byte-for-byte the pinned `tb/reference.md5`. Ten of ten. **No ROM moves, and the
link does not even notice.** The second half of that sentence is the finding: the
same experiment that proves the change is ROM-safe also proves the field is
completely unpoliced today.

## A.6 Recommendation — A

**Do not add a `MACH` field now. Add the `ABI` nibble and the reserved-bit
rejection now, and nothing else.**

Reasoning:

1. **`MACH` cannot pay for itself yet.** gas has no `-mmcu=` (A.5.1), so every
   object would carry one value. It would be pure ceremony, plus 8 files of
   machinery, plus a permanent compatibility surface. AVR and MSP430 both added
   `e_flags` machs *because they already had multi-part assemblers*; this port
   does not. Revisit when and if `-mmcu=` lands — and note that the RAM-overrun
   gap A.3.1 identifies is closed better and sooner by a `LENGTH` on a RAM region
   or a script `ASSERT` than by `e_flags`.

2. **The `ABI` nibble does pay for itself, cheaply, and only if done before the
   scheme changes.** The memory-space common scheme is port-private, is
   documented in the port's own source as unimplemented in its section-header
   half (A.3.3), and will be revised. A version stamp is worthless applied
   retroactively and near-free applied now: one `final_write_processing` (which
   must be re-added regardless — A.1.1), one merge hook, one `readelf` case.
   Zero keeps the entire existing corpus valid forever (A.4), which the 30
   shipped objects demonstrably need.

3. **Reject unknown reserved bits from day one.** This is the cheapest line in the
   whole proposal and the one that makes every later addition detectable by an
   older linker. Adding it later is impossible — by then old linkers are already
   ignoring bits.

4. Do **not** touch `EI_OSABI` or `EI_ABIVERSION` (A.3.4). Do not put vendor part
   numbers anywhere.

Net: a one-nibble, one-hook change that is invisible to every existing object and
buys exactly one thing — the ability to detect a future memory-space scheme
revision instead of mislinking through it. If the owner does not intend to revise
that scheme, then the honest answer is **do nothing at all**, and `e_flags = 0`
stays correct and self-documenting.

---

# B. `EI_DATA`

## B.1 What the gABI says it governs

From the System V gABI, ELF header, `e_ident[EI_DATA]`
(<https://www.sco.com/developers/gabi/latest/ch4.eheader.html>):

> Byte `e_ident[EI_DATA]` specifies the encoding of both the data structures used
> by object file container **and data contained in object file sections**.

> Encoding `ELFDATA2LSB` specifies 2's complement values, with the least
> significant byte occupying the lowest address.

> Encoding `ELFDATA2MSB` specifies 2's complement values, with the most
> significant byte occupying the lowest address.

The question in the brief — "ELF structures only, or section contents too?" — is
answered explicitly and unambiguously by the spec: **both**. `EI_DATA` is not a
statement about the container alone.

That makes this section's finding a conformance question, not a matter of taste:
this port declares `ELFDATA2LSB` and every byte in every section is MSB-first.

## B.2 What is actually LE and what is actually BE

### The two declarations disagree

`bfd/elf32-i51.c` (via `mcs51/additions.patch`):

```c
#define TARGET_LITTLE_SYM	i51_elf32_vec
#define TARGET_LITTLE_NAME	"elf32-i51"
```

`gas/config/tc-i51.h`, in the same patch:

```c
#define TARGET_BYTES_BIG_ENDIAN 1
/*   You should define this macro to be non-zero if the target is big
     endian, and zero if the target is little endian.  */
...
#define md_number_to_chars number_to_chars_bigendian
```

`number_to_chars_bigendian` is what `.word`, `.long`, `.short` and every
`md_apply_fix` write goes through. It is a hard `#define`, not a runtime choice —
so **`.word` data is big-endian regardless of the BFD vector.** The two halves of
the port state opposite things.

### This mismatch is unique in binutils 2.47

Every gas target that declares `TARGET_BYTES_BIG_ENDIAN 1`:

```
$ for f in gas/config/tc-*.h; do v=$(grep -h "define TARGET_BYTES_BIG_ENDIAN" $f | head -1 | awk '{print $3}'); [ "$v" = "1" ] && echo "$(basename $f)"; done
tc-d10v.h  tc-d30v.h  tc-dlx.h  tc-fr30.h  tc-frv.h  tc-h8300.h  tc-hppa.h
tc-i51.h   tc-ia64.h  tc-ip2k.h tc-iq2000.h tc-lm32.h tc-m32r.h  tc-m68hc11.h
tc-m68k.h  tc-microblaze.h  tc-mips.h  tc-mmix.h  tc-moxie.h  tc-mt.h
tc-nds32.h tc-or1k.h  tc-ppc.h  tc-s12z.h  tc-s390.h  tc-sparc.h  tc-spu.h
tc-tic30.h tc-visium.h  tc-xgate.h  tc-z8k.h
```

paired against what their BFD backend declares:

```
$ for t in ip2k iq2000 lm32 moxie mt or1k visium xgate fr30 d10v d30v microblaze; do
    printf "%-12s " $t; grep -ho "TARGET_BIG_SYM\|TARGET_LITTLE_SYM" bfd/elf32-$t.c | sort -u | tr '\n' ' '; echo; done
ip2k         TARGET_BIG_SYM
iq2000       TARGET_BIG_SYM
lm32         TARGET_BIG_SYM
moxie        TARGET_BIG_SYM TARGET_LITTLE_SYM
mt           TARGET_BIG_SYM
or1k         TARGET_BIG_SYM
visium       TARGET_BIG_SYM
xgate        TARGET_BIG_SYM
fr30         TARGET_BIG_SYM
d10v         TARGET_BIG_SYM
d30v         TARGET_BIG_SYM
microblaze   TARGET_BIG_SYM TARGET_LITTLE_SYM
i51          TARGET_LITTLE_SYM
```

`moxie` and `microblaze` declare both because they are genuinely bi-endian and
their gas switches at runtime. **`i51` is the only target in the tree whose gas
says big-endian and whose BFD backend offers a little-endian vector only.**

### The measured byte map

Probe source (`/tmp/r5/probe.s`), assembled with the port as shipped:

```
	ljmp	target
	lcall	target
	mov	dptr,#0x1234
	ajmp	target
	sjmp	start
	mov	a,#0x5a
target:	nop
	.word	0x1234
	.long	0x89abcdef
	.byte	0xde
	.byte	0xad
```

Raw bytes, read with `od` so no tool's interpretation is in the way
(`.text` is at file offset `0x34`, size `0x18`):

```
$ od -A x -t x1 -j 52 -N 24 probe.o
000034 02 00 00 12 00 00 90 12 34 01 00 80 f3 74 5a 00
000044 12 34 89 ab cd ef de ad
```

| Offset | Bytes | Source | Byte order of the multi-byte field |
|---|---|---|---|
| `0x00` | `02 00 00` | `ljmp target` | addr16 `0x0000` unrelocated — **MSB first** |
| `0x03` | `12 00 00` | `lcall target` | addr16 — **MSB first** |
| `0x06` | `90 12 34` | `mov dptr,#0x1234` | data16 `12 34` — **MSB first** |
| `0x09` | `01 00` | `ajmp target` | 11-bit, page bits in the opcode |
| `0x0b` | `80 f3` | `sjmp start` | 8-bit pc-relative, `-13` |
| `0x0d` | `74 5a` | `mov a,#0x5a` | 8-bit immediate |
| `0x0f` | `00` | `nop` | — |
| `0x10` | `12 34` | `.word 0x1234` | **MSB first — this is data, not an instruction** |
| `0x12` | `89 ab cd ef` | `.long 0x89abcdef` | **MSB first — data** |
| `0x16` | `de ad` | `.byte 0xde, 0xad` | — |

**So the answer to "does `.word` data flip?" is that it is already big-endian
today.** The brief's worry — "that WOULD move ROMs if any project stores 16-bit
data" — does not apply, because `.word` is not currently little-endian. See B.4.

Against that, the ELF container really is little-endian. `.rela.text` at `0xbc`,
three 12-byte entries:

```
$ od -A d -t x1 -j 188 -N 36 probe.o
0000188 01 00 00 00 09 01 00 00 0f 00 00 00 04 00 00 00
0000204 09 01 00 00 0f 00 00 00 09 00 00 00 04 01 00 00
0000220 0f 00 00 00
```

`r_offset = 01 00 00 00` = LE(1); `r_info = 09 01 00 00` = LE(`0x00000109`);
`r_addend = 0f 00 00 00` = LE(15). Matching `readelf`:

```
Relocation section '.rela.text' at offset 0xbc contains 3 entries:
 Offset     Info    Type            Sym.Value  Sym. Name + Addend
00000001  00000109 R_I51_16          00000000   .text + f
00000004  00000109 R_I51_16          00000000   .text + f
00000009  00000104 R_I51_11          00000000   .text + f
```

`.symtab` at `0x4c` likewise: `st_name = 01 00 00 00`, `st_value = 0f 00 00 00`.

### Summary

| Component | Byte order | Set by |
|---|---|---|
| `e_ident[EI_DATA]` declaration | **LSB** | `TARGET_LITTLE_SYM` in `bfd/elf32-i51.c` |
| ELF header, section headers | LE | the BFD vector |
| `.symtab` entries | LE | the BFD vector |
| `.rela` entries | LE | the BFD vector |
| Instruction `addr16` / `data16` fields | **BE** | ISA; `bfd_putb16` in `elf32_i51_relocate_section`, `md_number_to_chars` in gas |
| `.word` / `.long` / `.short` directive data | **BE** | `#define md_number_to_chars number_to_chars_bigendian` |
| `.byte` data | n/a | — |

Everything the gABI sentence calls "data contained in object file sections" is
big-endian. Everything it calls "the data structures used by object file
container" is little-endian. The declaration covers both and is right about one.

## B.3 How the declaration came to be wrong

This is not an original design decision; it is a side effect of the `e_machine`
re-stamp, and it is worth reading the evidence because it changes how much weight
the status quo deserves.

The 2001 originals, from `tb/base2001.7z`:

```
$ python3 findelf.py base2001
lib/web51_80.obj    2   0   0   1   29282   0x00000000
total ELF files: 28
```

28/28 with `EI_DATA = 2` (`ELFDATA2MSB`) and `e_machine = 29282` = `0x7262`
(`EM_I51`, the port's private number). **The original port was big-endian.**

The independent sibling port of the same lineage on binutils 2.38
(<https://github.com/github0null/binutils-mcs51>, `bfd/elf32-i51.c`) is also
big-endian, and kept the private machine number:

```c
#define TARGET_BIG_SYM       i51_elf32_vec
#define TARGET_BIG_NAME	     "elf32-i51"
...
#define ELF_MACHINE_CODE	EM_I51
```

Ghidra's 8051 language definitions (`Ghidra/Processors/8051/data/languages/8051.ldefs`)
are big-endian across every variant — `8051:BE:16:default`, `80251:BE:24:default`,
`80390:BE:24:default`, `8051:BE:24:mx51`, `8051:BE:24:cip-51`, all `endian="big"`.

The conversion happened in `tb/i51elf_le2be.py` (misnamed — it converts
big-endian → little-endian), whose docstring states the intent:

```python
"""
Convert old i51 ELF objects (big-endian, machine 0x7262)
to new i51 ELF objects (little-endian, machine EM_8051 = 165)
"""
```

and which performs both changes in the same pass:

```python
    data[5] = 1  # EI_DATA: little-endian
    ...
    data[18:20] = struct.pack('<H', 165)
```

Two changes rode in on one script. One of them — private `0x7262` → registered
`EM_8051` — is correct, reviewed, and settled. The other — `ELFDATA2MSB` →
`ELFDATA2LSB` — has no stated justification anywhere in the tree, and nothing
required it: the machine number and the byte order are independent fields.

Critically, the script rewrites **only** the ELF header, the section header table,
`SHT_SYMTAB` entries and `SHT_RELA` entries:

```
$ grep -n "SHT_SYMTAB\|SHT_RELA" tb/i51elf_le2be.py
134:        if sh_type == 2:  # SHT_SYMTAB
159:        if sh_type == 4:  # SHT_RELA
```

It never touches `PROGBITS` contents — correctly, since those are big-endian by
the ISA. So the section bytes in all 30 shipped objects are the *unmodified 2001
big-endian bytes*, sitting under a header that was flipped to say little-endian.
That is precisely the inconsistency measured in B.2.

## B.4 Cost of switching to `TARGET_BIG_SYM` — measured

### The diff

Two lines, in one file:

```c
-#define TARGET_LITTLE_SYM	i51_elf32_vec
-#define TARGET_LITTLE_NAME	"elf32-i51"
+#define TARGET_BIG_SYM	i51_elf32_vec
+#define TARGET_BIG_NAME	"elf32-i51"
```

Nothing else. The vector's C symbol (`i51_elf32_vec`) and its target-name string
(`"elf32-i51"`) are unchanged, so `bfd/config.bfd`, `bfd/targets.c`,
`gas`'s `TARGET_FORMAT` and `ld/emulparams/elf32i51.sh`'s `OUTPUT_FORMAT` all
need no edit. `bfd/elfxx-target.h` emits the correct `BFD_ENDIAN_BIG` /
`bfd_getb32` / `bfd_putb32` wiring from the `TARGET_BIG_SYM` branch.

### Which howtos change: none

All twelve howtos in `elf_i51_howto_table[]` use `bfd_elf_generic_reloc` with
`partial_inplace = false`, so the endian-sensitive generic path
(`_bfd_relocate_contents`) is never reached. Final-link relocation is done by
`elf32_i51_relocate_section`, which addresses bytes explicitly:

```c
      x = bfd_getb16 (contents);
      ...
      bfd_putb16 (x, contents);
      ...
      bfd_putb16 ((bfd_vma) srel & 0xFFFF, contents);
```

`bfd_getb16`/`bfd_putb16` do not consult the BFD vector. Nothing to change.

### Does `.word` data flip? No — proven

Same probe, same source, assembled by a toolchain rebuilt with `TARGET_BIG_SYM`:

```
$ od -A x -t x1 -j 0 -N 20 probe.o        # LE build
000000 7f 45 4c 46 01 01 01 00 00 00 00 00 00 00 00 00
000010 01 00 a5 00
$ od -A x -t x1 -j 52 -N 24 probe.o
000034 02 00 00 12 00 00 90 12 34 01 00 80 f3 74 5a 00
000044 12 34 89 ab cd ef de ad

$ od -A x -t x1 -j 0 -N 20 probe_be.o     # BE build
000000 7f 45 4c 46 01 02 01 00 00 00 00 00 00 00 00 00
000010 00 01 00 a5
$ od -A x -t x1 -j 52 -N 24 probe_be.o
000034 02 00 00 12 00 00 90 12 34 01 00 80 f3 74 5a 00
000044 12 34 89 ab cd ef de ad
```

`e_ident[5]` goes `01` → `02`; `e_type`/`e_machine` go `01 00 a5 00` → `00 01 00 a5`.
**The 24 bytes of `.text` are byte-for-byte identical**, `.word 0x1234` included.
Only the container moved. The relocations moved with it:

```
$ od -A d -t x1 -j 188 -N 36 probe_be.o
0000188 00 00 00 01 00 00 01 09 00 00 00 0f 00 00 00 04
0000204 00 00 01 09 00 00 00 0f 00 00 00 09 00 00 01 04
0000220 00 00 00 0f
```

### `make check`, first attempt: 10 of 10 fail

```
$ make check BUILD=.../work/modern/build
ld-new: ../../lib/web51_80.obj: relocations in generic ELF (EM: 165)
ld-new: ../../lib/web51_80.obj: error adding symbols: file in wrong format
...
FAIL diag     build-failed
...
10 of 10 projects failed
```

This is **not** ROM drift. Not one ROM was produced. The cause is entirely that
the 30 precompiled objects and the five `lib/*.a` archives `tb/base.7z` ships are
stamped `ELFDATA2LSB`, so a big-endian `elf32-i51` vector rejects them and `ld`
falls back to the generic ELF reader. The failure is **loud and immediate** —
"file in wrong format" at link time — never silent misinterpretation.

### `make check`, with the inputs re-stamped: 10 of 10 identical

The shipped inputs are stale, not wrong. Re-stamping them is the same mechanical
container flip in the other direction. A generalised version of the repo's own
`tb/i51elf_le2be.py` (`/tmp/r5/flip.py`, extended to archive members in
`/tmp/r5/fliplib.py`), validated first for byte-exactness against a natively
assembled big-endian object:

```
$ cp probe.o rt.o && python3 flip.py rt.o && cmp rt.o probe_be.o && echo MATCH
flipped container endianness of 1 ELF32 objects
MATCH: LE probe flipped == natively-assembled BE probe
```

Applied to the extracted testbench tree:

```
$ python3 /tmp/r5/flip.py lib cgi
flipped container endianness of 30 ELF32 objects
$ python3 /tmp/r5/fliplib.py libk80.a libw80.a libk23.a libw.a libw23.a
libk80.a: flipped 27 ELF members
libw80.a: flipped 37 ELF members
libk23.a: flipped 27 ELF members
libw.a:   flipped 37 ELF members
libw23.a: flipped 37 ELF members
```

then rebuild all ten projects with the big-endian toolchain:

```
$ sh /tmp/r5/rebuild.sh .../work/tb > be-results.md5
$ diff -u pinned.md5 be-results.md5 && echo IDENTICAL
IDENTICAL
```

**All ten ROMs byte-identical to the pinned `tb/reference.md5`.** So:

- `tb/reference.md5` does **not** change. Not one hash moves.
- The ten projects do **not** change. No source, no Makefile, no linker script.
- `tb/base.7z` **does** change — its 30 objects and 5 archives need the flip.
  Note this *restores* their original 2001 container endianness (B.3); it is
  undoing a conversion, not inventing one.

### The rest of the tool gate: unchanged

```
$ make roundtrip branch bits reloc defaultlink commons script BUILD=...
== table: 280 instructions
PASS
== table: 3 instructions
PASS
== table: 18 instructions
PASS
== branch: 24 cases
PASS
== bits: 50 cases
PASS
== reloc: 36 checks
PASS
run-defaultlink: PASS (default emulation links and lays out all spaces)
run-commons: PASS (commons and space directives keep their space, their name, and the real sections beside them)
run-script: PASS (every reachable *(...) arm of elf32i51.sc and lib/www51.sc placed its own input at its own address)
```

Every stage green, with no edit to any test.

### Total cost

| Item | Cost |
|---|---|
| `bfd/elf32-i51.c` | 2 lines |
| Every other source file | 0 |
| Howtos / relocation code | 0 |
| `tb/reference.md5` | 0 — proven identical |
| The ten projects | 0 |
| Tool gate stages | 0 — all pass unmodified |
| `tb/base.7z` | one mechanical re-stamp of 30 objects + 5 archives |
| `tb/base2001.7z` | 0 — already `ELFDATA2MSB` |
| Objects/archives users hold outside this repo | must be re-stamped, or they stop linking (loudly) |
| A supported re-stamp tool in `tb/` | new; `tb/i51elf_le2be.py` already does 80% of it |

## B.5 Cost of staying LE — measured

### The mis-decode reproduces

radare2 5.5.0, on the port's own object:

```
$ r2 -q -c "iI~arch,bits,endian,machine; pd 6 @ section..text" probe.o
arch     x86
bits     32
endian   little
machine  Intel 8051 and variants
  0x08000034      020000         add al, byte [eax]
  0x08000036      001200         add byte [edx], dl
  0x08000038      000000         add byte [eax], al
  0x0800003a      90             nop
  0x0800003b      123401         adc dh, byte [ecx + eax]
  0x0800003e      0080f3745a00   add byte [eax + 0x5a74f3], al
```

gdb 15.1:

```
$ gdb -batch -ex "info files" -ex "x/8i 0" probe.o
	`/tmp/r5/probe.o', file type elf32-little.
   0x0 <START>:	add    (%eax),%al
   0x2 <START+2>:	add    %dl,(%edx)
   0x4 <START+4>:	add    %al,(%eax)
   0x6 <START+6>:	nop
   0x7 <START+7>:	adc    (%ecx,%eax,1),%dh
```

Exactly the `02 01 12` → `add (%ecx),%al` family the brief describes.

### But it is not `EI_DATA`'s fault — proven two ways

**First**, radare2 already ships a correct 8051 disassembler, and it decodes this
port's little-endian-stamped output perfectly when told to use it:

```
$ r2 -q -a 8051 -c "pd 6 @ section..text" probe.o
  0x08000034      020000         ljmp 0x0000
  0x08000037      120000         lcall 0x0000
  0x0800003a      901234         mov dptr, #0x1234
  0x0800003d      0100           ajmp 0x0000
  0x0800003f      80f3           sjmp 0x0034
  0x08000041      745a           mov a, #0x5a
```

Every instruction correct, every big-endian 16-bit field read correctly, with
`EI_DATA` still `ELFDATA2LSB`. The disassembler knows the ISA's byte order
itself and does not consult `EI_DATA` for it — which is exactly right, and is
also why the wrong `EI_DATA` causes no instruction-level harm.

**Second**, flipping `EI_DATA` to `ELFDATA2MSB` fixes neither tool:

```
$ r2 -q -c "iI~arch,bits,endian,machine" probe_be.o
arch     x86
bits     32
endian   big
machine  Intel 8051 and variants

$ gdb -batch -ex "info files" -ex "x/4i 0" probe_be.o
	`/tmp/r5/probe_be.o', file type elf32-big.
   0x0 <START>:	add    (%eax),%al
   0x2 <START+2>:	add    %dl,(%edx)
   0x4 <START+4>:	add    %al,(%eax)
```

Both still say x86. Both still print `add (%eax),%al`. Only the reported endian
label changed.

The actual cause is that neither tool's **ELF loader** maps `e_machine = 165` to
its 8051 backend, so both fall back to a default architecture. r2 reads the
machine name correctly (`machine Intel 8051 and variants`) and *still* selects
x86. gdb, built for an x86 host, has no 8051 architecture compiled in at all:

```
$ gdb -batch -ex "set architecture"
Requires an argument. Valid arguments are i386, i386:x86-64, i386:x64-32,
i8086, i386:intel, i386:x86-64:intel, i386:x64-32:intel, auto.
```

So: **the consumer mis-decode is caused by the absence of an `EM_8051` → 8051-arch
mapping in those tools, not by `EI_DATA`.** Switching endianness buys exactly
nothing for radare2 or gdb. Fixing them means an upstream patch to their ELF
loaders (r2: an `EM_8051` case in its ELF arch mapping; gdb: an 8051 `gdbarch`,
which does not exist).

### What staying actually costs

| Item | Cost |
|---|---|
| radare2 / gdb decode | **nothing** — unaffected by the choice either way |
| Existing objects and archives | nothing — they keep working |
| `tb/` and the ten projects | nothing |
| gABI conformance | the header states an encoding that is false for every section byte |
| Internal consistency | gas says big-endian, BFD says little-endian; unique in the tree (B.2) |
| Lineage consistency | the 2001 original, the 2.38 sibling port and Ghidra are all big-endian; this port is the sole little-endian member |
| A generic consumer reading 16-bit section data by `EI_DATA` | reads it byte-reversed |
| Future cost of switching | grows monotonically with every object produced |

## B.6 Recommendation — B

**Switch to `TARGET_BIG_SYM`, in one commit that also re-stamps `tb/base.7z` and
adds a supported re-stamp tool.**

Reasoning:

1. **The declaration is factually wrong, and the gABI is explicit that it covers
   section contents** (B.1). Every byte of every section this port emits is
   MSB-first, including `.word` and `.long` data. This is not a stylistic
   preference between two defensible conventions; one of the two fields is
   lying about the other.

2. **The port already contradicts itself, uniquely in the tree.** `tc-i51.h`
   declares `TARGET_BYTES_BIG_ENDIAN 1` and hard-wires
   `md_number_to_chars = number_to_chars_bigendian`. i51 is the only target in
   binutils 2.47 with a big-endian gas and a little-endian-only BFD vector
   (B.2). Whichever way this is resolved, the two halves should agree — and the
   half that matches reality is the gas half.

3. **The status quo was never a decision.** The little-endian stamp was a side
   effect of `tb/i51elf_le2be.py`, which changed `EI_DATA` in the same pass as
   the `e_machine` fix and left the section bytes untouched (B.3). The
   `e_machine` half of that script was necessary and is settled; the `EI_DATA`
   half has no recorded justification and nothing depended on it. Switching
   *restores* the 2001 byte order rather than introducing a new one.

4. **The measured cost is two lines and no ROM.** `reference.md5` is unchanged,
   all ten projects produce byte-identical ROMs, and every tool-gate stage
   passes unmodified (B.4). The only real work is re-stamping the shipped
   binary inputs, which the repo is already 80% tooled for.

5. **The cost only grows.** The object corpus that would need re-stamping is
   today almost entirely inside this repository. That will not stay true if the
   port gets used.

6. **Do not switch expecting better tooling.** It buys no improvement in
   radare2 or gdb (B.5), and the report should say so plainly rather than let
   the change be sold on a benefit it does not deliver.

### If the owner declines to switch

Then **stay-and-document is the only acceptable alternative — not silent stasis.**
The current `include/elf/i51.h` comment is the place, and as written it
understates the problem:

```c
/* The machine number is the registered EM_8051 (165), defined in
   elf/common.h.  Objects are ELFDATA2LSB; the 16-bit fields inside
   instruction encodings (LJMP/LCALL addr16, MOV DPTR,#data16) are stored
   high byte first, as the instruction set defines them, and R_I51_L /
   R_I51_H address the two halves of a 16-bit value explicitly.  */
```

It says "the 16-bit fields inside instruction encodings", which reads as though
the exception is confined to instruction operands. B.2 shows it is not:
`.word`, `.long` and `.short` directive data are big-endian too, because
`md_number_to_chars` is `number_to_chars_bigendian` for everything. A
stay-and-document outcome must (a) correct that comment to say **all** section
contents are big-endian, (b) record that this knowingly departs from the gABI's
`EI_DATA` definition and why, and (c) note the `TARGET_BYTES_BIG_ENDIAN 1`
contradiction in `tc-i51.h` so the next reader does not rediscover it as a bug.

What must **not** happen is treating "radare2 and gdb show x86" as the argument
for either choice. That symptom is independent of `EI_DATA` and is fixed only in
those tools (B.5).

"""Directed tests: bit addressing at its boundaries.

The MCS-51 bit space is 256 bit addresses folded out of two disjoint byte
ranges, and nothing else in the machine is bit addressable:

  bits 0x00..0x7F   RAM 0x20..0x2F, bit b of byte a is (a - 0x20) * 8 + b
  bits 0x80..0xFF   an SFR whose address is a multiple of 8, bit b of
                    byte a is a + b
  anything else     not bit addressable, and must be refused

The port reaches that fold from three directions, and each has its own copy
of the rule: the `.3' suffix on a numeric operand (i51_fold_bit_suffix),
the B2B(byte,bit) operator on a constant (fixup8) and on a symbol resolved
at assembly time (md_apply_fix), and R_I51_8_B2B applied by the linker
(bfd/elf32-i51.c).  All four must agree, including about what is rejected -
so the cases below sit exactly on 0x20, 0x2F, 0x30, 0x80, 0xF8 and on the
first bit past the top of the RAM window.

ASM_CASES  assembled on their own.  `want' is the expected instruction
           encoding in hex; want=None means the assembler has to reject the
           line, and `msg' is a fragment its complaint must contain.
LINK_CASES `src' assembled, then linked with BDVAR defined at `addr'.
           `want' is the byte the relocation must leave at .text+1;
           want=None means the link has to report `msg'.
DIR_CASES  the `.bit' directive, assembled alone.  `section' names the
           section whose bytes `want' is compared with, because the
           directive emits into the memory space it was given and not
           into .text.
"""


def acase(name, src, want, msg=None):
    return {'name': name, 'src': src, 'want': want, 'msg': msg}


NOTBIT = 'not bit addressable'
NOTRANGE = 'out of bit range'

ASM_CASES = [
    # ---- `.b' suffix on a numeric byte address -----------------------
    acase('dot-ram-first',   'mov c,0x20.0',   'a2 00'),
    acase('dot-ram-first-7', 'mov c,0x20.7',   'a2 07'),
    acase('dot-ram-last',    'mov c,0x2f.7',   'a2 7f'),
    acase('dot-ram-last-0',  'mov c,0x2f.0',   'a2 78'),
    acase('dot-ram-mid',     'setb 0x21.3',    'd2 0b'),
    acase('dot-below-ram',   'mov c,0x1f.7',   None, NOTBIT),
    acase('dot-above-ram',   'mov c,0x30.0',   None, NOTBIT),
    acase('dot-gap',         'mov c,0x7f.0',   None, NOTBIT),
    acase('dot-sfr-first',   'mov c,0x80.0',   'a2 80'),
    acase('dot-sfr-first-7', 'mov c,0x80.7',   'a2 87'),
    acase('dot-sfr-last',    'mov c,0xf8.7',   'a2 ff'),
    acase('dot-sfr-mid',     'setb 0x88.1',    'd2 89'),
    acase('dot-sfr-unalign', 'mov c,0x81.0',   None, NOTBIT),
    acase('dot-sfr-unalign2', 'mov c,0xf9.0',  None, NOTBIT),
    acase('dot-sfr-past',    'mov c,0xff.7',   None, NOTBIT),

    # ---- B2B(byte,bit) on a constant --------------------------------
    acase('b2b-ram-first',   'setb B2B(0x20,0)', 'd2 00'),
    acase('b2b-ram-last',    'setb B2B(0x2f,7)', 'd2 7f'),
    acase('b2b-below-ram',   'setb B2B(0x1f,0)', None, NOTRANGE),
    acase('b2b-above-ram',   'setb B2B(0x30,0)', None, NOTRANGE),
    acase('b2b-gap',         'setb B2B(0x7f,0)', None, NOTRANGE),
    acase('b2b-sfr-first',   'setb B2B(0x80,0)', 'd2 80'),
    acase('b2b-sfr-mid',     'setb B2B(0x88,1)', 'd2 89'),
    acase('b2b-sfr-last',    'setb B2B(0xf8,7)', 'd2 ff'),
    acase('b2b-past-ram-top', 'setb B2B(0x2f,9)', None, NOTRANGE),

    # ---- B2B on a symbol already known: the constant path of fixup8 --
    acase('b2b-sym-ram',     'BD = 0x20\n\tsetb B2B(BD,1)',  'd2 01'),
    acase('b2b-sym-ram-top', 'BD = 0x2f\n\tsetb B2B(BD,7)',  'd2 7f'),
    acase('b2b-sym-sfr',     'BD = 0x88\n\tsetb B2B(BD,1)',  'd2 89'),
    acase('b2b-sym-bad',     'BD = 0x40\n\tsetb B2B(BD,0)',  None, NOTRANGE),

    # ---- B2B on a symbol defined later: the fold in md_apply_fix -----
    acase('b2b-fwd-ram',     'setb B2B(BD,1)\nBD = 0x20',     'd2 01'),
    acase('b2b-fwd-ram-top', 'setb B2B(BD,7)\nBD = 0x2f',     'd2 7f'),
    acase('b2b-fwd-sfr',     'setb B2B(BD,1)\nBD = 0x88',     'd2 89'),
    acase('b2b-fwd-sfr-last', 'setb B2B(BD,7)\nBD = 0xf8',    'd2 ff'),
    acase('b2b-fwd-below',   'setb B2B(BD,0)\nBD = 0x1f',     None, NOTBIT),
    acase('b2b-fwd-gap',     'setb B2B(BD,0)\nBD = 0x40',     None, NOTBIT),
    acase('b2b-fwd-past-top', 'setb B2B(BD,9)\nBD = 0x2f',    None, NOTRANGE),
]


def lcase(name, addr, off, want, msg=None):
    return {'name': name, 'addr': addr, 'off': off, 'want': want, 'msg': msg}


# `setb B2B(BDVAR,off)' against an undefined BDVAR, so the fold is the
# linker's R_I51_8_B2B rather than anything gas did.
LINK_CASES = [
    lcase('link-ram-first',  0x20, 0, 0x00),
    lcase('link-ram-last',   0x2f, 7, 0x7f),
    lcase('link-ram-mid',    0x21, 3, 0x0b),
    lcase('link-sfr-first',  0x80, 0, 0x80),
    lcase('link-sfr-mid',    0x88, 1, 0x89),
    lcase('link-sfr-last',   0xf8, 7, 0xff),
    lcase('link-below-ram',  0x10, 0, None, 'out of range'),
    lcase('link-above-ram',  0x30, 0, None, 'out of range'),
    lcase('link-gap',        0x7f, 0, None, 'out of range'),
    lcase('link-past-ram-top', 0x2f, 9, None, 'relocation truncated'),
    # Above the SFR space there is no byte address left to fold, so this is
    # refused like every other non-bit-addressable byte.  It used to be the
    # one arm with no diagnostic at all: R_I51_8_B2B returned bfd_reloc_ok
    # for srel >= 0x100 and left the byte alone, which contradicted the rule
    # at the top of this file.  claude/review-newcode changed that return to
    # bfd_reloc_outofrange; this case was pinning the behaviour it fixed.
    lcase('link-offchip',    0x100, 1, None, 'out of range'),
]

# The .bit directive takes one bit, says so when it is handed anything
# else, and emits one byte holding it into whatever section is current.
# That byte lands in the bit space, so every case names the section its
# `want' is measured against: compared against .text instead, a bit that
# was never emitted and a bit emitted wrong both read as no bytes at all,
# and the case passes whatever the assembler did.
def dcase(name, src, want, msg=None, section='.text'):
    return {'name': name, 'src': src, 'want': want, 'msg': msg,
            'section': section}


DIR_CASES = [
    dcase('bit-0',    '.bitdata\nBIT0:\t.bit 0', '00', section='.bitdata'),
    dcase('bit-1',    '.bitdata\nBIT1:\t.bit 1', '01', section='.bitdata'),
    dcase('bit-2',    '.bitdata\nBIT2:\t.bit 2', None, 'not in range 0..1',
          section='.bitdata'),
    dcase('bit-neg',  '.bitdata\nBITN:\t.bit -1', None, 'not in range 0..1',
          section='.bitdata'),
]

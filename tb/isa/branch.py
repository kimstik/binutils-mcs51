"""Directed tests: branch instructions with numeric (literal) targets.

The instruction table and testall.asm reach branches only through symbolic
labels.  These cases pin down the literal-address path instead: a numeric
operand of sjmp/jc/jz/djnz/cjne is an absolute address whose encoded
displacement is target minus the address of the next instruction, limited
to +127..-128; ajmp/acall encode A10..A0 of the target and require
A15..A11 to match those of the address after the instruction (the 2K page
of PC+2), everything else is an assembly error.

Each case assembles `src` at .text offset `skip` (the runner emits that
many zero padding bytes first; default 0).  `want` holds the expected
instruction bytes as hex; want=None marks a source the assembler must
reject (nonzero exit).
"""

def case(name, src, want, skip=0):
    return {'name': name, 'src': src, 'want': want, 'skip': skip}

CASES = [
    # relative branches: displacement = target - (addr + size)
    case('sjmp-fwd',        'sjmp 0x0006',            '80 04'),
    case('sjmp-self-next',  'sjmp 0x0002',            '80 00'),
    case('sjmp-fwd-max',    'sjmp 0x0081',            '80 7f'),
    case('sjmp-back',       'sjmp 0x0000',            '80 fa', skip=4),
    case('sjmp-back-min',   'sjmp 0x0082',            '80 80', skip=0x100),
    case('jc-fwd',          'jc 0x0006',              '40 04'),
    case('jz-fwd',          'jz 0x0006',              '60 04'),
    case('djnz-rn-fwd',     'djnz r2,0x0006',         'da 04'),
    case('djnz-dir-fwd',    'djnz 0x30,0x0006',       'd5 30 03'),
    case('cjne-a-imm-fwd',  'cjne a,#0x55,0x0006',    'b4 55 03'),
    case('cjne-rn-imm-fwd', 'cjne r7,#0x55,0x0006',   'bf 55 03'),

    # displacement out of range: one past each limit
    case('sjmp-plus128',    'sjmp 0x0082',            None),
    case('sjmp-minus129',   'sjmp 0x0081',            None, skip=0x100),

    # ajmp/acall: 11-bit target inside the 2K page of PC+2
    case('ajmp-page0',      'ajmp 0x0006',            '01 06'),
    case('acall-page0',     'acall 0x0006',           '11 06'),
    case('ajmp-a10a8',      'ajmp 0x0345',            '61 45'),
    case('acall-a10a8',     'acall 0x0345',           '71 45'),

    # at 0x07fe the instruction ends at 0x0800: its page is 0x800-0xfff,
    # so 0x0802 is reachable and anything below 0x0800 is not
    case('ajmp-cross-ok',   'ajmp 0x0802',            '01 02', skip=0x7fe),
    case('acall-cross-ok',  'acall 0x0802',           '11 02', skip=0x7fe),
    case('ajmp-back-cross', 'ajmp 0x07fd',            None,    skip=0x7fe),

    # target beyond the page of PC+2
    case('ajmp-next-page',  'ajmp 0x0800',            None),
    case('acall-next-page', 'acall 0x0800',           None),

    # 16-bit targets carry no page constraint
    case('ljmp-abs16',      'ljmp 0x1234',            '02 12 34'),
    case('lcall-abs16',     'lcall 0x0006',           '12 00 06'),
]

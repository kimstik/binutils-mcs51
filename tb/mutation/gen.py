#!/usr/bin/env python3
"""Generate single-fault mutants of the port's own source, mechanically.

Nothing here is a hand-written list of bugs.  A small set of mutation
operators is applied to every place in the port sources where the operator
matches; each match becomes one mutant.  Sources are the files the port
adds to binutils - mcs51/additions.patch - as they sit in a built tree.

Operators (each is one class of single fault a porter really makes):

  relop     relational operator swapped for its adjacent-strictness twin
            (< <-> <=, > <-> >=): an off-by-one in a range check.
  constpm1  an integer literal incremented: off-by-one field mask, wrong
            bound, wrong shift.
  guard0    the condition of a check that reports an error forced to 0:
            the range check is dropped entirely.
  cond0     any single-line `if' condition forced to 0 (disassembler:
            e.g. the MOV direct,direct operand swap disappears).
  retstatus a `return bfd_reloc_overflow/outofrange' turned into
            `return bfd_reloc_ok': the overflow is detected and ignored.
  endian    bfd_putb16/getb16, number_to_chars_bigendian swapped for the
            little-endian spelling.
  oporder   two adjacent statements that differ only in an operand index
            swapped: operands emitted in the wrong order.
  boolarg   the pc-relative flag of a fix_new_exp call flipped.
  howto     one field of one HOWTO entry perturbed (size, bitsize,
            rightshift, dst_mask, pc_relative, overflow complaint).
  opctab    one I51_INS row perturbed: opcode byte, match mask, or size.
  ldnum     an integer literal in the default linker script incremented.

Scope: only the listed functions of each C file, plus the HOWTO table, the
opcode table and the linker script.  Mutating binutils' own generic code
would test binutils, not the port.

How many: every match of every operator, capped per (file, operator) and
sampled evenly across the matches, so the population is deterministic and a
before/after comparison is on exactly the same mutants.

  gen.py --tree WORK/modern/binutils-2.47 [--cap 12] [--out mutants.json]
"""

import argparse
import json
import os
import re
import sys

# file key -> path inside the binutils tree
FILES = {
    'gas':  'gas/config/tc-i51.c',
    'bfd':  'bfd/elf32-i51.c',
    'dis':  'opcodes/i51-dis.c',
    'opc':  'include/opcode/i51.h',
    'ldsc': 'ld/scripttempl/elf32i51.sc',
}

# Functions worth mutating: the ones that encode, relocate or decode.
SCOPES = {
    'gas': ['md_apply_fix', 'fixup8', 'fixup11', 'fixup16', 'check_range',
            'i51_fold_bit_suffix', 'i51_build_ins', 'md_pcrel_from_section',
            'tc_gen_reloc', 'i51_bit', 'md_undefined_symbol'],
    'bfd': ['i51_final_link_relocate', 'elf32_i51_relocate_section',
            'i51_info_to_howto_rela', 'elf32_i51_section_from_bfd_section',
            'elf32_i51_add_symbol_hook', 'bfd_elf32_bfd_reloc_type_lookup'],
    'dis': ['print_insn_i51', 'i51dis_op16', 'i51dis_opcode'],
}


def read(path):
    with open(path, encoding='latin-1') as f:
        return f.read().splitlines()


def functions(lines):
    """(name, first, last) for each top-level function, 0-based inclusive."""
    out = []
    i = 0
    while i < len(lines):
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*\(', lines[i])
        if m:
            j = i
            while j < len(lines) and not lines[j].startswith('{'):
                if j > i + 12:
                    break
                j += 1
            if j < len(lines) and lines[j].startswith('{'):
                depth = 0
                k = j
                while k < len(lines):
                    depth += lines[k].count('{') - lines[k].count('}')
                    if depth == 0:
                        break
                    k += 1
                out.append((m.group(1), i, k))
                i = k
        i += 1
    return out


def scoped_lines(key, lines):
    """Indices of the lines this file exposes to the line operators."""
    names = SCOPES.get(key)
    if names is None:
        return list(range(len(lines)))
    idx = []
    for name, first, last in functions(lines):
        if name in names:
            idx.extend(range(first, last + 1))
    return sorted(set(idx))


# --------------------------------------------------------------- operators

def op_relop(lines, idx):
    swap = {'<': '<=', '<=': '<', '>': '>=', '>=': '>'}
    for i in idx:
        s = lines[i]
        if not re.search(r'0x[0-9A-Fa-f]|[^\w.]\d', s):
            continue
        for m in re.finditer(r'(?<![<>=!-])(<=|>=|<|>)(?![<>=])', s):
            yield (i, s[:m.start()] + swap[m.group(1)] + s[m.end():],
                   '%s -> %s' % (m.group(1), swap[m.group(1)]))


def op_constpm1(lines, idx):
    for i in idx:
        s = lines[i]
        if s.lstrip().startswith(('/*', '*', '//', '#')):
            continue
        for m in re.finditer(r'\b(0[xX][0-9A-Fa-f]+|[0-9]+)\b', s):
            tok = m.group(1)
            if tok.lower().startswith('0x'):
                new = '0x%0*X' % (len(tok) - 2, int(tok, 16) + 1)
            else:
                if int(tok) < 2:
                    continue
                new = str(int(tok) + 1)
            yield (i, s[:m.start()] + new + s[m.end():], '%s -> %s' % (tok, new))


ERRMARK = ('as_bad', 'as_fatal', 'bfd_reloc_overflow', 'bfd_reloc_outofrange',
           'bfd_set_error')


def op_guard0(lines, idx):
    inset = set(idx)
    for i in idx:
        s = lines[i]
        m = re.search(r'\bif\s*\(', s)
        if not m:
            continue
        # balanced-paren scan across lines for the condition
        depth = 0
        j, pos = i, m.end() - 1
        cond, end = [], None
        while j < len(lines) and j <= i + 6:
            row = lines[j]
            start = pos if j == i else 0
            for c in range(start, len(row)):
                if row[c] == '(':
                    depth += 1
                elif row[c] == ')':
                    depth -= 1
                    if depth == 0:
                        end = (j, c)
                        break
            if end:
                break
            cond.append(row[start:])
            j += 1
        if not end or end[0] != i:
            continue                        # single-line conditions only
        body = ' '.join(lines[i:min(i + 5, len(lines))])
        if not any(k in body for k in ERRMARK):
            continue
        if i not in inset:
            continue
        new = s[:m.end()] + '0' + s[end[1]:]
        yield (i, new, 'guard forced to 0')


def op_cond0(lines, idx):
    """Any single-line `if' condition forced to 0.  Used where guard0 does
    not apply because the branch reports nothing - the disassembler just
    formats differently, e.g. the MOV direct,direct operand swap."""
    for i in idx:
        s = lines[i]
        m = re.search(r'\bif\s*\(', s)
        if not m:
            continue
        depth, end = 0, None
        for c in range(m.end() - 1, len(s)):
            if s[c] == '(':
                depth += 1
            elif s[c] == ')':
                depth -= 1
                if depth == 0:
                    end = c
                    break
        if end is None or s[m.end() - 1:end + 1] == '(0)':
            continue
        yield (i, s[:m.end()] + '0' + s[end:], 'condition forced to 0')


def op_retstatus(lines, idx):
    for i in idx:
        s = lines[i]
        for what in ('bfd_reloc_overflow', 'bfd_reloc_outofrange'):
            if 'return ' + what in s:
                yield (i, s.replace('return ' + what, 'return bfd_reloc_ok'),
                       '%s -> ok' % what)


ENDIAN = [('bfd_putb16', 'bfd_putl16'), ('bfd_getb16', 'bfd_getl16'),
          ('number_to_chars_bigendian', 'number_to_chars_littleendian')]


def op_endian(lines, idx):
    for i in idx:
        s = lines[i]
        for a, b in ENDIAN:
            if a in s:
                yield (i, s.replace(a, b, 1), '%s -> %s' % (a, b))


def op_oporder(lines, idx):
    inset = set(idx)
    for i in idx:
        if i + 1 not in inset:
            continue
        a, b = lines[i].strip(), lines[i + 1].strip()
        if not a or not b or a == b:
            continue
        # differ only where a digit differs, and both are calls
        if '(' not in a or len(a) != len(b):
            continue
        diff = [k for k in range(len(a)) if a[k] != b[k]]
        if not diff or len(diff) > 2:
            continue
        if not all(a[k].isdigit() and b[k].isdigit() for k in diff):
            continue
        ind_a = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
        ind_b = lines[i + 1][:len(lines[i + 1]) - len(lines[i + 1].lstrip())]
        yield (i, [ind_a + b, ind_b + a], 'adjacent operand statements swapped')


def op_boolarg(lines, idx):
    for i in idx:
        s = lines[i]
        for m in re.finditer(r'(?<![\w>])(true|false)(?=\s*,)', s):
            if 'oper' not in s and 'exp' not in s:
                continue
            new = 'false' if m.group(1) == 'true' else 'true'
            yield (i, s[:m.start()] + new + s[m.end():],
                   'fix_new_exp pcrel %s -> %s' % (m.group(1), new))


HOWTO_FIELDS = [
    (r'^(\s*)(\d+),(\s*/\* size)', 'size', lambda v: str(int(v) + 1)),
    (r'^(\s*)(\d+),(\s*/\* bitsize)', 'bitsize', lambda v: str(int(v) + 1)),
    (r'^(\s*)(\d+),(\s*/\* rightshift)', 'rightshift',
     lambda v: '1' if v == '0' else '0'),
    (r'^(\s*)(0x[0-9a-fA-F]+),(\s*/\* dst_mask)', 'dst_mask',
     lambda v: '0x%0*X' % (len(v) - 2, (int(v, 16) >> 1))),
    (r'^(\s*)(true|false),(\s*/\* pc_relative)', 'pc_relative',
     lambda v: 'false' if v == 'true' else 'true'),
    (r'^(\s*)(complain_overflow_\w+),(\s*/\* complain_on_overflow)',
     'complain', lambda v: ('complain_overflow_dont' if v != 'complain_overflow_dont'
                            else 'complain_overflow_bitfield')),
]


def op_howto(lines, _idx):
    cur = None
    for i, s in enumerate(lines):
        m = re.match(r'\s*HOWTO \((R_I51_\w+),', s)
        if m:
            cur = m.group(1)
            continue
        if cur is None:
            continue
        for pat, field, fn in HOWTO_FIELDS:
            m = re.match(pat, s)
            if m:
                new = fn(m.group(2))
                if new == m.group(2):
                    continue
                yield (i, s[:m.start(2)] + new + s[m.end(2):],
                       '%s %s %s -> %s' % (cur, field, m.group(2), new))


INS = re.compile(r'^I51_INS \("([^"]+)",\s*"([^"]*)",\s*(0x[0-9A-Fa-f]+),'
                 r'\s*"([^"]*)",\s*\'(.)\',\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+)\)')


def op_opctab(lines, _idx):
    for i, s in enumerate(lines):
        m = INS.match(s)
        if not m:
            continue
        name, bins, mask = m.group(1), m.group(6), m.group(7)
        nb = '0x%02X' % (int(bins, 16) ^ 0x01)
        yield (i, s[:m.start(6)] + nb + s[m.end(6):],
               '%s opcode %s -> %s' % (name, bins, nb))
        nm = '0x%02X' % (int(mask, 16) ^ 0x01)
        yield (i, s[:m.start(7)] + nm + s[m.end(7):],
               '%s mask %s -> %s' % (name, mask, nm))
        sz = m.group(3)
        ns = '0x%02X' % (int(sz, 16) ^ 0x01)
        yield (i, s[:m.start(3)] + ns + s[m.end(3):],
               '%s size %s -> %s' % (name, sz, ns))


def op_ldnum(lines, _idx):
    body = False
    for i, s in enumerate(lines):
        if s.startswith('MEMORY') or s.startswith('SECTIONS'):
            body = True
        if not body or s.lstrip().startswith(('/*', '*', '#')):
            continue
        for m in re.finditer(r'\b(0[xX][0-9A-Fa-f]+|[0-9]+)\b', s):
            tok = m.group(1)
            if tok.lower().startswith('0x'):
                new = '0x%0*X' % (len(tok) - 2, int(tok, 16) + 1)
            elif int(tok) >= 2:
                new = str(int(tok) + 1)
            else:
                continue
            yield (i, s[:m.start()] + new + s[m.end():], '%s -> %s' % (tok, new))


OPERATORS = [
    ('relop',     op_relop,     ('gas', 'bfd', 'dis')),
    ('constpm1',  op_constpm1,  ('gas', 'bfd', 'dis')),
    ('guard0',    op_guard0,    ('gas', 'bfd')),
    ('cond0',     op_cond0,     ('dis',)),
    ('retstatus', op_retstatus, ('bfd',)),
    ('endian',    op_endian,    ('gas', 'bfd', 'dis')),
    ('oporder',   op_oporder,   ('gas', 'dis')),
    ('boolarg',   op_boolarg,   ('gas',)),
    ('howto',     op_howto,     ('bfd',)),
    ('opctab',    op_opctab,    ('opc',)),
    ('ldnum',     op_ldnum,     ('ldsc',)),
]


# Operators whose match set is large and uniform get a bigger share: the
# opcode table has 111 rows and the howto table 12 entries with six mutable
# fields each, and sampling those at the same rate as a handful of range
# checks would leave most of both untouched.
CAPS = {'howto': 30, 'opctab': 24}


def spread(items, cap):
    """At most CAP items, evenly spaced, order preserved.  Deterministic."""
    if cap <= 0 or len(items) <= cap:
        return items
    n = len(items)
    return [items[(k * n) // cap] for k in range(cap)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True, help='patched binutils source tree')
    ap.add_argument('--cap', type=int, default=8,
                    help='max mutants per operator per file (evenly spaced)')
    ap.add_argument('--out', default='-')
    ap.add_argument('--only', help='comma separated operator names')
    args = ap.parse_args()

    only = set(args.only.split(',')) if args.only else None
    mutants = []
    for key, rel in FILES.items():
        path = os.path.join(args.tree, rel)
        if not os.path.exists(path):
            sys.exit('missing %s' % path)
        lines = read(path)
        idx = scoped_lines(key, lines)
        for name, fn, keys in OPERATORS:
            if key not in keys or (only and name not in only):
                continue
            found = list(fn(lines, idx))
            for line, new, note in spread(found, CAPS.get(name, args.cap)):
                old = lines[line]
                rep = new if isinstance(new, list) else [new]
                orig = lines[line:line + len(rep)]
                if orig == rep:
                    continue
                mutants.append({
                    'id': '%s-%s-%d' % (key, name, line + 1),
                    'file': rel,
                    'op': name,
                    'line': line + 1,
                    'old': orig,
                    'new': rep,
                    'note': note,
                    'context': old.strip()[:90],
                })

    seen, uniq = set(), []
    for m in mutants:
        if m['id'] in seen:
            continue
        seen.add(m['id'])
        uniq.append(m)

    text = json.dumps(uniq, indent=1)
    if args.out == '-':
        print(text)
    else:
        with open(args.out, 'w') as f:
            f.write(text + '\n')
        print('%d mutants -> %s' % (len(uniq), args.out), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())

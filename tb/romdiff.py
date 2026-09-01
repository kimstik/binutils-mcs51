#!/usr/bin/env python3
"""Compare produced www8051.rom files against the reference copies, as markdown.

Reports per project: both sizes, both md5, how many bytes differ and where. When
two ROMs are the same length, it also tabulates every (reference byte -> produced
byte) pair seen at a differing offset. A small set of pairs that is consistent
across the whole ROM says the code is the same and only operand values moved -
which is what an internal-RAM address assigned differently looks like. Bytes that
map to more than one value are counted separately, since one byte value can serve
as both an address operand and an immediate.
"""

import argparse
import collections
import hashlib
import os
import sys


def md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def load(path):
    with open(path, 'rb') as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reference', required=True, help='tree holding the reference projekt/')
    ap.add_argument('--produced', required=True, help='tree holding the produced projekt/')
    ap.add_argument('--projects', required=True, help='space separated project names')
    ap.add_argument('--window', type=int, default=96, help='bytes of hexdump around a divergence')
    ap.add_argument('--expect', help='file recording the expected outcome per project; '
                                     'deviating from it makes this exit nonzero')
    args = ap.parse_args()

    projects = args.projects.split()
    rows = []
    detail = []
    outcome = {}
    same = differ = missing = 0

    for p in projects:
        r = os.path.join(args.reference, 'projekt', p, 'www8051.rom')
        g = os.path.join(args.produced, 'projekt', p, 'www8051.rom')
        if not os.path.exists(r):
            rows.append((p, '-', 'no reference', '', ''))
            outcome[p] = ('no-reference', 0, 0)
            missing += 1
            continue
        rb = load(r)
        if not os.path.exists(g):
            rows.append((p, '%d B' % len(rb), 'not produced', '', ''))
            outcome[p] = ('not-produced', 0, 0)
            missing += 1
            continue
        gb = load(g)
        if rb == gb:
            rows.append((p, '%d B' % len(rb), 'identical', '0', md5(r)))
            outcome[p] = ('identical', 0, len(gb))
            same += 1
            continue
        differ += 1
        n = min(len(rb), len(gb))
        offs = [i for i in range(n) if rb[i] != gb[i]]
        first = hex(offs[0]) if offs else 'length only'
        ndiff = len(offs) + abs(len(rb) - len(gb))
        outcome[p] = ('differ', ndiff, len(gb))
        rows.append((p, '%d B' % len(rb), '%d B' % len(gb),
                     '%d, from %s' % (ndiff, first),
                     '%s vs %s' % (md5(r), md5(g))))

        pairs = collections.defaultdict(collections.Counter)
        for i in offs:
            pairs[rb[i]][gb[i]] += 1
        stable = {k: v.most_common(1)[0][0] for k, v in pairs.items() if len(v) == 1}
        wobbly = sorted(k for k, v in pairs.items() if len(v) > 1)
        detail.append('\n### %s\n' % p)
        detail.append('%d differing offsets, %d distinct reference byte values, '
                      '%d of them map to a single produced value.\n'
                      % (len(offs), len(pairs), len(stable)))
        detail.append('\n```\n')
        detail.append('stable byte map (reference -> produced):\n')
        line = []
        for k in sorted(stable):
            line.append('%02x->%02x' % (k, stable[k]))
            if len(line) == 12:
                detail.append('  ' + ' '.join(line) + '\n')
                line = []
        if line:
            detail.append('  ' + ' '.join(line) + '\n')
        if wobbly:
            detail.append('ambiguous reference bytes: %s\n'
                          % ' '.join('%02x' % k for k in wobbly))
        # Nothing differs inside the shared prefix when one ROM is a truncation of the
        # other, so the window is taken at the point where the shorter one stops.
        start = max(0, ((offs[0] if offs else n) // 16) * 16 - 32)
        detail.append('\nreference %#x..%#x:\n' % (start, start + args.window))
        detail.append(hexdump(rb, start, args.window))
        detail.append('produced:\n')
        detail.append(hexdump(gb, start, args.window))
        detail.append('```\n')

    print('## frozen ROMs vs the reference ROMs shipped in base.7z\n')
    print('| project | reference | produced | differing bytes | md5 |')
    print('|---------|-----------|----------|-----------------|-----|')
    for row in rows:
        print('| %s | %s | %s | %s | %s |' % row)
    print('\nidentical %d, different %d, missing %d\n' % (same, differ, missing))
    sys.stdout.write(''.join(detail))

    if not args.expect:
        return 0
    return gate(outcome, args.expect)


def gate(outcome, path):
    """Compare each project's outcome against the recorded one.

    The 2001 toolchain does not reproduce the reference ROMs and is not expected
    to; what must not change silently is *how far* it is from them. Every project
    has one recorded line here, and any movement - a project that stops linking,
    one that starts, a differing-byte count that shifts, a ROM that changes
    length - is a failure that has to be explained and then re-recorded.

    Three columns are required per project: outcome, differing bytes, and the
    size of the ROM the frozen toolchain produced. The size column is what makes
    a stale expectation impossible to sit on: when *(reset_network) was restored
    in lib/www51.sc every ROM on both sides grew, and a file that recorded only
    the differing-byte count went on passing because that count did not move. A
    line with fewer than three columns is rejected rather than defaulted, so an
    old two-column file fails loudly instead of gating on half of itself.
    """
    expect = {}
    with open(path) as fh:
        for n, line in enumerate(fh, 1):
            line = line.split('#', 1)[0].split()
            if not line:
                continue
            if len(line) < 4:
                print('FAIL %s:%d: %r gives %d column(s) after the project '
                      'name, 3 required (outcome, differing bytes, ROM size) - '
                      'this expectation file predates the size column and '
                      'cannot be trusted'
                      % (path, n, ' '.join(line), len(line) - 1))
                return 1
            expect[line[0]] = (line[1], int(line[2]), int(line[3]))

    print('\n## outcome against %s\n' % path)
    print('```')
    bad = 0
    for p in sorted(set(outcome) | set(expect)):
        got = outcome.get(p)
        want = expect.get(p)
        if want is None:
            print('FAIL %-8s %s, nothing recorded' % (p, got))
            bad += 1
        elif got is None:
            print('FAIL %-8s not compared, recorded %s' % (p, want))
            bad += 1
        elif got != want:
            print('FAIL %-8s %s %d bytes differ, %d B ROM; recorded %s %d %d'
                  % (p, got[0], got[1], got[2], want[0], want[1], want[2]))
            bad += 1
        else:
            print('PASS %-8s %s %d %d' % (p, got[0], got[1], got[2]))
    print('```')
    if bad:
        print('\n**%d project(s) moved away from the recorded frozen outcome.**' % bad)
        return 1
    print('\nall %d projects match the recorded frozen outcome.' % len(expect))
    return 0


def hexdump(buf, start, count):
    out = []
    for i in range(start, min(start + count, len(buf)), 16):
        chunk = buf[i:i + 16]
        text = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
        out.append('%08x  %-47s  |%s|\n'
                   % (i, ' '.join('%02x' % c for c in chunk), text))
    return ''.join(out)


if __name__ == '__main__':
    sys.exit(main())

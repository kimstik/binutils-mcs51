#!/usr/bin/env python3
"""Reduce a full-matrix mutation run to per-stage coverage.

Input is the results.json of `run.py --all-stages', where every stage was
run against every mutant and each verdict recorded separately.  A
fail-first file is refused: in that mode a stage only ever gets to see the
mutants every earlier stage missed, so its kill count is a fact about its
position in the list.

  coverage.py --results coverage.json > COVERAGE.md

What comes out, and what each number does and does not mean:

  kills       mutants this stage caught, counted independently of every
              other stage.  This is the number the fail-first runs could
              not produce.
  unique      mutants this stage caught that NO other stage in the list
              caught.  Zero unique kills means nothing else in the list
              needed this stage to catch anything IN THIS POPULATION - it
              does not mean the stage asserts nothing (see the caveats the
              report prints).
  fail-first  what a fail-first run would have recorded for this stage: the
              mutants where it is the first red in list order.  Printed
              beside `kills' because the gap between the two columns is the
              whole reason this mode exists.
  1-stage     mutants caught by exactly one stage.  Those are the thin
              spots: one stage is all that stands between the port and that
              defect, whatever that stage's totals look like.
  pairs       every pair of stages that both caught something, with the
              size of each kill set's difference from the other.  A pair
              with an empty difference in one direction is where duplication
              actually lives.  Pairs against a stage that caught nothing are
              left out: an empty set sits inside every other set, and
              printing that as containment would read as duplication.
  wall clock  seconds each stage spent, across the run and on the clean
              tree, so a cost per unique kill can be stated rather than
              guessed.
"""

import argparse
import collections
import itertools
import json
import sys


def load(path):
    with open(path) as f:
        d = json.load(f)
    if not d.get('all_stages'):
        sys.exit(
            '%s is not a full-matrix run.\n'
            '\n'
            'Its per-mutant stage verdicts stop at the first red, so every\n'
            'stage but the first is recorded catching only what the stages\n'
            'before it missed.  Reducing that as coverage would report each\n'
            "stage's position in the list and call it reach - which is the\n"
            'reading this report exists to replace.  Produce a full matrix:\n'
            '\n'
            '    make -C tb mutants-coverage\n'
            '    ... or  mutation/run.py --all-stages ...\n' % path)
    return d


def table(head, rows, right=()):
    """A markdown table with every column padded to a common width."""
    body = [[str(c) for c in r] for r in rows]
    head = [str(h) for h in head]
    w = [len(h) for h in head]
    for r in body:
        for i, c in enumerate(r):
            w[i] = max(w[i], len(c))

    def line(cells):
        return '| ' + ' | '.join(
            c.rjust(w[i]) if i in right else c.ljust(w[i])
            for i, c in enumerate(cells)) + ' |'

    sep = '|' + '|'.join(('-' * (w[i] + 1) + ':') if i in right
                         else (':' + '-' * (w[i] + 1))
                         for i in range(len(head))) + '|'
    return '\n'.join([line(head), sep] + [line(r) for r in body])


def per(n, d, fmt='%.0f'):
    return fmt % (n / d) if d else '-'


HEADER = """\
# stage coverage of the mutation population

**This report measures; it does not recommend.**  Nothing below says a
stage should be removed, merged or kept.  It says what each stage caught in
one run, against one mutant population, and where two stages caught the
same things.  Deciding what to do about that is a separate job with a
separate burden of proof, and the reader who is about to skip to the zero
in the `unique' column should read the caveats at the foot first.

Three reasons a stage can read zero unique kills and still be the only
thing holding a defect out:

  * The mutation operators only express faults that fit a single-line edit
    of the port's own C source and tables.  A stage guarding anything else
    has no mutant to catch.  `script' exists because `*(reset_network)' sat
    commented out in base.7z's linker script with every stage green - no
    operator in gen.py can produce that fault, so no mutant here can measure
    the stage that catches it.
  * A mutant is one fault at a time.  Two stages that both catch every
    single fault can still differ on a fault the other one masks.
  * The population is a sample: gen.py caps each operator per file and
    spreads the cap evenly over the matches, so most of the matched lines
    are never mutated at all.
"""

CAVEATS = """\
## what these numbers do not cover

* **Only faults gen.py can express.**  Eleven operators, each a single-line
  edit inside a named function, the HOWTO table, the opcode table or the
  linker-script template.  A fault that lives in a build rule, in base.7z,
  in an installed tree, or across two lines at once is not in this
  population and no stage can be credited for catching it.
* **Only a sample of those.**  `--cap' bounds each (file, operator) pair and
  the matches are then spread evenly, so raising the cap changes which
  mutants exist.
* **Only this stage list.**  `unique' is unique among the stages that ran.
  Run it against a longer list and a stage's unique count can only fall.
* **The population is not stable across commits.**  gen.py names a mutant by
  file, operator and LINE NUMBER, so any edit to a mutated file - even one
  that changes nothing the operator matches - renumbers the mutants below
  it.  Kill and unique counts from two different commits are therefore not
  comparable mutant-for-mutant; compare them only as rates, and only when
  the mutated files did not move.
* **A timeout is counted as a kill.**  rc 124 means the stage did not finish
  inside `--timeout'.  A mutation that puts the tools in an infinite loop is
  a real kill; a loaded machine is not.  The `t/o' column says how many of a
  stage's kills were timeouts, so a stage whose kills are mostly timeouts
  should be re-run before anything is concluded from it.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True,
                    help='results.json from run.py --all-stages')
    ap.add_argument('--pairs', type=int, default=0,
                    help='show only the N most similar stage pairs '
                         '(default: all of them)')
    args = ap.parse_args()

    d = load(args.results)
    stages = d['stages']
    base = d.get('baseline_secs') or {}

    scored, incomplete, other = [], [], collections.Counter()
    for r in d['results']:
        if r['status'] not in ('killed', 'survived'):
            other[r['status']] += 1
            continue
        rcs = r.get('stages') or {}
        if any(s not in rcs for s in stages):
            incomplete.append(r)
        else:
            scored.append(r)

    print(HEADER)

    if incomplete:
        # Not a warning to be skimmed past: a truncated row makes every
        # unique count below wrong in the direction that flatters the
        # earlier stages.
        print('> **%d scored mutants carry a verdict for only some of the '
              'stages** and are excluded.\n> That should not happen in an '
              '--all-stages run; the run was probably interrupted.\n'
              % len(incomplete))

    red = {r['id']: frozenset(s for s in stages if r['stages'][s])
           for r in scored}
    killed = [r for r in scored if red[r['id']]]
    live = [r for r in scored if not red[r['id']]]

    print('## the run\n')
    rows = [['stages', ' '.join(stages)],
            ['mutants scored', len(scored)],
            ['killed by at least one stage', len(killed)],
            ['survived every stage', len(live)],
            ['kill rate', per(100 * len(killed), len(scored), '%.1f%%')]]
    for k in sorted(other):
        rows.append(['excluded: %s' % k, other[k]])
    print(table(['what', 'value'], rows))

    # ------------------------------------------------------------- per stage
    kills = {s: [] for s in stages}
    uniq = {s: [] for s in stages}
    first = {s: 0 for s in stages}
    tmo = {s: 0 for s in stages}
    secs = {s: 0.0 for s in stages}
    for r in scored:
        rset = red[r['id']]
        for s in stages:
            secs[s] += float(r.get('secs', {}).get(s, 0.0))
            if r['stages'][s]:
                kills[s].append(r['id'])
                if r['stages'][s] == 124:
                    tmo[s] += 1
                if len(rset) == 1:
                    uniq[s].append(r['id'])
        for s in stages:                    # fail-first is list order
            if s in rset:
                first[s] += 1
                break

    print('\n## per stage\n')
    print('`kills` counts this stage alone.  `fail-first` is what a run that '
          'stopped at the\nfirst red would have recorded for it - the gap '
          'between the two columns is position,\nnot reach.  `gate s` is the '
          "stage's wall clock on the clean tree, which is what the\nmerge "
          'gate pays for it on every push.\n')
    rows = []
    for s in stages:
        rows.append([
            s, len(kills[s]), len(uniq[s]), first[s], tmo[s],
            '%.0f' % secs[s],
            per(secs[s], len(scored), '%.1f'),
            per(secs[s], len(uniq[s]), '%.0f'),
            ('%.0f' % base[s]) if s in base else '-',
            per(base[s], len(uniq[s]), '%.1f') if s in base else '-',
        ])
    rows.append(['TOTAL', '', sum(len(uniq[s]) for s in stages),
                 sum(first.values()), sum(tmo.values()),
                 '%.0f' % sum(secs.values()),
                 per(sum(secs.values()), len(scored), '%.1f'), '',
                 ('%.0f' % sum(base.values())) if base else '-', ''])
    print(table(['stage', 'kills', 'unique', 'fail-first', 't/o', 'run s',
                 's/mutant', 'run s per uniq', 'gate s', 'gate s per uniq'],
                rows, right=set(range(1, 10))))

    nothing = [s for s in stages if not kills[s]]
    nouniq = [s for s in stages if kills[s] and not uniq[s]]
    print('\n* caught nothing in this population: %s'
          % (' '.join(nothing) if nothing else '(none)'))
    print('* caught something, but nothing another stage missed: %s'
          % (' '.join(nouniq) if nouniq else '(none)'))
    print('* sole catcher of at least one mutant: %s'
          % (' '.join(s for s in stages if uniq[s]) or '(none)'))

    # ------------------------------------------------------- fragility
    print('\n## how many stages caught each killed mutant\n')
    hist = collections.Counter(len(red[r['id']]) for r in killed)
    rows = [[n, hist[n], per(100 * hist[n], len(killed), '%.1f%%')]
            for n in sorted(hist)]
    print(table(['stages that caught it', 'mutants', 'share of killed'],
                rows, right={0, 1, 2}))

    thin = [r for r in killed if len(red[r['id']]) == 1]
    print('\n### caught by exactly one stage (%d)\n' % len(thin))
    print('For each of these the named stage is the only thing in the list '
          'standing between\nthe port and that fault.  These matter more than '
          'any stage total.\n')
    if thin:
        rows = [[r['id'], r['op'], '%s:%d' % (r['file'], r['line']),
                 r['note'], next(iter(red[r['id']]))]
                for r in sorted(thin, key=lambda x: (x['file'], x['line']))]
        print(table(['mutant', 'operator', 'where', 'fault',
                     'the only stage that caught it'], rows))
    else:
        print('(none - every killed mutant was caught by at least two stages)')

    # ------------------------------------------------------------- pairs
    print('\n## stage pairs, kill sets compared\n')
    print('`only a` is what a caught and b did not.  A zero there means a '
          'caught nothing in\nthis population that b did not also catch, '
          'which is what duplication looks like.\n`overlap` is the '
          'intersection over the union.  Sorted by overlap.\n')
    # Only pairs where BOTH stages caught something: a pair against a stage
    # that killed nothing is trivially contained in the other, and printing
    # that as `a within b' would read as duplication where there is only an
    # empty set.  The stages left out are named under `per stage' above.
    live_st = [s for s in stages if kills[s]]
    idle = [s for s in stages if not kills[s]]
    pr = []
    for a, b in itertools.combinations(live_st, 2):
        A, B = set(kills[a]), set(kills[b])
        both, oa, ob = len(A & B), len(A - B), len(B - A)
        j = both / float(both + oa + ob)
        if not oa and not ob:
            rel = 'identical'
        elif not oa:
            rel = 'a is a subset of b'
        elif not ob:
            rel = 'b is a subset of a'
        else:
            rel = ''
        pr.append((-j, -both, a, b, both, oa, ob, rel))
    pr.sort()
    if args.pairs > 0:
        pr = pr[:args.pairs]
    if pr:
        print(table(['a', 'b', 'both', 'only a', 'only b', 'overlap',
                     'relation'],
                    [[a, b, both, oa, ob, '%.2f' % -k, rel]
                     for k, _t, a, b, both, oa, ob, rel in pr],
                    right={2, 3, 4, 5}))
    else:
        print('(fewer than two stages caught anything - no pair to compare)')
    if idle:
        print('\nNot in the table, having caught nothing to compare: %s'
              % ' '.join(idle))

    # --------------------------------------------------------- survivors
    print('\n## survived every stage (%d)\n' % len(live))
    if live:
        rows = [[r['id'], r['op'], '%s:%d' % (r['file'], r['line']), r['note']]
                for r in sorted(live, key=lambda x: (x['file'], x['line']))]
        print(table(['mutant', 'operator', 'where', 'fault'], rows))
    else:
        print('(none)')

    print('\n' + CAVEATS)
    return 0


if __name__ == '__main__':
    sys.exit(main())

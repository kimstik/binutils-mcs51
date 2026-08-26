#!/usr/bin/env python3
"""Turn one or two mutation runs into the tables of TESTS-mutation.md.

  report.py --after results.json [--before results-before.json]

With both, it prints the kill rate on each side, which stage did the killing,
and - the point of the exercise - exactly which mutants the new stages moved
from surviving to killed.
"""

import argparse
import collections
import json
import sys


def load(path):
    d = json.load(open(path))
    return d['stages'], {r['id']: r for r in d['results']}


def rate(rows):
    killed = sum(1 for r in rows.values() if r['status'] == 'killed')
    scored = sum(1 for r in rows.values() if r['status'] in ('killed', 'survived'))
    return killed, scored, (100.0 * killed / scored if scored else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--after', required=True)
    ap.add_argument('--before')
    args = ap.parse_args()

    astages, after = load(args.after)
    print('## kill rate\n')
    if args.before:
        bstages, before = load(args.before)
        k, n, p = rate(before)
        print('| suite | stages | killed | scored | kill rate |')
        print('|---|---|---:|---:|---:|')
        print('| before | %s | %d | %d | **%.1f%%** |' % (' '.join(bstages), k, n, p))
        k, n, p = rate(after)
        print('| after  | %s | %d | %d | **%.1f%%** |' % (' '.join(astages), k, n, p))
    else:
        before = {}
        k, n, p = rate(after)
        print('killed %d of %d scored, %.1f%%' % (k, n, p))

    print('\n## what kills what\n')
    by = collections.Counter(r['killer'] for r in after.values()
                             if r['status'] == 'killed')
    print('| stage | mutants it is first to kill |')
    print('|---|---:|')
    for st in astages:
        print('| %s | %d |' % (st, by.get(st, 0)))

    if before:
        newly = [i for i, r in after.items()
                 if r['status'] == 'killed'
                 and before.get(i, {}).get('status') == 'survived']
        print('\n## mutants the new stages caught (%d)\n' % len(newly))
        print('| mutant | operator | where | fault | killed by |')
        print('|---|---|---|---|---|')
        for i in sorted(newly, key=lambda x: (after[x]['file'], after[x]['line'])):
            r = after[i]
            print('| `%s` | %s | %s:%d | %s | %s |'
                  % (r['id'], r['op'], r['file'], r['line'], r['note'], r['killer']))

        lost = [i for i, r in after.items()
                if r['status'] == 'survived'
                and before.get(i, {}).get('status') == 'killed']
        if lost:
            print('\n## regressed (killed before, survives now) - investigate\n')
            for i in lost:
                print('* `%s` %s' % (i, after[i]['note']))

    live = [r for r in after.values() if r['status'] == 'survived']
    print('\n## survivors (%d)\n' % len(live))
    print('| mutant | operator | where | fault | context |')
    print('|---|---|---|---|---|')
    for r in sorted(live, key=lambda x: (x['file'], x['line'])):
        print('| `%s` | %s | %s:%d | %s | `%s` |'
              % (r['id'], r['op'], r['file'], r['line'], r['note'],
                 r['context'].replace('|', '\\|')[:60]))
    return 0


if __name__ == '__main__':
    sys.exit(main())

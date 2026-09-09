#!/usr/bin/env python3
"""Run the testbench gate against every mutant and report the kill rate.

For each mutant produced by gen.py: patch the one line in the built tree,
rebuild incrementally, run the gate, restore the line.  A mutant that makes
any gate stage fail is killed; one that passes the whole gate is a hole in
the suite - a fault the tests cannot see.

The stages are the existing testbench targets, run through tb/Makefile, so
whatever `make -C tb <stage>' means today is what a mutant has to survive.
--stages is required and has no default: the one list of stages a mutant must
survive is tb/Makefile's $(MUTGATE), and a default here would be a second copy
of it that drifts.  A stage added to $(MUTGATE) then reaches this file for
free, and a hand run states what it measured against instead of quietly
measuring against less than the recorded runs did.

  run.py --tree WORK/modern/binutils-2.47 --build WORK/modern/build \
         --mutants mutants.json --out results.json \
         --stages isa,roundtrip,branch,bits,reloc,sim,defaultlink,commons,script,disasm,check

--all-stages runs every stage against every mutant instead of stopping at
the first red, and records each stage's verdict and wall clock separately.
It is a mode and not the default because it costs the whole gate for every
mutant, where the fail-first path costs only as far as the first red.  What
it buys is the one question the fail-first numbers cannot answer: in stage
order a stage can only ever be recorded killing what every stage before it
missed, so its count measures its POSITION as much as its reach.  The last
fail-first run read sim 0 and commons 0 - both run late, and something
earlier always got there first.  Nothing about removing or merging a stage
can be argued from a number like that.  mutation/coverage.py reduces the
full matrix this mode writes; it refuses a fail-first file outright.

Exit: 0 the run completed (kill rate in the report), 2 setup problem,
      3 the clean tree does not pass the gate.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TB = os.path.dirname(HERE)

# What the incremental rebuild must mention after a file is mutated.  If it
# does not, make did not pick the change up and the mutant was never really
# tested - that has to be an error, not a survivor.
REBUILD_MARK = {
    'gas/config/tc-i51.c': 'tc-i51',
    'bfd/elf32-i51.c': 'elf32-i51',
    'opcodes/i51-dis.c': 'i51-dis',
    'include/opcode/i51.h': 'tc-i51',
    'ld/scripttempl/elf32i51.sc': 'eelf32i51',
}


def run(cmd, cwd=None, timeout=600, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except subprocess.TimeoutExpired:
        return 124, 'timeout after %ds' % timeout


class Harness:
    def __init__(self, tree, build, work, jobs, stages, timeout):
        self.tree, self.build, self.work = tree, build, work
        self.jobs, self.stages, self.timeout = jobs, stages, timeout
        self.saved = {}

    def save(self, files):
        os.makedirs(os.path.join(self.work, 'pristine'), exist_ok=True)
        for rel in files:
            dst = os.path.join(self.work, 'pristine', rel.replace('/', '_'))
            shutil.copy2(os.path.join(self.tree, rel), dst)
            self.saved[rel] = dst

    def restore(self, rel=None):
        # copyfile, not copy2: the restored file must look newer than the
        # object built from the mutant, or make skips it and the mutation
        # stays in the binary for every mutant that follows.
        for r in ([rel] if rel else list(self.saved)):
            dst = os.path.join(self.tree, r)
            shutil.copyfile(self.saved[r], dst)
            os.utime(dst, None)

    # gas/Makefile carries no dependency edge from tc-i51.o to
    # include/opcode/i51.h, though tc-i51.c includes it. An incremental build
    # would leave the assembler holding the old opcode table, so the mutation
    # would only reach the disassembler. Touch the .c so both are rebuilt -
    # a fresh `make build' has the fault in both, and that is the fault being
    # measured.
    ALSO_TOUCH = {'include/opcode/i51.h': ['gas/config/tc-i51.c']}

    def apply(self, m):
        path = os.path.join(self.tree, m['file'])
        with open(path, encoding='latin-1') as f:
            lines = f.read().splitlines()
        first = m['line'] - 1
        n = len(m['old'])
        if lines[first:first + n] != m['old']:
            return False
        lines[first:first + n] = m['new']
        with open(path, 'w', encoding='latin-1') as f:
            f.write('\n'.join(lines) + '\n')
        for rel in self.ALSO_TOUCH.get(m['file'], ()):
            os.utime(os.path.join(self.tree, rel), None)
        return True

    def rebuild(self):
        return run(['make', '-j%d' % self.jobs, 'MAKEINFO=true',
                    'all-gas', 'all-ld', 'all-binutils'],
                   cwd=self.build, timeout=1800)

    def gate(self, every=False):
        """Run the stages against the tree as it stands.

        Default: stop at the first red.  One red is enough to call a mutant
        killed, and the stages after it would cost their whole wall clock to
        change nothing.

        every=True: run all of them whatever happens, so each stage's
        verdict on this mutant is recorded independently of where the stage
        sits in the list.  Safe to do because the stages do not share
        mutable state: each TOOLGATE stage builds its probes in a temporary
        directory of its own and deletes it again (run-bits, run-guard,
        run-reloc, run-disasm via tempfile.TemporaryDirectory, run-script
        via mkdtemp with an rmtree in its finally, run-commons and
        run-defaultlink via mktemp -d with a trap, run-testall likewise),
        and the two that do use $(WORK) - check and oracle - each begin by
        removing their own subdirectory of it.  So a stage that has already
        gone red cannot move the verdict of one that runs after it.

        Returns (first red or None, {stage: rc}, {stage: seconds}, the log
        of the first red).
        """
        rcs, secs = {}, {}
        first, flog = None, ''
        for st in self.stages:
            t0 = time.time()
            rc, log = run(['make', '--no-print-directory', '-C', TB, st,
                           'BUILD=' + self.build, 'WORK=' + self.work],
                          timeout=self.timeout)
            secs[st] = round(time.time() - t0, 2)
            rcs[st] = rc
            if rc != 0 and first is None:
                first, flog = st, log
                if not every:
                    break
        return first, rcs, secs, flog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--build', required=True)
    ap.add_argument('--mutants', required=True)
    ap.add_argument('--work', default=None, help='scratch dir (default <build>/../mut)')
    ap.add_argument('--out', default=None)
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--timeout', type=int, default=300, help='per gate stage')
    ap.add_argument('--stages', required=True,
                    help='comma separated tb/Makefile targets a mutant must '
                         'survive; the gate uses $(MUTGATE)')
    ap.add_argument('--only', help='comma separated mutant ids or operator names')
    ap.add_argument('--skip-baseline', action='store_true')
    ap.add_argument('--all-stages', action='store_true',
                    help='run every stage against every mutant instead of '
                         'stopping at the first red, and record each verdict '
                         'and its wall clock separately (slow; feeds '
                         'mutation/coverage.py)')
    args = ap.parse_args()

    stages = [s for s in args.stages.split(',') if s]
    # --stages '' or --stages ',' would leave nothing to run: every mutant
    # would survive an empty gate and the kill rate would read 0%.
    if not stages:
        sys.exit('--stages names no stage')

    tree = os.path.abspath(args.tree)
    build = os.path.abspath(args.build)
    work = os.path.abspath(args.work or os.path.join(build, os.pardir, 'mut'))
    os.makedirs(work, exist_ok=True)

    mutants = json.load(open(args.mutants))
    if args.only:
        want = set(args.only.split(','))
        mutants = [m for m in mutants if m['id'] in want or m['op'] in want]
    if not mutants:
        sys.exit('no mutants selected')

    h = Harness(tree, build, work, args.jobs, stages, args.timeout)
    h.save(sorted({m['file'] for m in mutants}))
    h.restore()      # normalises mtimes: a stale object from an earlier run
                     # would otherwise survive the baseline rebuild

    def bail(*_):
        h.restore()
        sys.exit('interrupted; sources restored')
    signal.signal(signal.SIGINT, bail)
    signal.signal(signal.SIGTERM, bail)

    # The gate must be green on the clean tree, or every mutant would read
    # as killed for reasons that have nothing to do with the mutation.
    base_secs = {}
    if not args.skip_baseline:
        rc, log = h.rebuild()
        if rc:
            print(log[-2000:])
            sys.exit('clean tree does not build')
        killer, base_rc, base_secs, log = h.gate(every=args.all_stages)
        if killer:
            print(log[-3000:])
            # In --all-stages every stage ran, so name every red one: the log
            # printed is the first one's, but a reader fixing the tree needs
            # to know it is not the only one.
            sys.exit('clean tree fails stage(s) %s - fix that first'
                     % ' '.join(s for s in stages if base_rc.get(s)))
        print('baseline: %s all pass' % ' '.join(stages))
        if args.all_stages:
            print('baseline cost: %s'
                  % '  '.join('%s %.0fs' % (s, base_secs[s]) for s in stages))

    results = []
    t0 = time.time()
    for n, m in enumerate(mutants, 1):
        if not h.apply(m):
            results.append(dict(m, status='stale', killer=None))
            print('%3d/%d %-28s STALE (source moved)' % (n, len(mutants), m['id']))
            continue
        rc, blog = h.rebuild()
        mark = REBUILD_MARK.get(m['file'])
        if rc:
            status, killer, stages_out, secs_out = 'nobuild', None, {}, {}
        elif mark and mark not in blog:
            status, killer, stages_out, secs_out = 'norebuild', None, {}, {}
        else:
            killer, stages_out, secs_out, _ = h.gate(every=args.all_stages)
            status = 'killed' if killer else 'survived'
        h.restore(m['file'])
        results.append(dict(m, status=status, killer=killer,
                            stages=stages_out, secs=secs_out))
        # In --all-stages the interesting number is how many of the stages
        # caught this mutant, not just which one got there first.
        if args.all_stages and stages_out:
            red = sum(1 for r in stages_out.values() if r)
            note = '%s %d/%d' % (killer or '-', red, len(stages_out))
        else:
            note = killer or ''
        print('%3d/%d %-28s %-9s %-16s %s'
              % (n, len(mutants), m['id'], status, note, m['note'][:44]))
        sys.stdout.flush()

    h.restore()
    rc, _ = h.rebuild()          # leave the tree as it was found
    # Fail-first even in --all-stages: this only has to prove nothing leaked
    # out of the loop, and one red is proof enough.
    killer, _, _, _ = h.gate()
    if killer:
        print('WARNING: the clean tree now fails %s - results are suspect' % killer)

    live = [r for r in results if r['status'] == 'survived']
    killed = [r for r in results if r['status'] == 'killed']
    nobuild = [r for r in results if r['status'] == 'nobuild']
    stale = [r for r in results if r['status'] in ('stale', 'norebuild')]
    scored = len(live) + len(killed)

    print('\n== %d mutants in %.0fs' % (len(results), time.time() - t0))
    print('   killed    %d' % len(killed))
    print('   survived  %d' % len(live))
    print('   no-build  %d (excluded: the fault cannot exist in that form)'
          % len(nobuild))
    if stale:
        print('   BROKEN    %d (stale/not rebuilt - harness problem)' % len(stale))
    print('   KILL RATE %.1f%% (%d/%d)'
          % (100.0 * len(killed) / scored if scored else 0.0, len(killed), scored))

    if live:
        print('\n== survivors')
        for r in live:
            print('   %-28s %-9s %s:%d  %s'
                  % (r['id'], r['op'], r['file'], r['line'], r['note']))

    if args.out:
        with open(args.out, 'w') as f:
            # all_stages is written whether it is true or false, and
            # coverage.py refuses a file that does not say true: a
            # fail-first matrix is truncated at the first red, and reducing
            # it as if it were complete would report a stage's position as
            # its coverage - the exact number this mode exists to replace.
            json.dump({'results': results, 'stages': stages,
                       'all_stages': bool(args.all_stages),
                       'baseline_secs': base_secs,
                       'killed': len(killed), 'survived': len(live),
                       'nobuild': len(nobuild)}, f, indent=1)
        print('\nresults -> %s' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())

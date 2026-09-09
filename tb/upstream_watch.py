#!/usr/bin/env python3
"""Notice a new upstream binutils release and prove the port still applies to it.

Run on a schedule by .github/workflows/upstream.yml, and by hand with
`make -C tb upstream'.  It reads the pinned release out of tb/Makefile, lists the
upstream release directory, and - only when that listing carries a release newer
than the pin - downloads the tarball, records its sha256, and applies
mcs51/additions.patch and mcs51/modifications.patch to it at --fuzz 0.  It writes
a report saying exactly what happened: clean, with offsets, or rejected, naming
the files and the hunks.

What it deliberately does not do: it never edits tb/Makefile, never rewrites
mcs51/*.patch, never commits and never opens a pull request.  The patches are the
deliverable; a machine may report that they still apply and may not decide that
they do.  It does not run `make refresh' either - see the note at the end of this
docstring.

WHERE IT LOOKS, and why ftp.gnu.org rather than sourceware.org

  Two directories publish binutils releases and both are plain Apache
  autoindexes of the same shape - one <a href="binutils-X.Y[.Z].tar.xz"> per
  file, with the detached .sig beside it in the same listing - so "a tarball
  WITH a matching signature" is decidable from a single page on either.
  Measured 2026-09-08:

    https://ftp.gnu.org/gnu/binutils/             28 *.tar.xz, 28 with a .sig
    https://sourceware.org/pub/binutils/releases/ 27 *.tar.xz, 25 with a .sig
                                                  (2.28.1 and 2.29 ship none)

  Neither carries -rc or -pre tarballs; both carry binutils-with-gold-X.Y.tar.xz,
  which the anchored regex below rejects because the version has to follow
  "binutils-" immediately.

  ftp.gnu.org is the one this watches, for one decisive reason: it is the
  directory tb/Makefile's PORT_URL downloads from, and the run asserts that -
  dirname(PORT_URL) has to equal the index being listed or the run fails.
  Watching a host the build does not fetch from can report a release that
  `make build' cannot download.  sourceware.org is upstream's own copy and gets
  a release first, so this watcher can be a few hours late; being late costs
  nothing, because the next night's run picks the release up, while reporting a
  tarball PORT_URL cannot fetch costs a human a wasted investigation.

  Neither host offers a JSON API.  The git tags on the binutils-gdb mirror are
  not a substitute: a tag exists before the tarball does, carries no signature,
  and the same repository tags gdb releases and release candidates.

HOW IT FAILS

  Loudly, and only in one direction.  Patches that do not apply to a NEW release
  are ordinary news, not a broken watcher: the run stays green and the report
  says "rejected".  Anything that makes the watcher itself untrustworthy - the
  index unreachable or unparsable, fewer releases parsed than could possibly be
  right, the pinned PORT_VERSION missing from the listing, PORT_URL pointing
  somewhere other than the listing, a download that is not a tarball, a .sig
  that is an HTML error page, `patch' in trouble rather than merely rejecting
  hunks - exits 3 and takes the job red.  There is no path on which a failure
  looks like "no new release".

REQUIREMENTS: python3 (stdlib only), make, GNU patch, tar with xz.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

INDEX_URL = "https://ftp.gnu.org/gnu/binutils/"
USER_AGENT = "binutils-mcs51-upstream-watch (+https://github.com/kimstik/binutils-mcs51)"

# A listing that parses to fewer releases than this is a parse failure, not an
# epoch in which binutils had no releases: ftp.gnu.org carried 28 signed .tar.xz
# on 2026-09-08 and that number only grows.
MIN_RELEASES = 10

# A detached OpenPGP signature is a few hundred bytes.  The bounds catch the case
# where the "signature" is an HTML error page or an empty file.
SIG_MIN_BYTES = 64
SIG_MAX_BYTES = 4096

# binutils-2.47.tar.xz is ~30 MB.  Anything under this is not a release tarball.
TARBALL_MIN_BYTES = 4 * 1024 * 1024

PATCHES = ("additions", "modifications")

CLEAN, OFFSETS, REJECTED = "clean", "offsets", "rejected"
WORST = {CLEAN: 0, OFFSETS: 1, REJECTED: 2}

# href="binutils-<version>.tar.xz", the version anchored right behind the dash so
# binutils-with-gold-2.44.tar.xz cannot match.
RE_RELEASE = re.compile(r'href="(binutils-([0-9]+(?:\.[0-9]+){1,2})\.tar\.xz)"')
RE_HREF = re.compile(r'href="([^"]+)"')
RE_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}$")

# GNU patch, one line at a time.
RE_PATCHING = re.compile(r"^patching file (.+)$")
RE_OK = re.compile(
    r"^Hunk #(\d+) succeeded at (\d+)(?: with fuzz \d+)?(?: \(offset (-?\d+) lines?\))?\.?$")
RE_FAILED = re.compile(r"^Hunk #(\d+) FAILED at (\d+)\.?$")
RE_TROUBLE = re.compile(
    r"^(can't find file to patch|The next patch would|Reversed \(or previously applied\)"
    r"|Only garbage was found|patch: \*\*\*|Assume -R|Skipping patch|\d+ out of \d+ hunks?)")


class Malfunction(Exception):
    """The watcher cannot answer the question it was asked.  Exit 3, job red."""


def say(msg):
    print(msg, flush=True)


def vtuple(v):
    return tuple(int(p) for p in v.split("."))


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ------------------------------------------------------------------ the pin

def read_pin(repo):
    """PORT_VERSION / PORT_URL / PORT_SHA256, straight out of tb/Makefile.

    Asked of make rather than scraped with a regex, so a `?=' default, an
    override on the command line and a future computed value all read the same.
    """
    mk = repo / "tb" / "Makefile"
    if not mk.is_file():
        raise Malfunction("no %s" % mk)
    cp = run(["make", "-C", str(repo / "tb"), "--no-print-directory", "print-port"])
    if cp.returncode != 0:
        raise Malfunction(
            "`make -C tb print-port' failed (rc=%d); tb/Makefile has to carry that target "
            "for the watcher to read the pin:\n%s%s" % (cp.returncode, cp.stdout, cp.stderr))
    pin = {}
    for line in cp.stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().startswith("PORT_"):
            pin[key.strip()] = value.strip()
    for key in ("PORT_VERSION", "PORT_URL", "PORT_SHA256"):
        if key not in pin:
            raise Malfunction("`make print-port' printed no %s:\n%s" % (key, cp.stdout))
    if not RE_VERSION.match(pin["PORT_VERSION"]):
        raise Malfunction("PORT_VERSION %r is not X.Y or X.Y.Z" % pin["PORT_VERSION"])
    return pin


def check_pin_against_index(pin, index_url):
    """The watcher has to list the directory the build downloads from."""
    want = "binutils-%s.tar.xz" % pin["PORT_VERSION"]
    base, _, name = pin["PORT_URL"].rpartition("/")
    if name != want:
        raise Malfunction(
            "PORT_URL ends in %r but PORT_VERSION is %s, so it should end in %r"
            % (name, pin["PORT_VERSION"], want))
    if base + "/" != index_url:
        raise Malfunction(
            "PORT_URL downloads from %s/ but this run lists %s.  A release found in one may "
            "not exist in the other; point --index-url at PORT_URL's directory, or repoint "
            "PORT_URL." % (base, index_url))


# ------------------------------------------------------------------ the listing

def http_get(url, tries=3, timeout=60):
    last = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # urllib raises a zoo; every one means "no answer"
            last = exc
            if attempt < tries:
                time.sleep(5 * attempt)
    raise Malfunction("cannot fetch %s after %d tries: %s" % (url, tries, last))


def http_download(url, dest, tries=3, timeout=300):
    last = None
    for attempt in range(1, tries + 1):
        try:
            digest = hashlib.sha256()
            size = 0
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            return digest.hexdigest(), size
        except Exception as exc:
            last = exc
            if attempt < tries:
                time.sleep(5 * attempt)
    raise Malfunction("cannot download %s after %d tries: %s" % (url, tries, last))


def parse_index(html, index_url, pin_version):
    """Every binutils-X.Y[.Z].tar.xz in the listing that has a .sig beside it.

    The .sig is the definition of a release here: a tarball can land in the
    directory before it is announced, and two of sourceware's have never had one.
    """
    hrefs = set(RE_HREF.findall(html))
    tarballs = RE_RELEASE.findall(html)
    releases = {}
    unsigned = []
    for name, version in tarballs:
        if name + ".sig" in hrefs:
            releases[version] = name
        else:
            unsigned.append(name)

    if len(releases) < MIN_RELEASES:
        raise Malfunction(
            "%s parsed to %d signed releases (%d tarballs, %d hrefs), fewer than the %d that "
            "must be there - the listing format changed, or that page is not the index.  "
            "First 400 bytes:\n%s"
            % (index_url, len(releases), len(tarballs), len(hrefs), MIN_RELEASES, html[:400]))
    if pin_version not in releases:
        raise Malfunction(
            "the pinned PORT_VERSION %s is not among the %d signed releases at %s.  Either the "
            "pin names something this directory does not serve - in which case `make build' "
            "cannot download it either - or the parse is wrong."
            % (pin_version, len(releases), index_url))
    if unsigned:
        say("note: %d listed tarball(s) carry no .sig and are not treated as releases: %s"
            % (len(unsigned), ", ".join(sorted(unsigned))))
    return releases


# ------------------------------------------------------------------ the patches

def patch_shape(path):
    """Files and hunks the patch file itself declares.

    Read from the patch, not from patch(1)'s output: a hunk that applies at its
    stated line prints nothing at all, so the log cannot say how many there were.
    """
    files, hunks = [], 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("+++ "):
                name = line[4:].strip().split("\t")[0]
                if name.startswith("b/"):
                    name = name[2:]
                files.append(name)
            elif line.startswith("@@"):
                hunks += 1
    return files, hunks


def parse_patch_log(log):
    """(offsets, failures, trouble), each a list of human-readable lines."""
    offsets, failures, trouble = [], [], []
    current = "?"
    for line in log.splitlines():
        line = line.rstrip()
        m = RE_PATCHING.match(line)
        if m:
            current = m.group(1)
            continue
        m = RE_OK.match(line)
        if m:
            if m.group(3) is not None:
                offsets.append("%s: hunk #%s landed at line %s, offset %s"
                               % (current, m.group(1), m.group(2), m.group(3)))
            continue
        m = RE_FAILED.match(line)
        if m:
            failures.append("%s: hunk #%s FAILED at line %s" % (current, m.group(1), m.group(2)))
            continue
        if RE_TROUBLE.match(line):
            trouble.append("%s: %s" % (current, line))
    return offsets, failures, trouble


def apply_patch(tree, patch_path, log_path, timeout=900):
    """Apply one patch exactly as tb/Makefile's `build' target does.

    Same flags, same --fuzz 0, same -p1.  --force is the one addition, and it is
    --force rather than --batch on purpose: both stop patch asking questions a
    scheduled job has nobody to answer, but --batch answers "assume the patch is
    reversed if it looks reversed", which would let patch UN-apply the port and
    exit 0 - a clean verdict on a tree that lost the port.  --force assumes the
    opposite, so a patch that looks already applied fails its hunks and is
    reported as rejected.  The timeout is the second half of the same rule: a
    question nobody answers must not become a job that runs until it is killed.
    """
    with open(patch_path, "rb") as fh:
        try:
            cp = subprocess.run(
                ["patch", "--force", "--fuzz", "0", "--no-backup-if-mismatch", "-p1",
                 "-d", str(tree)],
                stdin=fh, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise Malfunction("GNU patch is not installed")
        except subprocess.TimeoutExpired:
            raise Malfunction("patch did not finish within %ds on %s" % (timeout, patch_path))
    log = cp.stdout + cp.stderr
    log_path.write_text(log, encoding="utf-8")
    say(log.rstrip())

    if cp.returncode >= 2:
        # 2 is patch's "serious trouble": a missing file, an unreadable patch, an
        # I/O error.  That is the watcher malfunctioning, not upstream moving.
        raise Malfunction("patch exited %d on %s - that is trouble, not rejected hunks:\n%s"
                          % (cp.returncode, patch_path.name, log))

    offsets, failures, trouble = parse_patch_log(log)
    files, hunks = patch_shape(patch_path)

    # The verdict is read off parsed lines, so a line this parser does not
    # recognise would quietly become a clean verdict.  These three say, in the
    # crude way tb/Makefile's own `grep -q offset' says it, that the log and the
    # parse agree - and go red rather than guess when they do not.
    if "offset" in log.lower() and not offsets:
        raise Malfunction(
            "%s: the apply log says `offset' and this parser recognised none, so the "
            "verdict cannot be trusted:\n%s" % (patch_path.name, log))
    if "FAILED" in log and not failures and cp.returncode == 0:
        raise Malfunction(
            "%s: the apply log says `FAILED' and patch still exited 0:\n%s"
            % (patch_path.name, log))
    if cp.returncode == 0 and re.search(r"Reversed \(or previously applied\)|Assume -R", log):
        raise Malfunction(
            "%s: patch exited 0 while calling the patch reversed or already applied - the "
            "tree is not in a state this can report on:\n%s" % (patch_path.name, log))

    if cp.returncode == 1:
        verdict = REJECTED
        if not failures:
            # patch says something failed and the log names no hunk: say so rather
            # than report an empty list beside a red verdict.
            failures = ["patch exited 1 but named no failing hunk; read the log"]
    elif offsets:
        # tb/Makefile treats an offset as a failure and so does this: at --fuzz 0 a
        # hunk can still slide onto another line, and patch exits 0 when it does.
        verdict = OFFSETS
    else:
        verdict = CLEAN
    return {"name": patch_path.name, "rc": cp.returncode, "verdict": verdict,
            "files": files, "hunks": hunks, "offsets": offsets, "failures": failures,
            "trouble": trouble, "log": log_path}


# ------------------------------------------------------------------ the report

def bullets(items, cap=40):
    out = ["- %s" % item for item in items[:cap]]
    if len(items) > cap:
        out.append("- ... and %d more, in the run's artifact" % (len(items) - cap))
    return out


VERDICT_TITLE = {
    CLEAN: "the patches still apply",
    OFFSETS: "the patches land at an offset",
    REJECTED: "the patches are rejected",
}

VERDICT_WORDS = {
    CLEAN: "clean at --fuzz 0, no offset",
    OFFSETS: "applies, but a hunk slid",
    REJECTED: "rejected hunks",
}


def build_report(pin, baseline, newest_version, tarball, results, index_url, pretend):
    verdict = max((r["verdict"] for r in results), key=lambda v: WORST[v])
    title = "binutils %s is out: %s" % (newest_version, VERDICT_TITLE[verdict])

    L = ["<!-- upstream-watch -->", ""]
    L.append("`binutils %s` is on %s; the port is pinned to `%s`."
             % (newest_version, index_url, baseline))
    if pretend:
        L += ["", "> Forced run: compared against `%s` from the workflow input, not against "
                  "tb/Makefile's `PORT_VERSION = %s`." % (baseline, pin["PORT_VERSION"])]
    L += ["", "| | |", "|---|---|"]
    L.append("| tarball | `%s` (%d bytes) |" % (tarball["name"], tarball["size"]))
    L.append("| sha256 | `%s` |" % tarball["sha256"])
    L.append("| signature | `%s`, %d bytes, sha256 `%s` - present, **not** verified against a key |"
             % (tarball["sig_name"], tarball["sig_size"], tarball["sig_sha256"]))
    L.append("| pinned now | `PORT_VERSION = %s`, `PORT_SHA256 = %s` |"
             % (pin["PORT_VERSION"], pin["PORT_SHA256"]))
    L += ["", "## The patches against %s" % newest_version, ""]
    L.append("| patch | files | hunks | offsets | rejected | verdict |")
    L.append("|---|---|---|---|---|---|")
    for r in results:
        L.append("| `mcs51/%s` | %d | %d | %d | %d | **%s** |"
                 % (r["name"], len(r["files"]), r["hunks"], len(r["offsets"]),
                    len(r["failures"]), VERDICT_WORDS[r["verdict"]]))
    L.append("")
    for r in results:
        if r["verdict"] == CLEAN and not r["trouble"]:
            continue
        L += ["### `mcs51/%s`" % r["name"], "", "patch exited %d." % r["rc"]]
        if r["failures"]:
            L += ["", "Rejected:"] + bullets(r["failures"])
        if r["offsets"]:
            L += ["", "Offsets:"] + bullets(r["offsets"])
        if r["trouble"]:
            L += ["", "Also said:"] + bullets(r["trouble"])
        L.append("")

    L += ["## What this means", ""]
    if verdict == CLEAN:
        L.append("Both patches apply to %s at `--fuzz 0` with no hunk moving a line, which is "
                 "what `make -C tb build` demands. Nothing here says the result *builds* or "
                 "passes the gate - no configure and no compiler ran. A human bumps "
                 "`PORT_VERSION` and `PORT_SHA256` in `tb/Makefile`, and the gate answers that."
                 % newest_version)
    elif verdict == OFFSETS:
        L.append("Every hunk found a place, but at least one landed on a different line than the "
                 "patch names. `tb/Makefile` fails the build on exactly this: at `--fuzz 0` a hunk "
                 "can still slide, and a slide means the patches and the pinned release have "
                 "drifted apart. `make -C tb refresh` regenerates the patches with current line "
                 "numbers - from a tree a human has looked at.")
    else:
        L.append("At least one hunk was rejected: upstream changed lines this port edits. The "
                 "rejected hunks above are the work. `make -C tb build` stops in the same place.")
    L += ["", "## What this run did not do", ""]
    L.append("- did not change `PORT_VERSION` or `PORT_SHA256`, and did not open a pull request")
    L.append("- did not rewrite `mcs51/*.patch`, and did not run `make refresh`")
    L.append("- did not configure, compile or test anything")
    L.append("- did not verify the OpenPGP signature: it checked that the `.sig` exists and is a "
             "signature-sized file, which is what makes this a release and not a stray tarball")
    L += ["", "Reproduce it:", "", "```"]
    L.append("make -C tb upstream")
    L.append("make -C tb build PORT_VERSION=%s PORT_SHA256=%s" % (newest_version, tarball["sha256"]))
    L += ["```", ""]
    L.append("Close this issue once `tb/Makefile` is on a release a human has looked at; the next "
             "release opens a fresh one. While it is open the watcher rewrites this body rather "
             "than filing a second issue.")
    server = os.environ.get("GITHUB_SERVER_URL", "")
    slug = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if server and slug and run_id:
        L += ["", "Run: %s/%s/actions/runs/%s" % (server, slug, run_id)]
    return title, verdict, "\n".join(L) + "\n"


# ------------------------------------------------------------------ GitHub glue

def gha_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for key, value in kv.items():
            fh.write("%s=%s\n" % (key, str(value).replace("\n", " ").strip()))


def gha_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")


def truthy(value):
    return str(value).strip().lower() in ("1", "yes", "true", "on")


# ------------------------------------------------------------------ main

def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="watch for a newer binutils release")
    ap.add_argument("--repo", default=str(here.parent), help="repository root")
    ap.add_argument("--index-url", default=INDEX_URL, help="release directory to list")
    ap.add_argument("--work", default=None, help="scratch directory (wiped first)")
    ap.add_argument("--report", default=None, help="where to write the report")
    ap.add_argument("--pretend-version", default=os.environ.get("UPSTREAM_WATCH_PRETEND", ""),
                    help="compare against this instead of PORT_VERSION (forces a dry run)")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    work = Path(args.work) if args.work else repo / "work" / "upstream"
    report_path = Path(args.report) if args.report else work / "report.md"
    index_url = args.index_url if args.index_url.endswith("/") else args.index_url + "/"
    pretend = args.pretend_version.strip()
    dry_run = truthy(os.environ.get("UPSTREAM_WATCH_DRY_RUN", "")) or bool(pretend)

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    pin = read_pin(repo)
    check_pin_against_index(pin, index_url)
    say("pinned: PORT_VERSION=%s  PORT_SHA256=%s" % (pin["PORT_VERSION"], pin["PORT_SHA256"]))

    baseline = pin["PORT_VERSION"]
    if pretend:
        if not RE_VERSION.match(pretend):
            raise Malfunction("--pretend-version %r is not X.Y or X.Y.Z" % pretend)
        say("forced: comparing against %s instead of PORT_VERSION %s, and this run is a dry run"
            % (pretend, baseline))
        baseline = pretend

    say("listing %s" % index_url)
    html = http_get(index_url).decode("utf-8", "replace")
    releases = parse_index(html, index_url, pin["PORT_VERSION"])
    newest_version = max(releases, key=vtuple)
    say("%d signed releases listed, newest %s" % (len(releases), newest_version))

    if vtuple(newest_version) <= vtuple(baseline):
        line = ("upstream-watch: newest signed release is binutils %s, the port is pinned to %s. "
                "Nothing to report." % (newest_version, baseline))
        say(line)
        gha_summary(line)
        gha_output(action="none", version=newest_version, port_version=pin["PORT_VERSION"],
                   verdict="", title="", dry_run="yes" if dry_run else "no",
                   report=str(report_path))
        return 0

    name = releases[newest_version]
    tarball_url = index_url + name
    sig_url = tarball_url + ".sig"
    say("newer release: %s -> %s" % (baseline, newest_version))

    sig_path = work / (name + ".sig")
    say("downloading %s" % sig_url)
    sig_sha, sig_size = http_download(sig_url, sig_path)
    if not (SIG_MIN_BYTES <= sig_size <= SIG_MAX_BYTES):
        raise Malfunction("%s is %d bytes, not a detached signature" % (sig_url, sig_size))
    if sig_path.read_bytes().lstrip()[:1] == b"<":
        raise Malfunction("%s served markup, not a signature" % sig_url)

    tar_path = work / name
    say("downloading %s" % tarball_url)
    tar_sha, tar_size = http_download(tarball_url, tar_path)
    if tar_size < TARBALL_MIN_BYTES:
        raise Malfunction("%s is %d bytes, too small to be a binutils tarball"
                          % (tarball_url, tar_size))
    say("sha256  %s  %s" % (tar_sha, name))

    say("extracting")
    cp = run(["tar", "xf", str(tar_path), "-C", str(work)])
    if cp.returncode != 0:
        raise Malfunction("tar could not unpack %s (rc=%d):\n%s%s"
                          % (name, cp.returncode, cp.stdout, cp.stderr))
    # The same assumption tb/Makefile's `build' target makes, deliberately: it
    # patches and configures binutils-$(PORT_VERSION)/, so a tarball that unpacks
    # under another name breaks the build too and has to be seen, not guessed at.
    tree = work / ("binutils-%s" % newest_version)
    if not tree.is_dir():
        raise Malfunction("%s does not hold binutils-%s/ after extraction; it holds %s"
                          % (name, newest_version,
                             ", ".join(sorted(p.name for p in work.iterdir())) or "nothing"))

    results = []
    for stem in PATCHES:
        patch_path = repo / "mcs51" / ("%s.patch" % stem)
        if not patch_path.is_file():
            raise Malfunction("no %s" % patch_path)
        say("== applying mcs51/%s.patch to binutils-%s" % (stem, newest_version))
        # Both are attempted even when the first is rejected, because a complete
        # report is worth more: modifications.patch only touches files that were
        # already in the tarball, so its result does not depend on additions.patch
        # having landed.  `make build' stops at the first failure instead.
        results.append(apply_patch(tree, patch_path, work / ("%s.apply.log" % stem)))

    tarball = {"name": name, "size": tar_size, "sha256": tar_sha,
               "sig_name": name + ".sig", "sig_size": sig_size, "sig_sha256": sig_sha}
    title, verdict, report = build_report(
        pin, baseline, newest_version, tarball, results, index_url, pretend)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    say("")
    say(report)
    say("report written to %s" % report_path)
    gha_summary(report)
    gha_output(action="report", version=newest_version, port_version=pin["PORT_VERSION"],
               verdict=verdict, title=title, dry_run="yes" if dry_run else "no",
               report=str(report_path))
    if dry_run:
        say("dry run: no issue touched")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Malfunction as exc:
        print("::error title=upstream-watch::%s" % str(exc).replace("\n", " ")[:800],
              file=sys.stderr)
        print("upstream-watch: %s" % exc, file=sys.stderr)
        sys.exit(3)

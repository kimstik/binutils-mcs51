#!/usr/bin/env python3
"""Recompute the hunk headers and blob hashes of an all-additions patch.

Every file in mcs51/additions.patch is a new file, so each has exactly one
hunk of the form "@@ -0,0 +1,N @@" whose N is the number of added lines, and
one "index 00000000..HASH" line whose HASH is git's blob hash of the file that
hunk builds.  Editing the body leaves both stale: CI applies the patch with
--fuzz 0, which needs N, while git am and every reader who trusts the index
line need the hash.

Both are checked, because checking the count alone is a trap.  Two edits to
one file merged by hand produce a body that neither side's header describes;
a count-only check repairs N, prints that the headers are correct, and ships
the wrong hash underneath that sentence.

  usage: fixhunks.py PATCH...        rewrite the headers in place
         fixhunks.py --check PATCH...  report stale headers, change nothing

exit: 0 all headers correct (or rewritten), 1 stale headers found under
      --check, 2 the patch is not all-additions

walk () and added_files () below are the same reader used as a library: the
port has no source tree, so anything that wants to read the port's own C is
reading it out of these hunk bodies.  tb/doctruth.py does.
"""

import hashlib
import re
import sys

HUNK_PREFIX = "@@ -0,0 +1,"
INDEX_RE = re.compile(rb"^index (0{7,40})\.\.([0-9a-f]{7,40})$")
PLUSPLUS_RE = re.compile(rb"^\+\+\+ (?:b/)?(.+)$")


class NotAllAdditions(Exception):
    """A hunk that does not create a whole file from nothing."""


def blob_hash(body):
    """git's hash for a file made of BODY, one bytes object per line."""
    raw = b"\n".join(body) + b"\n"
    return hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()


def split_patch(raw):
    """RAW patch bytes as (lines, trailing_newline)."""
    lines = raw.split(b"\n")
    trailing_newline = bool(lines) and lines[-1] == b""
    if trailing_newline:
        lines = lines[:-1]
    return lines, trailing_newline


def walk(lines):
    """Yield (i, j, path) for every hunk of an all-additions patch.

    I indexes the "@@ -0,0 +1,N @@" line, J is one past the last line of its
    body, and PATH is the file the hunk builds, read from the "+++ b/..."
    line above it.  Raises NotAllAdditions on a hunk that is not one.
    """
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith(b"@@ "):
            i += 1
            continue
        if not line.startswith(HUNK_PREFIX.encode()):
            raise NotAllAdditions(
                "%d: not an all-additions hunk: %s"
                % (i + 1, line.decode("utf-8", "replace")))
        j = i + 1
        while j < len(lines):
            body = lines[j]
            if body.startswith(b"+") or body.startswith(b"\\"):
                j += 1                       # "\ No newline at end of file"
            else:
                break
        path = None
        if i >= 1:
            m = PLUSPLUS_RE.match(lines[i - 1])
            if m:
                path = m.group(1).decode("utf-8", "replace")
        yield i, j, path
        i = j


def hunk_body(lines, i, j):
    """The file contents a hunk builds: its + lines with the + taken off."""
    return [b[1:] for b in lines[i + 1:j] if b.startswith(b"+")]


def added_files(path):
    """{path inside the tree: [text lines]} for an all-additions patch.

    This is the port's source tree.  It does not exist on disk anywhere: the
    files live in mcs51/additions.patch as + lines and are reconstructed
    here, which is the same thing the hash check above does.
    """
    with open(path, "rb") as f:
        lines, _ = split_patch(f.read())
    out = {}
    for i, j, name in walk(lines):
        if name is None:
            raise NotAllAdditions("%d: hunk with no +++ line above it"
                                  % (i + 1))
        body = hunk_body(lines, i, j)
        out[name] = [b.decode("latin-1") for b in body]
    return out


def process(path, check):
    with open(path, "rb") as f:
        raw = f.read()
    lines, trailing_newline = split_patch(raw)

    stale = []
    try:
        for i, j, _name in walk(lines):
            line = lines[i]
            n = len(hunk_body(lines, i, j))
            want = b"@@ -0,0 +1,%d @@" % n
            if line != want:
                stale.append((i + 1, line.decode(), want.decode()))
                if not check:
                    lines[i] = want

            # The index line sits three above the hunk header, in the fixed
            # sequence diff --git / new file mode / index / --- / +++ / @@.
            idx = i - 3
            if idx >= 0:
                m = INDEX_RE.match(lines[idx])
                if m:
                    body = hunk_body(lines, i, j)
                    got = blob_hash(body).encode()[:len(m.group(2))]
                    if got != m.group(2):
                        fixed = b"index " + m.group(1) + b".." + got
                        stale.append((idx + 1, lines[idx].decode(),
                                      fixed.decode()))
                        if not check:
                            lines[idx] = fixed
    except NotAllAdditions as exc:
        sys.stderr.write("%s:%s\n" % (path, exc))
        return 2, stale

    if not check and stale:
        out = b"\n".join(lines)
        if trailing_newline:
            out += b"\n"
        with open(path, "wb") as f:
            f.write(out)
    return 0, stale


def main(argv):
    check = False
    args = list(argv)
    if args and args[0] == "--check":
        check = True
        args = args[1:]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    bad = 0
    for path in args:
        rc, stale = process(path, check)
        if rc:
            return rc
        for lineno, was, want in stale:
            print("%s:%d: %s -> %s" % (path, lineno, was, want))
        if stale:
            bad = 1 if check else 0
        else:
            print("%s: hunk headers correct" % path)
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

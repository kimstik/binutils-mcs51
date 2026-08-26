#!/usr/bin/env python3
"""Recompute the line counts in the hunk headers of an all-additions patch.

Every file in mcs51/additions.patch is a new file, so each has exactly one
hunk of the form "@@ -0,0 +1,N @@" whose N is the number of added lines.
Editing the body inside the patch leaves N stale, and CI applies the patch
with --fuzz 0, so N has to be brought back in line by counting.

  usage: fixhunks.py PATCH...        rewrite the headers in place
         fixhunks.py --check PATCH...  report stale headers, change nothing

exit: 0 all headers correct (or rewritten), 1 stale headers found under
      --check, 2 the patch is not all-additions
"""

import sys

HUNK_PREFIX = "@@ -0,0 +1,"


def process(path, check):
    with open(path, "rb") as f:
        raw = f.read()
    lines = raw.split(b"\n")
    trailing_newline = lines and lines[-1] == b""
    if trailing_newline:
        lines = lines[:-1]

    stale = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith(b"@@ "):
            i += 1
            continue
        if not line.startswith(HUNK_PREFIX.encode()):
            sys.stderr.write("%s:%d: not an all-additions hunk: %s\n"
                             % (path, i + 1, line.decode("utf-8", "replace")))
            return 2, stale
        # Count the added lines that follow, up to the next file or hunk.
        n = 0
        j = i + 1
        while j < len(lines):
            body = lines[j]
            if body.startswith(b"+"):
                n += 1
                j += 1
            elif body.startswith(b"\\"):     # "\ No newline at end of file"
                j += 1
            else:
                break
        want = b"@@ -0,0 +1,%d @@" % n
        if line != want:
            stale.append((i + 1, line.decode(), want.decode()))
            if not check:
                lines[i] = want
        i = j

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

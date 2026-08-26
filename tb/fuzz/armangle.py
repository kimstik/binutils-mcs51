#!/usr/bin/env python3
"""Mutate a well-formed ar archive: truncations and corrupt member headers.

  ./armangle.py good.a outdir/
"""
import os
import sys

MAGIC = b"!<arch>\n"


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    data = open(src, "rb").read()

    def emit(tag, blob):
        open(os.path.join(out, tag + ".a"), "wb").write(blob)

    # truncation at every 8-byte boundary and at every member header field
    for c in range(1, min(len(data), 512), 7):
        emit("trunc_%04d" % c, data[:c])
    emit("trunc_half", data[:len(data) // 2])
    emit("magic_only", MAGIC)
    emit("empty", b"")
    emit("bad_magic", b"!<arch>\r" + data[8:])

    # walk the members and corrupt each header
    pos = len(MAGIC)
    idx = 0
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        try:
            size = int(hdr[48:58].decode("latin1").strip() or "0")
        except ValueError:
            break
        b = bytearray(data)
        # size field: negative, huge, garbage, empty
        for tag, val in (("neg", b"-1        "), ("huge", b"4294967295"),
                         ("garbage", b"@@@@@@@@@@"), ("blank", b"          "),
                         ("big", b"99999999  ")):
            b = bytearray(data)
            b[pos + 48:pos + 58] = val
            emit("m%d_size_%s" % (idx, tag), bytes(b))
        # magic trailer
        b = bytearray(data)
        b[pos + 58:pos + 60] = b"XX"
        emit("m%d_trailer" % idx, bytes(b))
        # name field: long-name reference past the end of the string table
        b = bytearray(data)
        b[pos:pos + 16] = b"/4294967295     "
        emit("m%d_longname_oor" % idx, bytes(b))
        b = bytearray(data)
        b[pos:pos + 16] = b"/-1             "
        emit("m%d_longname_neg" % idx, bytes(b))
        # member body replaced with garbage
        b = bytearray(data)
        for i in range(pos + 60, min(pos + 60 + size, len(b))):
            b[i] = 0xFF
        emit("m%d_body_ff" % idx, bytes(b))
        pos += 60 + size + (size & 1)
        idx += 1

    print("%d archive mutants in %s" % (len(os.listdir(out)), out))


if __name__ == "__main__":
    main()

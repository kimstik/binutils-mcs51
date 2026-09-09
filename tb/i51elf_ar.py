#!/usr/bin/env python3
"""
Convert a 2001 i51 ELF archive, member by member, through the loose-object
pipeline.  See the note below: that pipeline no longer targets the format
the current port reads.

Each member goes through the same two steps as a loose object -
i51elf_le2be.py then i51elf_sym_uc.py - and neither changes a member's
length, so the archive keeps its layout: member offsets, the armap's
offset table and every header size field stay as they are.  What the
archive itself needs is the armap's symbol names uppercased to match the
members, and the headers put in the deterministic form GNU ar writes
(no timestamps, no uid/gid, plain mode), which is the form the archives
already in tb/base.7z carry.

  usage: i51elf_ar.py <old.a> <new.a>

This used to reproduce tb/base.7z's lib/libk80.a, lib/libk23.a and
lib/libw23.a byte-for-byte from their tb/base2001.7z originals.  It no
longer reproduces any of them.  Measured, on tb/base2001.7z's
lib/libk80.a, it writes
5c4af50d95a654b868ba189d1dfe281be67fa28bb41ae6f842a88b82cd28f42a where
tb/base.7z's lib/libk80.a is
fc3cdcc371837b1452d75d91f1f4d0098a595108b3e8dc4ec9b24ba3b6a2f268.  The
cause is in the member step, not here: i51elf_le2be.py byte-swaps the
container to ELFDATA2LSB, and base.7z has been ELFDATA2MSB since the
byte-order decision.  The archive-level work below - armap upper-casing and
deterministic ar headers - is correct: with the member transform corrected
to an e_machine restamp that leaves EI_DATA alone, lib/libk80.a,
lib/libk23.a, lib/libw23.a and lib/libw80.a all come out byte-identical to
base.7z (measured, 4 of 4).
"""
import contextlib
import io
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from i51elf_le2be import convert_elf
from i51elf_sym_uc import uppercase_symbols

AR_MAGIC = b"!<arch>\n"
HDR_SIZE = 60


def convert_member(payload):
    """Run one ELF member through the loose-object pipeline."""
    d = tempfile.mkdtemp()
    old = os.path.join(d, "old.obj")
    mid = os.path.join(d, "mid.obj")
    new = os.path.join(d, "new.obj")
    try:
        with open(old, "wb") as f:
            f.write(payload)
        # Both steps narrate what they do, which is useful for one object
        # and unreadable for a whole archive.
        with contextlib.redirect_stdout(io.StringIO()):
            ok = convert_elf(old, mid) and uppercase_symbols(mid, new)
        if not ok:
            raise SystemExit("conversion of an archive member failed")
        with open(new, "rb") as f:
            out = f.read()
    finally:
        for p in (old, mid, new):
            if os.path.exists(p):
                os.remove(p)
        os.rmdir(d)
    if len(out) != len(payload):
        raise SystemExit("conversion changed member length: %d -> %d"
                         % (len(payload), len(out)))
    return out


def convert_archive(src, dst):
    with open(src, "rb") as f:
        data = bytearray(f.read())
    if data[:8] != AR_MAGIC:
        sys.stderr.write("%s: not an ar archive\n" % src)
        return False

    members = 0
    pos = 8
    while pos + HDR_SIZE <= len(data):
        hdr = data[pos:pos + HDR_SIZE]
        name = hdr[0:16].decode("latin1").rstrip()
        size = int(hdr[48:58].decode("latin1").strip())
        body = bytes(data[pos + HDR_SIZE:pos + HDR_SIZE + size])

        data[pos + 16:pos + 28] = b"0".ljust(12)   # ar_date
        data[pos + 28:pos + 34] = b"0".ljust(6)    # ar_uid
        data[pos + 34:pos + 40] = b"0".ljust(6)    # ar_gid

        if name == "/":
            # armap: count, offset table, then the names.  Only the names
            # move to uppercase; uppercasing does not change their length.
            data[pos + 40:pos + 48] = b"0".ljust(8)
            n = struct.unpack(">I", body[:4])[0]
            split = 4 + 4 * n
            data[pos + HDR_SIZE:pos + HDR_SIZE + size] = \
                body[:split] + body[split:].upper()
            print("  armap: %d symbols uppercased" % n)
        elif name == "//":
            data[pos + 40:pos + 48] = b"0".ljust(8)
        else:
            data[pos + 40:pos + 48] = b"644".ljust(8)
            if body[:4] == b"\x7fELF":
                data[pos + HDR_SIZE:pos + HDR_SIZE + size] = convert_member(body)
                members += 1

        pos += HDR_SIZE + size + (size & 1)

    with open(dst, "wb") as f:
        f.write(data)
    print("Converted %d members of %s -> %s" % (members, src, dst))
    return True


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("usage: %s <old.a> <new.a>\n" % sys.argv[0])
        sys.exit(1)
    if not convert_archive(sys.argv[1], sys.argv[2]):
        sys.exit(1)

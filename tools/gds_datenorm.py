#!/usr/bin/env python3
"""Normalize GDS timestamps in place: BGNLIB (0x01) and BGNSTR (0x05)
records carry 12 int16 date fields (creation + modification, y m d h m s)
that magic stamps with wall-clock time -- the only nondeterminism in the
export (magic 8.3.676 accepts `gds datestamp` but ignores it on write).
Pinning them makes identical geometry produce byte-identical GDS, so CI
can prove the committed file matches a fresh rebuild from mag/.

Usage: python3 tools/gds_datenorm.py <file.gds> [...]
"""

import struct
import sys

DATE = struct.pack(">12h", 2025, 1, 1, 0, 0, 0, 2025, 1, 1, 0, 0, 0)


def normalize(path):
    data = bytearray(open(path, "rb").read())
    pos = patched = 0
    while pos + 4 <= len(data):
        (length,) = struct.unpack(">H", data[pos:pos + 2])
        if length < 4:
            sys.exit(f"{path}: corrupt record at offset {pos}")
        rectype = data[pos + 2]
        if rectype in (0x01, 0x05):          # BGNLIB / BGNSTR
            if length != 28:
                sys.exit(f"{path}: unexpected BGN record length {length}")
            data[pos + 4:pos + 28] = DATE
            patched += 1
        pos += length
    open(path, "wb").write(data)
    print(f"{path}: {patched} date records pinned")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        normalize(p)

#!/usr/bin/env python3
"""Drive lay_lib for the support blocks: place, route, DRC, LVS.

Row plans (bottom-up, names = golden card names sans leading X) chosen
NMOS rows low / PMOS rows high, big mirror devices on their own rows.

Usage: python3 tools/gen_block_layouts.py [block ...]   (default: all)
Exits nonzero if any block has DRC errors, unmatched devices, or an
LVS mismatch.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import lay_lib

ROWS = {
    # two wide rows: riser slots are a 1-per-um x resource, so small
    # dense blocks go wide, not tall
    "comp": [
        ["R1", "R2", "5", "6", "I1N", "I2N", "AQ3", "AQ4", "AB3", "AB4",
         "R3", "R4"],
        ["T", "1", "2", "3", "4", "I1P", "I2P", "AQ1", "AQ2", "AB1",
         "AB2"],
    ],
    "dff": [
        ["ICN", "TMN", "IM1N", "IM2N", "TMFN", "TSN", "IS1N", "IS2N",
         "TSFN", "IQ1N"],
        ["ICP", "TMP", "IM1P", "IM2P", "TMFP", "TSP", "IS1P", "IS2P",
         "TSFP", "IQ1P"],
    ],
    "bias": [
        ["RBNC", "RBPC"],
        ["RB", "RNB1", "RNB2"],
        ["M1", "M2", "SW"],
        ["IP", "IPC"],
        ["IN", "INC"],
        ["MP1", "MP2", "VN", "VP", "FD"],
        ["ST"],
    ],
    "buf": [
        ["3", "4"],
        ["1", "2"],
        ["TA"],
        ["TB"],
    ],
    "lvl": [
        ["IN", "N1", "N2", "B1N", "B2N"],
        ["IP", "P1", "P2", "B1P", "B2P"],
    ],
    # single row: two odrv instances must fit side by side in a
    # ~64 um column at assembly
    "odrv": [
        ["1N", "2N", "1P", "2P", "3N", "3P"],
    ],
}


def main():
    blocks = sys.argv[1:] or list(ROWS)
    fails = []
    for b in blocks:
        print(f"==== {b} ====", flush=True)
        lay_lib.build(b, ROWS[b])
        drc, matched, total = lay_lib.route(b)
        ok = lay_lib.lvs(b)
        if drc != 0 or matched != total or not ok:
            fails.append(b)
    if fails:
        print(f"FAILED blocks: {fails}")
        sys.exit(1)
    print("ALL BLOCK LAYOUTS CLEAN (DRC 0, devices matched, LVS)")


if __name__ == "__main__":
    main()

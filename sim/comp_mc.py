#!/usr/bin/env python3
"""Comparator input-referred offset: mismatch Monte Carlo (tt_mm).

Per mismatch sample: binary-search the DC trip point of INP (INM pinned at
0.9 V) to ~0.2 mV. Each sample runs in its own working directory with its
own .spiceinit (`set rndseed=N`) so the sky130 mismatch draws are seeded
deterministically per sample and identically across the bisection steps
of that sample (the netlist structure never changes, only one voltage
literal, so the parse-time agauss draw order is stable).

The race tmax is relaxed to 5 ps here: offset is a deterministic mV-scale
shift, far above the ~1 mV race-verdict noise floor, and the bisection
tolerates a noisy LSB.

Usage: python3 sim/comp_mc.py [N]    (default 20 samples)
Writes reports/results/comp_mc.json.
"""

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.comp_tb import SIZES, deck_point, TEDGE, VDD

BRACKET = 0.05     # +-50 mV search range
ITERS = 9          # ~0.2 mV resolution


def decide(dirpath, x):
    """True if Q latches high with INP = 0.9 + x (INM = 0.9)."""
    deck = deck_point(SIZES, 0.9 + x / 2, x, "mc", corner="tt_mm")
    deck = deck.replace(".tran 0.005n", ".tran 0.02n") \
               .replace(" 0 0.001n", " 0 0.005n")
    open(os.path.join(dirpath, "mc.spice"), "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "mc.spice"], cwd=dirpath,
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-300:])
    d = np.loadtxt(os.path.join(dirpath, "comp_mc.csv"))
    t, q = d[:, 0], d[:, 5]
    return q[(t >= TEDGE + 12e-9) & (t < TEDGE + 19e-9)].min() > 0.5 * VDD


def offset(seed):
    dirpath = f"spice/mc_{seed}"
    os.makedirs(dirpath, exist_ok=True)
    open(os.path.join(dirpath, ".spiceinit"), "w").write(
        f"set rndseed={seed}\n")
    lo, hi = -BRACKET, BRACKET
    if decide(dirpath, lo) or not decide(dirpath, hi):
        print(f"seed {seed}: offset outside +-{BRACKET*1e3:.0f} mV bracket!")
        return float("nan")
    for _ in range(ITERS):
        mid = (lo + hi) / 2
        if decide(dirpath, mid):
            hi = mid
        else:
            lo = mid
    off = (lo + hi) / 2
    print(f"seed {seed:3d}: offset {off*1e3:+7.2f} mV")
    shutil.rmtree(dirpath, ignore_errors=True)
    return off


def main(n):
    os.makedirs("spice", exist_ok=True)
    with ThreadPoolExecutor(max_workers=min(n, os.cpu_count())) as ex:
        offs = list(ex.map(offset, range(1, n + 1)))
    offs = np.array([o for o in offs if o == o])
    mean, std = offs.mean(), offs.std(ddof=1)
    print(f"\nN={len(offs)}: mean {mean*1e3:+.2f} mV, "
          f"sigma {std*1e3:.2f} mV, |max| {np.abs(offs).max()*1e3:.2f} mV")
    print("context: comparator offset in a 1-bit SD loop is a benign DC "
          "shift of the\nmodulator's own input offset; it does not degrade "
          "SNDR. Recorded for the record,\nnot against a spec.")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(dict(n=len(offs), mean_mv=round(mean * 1e3, 2),
                   sigma_mv=round(std * 1e3, 2),
                   max_abs_mv=round(float(np.abs(offs).max()) * 1e3, 2),
                   offsets_mv=[round(o * 1e3, 2) for o in offs]),
              open("reports/results/comp_mc.json", "w"), indent=1)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 20)

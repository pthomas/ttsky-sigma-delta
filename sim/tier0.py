#!/usr/bin/env python3
"""Tier-0 ideal difference-equation model of the 1st-order modulator.

Matches the tier-1 circuit: loop coefficient k = (VREFP-VCM)/RDAC * (TS/2)
/ CINT / FS_IN = 0.25 per cycle (referred to FS = +-1), one full cycle of
feedback delay, 1-bit quantizer, optional input dither.

Used for: long-run SNDR (pattern-noise statistics need >=2^20 bits),
cross-checking tier-1, and fast non-ideality sweeps.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import params as P
from sim.snr import sndr


def modulate(n, amp=P.AMP / P.FS_IN, k=0.25, sig_bin=None, dither=1e-3,
             seed=1):
    """Return n bits of the ideal 1st-order loop; sig_bin defaults to the
    same relative input frequency as the spice testbench."""
    if sig_bin is None:
        sig_bin = round(P.SIG_BIN / P.NFFT * n)
    rng = np.random.default_rng(seed)
    u = amp * np.sin(2 * np.pi * sig_bin * np.arange(n) / n)
    if dither:
        u = u + dither * rng.standard_normal(n)
    v, yk = 0.0, 1.0
    y = np.empty(n)
    for i in range(n):
        v += k * (u[i] - yk)        # yk is last cycle's bit: 1-cycle ELD
        yk = 1.0 if v >= 0 else -1.0
        y[i] = yk
    return y, sig_bin


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1 << 20
    bits, sig_bin = modulate(n)
    print(f"ideal 1st order, {n} bits, input {P.AMP/P.FS_IN:.2f} FS "
          f"at bin {sig_bin}")
    for name, osr in (("fast", P.OSR_FAST), ("precision", P.OSR_PREC)):
        s = sndr(bits, osr, sig_bin)
        print(f"  {name:>9s} (OSR {osr:3d}): {s:5.1f} dB  "
              f"{(s - 1.76) / 6.02:4.1f} ENOB")

#!/usr/bin/env python3
"""SNDR/ENOB of a modulator bitstream from an ngspice wrdata csv.

Usage: python3 sim/snr.py [spice/tier1_out.csv]

Resamples v(q) at mid-period (clk low, q guaranteed settled), takes a
coherent FFT of NFFT bits, and integrates noise+distortion up to the band
edge fs/(2*OSR) for each decimation path defined in params.py.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import params as P


def load_bits(csv_path):
    d = np.loadtxt(csv_path)          # cols: t q t clk t vin t int
    t, q = d[:, 0], d[:, 1]
    k = np.arange(P.NSETTLE, P.NSETTLE + P.NFFT)
    ts = (k + 0.5) * P.TS             # mid-period sample instants
    bits = np.where(np.interp(ts, t, q) > 1.65, 1.0, -1.0)
    return bits


def sndr(bits, osr, sig_bin):
    spec = np.abs(np.fft.rfft(bits)) ** 2
    band = len(bits) // (2 * osr)
    p_sig = spec[sig_bin - 1:sig_bin + 2].sum()   # signal bin +- 1 guard
    inband = spec[1:band + 1].copy()              # exclude DC
    inband[sig_bin - 3:sig_bin + 4] = 0.0
    return 10 * np.log10(p_sig / inband.sum())


if __name__ == "__main__":
    csv = sys.argv[1] if len(sys.argv) > 1 else "spice/tier1_out.csv"
    bits = load_bits(csv)
    ones = (bits > 0).mean()
    print(f"{csv}: {len(bits)} bits analyzed, ones density {ones:.3f}")
    print(f"{'path':>10s} {'OSR':>5s} {'BW':>9s} {'SNDR':>8s} {'ENOB':>6s}")
    for name, osr in [("fast", P.OSR_FAST), ("precision", P.OSR_PREC)]:
        s = sndr(bits, osr, P.SIG_BIN)
        bw = P.FS / (2 * osr)
        print(f"{name:>10s} {osr:5d} {bw/1e3:7.0f}kHz {s:8.1f} {(s-1.76)/6.02:6.1f}")

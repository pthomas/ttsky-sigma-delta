#!/usr/bin/env python3
"""SNDR/ENOB of a modulator bitstream from an ngspice wrdata csv, or
from a captured bit file -- the bench (FPGA / logic-analyzer capture)
is judged by the exact same estimator as every CI acceptance run
(pattern stolen from wulffern/tt06-sar: one analysis path, sim and
silicon).

Usage: python3 sim/snr.py [spice/tier1_out.csv]
       python3 sim/snr.py --bits <file> [--sigbin N]

--bits reads one 0/1 per line ('#'-prefixed header lines ignored --
the rtl/tb/vectors/pex_bits.txt format). The window length is the
file's line count (power of two recommended, coherent input assumed);
--sigbin is the input tone's FFT bin (odd, per the test plan).
"""

import json
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


def load_bitfile(path):
    vals = [ln.strip() for ln in open(path)
            if ln.strip() and not ln.startswith("#")]
    return np.where(np.array(vals, dtype=int) > 0, 1.0, -1.0)


if __name__ == "__main__":
    sig_bin = P.SIG_BIN
    if "--sigbin" in sys.argv:
        sig_bin = int(sys.argv[sys.argv.index("--sigbin") + 1])
    if "--bits" in sys.argv:
        csv = sys.argv[sys.argv.index("--bits") + 1]
        bits = load_bitfile(csv)
    else:
        csv = sys.argv[1] if len(sys.argv) > 1 else "spice/tier1_out.csv"
        bits = load_bits(csv)
    ones = (bits > 0).mean()
    print(f"{csv}: {len(bits)} bits analyzed, ones density {ones:.3f}")
    print(f"{'path':>10s} {'OSR':>5s} {'BW':>9s} {'SNDR':>8s} {'ENOB':>6s}")
    res = dict(nbits=len(bits), ones_density=round(ones, 3),
               fs_hz=P.FS, paths={})
    for name, osr in [("fast", P.OSR_FAST), ("precision", P.OSR_PREC)]:
        s = sndr(bits, osr, sig_bin)
        bw = P.FS / (2 * osr)
        print(f"{name:>10s} {osr:5d} {bw/1e3:7.0f}kHz {s:8.1f} {(s-1.76)/6.02:6.1f}")
        res["paths"][name] = dict(osr=osr, bw_hz=bw, sndr_db=round(s, 1),
                                  enob=round((s - 1.76) / 6.02, 1))
    os.makedirs("reports/results", exist_ok=True)
    # bench captures must not clobber the CI tier-1 result
    out = "snr_capture" if "--bits" in sys.argv else "snr"
    json.dump(res, open(f"reports/results/{out}.json", "w"), indent=1)

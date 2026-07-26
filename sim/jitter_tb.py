#!/usr/bin/env python3
"""Clock-jitter susceptibility of the modulator (tier 0), closing
DESIGN.md open item 2's sub-item: instead of waiting for a measured
PolarFire->TT jitter number, measure the loop's susceptibility curve and
show the margin against any plausible source.

Mechanism (why jitter matters at all with an RZ DAC): the feedback
charge per cycle is I_DAC * pulse_width, so edge timing noise modulates
the feedback charge bit-by-bit -- an UNSHAPED error injected at the
input summing node. Per-edge Gaussian jitter (sigma each, independent
edges) gives per-cycle relative width noise:

  RZ  (width TS/2, 2 jittered edges): e_i = y_i * (df_i - dr_i)/(TS/2)
  NRZ (width TS, error only at bit transitions -- a shifted boundary
       trades charge between adjacent opposite bits):
                                      e_i = (y_{i-1} - y_i) * d_i/TS

so RZ carries ~4x the noise power (2x amplitude sensitivity) of NRZ at
50% transition density -- the "2x jitter cost" accepted in the RZ
decision (DESIGN.md 2026-07-11). White in-band floors, FS = +-1 units:

  P_rz = 2 sigma^2/(TS/2)^2 / OSR      P_nrz ~ 2 sigma^2/TS^2 / OSR

Predicted 3 dB knees (jitter noise = quantization floor): precision
path (66 dB floor, OSR 250) sigma ~ 24 ps RMS; fast path (39 dB floor,
OSR 25) sigma ~ 170 ps RMS. The sweep below measures both.

Verdict scale: FPGA-output clock jitter is single-digit ps RMS
(PolarFire SoC CCC/global-buffer class), 5-10x under the precision
knee and ~50x under the fast knee.

ACCEPT gates on the extrapolated jitter-only floor at 10 ps RMS, not
on a direct baseline-vs-10ps subtraction: short-window precision SNDR
scatters +-1.5 dB from pattern-noise luck (the same statistics that
force 2^20-bit tier-0 runs), which swamps a ~1 dB effect. Instead the
jitter-only floor is measured at the largest sigma (power-subtracting
the jitter-free baseline; 30+ dB above scatter there) and slid back
at the verified 20 dB/decade to the gate point. Gates: >= 72 dB
(precision) and >= 45 dB (fast) -- 6 dB under the long-run
quantization floors (66 / 39 dB), i.e. <= 1 dB SNDR cost at a clock
10x worse than an FPGA output.

Usage: python3 sim/jitter_tb.py [--quick]   (2^20 bits; --quick 2^18)
Writes reports/results/jitter.json.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import params as P
from sim.snr import sndr

SIGMAS_PS = [0.0, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0]
SEEDS = 3
GATE_SIGMA_PS = 10.0
GATE_FLOOR_DB = {"fast": 45.0, "precision": 72.0}
QUANT_FLOOR_DB = {"fast": 39.0, "precision": 66.0}   # long-run tier-0 floors


def modulate_jitter(n, sigma_s, dac="rz", amp=P.AMP / P.FS_IN, k=0.25,
                    sig_bin=None, dither=1e-3, seed=1):
    """Tier-0 loop (sim/tier0.py) + DAC pulse-width jitter, sigma_s RMS
    per edge. Same coefficient, delay, dither and seed as tier0."""
    if sig_bin is None:
        sig_bin = round(P.SIG_BIN / P.NFFT * n)
    rng = np.random.default_rng(seed)
    u = amp * np.sin(2 * np.pi * sig_bin * np.arange(n) / n)
    if dither:
        u = u + dither * rng.standard_normal(n)
    jrng = np.random.default_rng(seed + 1)
    if dac == "rz":
        # two independent edges per pulse; relative width error on y_i
        w = jrng.standard_normal(n) * np.sqrt(2) * sigma_s / (P.TS / 2)
    else:
        # one boundary per period; charge trade at transitions only
        w = jrng.standard_normal(n) * sigma_s / P.TS
    v, yk, ykk = 0.0, 1.0, 1.0
    y = np.empty(n)
    for i in range(n):
        if dac == "rz":
            fb = yk * (1.0 + w[i])
        else:
            fb = yk + (ykk - yk) * w[i]
        v += k * (u[i] - fb)
        ykk = yk
        yk = 1.0 if v >= 0 else -1.0
        y[i] = yk
    return y, sig_bin


def main():
    n = 1 << 18 if "--quick" in sys.argv else 1 << 20
    paths = [("fast", P.OSR_FAST), ("precision", P.OSR_PREC)]
    res = {"nbits": n, "fs_hz": P.FS, "sigmas_ps": SIGMAS_PS, "dac": {}}
    print(f"tier-0 jitter sweep, {n} bits, RZ vs NRZ, per-edge RMS sigma")
    print(f"{'sigma':>8s} " + " ".join(f"{d}/{p:<9s}" for d in ("rz", "nrz")
                                       for p, _ in paths))
    table = {}
    for d in ("rz", "nrz"):
        table[d] = {p: [] for p, _ in paths}
        for s_ps in SIGMAS_PS:
            runs = {p: [] for p, _ in paths}
            for seed in range(1, 2 * SEEDS, 2):   # seed+1 is the jitter rng
                bits, sb = modulate_jitter(n, s_ps * 1e-12, dac=d, seed=seed)
                for p, osr in paths:
                    runs[p].append(sndr(bits, osr, sb))
            for p, _ in paths:
                table[d][p].append(round(float(np.median(runs[p])), 1))
        res["dac"][d] = table[d]
    for i, s_ps in enumerate(SIGMAS_PS):
        row = " ".join(f"{table[d][p][i]:12.1f}" for d in ("rz", "nrz")
                       for p, _ in paths)
        print(f"{s_ps:6.0f}ps {row}")

    ok = True
    res["gate"] = {"sigma_ps": GATE_SIGMA_PS, "checks": {}}
    for p, _ in paths:
        base, worst = table["rz"][p][0], table["rz"][p][-1]
        jit_pow = 10 ** (-worst / 10) - 10 ** (-base / 10)
        jit_db = -10 * np.log10(jit_pow)          # jitter-only, at max sigma
        floor = jit_db + 20 * np.log10(SIGMAS_PS[-1] / GATE_SIGMA_PS)
        good = floor >= GATE_FLOOR_DB[p]
        ok &= good
        # knee: per-edge sigma where jitter noise equals the quantization
        # floor (the datasheet number; -20 dB/decade from the gate point)
        knee = GATE_SIGMA_PS * 10 ** ((floor - QUANT_FLOOR_DB[p]) / 20)
        res["gate"]["checks"][p] = {"jitter_floor_db": round(float(floor), 1),
                                    "limit_db": GATE_FLOOR_DB[p],
                                    "knee_ps": round(float(knee)),
                                    "ok": bool(good)}
        print(f"  rz {p}: jitter-only floor at {GATE_SIGMA_PS:.0f} ps = "
              f"{floor:.1f} dB (gate >= {GATE_FLOOR_DB[p]:.0f}), knee "
              f"{knee:.0f} ps {'ok' if good else 'FAIL'}")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(res, open("reports/results/jitter.json", "w"), indent=1)
    print("ACCEPT" if ok else "REJECT -- jitter susceptibility above gate")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

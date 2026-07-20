#!/usr/bin/env python3
"""Output drivers (tier 2): the 3.3 V bitstream Q/QB -> TinyTapeout's
1.8 V digital outputs uo[0]/uo[1].

Per the IO decisions (DESIGN.md 2026-07-19): plain complementary CMOS
outputs, received differentially by the FPGA ("pseudo-LVDS"); no demux,
no true LVDS.

Level-DOWN without gate overstress: a 3.3 V signal must never land on a
thin-oxide gate, so stage 1 is an inverter built from 5 V devices powered
from VDPWR (1.8 V) -- 3.3 V is legal on a 5 V gate, and the output swings
0-1.8 V. Thin-oxide inverters then buffer the drive. One cell, two
instances (Q and QB paths); the TT-side load is the internal mux input
(~modest); 500 fF is used as a conservative stand-in.

Measured: swing, prop delay, rise/fall, Q-vs-QB skew (the FPGA's
differential receiver cares), duty error, power; corners x VDPWR.

Usage: python3 sim/odrv_tb.py    (sizes in OSIZES below)
Writes reports/results/odrv.json.
"""

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.ota_tb import PDK_LIB, WUNIT

NF, PF = "sky130_fd_pr__nfet_g5v0d10v5", "sky130_fd_pr__pfet_g5v0d10v5"
NF18, PF18 = "sky130_fd_pr__nfet_01v8", "sky130_fd_pr__pfet_01v8"

OSIZES = dict(
    W_IN_N=5, W_IN_P=10, L5=0.5,   # stage 1: 5V devices on the 1.8V rail
    W_B1=5, W_B2=12, L18=0.35,     # thin-oxide buffer chain (W in um).
                                   # L=0.35 (not 0.15): the 0.44um
                                   # column pitch at L=0.15 cannot fit
                                   # a DRC-legal strap via pad; W
                                   # scaled to keep W/L
)

TPER = 20e-9


def m(w):
    return max(1, round(w / WUNIT))


def odrv_subckt(p):
    return f"""
.subckt odrv IN33 OUT18 VDD18 VSS
* stage 1: 5V-gate inverter on the 1.8V rail (3.3V-safe input)
X1N a IN33 VSS  VSS  {NF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_IN_N'])}
X1P a IN33 VDD18 VDD18 {PF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_IN_P'])}
* thin-oxide buffers
X2N b a VSS  VSS  {NF18} W={p['W_B1']} L={p['L18']} nf=1 m=1
X2P b a VDD18 VDD18 {PF18} W={p['W_B1'] * 2} L={p['L18']} nf=1 m=1
X3N OUT18 b VSS  VSS  {NF18} W={p['W_B2']} L={p['L18']} nf=1 m=1
X3P OUT18 b VDD18 VDD18 {PF18} W={p['W_B2'] * 2} L={p['L18']} nf=1 m=1
.ends
"""


def run_corner(p, corner, v18):
    deck = f"""* output driver TB ({corner}, VDD18={v18})
.lib {PDK_LIB} {corner}
{odrv_subckt(p)}
.options method=gear reltol=1e-4 vntol=1e-6 abstol=1e-12
V18 vdd18i 0 {v18}
R18 vdd18i vdd18 1
VQ qr 0 PULSE(0 3.3 5n 0.3n 0.3n 9.7n {TPER * 1e9:g}n)
RQ qr q33 10
VQB qbr 0 PULSE(3.3 0 5n 0.3n 0.3n 9.7n {TPER * 1e9:g}n)
RQB qbr qb33 10
XDQ q33 uo0 vdd18 0 odrv
XDB qb33 uo1 vdd18 0 odrv
CL0 uo0 0 500f
CL1 uo1 0 500f
.tran 0.01n 200n
.control
run
wrdata odrv_tb.csv v(q33) v(uo0) v(uo1) i(V18)
.endc
.end
"""
    open("spice/odrv_tb.spice", "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "odrv_tb.spice"], cwd="spice",
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-800:])
        sys.exit(1)
    d = np.loadtxt("spice/odrv_tb.csv")
    t, q33, uo0, uo1 = d[:, 0], d[:, 1], d[:, 3], d[:, 5]
    i18 = d[:, 7]

    def crossings(w, th, rising):
        s = (w > th).astype(int)
        idx = np.where(np.diff(s) == (1 if rising else -1))[0]
        return t[idx]

    settle = 50e-9
    hv = v18 / 2
    # stage-1 inverts twice more -> uo0 follows q33 (three inversions?
    # no: inverter chain of 3 -> uo0 is the COMPLEMENT of q33; uo1
    # complements qb33, so uo0/uo1 are still a complementary pair and
    # polarity is a naming choice at assembly. Measure uo0 against the
    # FALLING q33 edge accordingly.
    rq = crossings(q33, 1.65, True);  rq = rq[rq > settle]
    r0 = crossings(uo0, hv, False);   r0 = r0[r0 > settle]
    r1 = crossings(uo1, hv, True);    r1 = r1[r1 > settle]
    n = min(len(rq), len(r0), len(r1)) - 1
    td = np.mean([r0[np.searchsorted(r0, x)] - x for x in rq[:n]])
    skew = np.mean(np.abs(
        [r0[np.searchsorted(r0, x)] - r1[np.searchsorted(r1, x)]
         for x in rq[:n]]))
    f0 = crossings(uo0, hv, True); f0 = f0[f0 > settle]
    duty = np.mean([abs((f0[np.searchsorted(f0, x)] - x) / TPER)
                    for x in r0[:n - 1]])
    w = t > settle
    return dict(swing=[round(float(uo0[w].min()), 3),
                       round(float(uo0[w].max()), 3)],
                td_ns=round(td * 1e9, 3),
                skew_ps=round(skew * 1e12),
                duty_pct=round(duty * 100, 1),
                power_uw=round(abs(np.trapz(i18[w], t[w])
                                   / (t[w][-1] - t[w][0]) * v18) * 1e6))


def main():
    os.makedirs("spice", exist_ok=True)
    allr = {}
    print(f"{'corner':>7s} {'V18':>5s} {'swing':>12s} {'td':>7s} "
          f"{'skew':>7s} {'duty':>6s} {'pwr':>6s}")
    for corner in ("tt", "ss", "ff", "sf", "fs"):
        for v18 in (1.62, 1.8, 1.98) if corner in ("tt", "ss") else (1.8,):
            r = run_corner(OSIZES, corner, v18)
            allr[f"{corner}/{v18}"] = r
            print(f"{corner:>7s} {v18:5.2f} {r['swing'][0]:4.2f}-"
                  f"{r['swing'][1]:4.2f} V {r['td_ns']:6.2f}n "
                  f"{r['skew_ps']:5d}ps {r['duty_pct']:5.1f}% "
                  f"{r['power_uw']:5d}u")
    ok = all(r["swing"][0] < 0.05 and r["swing"][1] > 0.95 * 1.62
             and r["td_ns"] < 5 and r["skew_ps"] < 1000
             and abs(r["duty_pct"] - 50) < 3 for r in allr.values())
    print("ACCEPT" if ok else "REJECT -- resize/tune")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(dict(ok=bool(ok), corners=allr, sizes=OSIZES),
              open("reports/results/odrv.json", "w"), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

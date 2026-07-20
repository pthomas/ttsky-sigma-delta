#!/usr/bin/env python3
"""Clock level shifter (tier 2): TinyTapeout's 1.8 V clock -> the 3.3 V
analog domain (comparator, DAC switches, retimer).

Topology: classic cross-coupled level shifter. A thin-oxide (01v8)
inverter on the 1.8 V rail makes the complement; two 5 V NMOS pulldowns
(driven at 1.8 V swing -- Vgs 1.8 against Vth ~0.8 is plenty) fight a
weak cross-coupled 5 V PMOS pair on the 3.3 V rail; 5 V inverters buffer
both output phases.

What matters for the modulator: full-rail swing, propagation delay well
under the half-period, and above all DUTY-CYCLE fidelity -- the RZ DAC
pulse width IS the clk-high time. A corner-static duty error is a pure
bit-independent loop-coefficient (gain) shift -- the error class the
tier-1 knees measured as benign -- so the gate is 3% static duty (~6%
gain). What must stay at zero is BIT-DEPENDENT width variation; the
shifter is deterministic and pattern-blind by construction.

Measured: swing, rise/fall prop delay, duty error, corners (device
corners x VDPWR 1.62/1.8/1.98), power.

Usage: python3 sim/lvl_tb.py    (sizes in LSIZES below)
Writes reports/results/lvl.json.
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

LSIZES = dict(
    W_PD=40,            # 5V NMOS pulldowns (must win the contention)
    W_XC=10, L_XC=0.5,  # cross-coupled 5V PMOS (weak vs pulldowns)
    W_BUF=10,           # 5V output inverters
    L5=0.5,
)

TPER = 20e-9


def m(w):
    return max(1, round(w / WUNIT))


def lvl_subckt(p):
    return f"""
.subckt lvl CLK18 CLK33 CLKB33 VDD18 VDD33 VSS
* 1.8 V complement (thin-oxide; single wide fingers, L=0.35 --
* L=0.15's 0.44um column pitch can't fit a DRC-legal strap via)
XIN nb18 CLK18 VSS VSS {NF18} W=5 L=0.35 nf=1 m=1
XIP nb18 CLK18 VDD18 VDD18 {PF18} W=10 L=0.35 nf=1 m=1
* contention stage: strong 5V NMOS pulldowns vs weak cross-coupled PMOS
XN1 n1 CLK18 VSS VSS {NF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_PD'])}
XN2 n2 nb18  VSS VSS {NF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_PD'])}
XP1 n1 n2 VDD33 VDD33 {PF} W={WUNIT} L={p['L_XC']} nf=1 m={m(p['W_XC'])}
XP2 n2 n1 VDD33 VDD33 {PF} W={WUNIT} L={p['L_XC']} nf=1 m={m(p['W_XC'])}
* 5V output buffers (n1 low when CLK18 high -> CLK33 follows CLK18)
XB1N CLK33 n1 VSS VSS {NF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_BUF'])}
XB1P CLK33 n1 VDD33 VDD33 {PF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_BUF'])}
XB2N CLKB33 n2 VSS VSS {NF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_BUF'])}
XB2P CLKB33 n2 VDD33 VDD33 {PF} W={WUNIT} L={p['L5']} nf=1 m={m(p['W_BUF'])}
.ends
"""


def run_corner(p, corner, v18):
    deck = f"""* level shifter TB ({corner}, VDD18={v18})
.lib {PDK_LIB} {corner}
{lvl_subckt(p)}
.options method=gear reltol=1e-4 vntol=1e-6 abstol=1e-12
V18 vdd18i 0 {v18}
R18 vdd18i vdd18 1
V33 vdd33i 0 3.3
R33 vdd33i vdd33 1
VCK clkr 0 PULSE(0 {v18} 5n 0.2n 0.2n 9.8n {TPER * 1e9:g}n)
RCK clkr clk18 10
XL clk18 clk33 clkb33 vdd18 vdd33 0 lvl
* realistic load: comparator clock pin + DFF + DAC switch gates ~ 100 fF
CL1 clk33 0 100f
CL2 clkb33 0 100f
.tran 0.01n 200n
.control
run
wrdata lvl_tb.csv v(clk18) v(clk33) i(V33)
.endc
.end
"""
    open("spice/lvl_tb.spice", "w").write(deck)
    r = subprocess.run(["ngspice", "-b", "lvl_tb.spice"], cwd="spice",
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-800:])
        sys.exit(1)
    d = np.loadtxt("spice/lvl_tb.csv")
    t, c18, c33, i33 = d[:, 0], d[:, 1], d[:, 3], d[:, 5]

    def crossings(w, th, rising):
        s = (w > th).astype(int)
        e = np.diff(s)
        idx = np.where(e == (1 if rising else -1))[0]
        return t[idx]

    settle = 50e-9
    r18 = crossings(c18, v18 / 2, True);  r18 = r18[r18 > settle]
    f18 = crossings(c18, v18 / 2, False); f18 = f18[f18 > settle]
    r33 = crossings(c33, 1.65, True);     r33 = r33[r33 > settle]
    f33 = crossings(c33, 1.65, False);    f33 = f33[f33 > settle]
    n = min(len(r18), len(r33), len(f18), len(f33)) - 1
    td_r = np.mean([r33[np.searchsorted(r33, x)] - x for x in r18[:n]])
    td_f = np.mean([f33[np.searchsorted(f33, x)] - x for x in f18[:n]])
    duty_in = np.mean(f18[:n] - r18[:n]) / TPER
    duty_out = np.mean(f33[:n] - r33[:n]) / TPER
    w = t > settle
    return dict(swing=[round(float(c33[w].min()), 3),
                       round(float(c33[w].max()), 3)],
                td_rise_ns=round(td_r * 1e9, 3),
                td_fall_ns=round(td_f * 1e9, 3),
                duty_err_pct=round((duty_out - duty_in) * 100, 2),
                power_uw=round(abs(np.trapz(i33[w], t[w])
                                   / (t[w][-1] - t[w][0]) * 3.3) * 1e6))


def main():
    os.makedirs("spice", exist_ok=True)
    allr = {}
    print(f"{'corner':>7s} {'V18':>5s} {'swing':>13s} {'td_r':>7s} "
          f"{'td_f':>7s} {'duty':>7s} {'pwr':>6s}")
    for corner in ("tt", "ss", "ff", "sf", "fs"):
        for v18 in (1.62, 1.8, 1.98) if corner in ("tt", "ss") else (1.8,):
            r = run_corner(LSIZES, corner, v18)
            allr[f"{corner}/{v18}"] = r
            print(f"{corner:>7s} {v18:5.2f} {r['swing'][0]:5.2f}-"
                  f"{r['swing'][1]:5.2f} V {r['td_rise_ns']:6.2f}n "
                  f"{r['td_fall_ns']:6.2f}n {r['duty_err_pct']:6.2f}% "
                  f"{r['power_uw']:5d}u")
    ok = all(r["swing"][0] < 0.05 and r["swing"][1] > 3.25
             and max(r["td_rise_ns"], r["td_fall_ns"]) < 2.0
             and abs(r["duty_err_pct"]) < 3.0 for r in allr.values())
    print("ACCEPT" if ok else "REJECT -- resize/tune")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(dict(ok=bool(ok), corners=allr, sizes=LSIZES),
              open("reports/results/lvl.json", "w"), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

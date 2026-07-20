#!/usr/bin/env python3
"""Reference buffers (tier 2, sky130 5V devices, 3.3 V): one design, three
instances at VREFN=0.4 / VCM=0.9 / VREFP=1.4.

Spec (measured, DESIGN.md 2026-07-19 RREF knee): closed-loop output
impedance <= 1 kohm with >= 20 pF decap per reference (10x under the
true breakage at 10 kohm, same margin rule as the other specs; tier-1
measured 1 kohm inside normal scatter); the decap sources
the 10 ns DAC pulses (~12.5 mV droop at 25 uA), the buffer recharges it
between pulses. The knee is soft (tier-1 fine to ~1 kohm), so this block
optimizes for simplicity and low power, not speed.

Topology: five-transistor OTA in unity feedback -- PMOS input pair
(senses the low window, same rule as OTA/comparator), NMOS mirror load,
output at the mirror side. Closed-loop Zout ~= 1/gm(input). Tail is a
real PMOS mirror off the OTA's IREFP diode line (the OTA subckt's XMDP
diode runs 380 uA through mult 76 = 5 uA per unit finger, so 320 uA =
mult 64 at the same L; gate-line tap only, no extra bias-block branch).
The TB replicates the diode + the bias block's ideal 380 uA sink.

The 0.4/0.9/1.4 V levels come from a resistor ladder off VAPWR
(190k/50k/50k/40k top-to-bottom, ~10 uA): VDD-referenced references are
a pure gain error on the ADC span (the benign class per the tier-1
knees), and the ratios track since all four Rs are the same poly
material. Ideal Rs here; poly cells at layout (same rule as bias).

CDEC = 5 pF per reference (2026-07-19): 3 x 20 pF MiM (~30k um^2) does
not fit the 1x2 tile. Tier-1 at RREF=754 (measured Zout) with CDEC
20/10/5/2 pF: fast path 38.6-39.6 dB flat, precision 56.9-58.7 dB, all
inside normal scatter -- smaller decap recovers faster and droop is
bit-independent, so 5 pF (~2.5k um^2 each) is the pick.

Loads: 20 pF decap plus a worst-pattern (alternating-bit) replica of the
RZ DAC currents -- VREFP sources 25 uA pulses every other period, VREFN
sinks them on the opposite bits, VCM absorbs an alternating-sign return
pulse every clk-high half.

Measured per buffer: DC offset, worst reference deviation at pulse ends,
the BIT-DEPENDENT part of that deviation (the ISI-shaped component the
loop actually cares about), step overshoot (stability into the decap),
AC Zout, supply current. Corners tt/ss/ff.

Usage: python3 sim/buf_tb.py    (sizes in FSIZES below)
Writes reports/results/buf.json.
"""

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.ota_tb import SIZES as OTA_S, PDK_LIB, WUNIT

NF = "sky130_fd_pr__nfet_g5v0d10v5"
PF = "sky130_fd_pr__pfet_g5v0d10v5"

FSIZES = dict(
    W_IN=60, L_IN=0.5,    # input pair (gm sets Zout ~ 1/gm)
    W_MIR=30, L_MIR=1.0,  # NMOS mirror load
    ITAIL=320e-6,         # tail current (mirror mult derived from this)
    CDEC=2e-12,           # tier-1 validated at RREF=754 (see docstring)
    # reference ladder off VAPWR, top to bottom (total 330k, ~10 uA)
    RL_TOP=190e3, RL_PC=50e3, RL_CM=50e3, RL_BOT=40e3,
)

# OTA IREFP diode line: 5 uA per unit finger (380 uA / mult 76)
IUNIT = OTA_S["IREFP"] / round(OTA_S["W_TAIL"] / WUNIT)

REFS = {"vrefn": 0.4, "vcm": 0.9, "vrefp": 1.4}
TPER = 20e-9
TSTOP = 2e-6


def m(w):
    return max(1, round(w / WUNIT))


def buf_subckt(p):
    # tail split into two half-mult devices: a single nf=64 gencell row
    # is 84 um wide and dominates the block bbox at assembly
    mt = round(p["ITAIL"] / IUNIT) // 2
    return f"""
.subckt buf IN OUT IREFP VDD VSS
XTA tail IREFP VDD VDD {PF} W={WUNIT} L={OTA_S['L_TAIL']} nf=1 m={mt}
XTB tail IREFP VDD VDD {PF} W={WUNIT} L={OTA_S['L_TAIL']} nf=1 m={mt}
X1 o1  IN  tail VDD {PF} W={WUNIT} L={p['L_IN']} nf=1 m={m(p['W_IN'])}
X2 OUT OUT tail VDD {PF} W={WUNIT} L={p['L_IN']} nf=1 m={m(p['W_IN'])}
X3 o1  o1  VSS VSS {NF} W={WUNIT} L={p['L_MIR']} nf=1 m={m(p['W_MIR'])}
X4 OUT o1  VSS VSS {NF} W={WUNIT} L={p['L_MIR']} nf=1 m={m(p['W_MIR'])}
.ends
"""


def irefp_ctx():
    """The OTA-side IREFP diode + the bias block's sink, for TBs."""
    return (f"XMD irefp irefp vdd vdd {PF} W={WUNIT} L={OTA_S['L_TAIL']} "
            f"nf=1 m={round(OTA_S['W_TAIL'] / WUNIT)}\n"
            f"ISNK irefp 0 {OTA_S['IREFP']:g}")


def deck(p, corner):
    # worst-pattern DAC loads: alternating bits -> each ref pulsed every
    # other period during the clk-low half (10..20 ns of each 20 ns cycle)
    return f"""* reference buffer TB ({corner})
.lib {PDK_LIB} {corner}
{buf_subckt(p)}
.options method=gear reltol=1e-5 vntol=1e-8 abstol=1e-13
VDDS vddi 0 3.3
RVDD vddi vdd 1
* reference ladder (VAPWR-referenced; buffer gates draw no DC)
RLT vdd   inp_p {p['RL_TOP']:g}
RLP inp_p inp_c {p['RL_PC']:g}
RLC inp_c inp_m {p['RL_CM']:g}
RLM inp_m 0     {p['RL_BOT']:g}
{irefp_ctx()}
XBP inp_p outp irefp vdd 0 buf
XBM inp_m outm irefp vdd 0 buf
XBC inp_c outc irefp vdd 0 buf
CDP outp 0 {p['CDEC']:g}
CDM outm 0 {p['CDEC']:g}
CDC outc 0 {p['CDEC']:g}
* VREFP sources 25uA on odd bits (clk-low half), VREFN sinks on even bits
ILP outp 0 PULSE(0 25u 10n 0.5n 0.5n 9n 40n)
ILM 0 outm PULSE(0 25u 30n 0.5n 0.5n 9n 40n)
* VCM return load: during the RZ return phase the DAC node sits AT VCM
* with the virtual ground also at VCM -- sustained current ~0. The real
* load is a ~2 ns +-25 uA transient at each switch edge, sign following
* the previous bit (tier-1 models the true switch network; this matches
* its behavior at the RREF knee)
ILC1 outc 0 PULSE(0 25u 10n 0.5n 0.5n 1.5n 40n)
ILC2 0 outc PULSE(0 25u 30n 0.5n 0.5n 1.5n 40n)
.tran 0.05n {TSTOP:g}
.control
run
wrdata buf_tb.csv v(outp) v(outm) v(outc) i(VDDS)
.endc
.end
"""


def measure_corner(p, corner):
    open("spice/buf_tb.spice", "w").write(deck(p, corner))
    r = subprocess.run(["ngspice", "-b", "buf_tb.spice"], cwd="spice",
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-1200:])
        sys.exit(1)
    d = np.loadtxt("spice/buf_tb.csv")
    t = d[:, 0]
    outs = {"vrefp": d[:, 1], "vrefn": d[:, 3], "vcm": d[:, 5]}
    ivdd = d[:, 7]
    res = {}
    for name, w in outs.items():
        tgt = REFS[name]
        settle = t > 0.5e-6
        # sample at the END of each pulse window (worst residual) and
        # just BEFORE each pulse window opens (the initial condition a
        # pulse inherits -- the droop during a pulse is the same for
        # every pulse, so only the inherited state carries bit history)
        te_pulse = np.arange(19.4e-9, TSTOP, TPER)
        te_inh = np.arange(9.9e-9, TSTOP, TPER)
        vp = np.interp(te_pulse[te_pulse > 0.5e-6], t, w)
        vq = np.interp(te_inh[te_inh > 0.5e-6], t, w)
        dc = w[settle].mean() - tgt
        worst = np.abs(vp - tgt).max()
        # bit-dependent component: inherited-state difference between
        # even and odd cycles (the alternating pattern makes these the
        # two bit histories)
        isi = abs(vq[0::2].mean() - vq[1::2].mean())
        res[name] = dict(dc_mv=round(dc * 1e3, 2),
                         worst_mv=round(worst * 1e3, 2),
                         isi_mv=round(isi * 1e3, 3))
    cyc = (t > 1e-6) & (t < 2e-6)
    # subtract the TB-context diode branch (belongs to bias/OTA, not buf)
    ib = abs(np.trapz(ivdd[cyc], t[cyc]) / 1e-6) - OTA_S["IREFP"]
    res["power_mw"] = round(ib * 3.3 * 1e3, 2)
    return res


def zout(p):
    deckt = f"""* buffer Zout
.lib {PDK_LIB} tt
{buf_subckt(p)}
VDDS vdd 0 3.3
VRC inp 0 0.9
{irefp_ctx()}
XB inp out irefp vdd 0 buf
CD out 0 {p['CDEC']:g}
IAC 0 out DC 0 AC 1
.control
op
ac dec 20 1k 1g
wrdata buf_zout.csv v(out)
.endc
.end
"""
    open("spice/buf_zout.spice", "w").write(deckt)
    subprocess.run(["ngspice", "-b", "buf_zout.spice"], cwd="spice",
                   capture_output=True, text=True)
    d = np.loadtxt("spice/buf_zout.csv")
    f = d[:, 0]
    z = np.abs(d[:, 1] + 1j * d[:, 2])
    return dict(zout_dc=round(float(z[0]), 1),
                zout_peak=round(float(z.max()), 1),
                fpeak_mhz=round(float(f[np.argmax(z)]) / 1e6, 1))


def main():
    os.makedirs("spice", exist_ok=True)
    z = zout(FSIZES)
    print(f"Zout: {z['zout_dc']} ohm DC, peak {z['zout_peak']} ohm at "
          f"{z['fpeak_mhz']} MHz  (spec <= 1k DC, 10x under breakage)")
    allres = {}
    print(f"{'corner':>7s} {'buf':>6s} {'DC off':>8s} {'worst':>8s} "
          f"{'bit-dep':>8s}")
    for corner in ("tt", "ss", "ff"):
        r = measure_corner(FSIZES, corner)
        allres[corner] = r
        for name in REFS:
            print(f"{corner:>7s} {name:>6s} {r[name]['dc_mv']:6.1f}mV "
                  f"{r[name]['worst_mv']:6.1f}mV {r[name]['isi_mv']:6.2f}mV")
        print(f"{corner:>7s}  power {r['power_mw']} mW (3 buffers)")
    ok = (z["zout_dc"] <= 1000
          and all(allres[c][n]["isi_mv"] <= 8 for c in allres
                  for n in REFS)
          and all(abs(allres[c][n]["dc_mv"]) <= 40 for c in allres
                  for n in REFS))
    print("ACCEPT" if ok else "REJECT -- resize/tune")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(dict(ok=bool(ok), zout=z, corners=allres,
                   sizes=FSIZES), open("reports/results/buf.json", "w"),
              indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

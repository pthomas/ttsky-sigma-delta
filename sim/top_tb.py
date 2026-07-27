#!/usr/bin/env python3
"""Extracted-top acceptance: shortened modulator transient on the PEX
netlist (STATUS step 5).

Runs the FULL first-order modulator (spice/sd_top_pex.spice from
tools/pex_top.py -- every block transistor-level plus 2.9 pF of
extracted top-level wiring parasitics) for NFFT + NSETTLE clock
cycles, samples the UO0 bitstream at mid-period, and computes the
fast-path SNDR with sim/snr.py's estimator. This is the sanity gate
from the campaign plan -- >= 512 bits, fast path >= 35 dB -- not the
full tier-1-length characterization (4096 bits of transistor-level
PEX transient would run for hours; the 512-bit window resolves the
fast band at 10 FFT bins which is enough to catch a broken loop,
wrong DAC polarity, or a dead reference, the failure modes layout
could have introduced).

Usage: python3 sim/top_tb.py [--bits N]   (default 2048)
Writes reports/results/top_pex.json. Exits nonzero below the gate.
"""

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import params as P
from sim.snr import sndr

PDK_LIB = os.environ.get(
    "PDK_ROOT", "/home/nvme/pdk") + \
    "/sky130A/libs.tech/ngspice/sky130.lib.spice"

NSETTLE = 64
# Gate rationale (2026-07-25): 512-bit windows scatter +-3 dB
# run-to-run, so the acceptance runs a 2048-bit window (41 in-band
# bins). After the loop rephase the extracted top measures
# 38.3-40.7 dB across three tone placements (tier-1 band 36.4-38.0);
# the gate at 36 sits 2 dB under the measured minimum and far above
# any catastrophic-failure signature (<20 dB).
GATE_DB = 36.0


def deck(nfft, sig_bin, corner="tt", idealclk33=False,
         idealrefs=False, golden=False, ramp=None, vapwr=3.3,
         temp=27.0):
    tstop = (nfft + NSETTLE) * P.TS
    fin = sig_bin * P.FS / nfft
    # Diagnostic (--idealclk33): overpower the level shifter's output
    # net (extracted name dff_layout_0/CLK) with an ideal fast-edge
    # 3.3 V clock. Isolates the decision-path-noise mechanism: if SNDR
    # recovers, the on-chip clk33 slew (comparator aperture + S_MID
    # gate) is the culprit; if not, look at the q33/clkb33-driven DAC
    # switches. The 0.4 ns delay approximates the level shifter's own
    # propagation so the RZ window barely moves.
    force = (f"VCLKI xdut.dff_layout_0/clk 0 PULSE(0 3.3 0.4n 0.1n "
             f"0.1n {P.TS/2*1e9:.1f}n {P.TS*1e9:.1f}n)\n"
             if idealclk33 else "")
    # Diagnostic (--idealrefs): pin the three references to ideal DC
    # sources (extracted net names: bufp/bufc/bufn outputs). If SNDR
    # recovers, the mechanism is data-dependent reference droop
    # through the buffers' ~750 ohm output impedance.
    if idealrefs:
        force += (f"VRP xdut.buf_layout_2/out 0 {P.VREFP:g}\n"
                  f"VCMF xdut.ota_layout_0/inp 0 {P.VCM:g}\n"
                  f"VRN xdut.buf_layout_0/out 0 {P.VREFN:g}\n")
    netfile = ("golden/top.spice" if golden else "sd_top_pex.spice")
    # the golden and extracted subckts declare different port orders
    dut = ("XDUT ua0 ua1 uo0 uo1 clk vdpwr vapwr vgnd sd_top" if golden
           else "XDUT ua0 uo0 uo1 clk vdpwr ua1 vgnd vapwr sd_top")
    # --ramp: cold start from 0 V supplies. Every plain .tran starts
    # from ngspice's DC operating point, which silently assumes the
    # bias core lands in its good state -- the classic masked failure
    # is a startup circuit that never fires on a real supply ramp.
    # Both sequencing orders: the other rail comes up fast (100 ns),
    # the late rail ramps 0.2 -> 2.2 us; the clock and input drive
    # from t=0 (bench-realistic: FPGA up before the DUT supplies).
    if ramp == "analog-late":
        vap = "VAP vapwr 0 PWL(0 0 200n 0 2200n 3.3)"
        vdp = "VDP vdpwr 0 PWL(0 0 100n 1.8)"
    elif ramp == "digital-late":
        vap = "VAP vapwr 0 PWL(0 0 100n 3.3)"
        vdp = "VDP vdpwr 0 PWL(0 0 200n 0 2200n 1.8)"
    else:
        vap = f"VAP vapwr 0 {vapwr:g}"
        vdp = "VDP vdpwr 0 1.8"
    return f"""* sd_top PEX acceptance ({corner}, {nfft} bits{
        ', ramp ' + ramp if ramp else ''})
.lib {PDK_LIB} {corner}
.include {netfile}
.options method=gear reltol=1e-4 vntol=1e-6 abstol=1e-12
.temp {temp:g}
{vap}
{vdp}
VGN vgnd 0 0
VCLK clk 0 PULSE(0 1.8 0 0.2n 0.2n {P.TS/2*1e9:.1f}n {P.TS*1e9:.1f}n)
* input scales with VAPWR: references are ratiometric to the rail, and
* so is the bench source (test plan: DAC referenced to the VAPWR rail)
VIN ua0 0 SIN({P.VIN_MID*vapwr/3.3:g} {P.AMP*vapwr/3.3:g} {fin:g})
* pad-ish loads on the bitstream outputs
CU0 uo0 0 1p
CU1 uo1 0 1p
CA1 ua1 0 50f
{dut}
{force}.tran {P.TSTEP*1e9:g}n {tstop*1e9:.1f}n
.control
set num_threads=8
run
wrdata top_tb.csv v(uo0) v(clk) v(ua1)
.endc
.end
"""


def main():
    nfft = 2048
    if "--bits" in sys.argv:
        nfft = int(sys.argv[sys.argv.index("--bits") + 1])
    # odd bin inside the fast band (2048 -> 41 bins)
    sig_bin = 13
    if "--sigbin" in sys.argv:
        sig_bin = int(sys.argv[sys.argv.index("--sigbin") + 1])
    corner = "tt"
    if "--corner" in sys.argv:
        corner = sys.argv[sys.argv.index("--corner") + 1]
    gate = GATE_DB
    if "--gate" in sys.argv:
        gate = float(sys.argv[sys.argv.index("--gate") + 1])
    ideal = "--idealclk33" in sys.argv
    irefs = "--idealrefs" in sys.argv
    gold = "--golden" in sys.argv
    ramp = None
    if "--ramp" in sys.argv:
        ramp = sys.argv[sys.argv.index("--ramp") + 1]
        if "--bits" not in sys.argv:
            nfft = 512
    vapwr = 3.3
    if "--vapwr" in sys.argv:
        vapwr = float(sys.argv[sys.argv.index("--vapwr") + 1])
    temp = 27.0
    if "--temp" in sys.argv:
        temp = float(sys.argv[sys.argv.index("--temp") + 1])
    tag = ""
    if "--tag" in sys.argv:
        tag = "_" + sys.argv[sys.argv.index("--tag") + 1]
    elif corner != "tt":
        tag = "_" + corner
    elif vapwr != 3.3:
        tag = f"_v{vapwr*10:.0f}"
    elif temp != 27.0:
        tag = f"_t{temp:g}"
    os.makedirs("spice", exist_ok=True)
    open("spice/top_tb.spice", "w").write(
        deck(nfft, sig_bin, corner, ideal, irefs, gold, ramp, vapwr,
             temp))
    r = subprocess.run(["ngspice", "-b", "top_tb.spice"], cwd="spice",
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists("spice/top_tb.csv"):
        print(r.stderr[-2000:])
        sys.exit(1)
    d = np.loadtxt("spice/top_tb.csv")
    t, uo0, ua1 = d[:, 0], d[:, 1], d[:, 5]

    if ramp:
        # aliveness, not SNDR: after the late rail tops out, the loop
        # must modulate -- toggling bitstream, sane ones density, and
        # an integrator inside the rails (a latched-off bias shows a
        # railed integrator and a frozen bitstream)
        k = np.arange(nfft - 256, nfft)
        ts = (k + NSETTLE + 0.5) * P.TS
        bits = np.where(np.interp(ts, t, uo0) > 0.9, 1.0, -1.0)
        ones = (bits > 0).mean()
        trans = int(np.abs(np.diff(bits)).sum() / 2)
        late = t > (t[-1] - 256 * P.TS)
        swing = (float(ua1[late].min()), float(ua1[late].max()))
        ok = (0.2 < ones < 0.8 and trans >= 20
              and 0.1 < swing[0] and swing[1] < 1.8)
        print(f"sd_top cold start ({ramp}): last-256-bit ones density "
              f"{ones:.3f}, {trans} transitions, integrator "
              f"{swing[0]:.2f}-{swing[1]:.2f} V")
        print("ALIVE" if ok else "DEAD -- startup failure")
        os.makedirs("reports/results", exist_ok=True)
        json.dump(dict(ok=bool(ok), mode=ramp, nfft=nfft,
                       ones_density=round(ones, 3), transitions=trans,
                       ua1_swing=[round(v, 3) for v in swing]),
                  open(f"reports/results/top_ramp_{ramp}.json", "w"),
                  indent=1)
        sys.exit(0 if ok else 1)
    k = np.arange(NSETTLE, NSETTLE + nfft)
    ts = (k + 0.5) * P.TS
    bits = np.where(np.interp(ts, t, uo0) > 0.9, 1.0, -1.0)
    ones = (bits > 0).mean()
    s = sndr(bits, P.OSR_FAST, sig_bin)
    # swing after the settle window: the first ~15 cycles rail during
    # startup (benign, discarded from the FFT too) and at cold reached
    # 3.33 V, which made the raw min/max useless as a health signal
    settled = t > NSETTLE * P.TS
    swing = (float(ua1[settled].min()), float(ua1[settled].max()))
    print(f"sd_top PEX: {nfft} bits, ones density {ones:.3f}, "
          f"integrator {swing[0]:.2f}-{swing[1]:.2f} V")
    print(f"fast path (OSR {P.OSR_FAST}): SNDR {s:.1f} dB "
          f"(gate >= {gate:g})")
    ok = s >= gate and 0.2 < ones < 0.8
    print("ACCEPT" if ok else "REJECT")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(dict(ok=bool(ok), nfft=nfft, sig_bin=sig_bin,
                   corner=corner, sndr_fast_db=round(s, 1),
                   ones_density=round(ones, 3),
                   ua1_swing=[round(v, 3) for v in swing]),
              open(f"reports/results/top_pex{tag}.json", "w"), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

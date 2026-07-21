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

Usage: python3 sim/top_tb.py [--bits N]   (default 512)
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
SIG_BIN = 3          # odd bin inside the fast band (NFFT=512 -> 10 bins)
GATE_DB = 35.0


def deck(nfft, corner="tt"):
    tstop = (nfft + NSETTLE) * P.TS
    fin = SIG_BIN * P.FS / nfft
    return f"""* sd_top PEX acceptance ({corner}, {nfft} bits)
.lib {PDK_LIB} {corner}
.include sd_top_pex.spice
.options method=gear reltol=1e-4 vntol=1e-6 abstol=1e-12
.temp 27
VAP vapwr 0 3.3
VDP vdpwr 0 1.8
VGN vgnd 0 0
VCLK clk 0 PULSE(0 1.8 0 0.2n 0.2n {P.TS/2*1e9:.1f}n {P.TS*1e9:.1f}n)
VIN ua0 0 SIN({P.VCM:g} {P.AMP:g} {fin:g})
* pad-ish loads on the bitstream outputs
CU0 uo0 0 1p
CU1 uo1 0 1p
CA1 ua1 0 50f
XDUT ua0 uo0 uo1 clk vdpwr ua1 vgnd vapwr sd_top
.tran {P.TSTEP*1e9:g}n {tstop*1e9:.1f}n
.control
set num_threads=8
run
wrdata top_tb.csv v(uo0) v(clk) v(ua1)
.endc
.end
"""


def main():
    nfft = 512
    if "--bits" in sys.argv:
        nfft = int(sys.argv[sys.argv.index("--bits") + 1])
    os.makedirs("spice", exist_ok=True)
    open("spice/top_tb.spice", "w").write(deck(nfft))
    r = subprocess.run(["ngspice", "-b", "top_tb.spice"], cwd="spice",
                       capture_output=True, text=True)
    if r.returncode or not os.path.exists("spice/top_tb.csv"):
        print(r.stderr[-2000:])
        sys.exit(1)
    d = np.loadtxt("spice/top_tb.csv")
    t, uo0, ua1 = d[:, 0], d[:, 1], d[:, 5]
    k = np.arange(NSETTLE, NSETTLE + nfft)
    ts = (k + 0.5) * P.TS
    bits = np.where(np.interp(ts, t, uo0) > 0.9, 1.0, -1.0)
    ones = (bits > 0).mean()
    s = sndr(bits, P.OSR_FAST, SIG_BIN)
    swing = (float(ua1.min()), float(ua1.max()))
    print(f"sd_top PEX: {nfft} bits, ones density {ones:.3f}, "
          f"integrator {swing[0]:.2f}-{swing[1]:.2f} V")
    print(f"fast path (OSR {P.OSR_FAST}): SNDR {s:.1f} dB "
          f"(gate >= {GATE_DB:g})")
    ok = s >= GATE_DB and 0.2 < ones < 0.8
    print("ACCEPT" if ok else "REJECT")
    os.makedirs("reports/results", exist_ok=True)
    json.dump(dict(ok=bool(ok), nfft=nfft, sndr_fast_db=round(s, 1),
                   ones_density=round(ones, 3),
                   ua1_swing=[round(v, 3) for v in swing]),
              open("reports/results/top_pex.json", "w"), indent=1)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

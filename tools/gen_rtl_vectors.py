#!/usr/bin/env python3
"""Extract the modulator bitstream from the last extracted-top
acceptance run (spice/top_tb.csv) into an RTL test vector.

Samples UO0 at mid-period exactly as sim/top_tb.py does, so the RTL
testbench decimates the same bits the chip's acceptance was judged
on: transistor-level analog in, AXI4-Lite register values out.

Writes rtl/tb/vectors/pex_bits.txt (one 0/1 per line, first line a
'# key=value ...' header). The vector is committed so the RTL tests
run without a spice installation.

Usage: python3 tools/gen_rtl_vectors.py   (after make topaccept)
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import params as P

NSETTLE = 64


def main():
    d = np.loadtxt("spice/top_tb.csv")
    t, uo0 = d[:, 0], d[:, 1]
    nfft = int(round(t[-1] / P.TS)) - NSETTLE
    k = np.arange(NSETTLE, NSETTLE + nfft)
    bits = (np.interp((k + 0.5) * P.TS, t, uo0) > 0.9).astype(int)
    # carry the tone placement if the acceptance json is around
    sig_bin = None
    try:
        sig_bin = json.load(open("reports/results/top_pex.json"))["sig_bin"]
    except Exception:
        pass
    os.makedirs("rtl/tb/vectors", exist_ok=True)
    out = "rtl/tb/vectors/pex_bits.txt"
    with open(out, "w") as f:
        f.write(f"# nfft={nfft} sig_bin={sig_bin} fs_hz={P.FS:g} "
                f"ones={bits.mean():.4f} source=spice/top_tb.csv\n")
        f.writelines(f"{b}\n" for b in bits)
    print(f"wrote {out}: {nfft} bits, ones density {bits.mean():.4f}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PEX: extract sd_top with parasitic capacitances for simulation.

Same flow as tools/pex_ota.py (fresh magic process, no writes back to
mag/ -- the writeall-force gotcha), C-only extraction (cthresh 0, no
resistance). Writes spice/sd_top_pex.spice with the sd_top subcircuit
(ports UA0 UO0 UO1 CLK VDPWR UA1 VGND VAPWR). Consumed by
sim/top_tb.py.

Usage: python3 tools/pex_top.py   (from repo root)
"""

import os
import re
import subprocess
import sys

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"

TCL = """
load sd_top
select top cell
expand
extract all
ext2spice cthresh 0
ext2spice hierarchy off
ext2spice subcircuit top on
ext2spice merge conservative
ext2spice -o ../spice/sd_top_pex.spice
quit -noprompt
"""


def main():
    os.makedirs("spice", exist_ok=True)
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=TCL, capture_output=True, text=True,
                       cwd="mag", timeout=1800,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    out = r.stdout + r.stderr
    if not os.path.exists("spice/sd_top_pex.spice"):
        print(out[-2000:])
        sys.exit(1)
    txt = open("spice/sd_top_pex.spice").read()
    ndev = len(re.findall(r"^X\d", txt, re.M))
    caps = re.findall(r"^C\d+ \S+ \S+\s+([0-9.]+)f", txt, re.M)
    ctot = sum(float(c) for c in caps) * 1e-15
    ports = re.search(r"^\.subckt (\S+) (.*)$", txt, re.M)
    print("PEX netlist: spice/sd_top_pex.spice")
    print(f"  devices: {ndev}, parasitic caps: {len(caps)} "
          f"(total {ctot*1e12:.2f} pF)")
    print(f"  .subckt {ports.group(1)} {ports.group(2)}")


if __name__ == "__main__":
    main()

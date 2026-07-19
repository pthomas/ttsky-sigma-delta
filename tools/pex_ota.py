#!/usr/bin/env python3
"""PEX: extract the OTA layout with parasitic capacitances for simulation.

Loads mag/ota_layout.mag in a fresh magic process (no writes back to mag/ --
see the writeall-force gotcha in DESIGN.md 2026-07-19), extracts with all
parasitic caps (cthresh 0: node-to-substrate and node-to-node coupling; no
resistance extraction in this pass), and writes spice/ota_pex.spice with
the ota_layout subcircuit. Consumed by `python3 sim/ota_tb.py --pex`.

Usage: python3 tools/pex_ota.py   (from repo root)
"""

import os
import re
import subprocess
import sys

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"

TCL = """
load ota_layout
select top cell
expand
extract all
ext2spice cthresh 0
ext2spice hierarchy off
ext2spice subcircuit top on
ext2spice merge conservative
ext2spice -o ../spice/ota_pex.spice
quit -noprompt
"""


def main():
    os.makedirs("spice", exist_ok=True)
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=TCL, capture_output=True, text=True,
                       cwd="mag", timeout=600,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    out = r.stdout + r.stderr
    if not os.path.exists("spice/ota_pex.spice"):
        print(out[-2000:])
        sys.exit(1)
    txt = open("spice/ota_pex.spice").read()
    ndev = len(re.findall(r"^X\d", txt, re.M))
    caps = re.findall(r"^C\d+ \S+ \S+\s+([0-9.]+)f", txt, re.M)
    ctot = sum(float(c) for c in caps) * 1e-15
    ports = re.search(r"^\.subckt (\S+) (.*)$", txt, re.M)
    print(f"PEX netlist: spice/ota_pex.spice")
    print(f"  subckt {ports.group(1)} ports: {ports.group(2)}")
    print(f"  {ndev} devices, {len(caps)} parasitic caps, "
          f"total {ctot*1e12:.2f} pF")


if __name__ == "__main__":
    main()

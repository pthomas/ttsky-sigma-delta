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


def canonicalize(path):
    """Make the netlist byte-stable across magic processes: ext2spice
    emits the parasitic cap lines in per-process hash order (ASLR) with
    ~0.01 aF accumulation jitter in the last digit, so the same layout
    produced a differently-ordered deck every run -- different matrix
    ordering in ngspice, different roundoff, a different transient
    trajectory (the cause of the 2026-07-31 nightly vapwr-3.0
    convergence abort). Sort caps by node pair, renumber, and round to
    1 aF; same rationale as tools/gds_datenorm.py for the GDS. Device
    lines have been observed order-stable; the nightly netlist drift
    check will catch it if that ever changes."""
    cap_re = re.compile(r"^C\d+ (\S+) (\S+) ([0-9.]+)([fpnu]?)$")
    to_ff = {"f": 1.0, "p": 1e3, "n": 1e6, "u": 1e9, "": 0.0}
    lines = open(path).read().splitlines()
    caps, out, slot = [], [], None
    for ln in lines:
        m = cap_re.match(ln)
        if not m:
            out.append(ln)
            continue
        if slot is None:
            slot = len(out)
        a, b, v, suf = m.groups()
        v = round(float(v) * to_ff[suf], 3)
        caps.append((*sorted((a, b)), v))
    block = [f"C{i} {a} {b} {v:g}{'f' if v else ''}"
             for i, (a, b, v) in enumerate(sorted(caps))]
    out[slot:slot] = block
    open(path, "w").write("\n".join(out) + "\n")


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
    canonicalize("spice/sd_top_pex.spice")
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

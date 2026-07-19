#!/usr/bin/env python3
"""Equivalence check: xschem-generated comparator vs sim/comp_tb.py.

Extracts .subckt comp from spice/comp_top.spice (xschem netlist of the
generated schematic) and runs the SAME race testbench on it via
sim.comp_tb.measure (quick grid). The xschem symbol pins are ordered
identically to the inline subckt (INP INM CLK Q QB ON1 ON2 VDD VSS), so
the decks are interchangeable. Passes if the xschem netlist decides
correctly everywhere and its tau / decision times / power track the
inline reference within tolerance.

Run via make compcheck (after tools/gen_comp_sch.py + xschem netlisting).
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.comp_tb import SIZES, measure

m = re.search(r"^\.subckt comp .*?^\.ends\b",
              open("spice/comp_top.spice").read(), re.M | re.S)
if not m:
    sys.exit("no .subckt comp in spice/comp_top.spice -- netlist "
             "comp_top.sch first")
ports = re.match(r"\.subckt comp (\S+(?: \S+)*)", m.group(0)).group(1)
want = "INP INM CLK Q QB ON1 ON2 VDD VSS"
if ports.upper() != want:
    sys.exit(f"port order drifted: {ports} (want {want}) -- comp.sym and "
             f"comp_tb.py must stay in sync")

print("=== xschem netlist ===")
x = measure(SIZES, quick=True, subckt=m.group(0), write_json=False)
print("\n=== inline reference ===")
r = measure(SIZES, quick=True, write_json=False)

ok = (x["ok"] and r["ok"]
      and abs(x["tau_ps"] - r["tau_ps"]) <= 0.25 * r["tau_ps"]
      and abs(x["worst_tdec_ns"] - r["worst_tdec_ns"])
      <= 0.15 * r["worst_tdec_ns"]
      and abs(x["power_uw"] - r["power_uw"]) <= 0.15 * r["power_uw"])
print(f"\nxschem : tau {x['tau_ps']} ps, worst {x['worst_tdec_ns']} ns, "
      f"{x['power_uw']} uW")
print(f"inline : tau {r['tau_ps']} ps, worst {r['worst_tdec_ns']} ns, "
      f"{r['power_uw']} uW")
print("MATCH" if ok else "MISMATCH -- investigate")
sys.exit(0 if ok else 1)

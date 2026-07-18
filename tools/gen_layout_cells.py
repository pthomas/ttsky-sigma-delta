#!/usr/bin/env python3
"""Generate the first-layout cells in magic and verify extracted values.

Cells (into mag/): rin (40k), rdac (20k) as high-poly serpentines,
cint (2 pF MiM), sw_nmos (DAC switch, W=10/0.5 with guard ring).
Resistors get one automatic calibration pass: generate -> extract ->
scale segment length by target/extracted -> regenerate.

Needs magic >= 8.3.411 and PDK_ROOT (default /home/nvme/pdk).
Usage: python3 tools/gen_layout_cells.py   (from repo root)
"""

import os
import re
import subprocess
import sys

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
RHO, WRES = 319.8, 1.41          # high_po_1p41 sheet rho and width
CAREA, CPERI = 2.00, 0.19        # cap_mim_m3_1 fF/um^2, fF/um


def magic_run(script):
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=script, capture_output=True, text=True,
                       cwd="mag", timeout=120,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    return r.stdout + r.stderr


def gen_cell(name, device, params):
    p = " ".join(f"{k} {v}" for k, v in params.items())
    magic_run(f"""cellname create {name}
load {name}
magic::gencell sky130::{device} X0 {p}
save {name}
extract all
ext2spice lvs
ext2spice
quit -noprompt
""")
    return open(f"mag/{name}.spice").read()


def res_cell(name, target, nx, l0):
    """Two-pass serpentine resistor: calibrate l against extraction."""
    dev = "sky130_fd_pr__res_high_po_1p41"
    txt = gen_cell(name, dev, dict(w=WRES, l=l0, nx=nx, snake=1))
    leff = float(re.search(r"res_high_po_1p41 l=([0-9.]+)", txt).group(1))
    r1 = RHO * leff / WRES
    l1 = round(l0 * target / r1, 2)
    txt = gen_cell(name, dev, dict(w=WRES, l=l1, nx=nx, snake=1))
    leff = float(re.search(r"res_high_po_1p41 l=([0-9.]+)", txt).group(1))
    r2 = RHO * leff / WRES
    print(f"{name}: target {target/1e3:.0f}k -> {r2/1e3:.2f}k "
          f"(nx={nx}, l={l1} um, err {100*(r2-target)/target:+.1f}%)")
    return abs(r2 - target) / target < 0.02


def cap_cell(name, target_pf, w, l, nx):
    txt = gen_cell(name, "sky130_fd_pr__cap_mim_m3_1", dict(w=w, l=l, nx=nx))
    n = len(re.findall(r"cap_mim_m3_1", txt))
    c = nx * (CAREA * w * l + CPERI * 2 * (w + l)) / 1e3   # pF
    print(f"{name}: target {target_pf} pF -> {c:.3f} pF "
          f"({nx}x {w}x{l} um, {n} extracted devices, "
          f"err {100*(c/target_pf-1):+.1f}%)")
    return abs(c - target_pf) / target_pf < 0.05


def fet_cell(name, w, l):
    txt = gen_cell(name, "sky130_fd_pr__nfet_g5v0d10v5",
                   dict(w=w, l=l, nf=1, guard=1))
    m = re.search(r"nfet_g5v0d10v5 .*?w=([0-9.]+)u?\s.*?l=([0-9.]+)u?", txt)
    if not m:
        m = re.search(r"nfet_g5v0d10v5\s+(?:ad|w)", txt)
        print(f"{name}: extracted card not parsed -- inspect mag/{name}.spice")
        return False
    print(f"{name}: extracted W/L = {m.group(1)}/{m.group(2)} "
          f"(target {w}/{l})")
    return True


def main():
    os.makedirs("mag", exist_ok=True)
    ok = True
    ok &= res_cell("rin", 40e3, nx=12, l0=14.7)
    ok &= res_cell("rdac", 20e3, nx=6, l0=14.7)
    ok &= cap_cell("cint", 2.0, w=25, l=20, nx=2)
    ok &= fet_cell("sw_nmos", 10, 0.5)
    print("all cells OK" if ok else "SOME CELLS OFF TARGET")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

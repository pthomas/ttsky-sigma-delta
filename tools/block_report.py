#!/usr/bin/env python3
"""Per-block report artifacts: 3D geometry dumps + schematic SVGs, plus
the COMBINED top-level (sd_top) geometry for the main-page viewer.

Generalizes tools/layout_report.py's geometry() to any cell (fresh
magic process, flatten to a transient cell, dump per-layer rects with
the sky130 z-stack) and gen_doc_figs.py's export_sch() to every block
schematic. Consumed by tools/gen_docs.py, which builds one sub-page
per block (public/blocks/<b>.html: metrics + schematic + its own 3D)
and points the main-page viewer at the combined top geometry.

Outputs:
  reports/results/<b>_geom.json    per-block 3D geometry
  reports/results/top_geom.json    combined sd_top geometry
  reports/results/figs/sch_<b>.svg per-block schematic

Usage: python3 tools/block_report.py   (from repo root)
"""

import json
import os
import re
import subprocess
import sys

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
FIGS = "reports/results/figs"

# (short name, mag cell, xschem schematic)
BLOCKS = [
    ("ota", "ota_layout", "ota"),
    ("comp", "comp_layout", "comp"),
    ("dff", "dff_layout", "dff"),
    ("bias", "bias_layout", "bias"),
    ("buf", "buf_layout", "buf"),
    ("lvl", "lvl_layout", "lvl"),
    ("odrv", "odrv_layout", "odrv"),
]

# sky130 process stack, um above substrate surface: (z_bottom, z_top,
# color). Superset of layout_report.py's STACK: the support blocks add
# thin-oxide devices, the passives add the high-poly resistor, and the
# top level adds met4/via3 and the MiM caps.
STACK = {
    "nwell":          (-0.40, 0.00, "#3a2a52"),
    "mvpdiff":        (0.00, 0.12, "#b06060"),
    "mvndiff":        (0.00, 0.12, "#6080b0"),
    "mvnsubdiff":     (0.00, 0.12, "#4a6a9a"),
    "mvpsubdiff":     (0.00, 0.12, "#9a5a5a"),
    "pdiff":          (0.00, 0.12, "#b06060"),
    "ndiff":          (0.00, 0.12, "#6080b0"),
    "nsubdiff":       (0.00, 0.12, "#4a6a9a"),
    "psubdiff":       (0.00, 0.12, "#9a5a5a"),
    "mvpdiffc":       (0.12, 0.94, "#c0a040"),
    "mvndiffc":       (0.12, 0.94, "#c0a040"),
    "mvnsubdiffcont": (0.12, 0.94, "#c0a040"),
    "mvpsubdiffcont": (0.12, 0.94, "#c0a040"),
    "pdiffc":         (0.12, 0.94, "#c0a040"),
    "ndiffc":         (0.12, 0.94, "#c0a040"),
    "nsubdiffcont":   (0.12, 0.94, "#c0a040"),
    "psubdiffcont":   (0.12, 0.94, "#c0a040"),
    "poly":           (0.32, 0.50, "#cc4444"),
    "npolyres":       (0.32, 0.50, "#e07050"),
    "ppolyres":       (0.32, 0.50, "#e07050"),
    "xpolycontact":   (0.50, 0.94, "#c0a040"),
    "polycont":       (0.50, 0.94, "#c0a040"),
    "viali":          (0.12, 0.94, "#c0a040"),
    "locali":         (0.94, 1.04, "#40b0b0"),
    "mcon":           (1.04, 1.38, "#c0c0c0"),
    "metal1":         (1.38, 1.74, "#4488dd"),
    "via1":           (1.74, 2.00, "#c0c0c0"),
    "metal2":         (2.00, 2.36, "#dd8844"),
    "via2":           (2.36, 2.79, "#c0c0c0"),
    "metal3":         (2.79, 3.63, "#44bb66"),
    "mimcap":         (3.83, 3.94, "#b044b0"),
    "mimcapcontact":  (3.94, 4.02, "#c0a040"),
    "via3":           (3.63, 4.02, "#c0c0c0"),
    "metal4":         (4.02, 4.87, "#bb9944"),
}
DEVICE_TILES = {"mvpmos": "#cc4444", "mvnmos": "#cc4444",
                "pmos": "#cc4444", "nmos": "#cc4444"}


def magic_run(script, timeout=900):
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=script, capture_output=True, text=True,
                       cwd="mag", timeout=timeout,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    return r.stdout + r.stderr


def mag_units_of(path):
    head = open(path).read(300)
    mm = re.search(r"^magscale (\d+) (\d+)", head, re.M)
    return 100 * int(mm.group(2)) / int(mm.group(1)) if mm else 100


def geometry(cell, out_json):
    """Flatten `cell` and dump per-layer rects for the 3D viewer."""
    tmp = f"{cell}_flat3d"
    magic_run(f"load {cell}\nselect top cell\nexpand\n"
              f"flatten {tmp}\nload {tmp}\n"
              f"writeall force {tmp}\nquit -noprompt\n")
    path = f"mag/{tmp}.mag"
    uu = mag_units_of(path)
    layer, layers = None, {}
    for line in open(path):
        if line.startswith("<< "):
            layer = line.strip("< >\n")
        m = re.match(r"rect (-?\d+) (-?\d+) (-?\d+) (-?\d+)", line)
        if m and layer:
            layers.setdefault(layer, []).append(
                [round(int(v) / uu, 3) for v in m.groups()])
    os.remove(path)
    out, skipped = [], {}
    for name, rects in layers.items():
        if name in STACK:
            z0, z1, color = STACK[name]
        elif name in DEVICE_TILES:
            z0, z1, color = STACK["poly"][0], STACK["poly"][1], \
                DEVICE_TILES[name]
        elif name.endswith(("mos", "fet")):
            z0, z1, color = STACK["poly"][0], STACK["poly"][1], "#cc4444"
        else:
            skipped[name] = len(rects)
            continue
        out.append(dict(name=name, z0=z0, z1=z1, color=color, rects=rects))
    out.sort(key=lambda l: l["z0"])
    nrect = sum(len(l["rects"]) for l in out)
    json.dump(dict(units="um", cell=cell, layers=out), open(out_json, "w"))
    kb = os.path.getsize(out_json) / 1024
    note = f" (skipped: {skipped})" if skipped else ""
    print(f"{cell}: {nrect} rects, {len(out)} layers -> {out_json} "
          f"({kb:.0f} kB){note}")
    return nrect


def export_sch(sch, name):
    os.makedirs(FIGS, exist_ok=True)
    out = f"{FIGS}/{name}.svg"
    subprocess.run(["xschem", "-q", "-x", "--svg", "--plotfile",
                    os.path.abspath(out), f"xschem/{sch}.sch"],
                   capture_output=True, text=True)
    if os.path.exists(out):
        print(f"wrote {out}")
    else:
        print(f"xschem export FAILED for {sch}")


def main():
    os.makedirs("reports/results", exist_ok=True)
    for b, cell, sch in BLOCKS:
        geometry(cell, f"reports/results/{b}_geom.json")
        export_sch(sch, f"sch_{b}")
    geometry("sd_top", "reports/results/top_geom.json")


if __name__ == "__main__":
    main()

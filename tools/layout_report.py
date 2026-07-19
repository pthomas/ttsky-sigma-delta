#!/usr/bin/env python3
"""Layout verification report: DRC + LVS + PEX summary, GDS export, and a
flattened per-layer geometry dump for the 3D stack-up viewer.

All checks run in fresh processes on the saved files (the only trustworthy
method -- see DESIGN.md 2026-07-19 gotchas). Nothing is written back into
mag/ except a transient flattened cell that is deleted afterwards.

Outputs (consumed by tools/gen_docs.py and the CI pages job):
  reports/results/layout.json   -- DRC count + per-rule breakdown, LVS
                                   verdict, PEX cap summary
  reports/results/ota_geom.json -- per-layer rects (um) + z stack for the
                                   three.js viewer
  reports/ota_layout.gds        -- the mask geometry itself

Usage: python3 tools/layout_report.py   (from repo root)
"""

import json
import os
import re
import subprocess
import sys

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
U = 200.0  # magic internal units per um (magscale 1 2 files)

# sky130 process stack, um above substrate surface: (z_bottom, z_top, color).
# Heights from the open_pdks stack-up documentation; diffusion/implant
# thicknesses are symbolic (drawn thin) -- this is a visualization, not a
# process simulation.
STACK = {
    "nwell":          (-0.40, 0.00, "#3a2a52"),
    "mvpdiff":        (0.00, 0.12, "#b06060"),
    "mvndiff":        (0.00, 0.12, "#6080b0"),
    "mvnsubdiff":     (0.00, 0.12, "#4a6a9a"),
    "mvpsubdiff":     (0.00, 0.12, "#9a5a5a"),
    "mvpdiffc":       (0.12, 0.94, "#c0a040"),
    "mvndiffc":       (0.12, 0.94, "#c0a040"),
    "mvnsubdiffcont": (0.12, 0.94, "#c0a040"),
    "mvpsubdiffcont": (0.12, 0.94, "#c0a040"),
    "poly":           (0.32, 0.50, "#cc4444"),
    "polycont":       (0.50, 0.94, "#c0a040"),
    "viali":          (0.12, 0.94, "#c0a040"),
    "locali":         (0.94, 1.04, "#40b0b0"),
    "mcon":           (1.04, 1.38, "#c0c0c0"),
    "metal1":         (1.38, 1.74, "#4488dd"),
    "via1":           (1.74, 2.00, "#c0c0c0"),
    "metal2":         (2.00, 2.36, "#dd8844"),
    "via2":           (2.36, 2.79, "#c0c0c0"),
    "metal3":         (2.79, 3.63, "#44bb66"),
}
# device channel regions (mos tiles) render as poly-height gates
DEVICE_TILES = {"mvpmos": "#cc4444", "mvnmos": "#cc4444"}


def magic_run(script, timeout=600):
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=script, capture_output=True, text=True,
                       cwd="mag", timeout=timeout,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    return r.stdout + r.stderr


def drc():
    out = magic_run("load ota_layout\nselect top cell\nexpand\n"
                    "drc check\ndrc catchup\n"
                    'puts "DRCCOUNT [drc listall count total]"\n'
                    'puts "WHY [drc listall why]"\nquit -noprompt\n')
    count = int(re.search(r"DRCCOUNT (\d+)", out).group(1))
    rules = {}
    m = re.search(r"WHY (.*)", out, re.S)
    if m:
        for rule, boxes in re.findall(r"\{([^{}]+)\} \{((?:\{[^{}]*\} ?)+)\}",
                                      m.group(1)):
            rules[rule] = len(re.findall(r"\{", boxes))
    return dict(count=count, rules=rules)


def lvs():
    r = subprocess.run(
        ["netgen", "-batch", "lvs",
         "mag/ota_layout.spice ota_layout", "spice/ota_top.spice ota",
         f"{PDK_ROOT}/sky130A/libs.tech/netgen/sky130A_setup.tcl",
         "reports/results/lvs_report.out"],
        capture_output=True, text=True,
        env={**os.environ, "PDK_ROOT": PDK_ROOT})
    out = r.stdout + r.stderr
    match = "match uniquely" in out.lower()
    dev = re.search(r"Circuit 1 contains (\d+) devices, Circuit 2 contains "
                    r"(\d+) devices", out)
    net = re.search(r"Circuit 1 contains (\d+) nets,\s+Circuit 2 contains "
                    r"(\d+) nets", out)
    return dict(match=match,
                verdict="Circuits match uniquely" if match else "MISMATCH",
                devices=[int(dev.group(1)), int(dev.group(2))] if dev else [],
                nets=[int(net.group(1)), int(net.group(2))] if net else [])


def pex_summary():
    try:
        txt = open("spice/ota_pex.spice").read()
    except FileNotFoundError:
        return None
    caps = [float(c) for c in re.findall(r"^C\d+ \S+ \S+\s+([0-9.]+)f",
                                         txt, re.M)]
    return dict(ncaps=len(caps), ctotal_f=round(sum(caps) * 1e-15, 18))


def export_gds():
    magic_run("load ota_layout\nselect top cell\nexpand\n"
              "gds write ../reports/ota_layout.gds\nquit -noprompt\n")
    return os.path.getsize("reports/ota_layout.gds")


def geometry():
    """Flatten the layout and dump per-layer rects for the 3D viewer."""
    magic_run("load ota_layout\nselect top cell\nexpand\n"
              "flatten ota_flat3d\nload ota_flat3d\n"
              "writeall force ota_flat3d\nquit -noprompt\n")
    layer, layers = None, {}
    for line in open("mag/ota_flat3d.mag"):
        if line.startswith("<< "):
            layer = line.strip("< >\n")
        m = re.match(r"rect (-?\d+) (-?\d+) (-?\d+) (-?\d+)", line)
        if m and layer:
            layers.setdefault(layer, []).append(
                [round(int(v) / U, 3) for v in m.groups()])
    os.remove("mag/ota_flat3d.mag")
    out = []
    for name, rects in layers.items():
        if name in STACK:
            z0, z1, color = STACK[name]
        elif name in DEVICE_TILES:
            z0, z1, color = STACK["poly"][0], STACK["poly"][1], \
                DEVICE_TILES[name]
        else:
            continue
        out.append(dict(name=name, z0=z0, z1=z1, color=color, rects=rects))
    out.sort(key=lambda l: l["z0"])
    nrect = sum(len(l["rects"]) for l in out)
    return out, nrect


def main():
    os.makedirs("reports/results", exist_ok=True)
    d = drc()
    print(f"DRC (fresh process, expanded): {d['count']} errors")
    for rule, n in d["rules"].items():
        print(f"  {n:5d}  {rule}")
    l = lvs()
    print(f"LVS: {l['verdict']} (devices {l['devices']}, nets {l['nets']})")
    p = pex_summary()
    if p:
        print(f"PEX: {p['ncaps']} caps, {p['ctotal_f']*1e12:.2f} pF total")
    gsize = export_gds()
    print(f"GDS: reports/ota_layout.gds ({gsize/1024:.0f} kB)")
    geom, nrect = geometry()
    json.dump(dict(units="um", layers=geom),
              open("reports/results/ota_geom.json", "w"))
    print(f"3D geometry: {nrect} rects across {len(geom)} layers "
          f"-> reports/results/ota_geom.json")
    json.dump(dict(drc=d, lvs=l, pex=p, gds_bytes=gsize),
              open("reports/results/layout.json", "w"), indent=1)
    if d["count"] != 0 or not l["match"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

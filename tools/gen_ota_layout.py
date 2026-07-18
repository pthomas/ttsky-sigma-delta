#!/usr/bin/env python3
"""OTA layout, phase 1: fingered-device placement + extraction feedback.

Places the 13 OTA devices (sizes from sim/ota_tb.py, fingered at 5 um) in
analog rows in magic, saves mag/ota_layout.mag, extracts, and structurally
compares the extracted devices against the xschem golden netlist
(spice/ota_top.spice). Routing is iterated on top of this in later phases;
until then the compare reports disconnected nets as expected.

Usage: python3 tools/gen_ota_layout.py   (from repo root; needs magic >= 8.3.4)
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.ota_tb import SIZES as S

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
NF, PF = "sky130_fd_pr__nfet_g5v0d10v5", "sky130_fd_pr__pfet_g5v0d10v5"

# name, model, total W, L, row, order-in-row
PLACEMENT = [
    ("M3",  NF, S["W_SINK"], S["L_SINK"], 0, 0),
    ("M4",  NF, S["W_SINK"], S["L_SINK"], 0, 1),
    ("MDN", NF, S["W_SINK"], S["L_SINK"], 0, 2),
    ("M5",  NF, S["W_CAS"],  S["L_CAS"],  1, 0),
    ("M6",  NF, S["W_CAS"],  S["L_CAS"],  1, 1),
    ("M7",  PF, S["W_PCAS"], S["L_PCAS"], 2, 0),
    ("M8",  PF, S["W_PCAS"], S["L_PCAS"], 2, 1),
    ("M9",  PF, S["W_MIR"],  S["L_MIR"],  3, 0),
    ("M10", PF, S["W_MIR"],  S["L_MIR"],  3, 1),
    ("M1",  PF, S["W_IN"],   S["L_IN"],   4, 0),
    ("M2",  PF, S["W_IN"],   S["L_IN"],   4, 1),
    ("MT",  PF, S["W_TAIL"], S["L_TAIL"], 5, 0),
    ("MDP", PF, S["W_TAIL"], S["L_TAIL"], 5, 1),
]
ROW_Y = [0, 12, 24, 36, 48, 62]      # um, provisional row baselines
COL_X = [0, 60, 120]                  # um, provisional column starts


def magic_run(script):
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=script, capture_output=True, text=True,
                       cwd="mag", timeout=300,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    return r.stdout + r.stderr


def build():
    # pass 1: generate each device at origin, measure bboxes (magic internal
    # units, 200/um); gencell w is PER-FINGER width -> w=5, nf=mult
    probe = ["cellname create sizer", "load sizer"]
    for name, model, w, l, row, col in PLACEMENT:
        nf = max(1, round(w / 5))
        probe.append(f"magic::gencell sky130::{model} {name} "
                     f"w 5 l {l:g} nf {nf} guard 1 doports 1")
        probe.append(f"select cell {name}")
        probe.append(f"puts \"BBOX {name} [box values]\"")
        probe.append("delete")
    probe.append("quit -noprompt")
    out = magic_run("\n".join(probe) + "\n")
    dims = {}
    for m in re.finditer(r"BBOX (\S+) (-?\d+) (-?\d+) (-?\d+) (-?\d+)", out):
        n, x1, y1, x2, y2 = m.group(1), *map(int, m.groups()[1:])
        dims[n] = ((x2 - x1) / 200.0, (y2 - y1) / 200.0)   # um
    if len(dims) != len(PLACEMENT):
        print("sizer pass failed:", out[-500:]); sys.exit(1)

    # pass 2: place with 3 um margins, rows bottom-up
    gap = 3.0
    rows = {}
    for name, model, w, l, row, col in PLACEMENT:
        rows.setdefault(row, []).append(name)
    y = 0.0
    pos, row_h = {}, {}
    for r in sorted(rows):
        x = 0.0
        hmax = 0.0
        for name in rows[r]:
            wd, ht = dims[name]
            pos[name] = (x, y)
            x += wd + gap
            hmax = max(hmax, ht)
        row_h[r] = hmax
        y += hmax + gap
    lines = ["drc off", "cellname create ota_layout", "load ota_layout"]
    for name, model, w, l, row, col in PLACEMENT:
        nf = max(1, round(w / 5))
        px, py = pos[name]
        lines.append(f"magic::gencell sky130::{model} {name} "
                     f"w 5 l {l:g} nf {nf} guard 1 doports 1")
        lines.append(f"select cell {name}")
        lines.append(f"move to {px:.2f}um {py:.2f}um")
    lines += ["save ota_layout", "extract all",
              "ext2spice merge conservative", "ext2spice lvs", "ext2spice",
              "drc on", "drc check", "drc catchup",
              'puts "DRCCOUNT [drc listall count total]"',
              "quit -noprompt"]
    out = magic_run("\n".join(lines) + "\n")
    m = re.search(r"DRCCOUNT (\d+)", out)
    print(f"placed {len(PLACEMENT)} devices, "
          f"floorplan {max(p[0]+dims[n][0] for n,p in pos.items()):.0f} x "
          f"{y:.0f} um, DRC errors: {m.group(1) if m else '?'}")


def compare():
    """Structural compare: extracted devices vs xschem golden subckt."""
    want = {}
    sub = re.search(r"^\.subckt ota .*?^\.ends", open("spice/ota_top.spice").read(),
                    re.M | re.S).group(0)
    for m in re.finditer(r"^XM(\S+) (\S+) (\S+) (\S+) (\S+) (sky130\S+)", sub, re.M):
        want["M" + m.group(1)] = (m.group(6), m.group(2), m.group(3),
                                  m.group(4), m.group(5))
    got = {}
    txt = open("mag/ota_layout.spice").read()
    for m in re.finditer(r"^X(\S+) (\S+) (\S+) (\S+) (\S+) (sky130\S+)", txt, re.M):
        got[m.group(1)] = (m.group(6), m.group(2), m.group(3), m.group(4),
                          m.group(5))
    print(f"golden devices: {len(want)}, extracted: {len(got)}")
    return want, got


if __name__ == "__main__":
    os.makedirs("mag", exist_ok=True)
    build()
    compare()

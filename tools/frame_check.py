#!/usr/bin/env python3
"""TT requirements the shuttle precheck does NOT verify (found the hard
way -- DESIGN.md 2026-07-26 dead-board audit):

1. NO FLOATING DIGITAL OUTPUTS. The TT analog spec requires every
   unused uo_out / uio_out / uio_oe pin tied to GND; precheck's
   pin_check.py validates pin GEOMETRY only, so 22 floating stubs
   passed green and would have fed floating tristate-buffer inputs in
   the TT mux (crowbar current; undefined uio_oe can drive board pins).
2. FRAME CONNECTIVITY. The def-pin hookups are by coordinate; nothing
   else proves electrically that ua[0] reaches the input resistor and
   not the integrator monitor. Every pin described in info.yaml must
   merge with its sd_top port; live pins must be pairwise isolated and
   not grounded; undescribed (unpaid) analog pins must touch nothing.
3. info.yaml CONSISTENCY: analog_pins == number of described ua pins.
4. NO METAL5 anywhere in the design (TT power-grid layer).

Method: fresh magic extraction of the framed cell (tt_frame/extq.tcl)
+ union-find over the .ext connectivity records. NOTE: both "merge"
AND "equiv" records carry connectivity -- parsing merge alone
false-reports floating nodes.

Usage: python3 tools/frame_check.py   (after `make tt`; repo root)
Exits nonzero on any failure.
"""

import glob
import itertools
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
FRAME = "tt_um_pthomas_sigma_delta"
INST = "sd_top_0"


def pinout():
    """info.yaml pinout: {'ua': {0: desc, ...}, 'uo': {...}, ...} plus
    analog_pins."""
    txt = open(f"{REPO}/info.yaml").read()
    pins = {"ua": {}, "uo": {}, "uio": {}, "ui": {}}
    for kind, idx, desc in re.findall(
            r'^\s*(ua|uo|uio|ui)\[(\d)\]:\s*"([^"]*)"', txt, re.M):
        if desc.strip():          # empty "" = unused pin
            pins[kind][int(idx)] = desc
    ap = int(re.search(r"^\s*analog_pins:\s*(\d+)", txt, re.M).group(1))
    return pins, ap


def extract():
    r = subprocess.run(
        ["magic", "-dnull", "-noconsole", "-rcfile", RC, "extq.tcl"],
        cwd=f"{REPO}/tt_frame", capture_output=True, text=True,
        env={**os.environ, "PDK_ROOT": PDK_ROOT,
             "SIGMA_DELTA_MAG": f"{REPO}/mag"}, timeout=1800)
    if "extract" not in (r.stdout + r.stderr).lower():
        print(r.stdout[-1000:] + r.stderr[-1000:])
        sys.exit("frame extraction failed")


def groups():
    ext = open(f"{REPO}/tt_frame/{FRAME}.ext").read()
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for m in re.finditer(r'^(?:merge|equiv) "([^"]+)" "([^"]+)"', ext,
                         re.M):
        parent[find(m.group(1))] = find(m.group(2))
    if not any(k.startswith(INST + "/") for k in parent):
        sys.exit(f"no {INST}/* nodes in extraction -- wrong instance "
                 "name or empty frame")
    return find, parent


def main():
    pins, analog_pins = pinout()
    extract()
    find, parent = groups()
    gnd = find("VGND")
    fails = []

    def check(ok, what):
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    # 3. info.yaml consistency
    check(len(pins["ua"]) == analog_pins,
          f"info.yaml: analog_pins={analog_pins} matches "
          f"{len(pins['ua'])} described ua pins")

    # 1. every undescribed digital output tied to VGND (uio_oe is an
    # output for ALL uio indices unless the design drives it)
    tie = [f"uo_out[{i}]" for i in range(8) if i not in pins["uo"]] \
        + [f"uio_out[{i}]" for i in range(8) if i not in pins["uio"]] \
        + [f"uio_oe[{i}]" for i in range(8) if i not in pins["uio"]]
    untied = [p for p in tie if find(p) != gnd]
    check(not untied,
          f"{len(tie)} unused digital outputs tied to VGND"
          + (f" -- floating: {untied}" if untied else ""))

    # 2a. described pins reach their sd_top ports
    live = {"clk": f"{INST}/CLK"}
    for i in pins["ua"]:
        live[f"ua[{i}]"] = f"{INST}/UA{i}"
    for i in pins["uo"]:
        live[f"uo_out[{i}]"] = f"{INST}/UO{i}"
    for pin, port in live.items():
        check(find(pin) == find(port), f"{pin} <-> {port}")

    # 2b. live pins pairwise isolated, none grounded
    for a, b in itertools.combinations(live, 2):
        check(find(a) != find(b), f"{a} isolated from {b}")
    for p in list(live) + ["VAPWR", "VDPWR"]:
        check(find(p) != gnd, f"{p} not shorted to VGND")
    check(find("VAPWR") != find("VDPWR"), "VAPWR not shorted to VDPWR")

    # 2c. supplies actually enter the design
    for rail in ("VAPWR", "VDPWR", "VGND"):
        r = find(rail)
        inside = any(k.startswith(INST + "/") and find(k) == r
                     for k in list(parent))
        check(inside, f"{rail} connected into {INST}")

    # 2d. unpaid analog pins touch nothing inside the design
    for i in range(8):
        if i in pins["ua"]:
            continue
        r = find(f"ua[{i}]")
        touching = [k for k in parent
                    if k.startswith(INST + "/") and find(k) == r]
        check(not touching, f"ua[{i}] (unpaid) unconnected"
              + (f" -- touches {touching[:3]}" if touching else ""))

    # 4. no metal5
    m5 = [f for f in glob.glob(f"{REPO}/mag/*.mag")
          + [f"{REPO}/tt_frame/{FRAME}.mag"]
          if "<< metal5 >>" in open(f, errors="ignore").read()]
    check(not m5, "no metal5 in any layout"
          + (f" -- found in {[os.path.basename(f) for f in m5]}"
             if m5 else ""))

    print(f"\nframe_check: {'PASS' if not fails else 'FAIL'} "
          f"({len(fails)} failures)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

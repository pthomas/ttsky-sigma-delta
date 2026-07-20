#!/usr/bin/env python3
"""Top-level assembly: place every block + passive in sd_top, tap all
terminals up to met3/met4, wire the nets, verify.

Wiring model:
  - terminals: block ports (m1 track labels) stack via1+via2 -> met3;
    res/switch cells tap like lay_lib (via1 on end-m1 / strap points)
    then via2 -> met3; cap cells strap their units with a met4 bus
    (top plate C1, stubs in the inter-unit gaps) and a met3 bus below
    (bottom plate C2).
  - routing: met3 horizontal, met4 vertical, via3 at bends. Blocks
    contain no met4, so met4 may cross them freely; met3 must stay
    outside block bboxes; nothing crosses cap cells except their own
    straps (caps carry met4).
  - supplies: 2 um met4 vertical trunks (VGND x=138, VAPWR x=233,
    VDPWR x=66) + met3 feeds from each block's supply ports.

Run: python3 tools/asm_top.py [--report]   (--report: stop after
printing terminal coordinates, no paint)
Then: fresh-process DRC + netgen LVS vs spice/golden/top.spice.
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools import lay_lib
from tools.lay_lib import (magic_run, parse_parent, parse_ports,
                           subcell_layer_bbox, U, VIA, PAD, PDK_ROOT)

MW = 0.6      # signal wire width
SW = 2.0      # supply trunk width

# cell, bbox-lower-left target (um). Streets >= ~3 um.
PLACE = {
    "ota":   ("ota_layout", 12, 12),
    "bias":  ("bias_layout", 142, 12),
    "bufn":  ("buf_layout", 236, 12),
    "bufc":  ("buf_layout", 236, 60),
    "bufp":  ("buf_layout", 236, 108),
    "bufc2": None,   # placeholder removed below
}
PLACE.pop("bufc2")
PLACE.update({
    "bufc": ("buf_layout", 236, 64),
    "bufp": ("buf_layout", 236, 116),
    "rlt":   ("rl_top", 285, 12),
    "rlp":   ("rl_pc", 285, 78),
    "rlc":   ("rl_cm", 300, 78),
    "rlb":   ("rl_bot", 285, 130),
    "rin":   ("rin", 12, 104),
    "rdac":  ("rdac", 42, 104),
    "sm":    ("sw_nmos", 59, 104),
    "st1":   ("sw_nmos", 66, 104),
    "st2":   ("sw_nmos", 73, 104),
    "sb1":   ("sw_nmos", 80, 104),
    "sb2":   ("sw_nmos", 87, 104),
    "cint":  ("cint", 12, 129),
    "cdec1": ("cdec", 74, 129),
    "comp":  ("comp_layout", 12, 153),
    "lvl":   ("lvl_layout", 85, 153),
    "cdec2": ("cdec", 12, 191),
    "cdec3": ("cdec", 74, 191),
    "dff":   ("dff_layout", 142, 140),
    "odrvb": ("odrv_layout", 142, 175),
    "cflt1": ("cflt", 178, 175),
    "odrvq": ("odrv_layout", 206, 175),
    "cflt2": ("cflt", 270, 192),
})

BLOCKS = {"ota", "bias", "bufn", "bufc", "bufp", "odrvq", "odrvb",
          "comp", "lvl", "dff"}
# ports each block exposes to the top wiring (blocks label internal
# nets too -- only these get via stacks)
BPORTS = {
    "ota": ["INP", "INM", "OUT", "VDD", "VSS", "IREFP", "IREFN",
            "VBNC", "VBPC"],
    "comp": ["INP", "INM", "CLK", "Q", "VDD", "VSS"],
    "dff": ["D", "CLK", "Q", "QB", "VDD", "VSS"],
    "bias": ["IREFP", "IREFN", "VBNC", "VBPC", "VDD", "VSS"],
    "bufn": ["IN", "OUT", "IREFP", "VDD", "VSS"],
    "bufc": ["IN", "OUT", "IREFP", "VDD", "VSS"],
    "bufp": ["IN", "OUT", "IREFP", "VDD", "VSS"],
    "lvl": ["CLK18", "CLK33", "CLKB33", "VDD18", "VDD33", "VSS"],
    "odrvq": ["IN33", "OUT18", "VDD18", "VSS"],
    "odrvb": ["IN33", "OUT18", "VDD18", "VSS"],
}
CAPS = {"cint", "cdec1", "cdec2", "cdec3", "cflt1", "cflt2"}
RESC = {"rlt", "rlp", "rlc", "rlb", "rin", "rdac"}
SWS = {"sm", "st1", "st2", "sb1", "sb2"}

# WIRES: net -> list of polylines; points are (x, y) or ("T", inst,
# port) terminal references. Consecutive points differ in one coord:
# horizontal segments paint met3, vertical met4; layer transitions and
# terminal hookups get via3 (and the terminal's own stack).
WIRES = {}


def bbox_probe():
    cells = sorted({c for c, _, _ in PLACE.values()})
    path = "mag/asm_bbox.json"
    probe = []
    for c in cells:
        probe += [f"load {c}", "select top cell",
                  f'puts "BB {c} [box values]"']
    out = magic_run("\n".join(probe) + "\nquit -noprompt\n")
    bb = {}
    for mm in re.finditer(r"BB (\S+) (-?\d+) (-?\d+) (-?\d+) (-?\d+)", out):
        c = mm.group(1)
        bb[c] = [int(v) / U for v in mm.groups()[1:]]
    json.dump(bb, open(path, "w"), indent=1)
    return bb


def placements(bb):
    """inst -> (cell, origin_x, origin_y, bbox at target)."""
    out = {}
    for inst, (cell, tx, ty) in PLACE.items():
        x1, y1, x2, y2 = bb[cell]
        ox, oy = tx - x1, ty - y1
        out[inst] = (cell, ox, oy, (tx, ty, tx + (x2 - x1),
                                    ty + (y2 - y1)))
    return out


def overlap_check(pl):
    bad = 0
    items = list(pl.items())
    for i, (na, (_, _, _, a)) in enumerate(items):
        for nb, (_, _, _, b) in items[i + 1:]:
            pa = 3.0 if na in CAPS or nb in CAPS else 0.0
            if (a[0] - pa < b[2] and b[0] - pa < a[2]
                    and a[1] - pa < b[3] and b[1] - pa < a[3]):
                print(f"PLACEMENT OVERLAP: {na} {a} vs {nb} {b}")
                bad += 1
    return bad == 0


def block_ports(cell):
    """port label -> (x, y) from the routed block's flabel lines."""
    ports = {}
    for mm in re.finditer(
            r"flabel metal1 (-?\d+) (-?\d+) (-?\d+) (-?\d+) \d+ \S+ "
            r"\d+ \d+ \d+ \d+ (\S+)\n", open(f"mag/{cell}.mag").read()):
        x = (int(mm.group(1)) + int(mm.group(3))) / 2 / U
        y = (int(mm.group(2)) + int(mm.group(4))) / 2 / U
        ports[mm.group(5)] = (x, y)
    return ports


def main():
    report = "--report" in sys.argv
    os.makedirs("mag", exist_ok=True)
    bb = bbox_probe()
    pl = placements(bb)
    if not overlap_check(pl):
        sys.exit("fix placement overlaps first")

    tcl = ["drc off", "cellname create sd_top", "load sd_top",
           "addpath ."]
    audit = []
    cur = [None]
    # a cap's own C1 stub inherently overlaps its own cap bbox (m4) --
    # exempt just THAT entry from the forbid_m4 check via this flag,
    # independent of `cur[0]` (which must hold the real net name so the
    # NEAR/CROSS check recognizes it as the same net as the wire it
    # connects to, not a name-mangled alias of it)
    cur_capself = [False]

    # map every block/passive terminal to the top-level net name that
    # actually connects to it (from tools/asm_wires.py), so terminal-tap
    # audit entries and the wires that connect to them share one name
    from tools.asm_wires import WIRES as _W
    term_to_net = {}
    for _net, _polys in _W.items():
        for _poly in _polys:
            for _p in _poly:
                if isinstance(_p, tuple) and _p and _p[0] == "T":
                    term_to_net[f"{_p[1]}.{_p[2]}"] = _net

    def paint(x1, y1, x2, y2, layers, pads=None):
        x1, y1, x2, y2 = (round(v * U) / U for v in (x1, y1, x2, y2))
        tcl.append(f"box {x1:.3f}um {y1:.3f}um {x2:.3f}um {y2:.3f}um")
        for l in layers:
            tcl.append(f"paint {l}")
            audit.append((l, x1, y1, x2, y2, cur[0], cur_capself[0]))
        if pads:
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            p = PAD / 2
            tcl.append(f"box {cx-p:.3f}um {cy-p:.3f}um "
                       f"{cx+p:.3f}um {cy+p:.3f}um")
            for l in pads:
                tcl.append(f"paint {l}")
                audit.append((l, cx - p, cy - p, cx + p, cy + p, cur[0],
                             cur_capself[0]))

    # ---- place cells ---------------------------------------------------
    for inst, (cell, ox, oy, _) in pl.items():
        tcl.append(f"box {ox:.3f}um {oy:.3f}um {ox:.3f}um {oy:.3f}um")
        tcl.append(f"getcell {cell} child 0um 0um")

    # ---- terminals -----------------------------------------------------
    # name -> (x, y, layer): layer is the level the terminal reaches
    terms = {}

    def stack_m1_to_m3(name, x, y):
        paint(x - VIA / 2, y - VIA / 2, x + VIA / 2, y + VIA / 2,
              ["via1"], pads=["m1", "m2"])
        paint(x - VIA / 2, y - VIA / 2, x + VIA / 2, y + VIA / 2,
              ["via2"], pads=["m2", "m3"])
        terms[name] = (x, y, "m3")

    for inst in sorted(BLOCKS):
        cell, ox, oy, _ = pl[inst]
        bp = block_ports(cell)
        for port in BPORTS[inst]:
            px, py = bp[port]
            cur[0] = term_to_net.get(f"{inst}.{port}", f"{inst}.{port}")
            stack_m1_to_m3(f"{inst}.{port}", ox + px, oy + py)

    for inst in sorted(RESC):
        cell, ox, oy, _ = pl[inst]
        child = parse_parent(cell)
        (ccell, ctx, cty) = list(child.values())[0]
        ports = parse_ports(ccell)
        for port in ("R1", "R2"):
            px, py = ports[port][0]
            vb = subcell_layer_bbox(ccell, "viali", px, py, win=2.3)
            vx = round((ctx + (vb[0] + vb[2]) / 2) * U) / U + ox
            vy = round((cty + (vb[1] + vb[3]) / 2) * U) / U + oy
            cur[0] = term_to_net.get(f"{inst}.{port}", f"{inst}.{port}")
            paint(vx - VIA / 2, vy - VIA / 2, vx + VIA / 2,
                  vy + VIA / 2, ["via1"], pads=["m2"])
            paint(vx - VIA / 2, vy - VIA / 2, vx + VIA / 2,
                  vy + VIA / 2, ["via2"], pads=["m2", "m3"])
            terms[f"{inst}.{port}"] = (vx, vy, "m3")
        bx, by = ports["B"][0]
        bx, by = ox + ctx + bx, oy + cty + by
        cur[0] = term_to_net.get(f"{inst}.B", f"{inst}.B")
        paint(bx - VIA / 2, by - VIA / 2, bx + VIA / 2, by + VIA / 2,
              ["mcon", "via1"], pads=["m1", "m2"])
        paint(bx - VIA / 2, by - VIA / 2, bx + VIA / 2, by + VIA / 2,
              ["via2"], pads=["m2", "m3"])
        terms[f"{inst}.B"] = (bx, by, "m3")

    for inst in sorted(SWS):
        cell, ox, oy, _ = pl[inst]
        child = parse_parent(cell)
        (ccell, ctx, cty) = list(child.values())[0]
        ports = parse_ports(ccell)
        # D/S contacts sit only ~0.79um apart (single-finger nfet) --
        # too tight for two independent via1/via2 PAD-sized (0.5um)
        # stacks to keep the 0.3um met3 spacing rule (met3.2). Push
        # each via out along its own m1 finger, away from the other,
        # before stacking up -- same "flag" idea as the gate tap below.
        for port, sign in (("D", -1), ("S", 1)):
            px, py = ports[port][0]
            px, py = ox + ctx + px, oy + cty + py
            vx = px + sign * 0.4
            cur[0] = term_to_net.get(f"{inst}.{port}", f"{inst}.{port}")
            paint(min(px, vx) - 0.2, py - 0.2, max(px, vx) + 0.2, py + 0.2,
                  ["m1"])
            stack_m1_to_m3(f"{inst}.{port}", vx, py)
        # gate: m1 flag above the G-contact mosaic (lay_lib recipe)
        gx, gy = ports["G"][0]
        gb = subcell_layer_bbox(ccell, "metal1", gx, gy)
        cx = round((ctx + (gb[0] + gb[2]) / 2) * U) / U + ox
        gyv = round((cty + gb[3] + 0.25) * U) / U + oy
        cur[0] = term_to_net.get(f"{inst}.G", f"{inst}.G")
        paint(ox + ctx + gb[0], oy + cty + gb[3] - 0.05,
              ox + ctx + gb[2], oy + cty + gb[3] + 0.55, ["m1"])
        gv = 0.26 / 2
        paint(cx - gv, gyv - gv, cx + gv, gyv + gv, ["via1"],
              pads=["m2"])
        paint(cx - VIA / 2, gyv - VIA / 2, cx + VIA / 2, gyv + VIA / 2,
              ["via2"], pads=["m2", "m3"])
        terms[f"{inst}.G"] = (cx, gyv, "m3")
        bx, by = ports["B"][0]
        bx, by = ox + ctx + bx, oy + cty + by
        cur[0] = term_to_net.get(f"{inst}.B", f"{inst}.B")
        paint(bx - VIA / 2, by - VIA / 2, bx + VIA / 2, by + VIA / 2,
              ["mcon", "via1"], pads=["m1", "m2"])
        paint(bx - VIA / 2, by - VIA / 2, bx + VIA / 2, by + VIA / 2,
              ["via2"], pads=["m2", "m3"])
        terms[f"{inst}.B"] = (bx, by, "m3")

    for inst in sorted(CAPS):
        cell, ox, oy, bbx = pl[inst]
        children = parse_parent(cell)
        c1s, c2s, ymin, ymax = [], [], 1e9, -1e9
        for cname, (ccell, ctx, cty) in children.items():
            ports = parse_ports(ccell)
            for pn, plist in ports.items():
                for (px, py) in plist:
                    x, y = ox + ctx + px, oy + cty + py
                    if pn.startswith("C1"):
                        c1s.append((x, y))
                    elif pn.startswith("C2"):
                        c2s.append((x, y))
        # C2 (bottom plate, met3 at the vias): met3 stubs down to a bus
        yb2 = bbx[1] - 1.2
        cur[0] = term_to_net.get(f"{inst}.C2", f"{inst}.C2")
        for (x, y) in c2s:
            paint(x - 0.3, yb2 - 0.3, x + 0.3, y + 0.3, ["m3"])
        paint(min(x for x, _ in c2s) - 0.3, yb2 - 0.3,
              max(x for x, _ in c2s) + 0.3, yb2 + 0.3, ["m3"])
        terms[f"{inst}.C2"] = (c2s[0][0], yb2, "m3")
        # C1 (top plate, met4 at the mimcc): met4 stubs up (the C1
        # contacts sit in the inter-unit gaps, clear of the plates) to
        # a met4 bus above the cell
        yb1 = bbx[3] + 1.2
        cur[0] = term_to_net.get(f"{inst}.C1", f"{inst}.C1")
        cur_capself[0] = True
        for (x, y) in c1s:
            paint(x - 0.3, y - 0.3, x + 0.3, yb1 + 0.3, ["m4"])
        paint(min(x for x, _ in c1s) - 0.3, yb1 - 0.3,
              max(x for x, _ in c1s) + 0.3, yb1 + 0.3, ["m4"])
        cur_capself[0] = False
        terms[f"{inst}.C1"] = (c1s[0][0], yb1, "m4")

    if report:
        for name in sorted(terms):
            x, y, l = terms[name]
            print(f"T {name:20s} ({x:7.2f},{y:7.2f}) {l}")
        return

    # ---- wires ---------------------------------------------------------
    from tools.asm_wires import WIRES as W, TRUNKS, LABELS
    # (inst, bbox) so the M3-OVER-CELL check can tell a wire legitimately
    # entering ITS OWN destination block/cap (own port inside that exact
    # bbox) from one actually crossing through a foreign one
    forbid_m3 = [(b, pl[b][3]) for b in BLOCKS] + [(c, pl[c][3]) for c in CAPS]
    forbid_m4 = [(c, pl[c][3]) for c in CAPS]
    # inst -> set of net names that legitimately terminate inside it
    own_nets = {}
    for term, net in term_to_net.items():
        own_nets.setdefault(term.split(".")[0], set()).add(net)
    cur_capself[0] = False

    for net, x, y1, y2 in TRUNKS:
        cur[0] = net
        paint(x - SW / 2, y1, x + SW / 2, y2, ["m4"])

    def resolve(p):
        if isinstance(p, tuple) and p and p[0] == "T":
            x, y, l = terms[f"{p[1]}.{p[2]}"]
            return x, y, l
        return p[0], p[1], None

    for net, polys in W.items():
        cur[0] = net
        for poly in polys:
            pts = [resolve(p) for p in poly]
            for i in range(len(pts) - 1):
                (x1, y1, l1), (x2, y2, l2) = pts[i], pts[i + 1]
                if abs(y1 - y2) < 0.001:      # horizontal -> m3
                    paint(min(x1, x2) - MW / 2, y1 - MW / 2,
                          max(x1, x2) + MW / 2, y1 + MW / 2, ["m3"])
                elif abs(x1 - x2) < 0.001:    # vertical -> m4
                    paint(x1 - MW / 2, min(y1, y2) - MW / 2,
                          x1 + MW / 2, max(y1, y2) + MW / 2, ["m4"])
                else:
                    sys.exit(f"{net}: non-manhattan segment "
                             f"({x1},{y1})-({x2},{y2})")
            # via3 wherever the polyline changes direction or meets a
            # terminal whose layer differs from the segment layer
            for i, (x, y, l) in enumerate(pts):
                segs = []
                if i > 0:
                    segs.append("h" if abs(pts[i-1][1] - y) < 0.001
                                else "v")
                if i < len(pts) - 1:
                    segs.append("h" if abs(pts[i+1][1] - y) < 0.001
                                else "v")
                need34 = ("h" in segs and "v" in segs)
                if l == "m3" and segs and segs[0] == "v":
                    need34 = True
                if l == "m4" and segs and "h" in segs:
                    need34 = True
                if need34:
                    paint(x - VIA / 2, y - VIA / 2, x + VIA / 2,
                          y + VIA / 2, ["via3"], pads=["m3", "m4"])

    # audit: m3 segments must avoid block/cap bboxes; same-layer
    # different-net spacing >= 0.3
    bad = 0
    for (l, x1, y1, x2, y2, n, capself) in audit:
        if l == "m3" and (x2 - x1) > 2.0:    # long horizontal runs
            for (inst, (fx1, fy1, fx2, fy2)) in forbid_m3:
                if n in own_nets.get(inst, ()):
                    continue
                if x1 < fx2 and fx1 < x2 and y1 < fy2 and fy1 < y2:
                    print(f"M3-OVER-CELL: {n} ({x1:.1f},{y1:.1f})-"
                          f"({x2:.1f},{y2:.1f})")
                    bad += 1
        if l == "m4" and not capself:
            for (inst, (fx1, fy1, fx2, fy2)) in forbid_m4:
                if n in own_nets.get(inst, ()):
                    continue
                if x1 < fx2 and fx1 < x2 and y1 < fy2 and fy1 < y2:
                    print(f"M4-OVER-CAP: {n} ({x1:.1f},{y1:.1f})-"
                          f"({x2:.1f},{y2:.1f})")
                    bad += 1
    for i in range(len(audit)):
        l1, a1, b1, c1, d1, n1, _ = audit[i]
        if l1 not in ("m3", "m4"):
            continue
        for j in range(i + 1, len(audit)):
            l2, a2, b2, c2, d2, n2, _ = audit[j]
            if l1 != l2 or n1 == n2 or n1 is None or n2 is None:
                continue
            if a1 < c2 + 0.3 and a2 < c1 + 0.3 \
                    and b1 < d2 + 0.3 and b2 < d1 + 0.3:
                print(f"NEAR/CROSS {l1}: {n1} ({a1:.1f},{b1:.1f})-"
                      f"({c1:.1f},{d1:.1f}) vs {n2} ({a2:.1f},{b2:.1f})"
                      f"-({c2:.1f},{d2:.1f})")
                bad += 1
    if bad:
        sys.exit(f"{bad} wiring conflicts -- fix tools/asm_wires.py")

    for net, x, y in LABELS:
        tcl.append(f"box {x:.3f}um {y - 0.2:.3f}um {x + 0.4:.3f}um "
                   f"{y + 0.2:.3f}um")
        tcl.append(f"label {net} FreeSans 0.5um 0 0 0 c m4")
        tcl.append("port make")

    tcl += ["save sd_top", "extract all",
            "ext2spice lvs", "ext2spice hierarchy off",
            "ext2spice subcircuit top on",
            "ext2spice merge conservative", "ext2spice",
            "quit -noprompt"]
    out = magic_run("\n".join(tcl) + "\n", timeout=1800)
    if "rror" in out:
        print(out[-600:])

    out2 = magic_run("load sd_top\nselect top cell\nexpand\n"
                     "drc on\ndrc check\ndrc catchup\n"
                     'puts "DRCCOUNT [drc listall count total]"\n'
                     "quit -noprompt\n", timeout=3600)
    mm = re.search(r"DRCCOUNT (\d+)", out2)
    print(f"sd_top: DRC errors (fresh reload): "
          f"{mm.group(1) if mm else '?'}")

    r = subprocess.run(
        ["netgen", "-batch", "lvs", "mag/sd_top.spice sd_top",
         "spice/golden/top.spice sd_top",
         f"{PDK_ROOT}/sky130A/libs.tech/netgen/sky130A_setup.tcl",
         "spice/lvs_top.out"],
        capture_output=True, text=True,
        env={**os.environ, "PDK_ROOT": PDK_ROOT})
    ok = "Circuits match uniquely" in (r.stdout + r.stderr)
    print(f"sd_top: LVS {'match' if ok else 'MISMATCH'}")
    if not ok:
        print((r.stdout + r.stderr)[-800:])


if __name__ == "__main__":
    main()

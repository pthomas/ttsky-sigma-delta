#!/usr/bin/env python3
"""Route tools/asm_wires.py from tools/asm_top.py's PLACE floorplan.

A grid-based maze router (1um cells) that enforces the same DRC rules
tools/asm_top.py's own audit checks: horizontal runs (met3) must avoid
BLOCK+CAP bboxes, vertical runs (met4) must avoid CAP bboxes only (the
docstring rule: "blocks contain no met4, so met4 may cross them
freely"). Different nets are kept off each other's already-routed grid
cells on the same layer so the real painted metal (0.3um half-width
each side of the centerline) keeps the sky130A met3.2/met4.2 0.3um
spacing rule. See DESIGN.md 2026-07-20 for the debugging history
(precision pitfalls, self-overlap exemptions, congestion order
sensitivity) -- read it before changing this file.

Usage: python3 tools/asm_route.py   (needs mag/*.mag + mag/asm_bbox.json
already built by tools/asm_top.py --report)
Writes tools/asm_wires.py.

Known residual: this run leaves a couple dozen NEAR/CROSS spacing
near-misses in a few congested corridors (the switch row, the y~189-190
band around the caps, the y~173 dff/odrvq band, the vbpc bus vs
UO0/UO1). Topology/connectivity is correct (all nets routed, no
BLOCK/CAP crossings) -- what's left is tightening a handful of parallel
runs by ~0.5-1um each. Iterate with `python3 tools/asm_top.py` and feed
the NEAR/CROSS output back into ORDER/hand patches below.
"""

import heapq
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.asm_top import (PLACE, BLOCKS, BPORTS, RESC, SWS, CAPS,
                           placements, block_ports)
from tools.lay_lib import parse_parent, parse_ports, subcell_layer_bbox, U

BLOCK_NAMES = ["ota", "comp", "dff", "bias", "bufn", "bufc", "bufp",
               "lvl", "odrvq", "odrvb"]
CAP_NAMES = ["cint", "cdec1", "cdec2", "cdec3", "cflt1", "cflt2"]

# ---------------------------------------------------------------------
# exact terminal coordinates + block/cap bboxes (mirrors asm_top.py's
# own terminal-tapping math so the router plans against precisely what
# will be painted)
# ---------------------------------------------------------------------


def compute_terms_and_bb():
    bb = json.load(open("mag/asm_bbox.json"))
    pl = placements(bb)
    terms = {}
    abs_bb = {inst: bbox for inst, (_, _, _, bbox) in pl.items()}

    for inst in sorted(BLOCKS):
        cell, ox, oy, _ = pl[inst]
        bp = block_ports(cell)
        for port in BPORTS[inst]:
            px, py = bp[port]
            terms[f"{inst}.{port}"] = (ox + px, oy + py)

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
            terms[f"{inst}.{port}"] = (vx, vy)
        bx, by = ports["B"][0]
        terms[f"{inst}.B"] = (ox + ctx + bx, oy + cty + by)

    for inst in sorted(SWS):
        cell, ox, oy, _ = pl[inst]
        child = parse_parent(cell)
        (ccell, ctx, cty) = list(child.values())[0]
        ports = parse_ports(ccell)
        # D/S sit only ~0.79um apart (single-finger nfet) -- too tight
        # for two independent via1/via2 PAD-sized (0.5um) stacks to
        # keep 0.3um met3 spacing; asm_top.py pushes each via out along
        # its own m1 finger (see the SWS loop there) -- mirror that
        # here so the router plans against the ACTUAL via positions
        for port, sign in (("D", -1), ("S", 1)):
            px, py = ports[port][0]
            px, py = ox + ctx + px, oy + cty + py
            terms[f"{inst}.{port}"] = (px + sign * 0.4, py)
        gx_, gy_ = ports["G"][0]
        gb = subcell_layer_bbox(ccell, "metal1", gx_, gy_)
        cx = round((ctx + (gb[0] + gb[2]) / 2) * U) / U + ox
        gyv = round((cty + gb[3] + 0.25) * U) / U + oy
        terms[f"{inst}.G"] = (cx, gyv)
        bx, by = ports["B"][0]
        terms[f"{inst}.B"] = (ox + ctx + bx, oy + cty + by)

    for inst in sorted(CAPS):
        cell, ox, oy, bbx = pl[inst]
        children = parse_parent(cell)
        c1s, c2s = [], []
        for cname, (ccell, ctx, cty) in children.items():
            ports = parse_ports(ccell)
            for pn, plist in ports.items():
                for (px, py) in plist:
                    x, y = ox + ctx + px, oy + cty + py
                    if pn.startswith("C1"):
                        c1s.append((x, y))
                    elif pn.startswith("C2"):
                        c2s.append((x, y))
        yb2 = bbx[1] - 1.2
        terms[f"{inst}.C2"] = (c2s[0][0], yb2)
        yb1 = bbx[3] + 1.2
        terms[f"{inst}.C1"] = (c1s[0][0], yb1)

    return terms, abs_bb


# ---------------------------------------------------------------------
# grid maze router
# ---------------------------------------------------------------------

GRID = 1.0
XMIN, XMAX = -10, 320
YMIN, YMAX = -10, 222
# Wires paint MW/2=0.3um beyond their routed centerline (tools/asm_top.py
# paint()); a centerline the router treats as "clear" must keep the
# full bbox at least that far away, or the painted metal itself would
# clip the block/cap even though the grid CENTER point never touched
# it. Expand (not shrink) the forbidden zones by that half-width plus
# a hair of slack.
MARGIN = -0.35


def gx(v):
    return round(v / GRID)


def ux(i):
    return i * GRID


NX = gx(XMAX) - gx(XMIN) + 1
NY = gx(YMAX) - gx(YMIN) + 1
IX0 = gx(XMIN)
IY0 = gx(YMIN)


class Router:
    def __init__(self, abs_bb):
        def rects(names):
            out = []
            for n in names:
                x1, y1, x2, y2 = abs_bb[n]
                out.append((x1 + MARGIN, y1 + MARGIN, x2 - MARGIN, y2 - MARGIN))
            return out

        def build_mask(rlist):
            mask = bytearray(NX * NY)
            for (x1, y1, x2, y2) in rlist:
                i1, i2 = max(0, gx(x1) - IX0), min(NX - 1, gx(x2) - IX0)
                j1, j2 = max(0, gx(y1) - IY0), min(NY - 1, gx(y2) - IY0)
                for i in range(i1, i2 + 1):
                    base = i * NY
                    for j in range(j1, j2 + 1):
                        mask[base + j] = 1
            return mask

        self.abs_bb = abs_bb
        self.m3_mask = build_mask(rects(BLOCK_NAMES + CAP_NAMES))
        self.m4_mask = build_mask(rects(CAP_NAMES))
        # owner net name per cell, separately for h-corridor (m3) and
        # v-corridor (m4) use -- a cell owned by net X is only an
        # obstacle for a DIFFERENT net's move of the same kind;
        # crossing layers is always free.
        self.m3_owner = [None] * (NX * NY)
        self.m4_owner = [None] * (NX * NY)

    def _mark(self, i, j, kind, net, r=0, perp=0):
        owner = self.m3_owner if kind == 'h' else self.m4_owner
        dxi = r if kind == 'h' else r + perp
        dyj = r + perp if kind == 'h' else r
        for di in range(-dxi, dxi + 1):
            for dj in range(-dyj, dyj + 1):
                ni, nj = i + di, j + dj
                if 0 <= ni < NX and 0 <= nj < NY:
                    idx = ni * NY + nj
                    if owner[idx] is None:
                        owner[idx] = net

    def reserve_terminals(self, term_net, terms):
        """Pre-seed every terminal's own cell with its own net, on both
        layers, before any pathfinding -- otherwise another net's
        merely-passing-through waypoint can land exactly on a foreign
        terminal's rounded grid cell (unowned at that point), and the
        REAL painted geometry there (vias, wire half-width) clashes
        even though the two nets' path centerlines never conflicted
        during search."""
        for member, net in term_net.items():
            x, y = terms[member]
            i, j = gx(x) - IX0, gx(y) - IY0
            self._mark(i, j, 'h', net, r=0)
            self._mark(i, j, 'v', net, r=0)

    def commit(self, path, net, perp=0):
        for k in range(len(path) - 1):
            x0, y0 = path[k]
            x1, y1 = path[k + 1]
            i0, j0 = gx(x0) - IX0, gx(y0) - IY0
            i1, j1 = gx(x1) - IX0, gx(y1) - IY0
            if j0 == j1:
                for ii in range(min(i0, i1), max(i0, i1) + 1):
                    self._mark(ii, j0, 'h', net, perp=perp)
            elif i0 == i1:
                for jj in range(min(j0, j1), max(j0, j1) + 1):
                    self._mark(i0, jj, 'v', net, perp=perp)
            else:
                raise ValueError(f"non-manhattan commit segment "
                                 f"{path[k]}-{path[k+1]}")

    def route(self, start, end, net=None):
        sx, sy = start
        ex, ey = end
        si = (gx(sx) - IX0, gx(sy) - IY0)
        ei = (gx(ex) - IX0, gx(ey) - IY0)

        def clear(i, j, kind, at_start):
            if not (0 <= i < NX and 0 <= j < NY):
                return False
            idx = i * NY + j
            mask = self.m3_mask if kind == 'h' else self.m4_mask
            if mask[idx] and not at_start and (i, j) != ei:
                return False
            owner = (self.m3_owner if kind == 'h' else self.m4_owner)[idx]
            if owner is not None and owner != net:
                return False
            return True

        dist = {si: 0}
        prev = {}
        pq = [(0, si, None)]
        goal = None
        while pq:
            d, node, direction = heapq.heappop(pq)
            if d > dist.get(node, 1e18):
                continue
            if node == ei:
                goal = node
                break
            i, j = node
            at_start = (node == si)
            for di, dj, nd, kind in ((1, 0, 'E', 'h'), (-1, 0, 'W', 'h'),
                                      (0, 1, 'N', 'v'), (0, -1, 'S', 'v')):
                ni, nj = i + di, j + dj
                if not clear(ni, nj, kind, at_start):
                    continue
                bend = 0 if direction in (None, nd) else 4
                nnode = (ni, nj)
                nd_cost = d + 1 + bend
                if nd_cost < dist.get(nnode, 1e18):
                    dist[nnode] = nd_cost
                    prev[nnode] = (node, nd)
                    heapq.heappush(pq, (nd_cost, nnode, nd))
        if goal is None:
            return None
        path = []
        node = goal
        while node in prev:
            path.append(node)
            node, _ = prev[node]
        path.append(si)
        path.reverse()
        pts = [(ux(i + IX0), ux(j + IY0)) for (i, j) in path]
        simp = [pts[0]]
        for k in range(1, len(pts) - 1):
            x0, y0 = pts[k - 1]
            x1, y1 = pts[k]
            x2, y2 = pts[k + 1]
            if (x1 - x0, y1 - y0) != (x2 - x1, y2 - y1):
                simp.append(pts[k])
        simp.append(pts[-1])
        return simp


# ---------------------------------------------------------------------
# net list + routing order (see gen_top_golden.py docstring for the
# connectivity contract this must match)
# ---------------------------------------------------------------------

NETS = {
 "sum": ["rin.R2", "rdac.R2", "cint.C2", "ota.INM"],
 "vcm": ["ota.INP", "comp.INM", "sm.S", "bufc.OUT"],
 "UA1": ["ota.OUT", "cint.C1", "comp.INP"],
 "clk33": ["comp.CLK", "dff.CLK", "sm.G", "lvl.CLK33"],
 "clkb33": ["lvl.CLKB33", "st2.G", "sb2.G"],
 "cq": ["comp.Q", "dff.D"],
 "q33": ["dff.Q", "odrvq.IN33", "st1.G"],
 "qb33": ["dff.QB", "odrvb.IN33", "sb1.G"],
 "dac": ["rdac.R1", "sm.D", "st2.S", "sb2.S"],
 "xt": ["st1.S", "st2.D"],
 "xb": ["sb1.S", "sb2.D"],
 "vrefp": ["st1.D", "bufp.OUT", "cdec3.C1"],
 "vrefn": ["sb1.D", "bufn.OUT", "cdec2.C1"],
 "lad_p": ["rlt.R2", "bufp.IN"],
 "lad_c": ["rlp.R2", "rlc.R1", "bufc.IN"],
 "lad_n": ["rlc.R2", "rlb.R1", "bufn.IN"],
 "irefp": ["ota.IREFP", "bias.IREFP", "bufp.IREFP", "bufc.IREFP", "bufn.IREFP"],
 "irefn": ["ota.IREFN", "bias.IREFN"],
 "vbnc": ["ota.VBNC", "bias.VBNC", "cflt1.C1"],
 "vbpc": ["ota.VBPC", "bias.VBPC", "cflt2.C1"],
 "VGND": ["ota.VSS", "comp.VSS", "dff.VSS", "bias.VSS", "bufn.VSS",
          "bufc.VSS", "bufp.VSS", "lvl.VSS", "odrvq.VSS", "odrvb.VSS",
          "rin.B", "rdac.B", "rlt.B", "rlp.B", "rlc.B", "rlb.B", "rlb.R2",
          "sm.B", "st1.B", "st2.B", "sb1.B", "sb2.B", "cdec1.C2",
          "cdec2.C2", "cdec3.C2", "cflt1.C2", "cflt2.C2"],
 "VAPWR": ["ota.VDD", "lvl.VDD33", "comp.VDD", "dff.VDD", "bias.VDD",
           "bufn.VDD", "bufc.VDD", "bufp.VDD", "rlt.R1"],
 "VDPWR": ["lvl.VDD18", "odrvq.VDD18", "odrvb.VDD18"],
}

# routing order matters: earlier nets get first pick of the congested
# corridors (the y~151 gap past cdec1/cint, the y~189 gap past
# cdec2/cdec3, etc). This order was tuned empirically -- see DESIGN.md
# 2026-07-20 for which reorderings fixed which failures.
ORDER = ["xt", "xb", "dac", "VDPWR", "clkb33", "UA1", "clk33", "vcm",
         "cq", "VGND", "VAPWR", "q33", "qb33",
         "irefp", "irefn", "vbnc", "vbpc", "sum",
         "vrefp", "vrefn", "lad_p", "lad_c", "lad_n"]

LABELS_REQ = {
    "UA0": (5, 106), "UA1": (5, 150), "UO0": (235, 218),
    "UO1": (170, 218), "CLK": (91, 218), "VGND": (138, 218),
    "VAPWR": (233, 218), "VDPWR": (134, 218),
}
PASSTHRU = {"UA0": "rin.R1", "UO0": "odrvq.OUT18", "UO1": "odrvb.OUT18",
            "CLK": "lvl.CLK18"}

# a handful of legs the auto-router can't currently thread through
# (see the module docstring); routed by hand instead and skipped here
SKIP_OK = {("VAPWR", "lvl.VDD33")}


def plan(rt, terms):
    result = {}
    labels_out = []

    def do_net(name, members):
        pts_all = []
        placed = []
        m0 = members[0]
        x0, y0 = terms[m0]
        pts_all.append(("T", m0, (x0, y0)))
        placed.append((m0, (x0, y0)))
        for m in members[1:]:
            cur = terms[m]
            path = None
            frm = None
            for pm, pxy in sorted(placed, key=lambda p:
                                  abs(p[1][0] - cur[0]) + abs(p[1][1] - cur[1])):
                path = rt.route(pxy, cur, net=name)
                if path is not None:
                    frm = pm
                    break
            if path is None and (name, m) in SKIP_OK:
                print(f"--- {name}: skipping {m}{cur} (hand-patched)")
                continue
            if path is None:
                print(f"*** {name}: NO PATH (any) -> {m}{cur}")
                result[name] = None
                return False
            rt.commit(path, name)
            pts_all.append(("PATH", frm, m, path))
            placed.append((m, cur))
        result[name] = pts_all
        print(f"{name}: OK ({len(members)} terms)")
        return True

    def do_label(name, fromterm):
        lx, ly = LABELS_REQ[name]
        x, y = terms[fromterm]
        ly2 = ly - 3 if ly > y else ly + 3
        p = rt.route((x, y), (lx, ly2), net=name)
        if p is None:
            print(f"*** {name}: label leg failed")
            return
        p = p + [(lx, ly)]
        rt.commit(p, name)
        result[name].append(("LABELPATH", fromterm, None, p))
        labels_out.append((name, lx, ly))

    term_net = {}
    for name, members in NETS.items():
        for m in members:
            term_net[m] = name
    for net, term in PASSTHRU.items():
        term_net[term] = net
    rt.reserve_terminals(term_net, terms)

    for net, term in PASSTHRU.items():
        x, y = terms[term]
        result[net] = [("T", term, (x, y))]
        do_label(net, term)

    for name in ORDER:
        ok = do_net(name, NETS[name])
        if ok and name in LABELS_REQ:
            do_label(name, NETS[name][-1])

    fails = [n for n, v in result.items() if v is None]
    if fails:
        sys.exit(f"routing failed for: {fails}")
    return result, labels_out


# ---------------------------------------------------------------------
# generate tools/asm_wires.py (WIRES/TRUNKS/LABELS) from the routed
# result, substituting exact terminal coordinates for the router's
# grid-rounded stand-ins and clipping any long over-length block entry
# ---------------------------------------------------------------------


def exact(terms, member):
    x, y = terms[member]
    inst, port = member.split(".")
    return ("T", inst, port), (x, y)


def snapped(exact_pt, other_grid, anchor_grid):
    ox, oy = anchor_grid
    nx, ny = other_grid
    if abs(oy - ny) < 1e-6:
        return (other_grid[0], exact_pt[1])
    return (exact_pt[0], other_grid[1])


def fixup(path, start_exact, end_exact):
    pts = [tuple(p) for p in path]
    if end_exact is None:
        end_exact = pts[-1]
    if len(pts) == 2:
        sx, sy = start_exact
        ex, ey = end_exact
        if abs(sx - ex) < 1e-6 or abs(sy - ey) < 1e-6:
            return [start_exact, end_exact]
        was_h = abs(path[0][1] - path[1][1]) < 1e-6
        corner = (ex, sy) if was_h else (sx, ey)
        return [start_exact, corner, end_exact]
    mid = pts[1:-1]
    p1 = snapped(start_exact, pts[1], pts[0])
    pn1 = snapped(end_exact, pts[-2], pts[-1])
    out = [start_exact, p1] + mid[1:-1] + [pn1, end_exact]
    dedup = [out[0]]
    for p in out[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    fixed = [dedup[0]]
    for k in range(1, len(dedup)):
        x0, y0 = fixed[-1]
        x1, y1 = dedup[k]
        if abs(x0 - x1) < 1e-6 or abs(y0 - y1) < 1e-6:
            fixed.append((x1, y1))
        else:
            fixed.append((x1, y0))
            fixed.append((x1, y1))
    return fixed


def clip_entry(terms, abs_bb, poly, end):
    """The router's last grid step may land on a terminal's own
    (masked) cell -- fine at grid resolution, but once that corner is
    replaced by the exact off-grid coordinate, a long straight run
    leading up to it can dip >2um into that block's bbox and trip
    asm_top.py's M3-OVER-CELL check. Insert one extra corner right at
    the block's own edge (offset by the paint half-width too) so only
    a short stub -- however deep the port sits -- legitimately enters."""
    idx = 0 if end == 'start' else -1
    p = poly[idx]
    if not (isinstance(p, tuple) and p and p[0] == "T"):
        return poly
    inst = p[1]
    if inst not in abs_bb or inst not in (BLOCK_NAMES + CAP_NAMES):
        return poly
    bx1, by1, bx2, by2 = abs_bb[inst]
    nb = 1 if end == 'start' else -2
    if not (-len(poly) <= nb < len(poly)):
        return poly
    neighbor = poly[nb]
    if isinstance(neighbor, tuple) and neighbor and neighbor[0] == "T":
        return poly
    tx, ty = terms[f"{p[1]}.{p[2]}"]
    nx, ny = neighbor
    if abs(ty - ny) > 1e-6 or not (by1 - 0.01 <= ty <= by2 + 0.01):
        return poly
    if bx1 <= nx <= bx2:
        return poly
    edge = bx1 - 0.35 if nx < tx else bx2 + 0.35
    if end == 'start':
        return [poly[0], (edge, ty)] + poly[1:]
    return poly[:-1] + [(edge, ty), poly[-1]]


def build_wires(terms, abs_bb, result):
    nets_out = {}
    for name, legs in result.items():
        polylines = []
        for leg in legs:
            if leg[0] == 'T':
                continue
            kind, frm, to, path = leg
            tfrom, xyfrom = exact(terms, frm)
            tto, xyto = (None, None) if to is None else exact(terms, to)
            fixed = fixup(path, xyfrom, xyto)
            poly = [tfrom] + fixed[1:-1] + ([tto] if tto else [fixed[-1]])
            poly = clip_entry(terms, abs_bb, poly, 'start')
            if tto:
                poly = clip_entry(terms, abs_bb, poly, 'end')
            polylines.append(poly)
        nets_out[name] = polylines

    # hand patch: lvl.VDD33 sits inside lvl's own bbox behind the same
    # congested cdec1-vs-lvl/comp escape corridor VDPWR/VGND already
    # fill. Tap it from ABOVE instead into the existing y=214 VAPWR
    # bus. The straight-down column at x=103.9 crosses cdec3
    # (x74-131.65, y191-211.4) though, so detour the long vertical run
    # over to x=136 (clear of every cap and of q33's own x=134 column)
    # and only cross back to x=103.9 in the y<191 gap below cdec3.
    nets_out.setdefault("VAPWR", []).append(
        [(135.6, 214), (136, 214), (136, 190), (103.9, 190),
         ("T", "lvl", "VDD33")])
    return nets_out


def fmt_point(p):
    if isinstance(p, tuple) and len(p) == 3 and p[0] == "T":
        return f'("T", {p[1]!r}, {p[2]!r})'
    x, y = p
    return f'({x:g}, {y:g})'


def write_asm_wires(nets_out, labels_out, path="tools/asm_wires.py"):
    lines = [
        '#!/usr/bin/env python3',
        '"""Top-level wiring plan for tools/asm_top.py.',
        '',
        'Generated by tools/asm_route.py -- re-run that script (not this',
        'file by hand) if PLACE in tools/asm_top.py changes. See',
        'DESIGN.md 2026-07-20 and tools/asm_route.py\'s own docstring for',
        'the routing method and known residual NEAR/CROSS conflicts.',
        '"""',
        '',
        'WIRES = {',
    ]
    for name in nets_out:
        lines.append(f'    {name!r}: [')
        for poly in nets_out[name]:
            ptxt = ', '.join(fmt_point(p) for p in poly)
            lines.append(f'        [{ptxt}],')
        lines.append('    ],')
    lines.append('}')
    lines.append('')
    lines.append('# vertical met4 supply trunks: (net, x, y1, y2)')
    lines.append('TRUNKS = []')
    lines.append('')
    lines.append('# top-level port labels: (net, x, y) -- must land on met4')
    lines.append('LABELS = [')
    for net, x, y in labels_out:
        lines.append(f'    ({net!r}, {x:g}, {y:g}),')
    lines.append(']')
    open(path, "w").write("\n".join(lines) + "\n")


def main():
    terms, abs_bb = compute_terms_and_bb()
    rt = Router(abs_bb)
    result, labels_out = plan(rt, terms)
    nets_out = build_wires(terms, abs_bb, result)
    write_asm_wires(nets_out, labels_out)
    print(f"wrote tools/asm_wires.py ({len(nets_out)} nets, "
          f"{len(labels_out)} labels)")


if __name__ == "__main__":
    main()

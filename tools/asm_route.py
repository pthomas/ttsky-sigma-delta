#!/usr/bin/env python3
"""Route tools/asm_wires.py from tools/asm_top.py's PLACE floorplan.

A grid-based maze router (1um cells). Obstacle model (2026-07-20 v2,
geometry-precise -- see DESIGN.md):

- Horizontal moves paint met3. Forbidden within 0.65um (0.3 spacing +
  0.3 wire half-width + slack) of any placed instance's REAL metal3
  geometry (lay_lib.cell_layer_rects): the blocks carry hundreds of
  internal m3 riser pads, the MiM caps' bottom plates are m3 across
  their whole footprint, and the poly-resistor/switch passives carry
  no m3 at all -- so the resistor/switch region is open to crossing,
  which is where most of the congestion lived under the old
  bbox-blanket model.
- Vertical moves paint met4. Forbidden over cap bboxes only (caps
  carry top-plate m4 pickups; blocks/passives have no m4).
- Every terminal's painted via-pad footprint and the cap C1/C2
  bus+stub geometry are pre-seeded into the per-net ownership map, so
  a foreign net keeps real clearance from pads it cannot see as
  wires -- this kills the collinear-terminal near-short class (all
  switch D/S taps share y=110.29, all resistor ends share y=105.9).
- Different nets keep off each other's committed cells per layer.

Usage: python3 tools/asm_route.py   (needs mag/*.mag + mag/asm_bbox.json
already built by tools/asm_top.py --report)
Writes tools/asm_wires.py. Verify with `python3 tools/asm_top.py`.
"""

import heapq
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.asm_top import (PLACE, BLOCKS, BPORTS, RESC, SWS, CAPS,
                           placements, block_ports)
from tools.lay_lib import (parse_parent, parse_ports, subcell_layer_bbox,
                           cell_layer_rects, U)

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
            terms[f"{inst}.{port}"] = (px + sign * 0.55, py)
        gx_, gy_ = ports["G"][0]
        gb = subcell_layer_bbox(ccell, "metal1", gx_, gy_)
        cx = round((ctx + (gb[0] + gb[2]) / 2) * U) / U + ox
        gyv = round((cty + gb[3] + 0.25) * U) / U + oy
        terms[f"{inst}.G"] = (cx, gyv)
        bx, by = ports["B"][0]
        terms[f"{inst}.B"] = (ox + ctx + bx, oy + cty + by)

    # cap C1/C2 bus + stub geometry (mirrors asm_top.py's CAPS loop) --
    # returned as (termname, kind, rect) seeds so foreign nets keep
    # clear of the whole painted structure, not just the terminal point
    cap_seeds = []
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
        yb2 = bbx[1] - 1.6
        terms[f"{inst}.C2"] = (c2s[0][0], yb2)
        # C2: met4 bus at yb2 + met4 stubs up into the cell's own
        # via3-strip m4 (all-met4 scheme, see asm_top's CAPS loop)
        cap_seeds.append((f"{inst}.C2", 'v',
                          (min(x for x, _ in c2s) - 0.3, yb2 - 0.3,
                           max(x for x, _ in c2s) + 0.3, bbx[1] + 0.6)))
        yb1 = bbx[3] + 1.7
        terms[f"{inst}.C1"] = (c1s[0][0], yb1)
        # C1: m4 bus at yb1 + m4 stubs from bbox top up to the bus
        cap_seeds.append((f"{inst}.C1", 'v',
                          (min(x for x, _ in c1s) - 0.3, bbx[3],
                           max(x for x, _ in c1s) + 0.3, yb1 + 0.3)))

    # precise m3 obstacle map: every placed instance's REAL metal3
    # rects in absolute coordinates (blocks: internal riser pads; caps:
    # bottom plate = whole footprint; passives: none). The MiM top
    # plates (mimcap) additionally repel unrelated metal3 by 1.34um
    # (capm.11) -- pre-expand those rects so the router's uniform
    # DILATE (0.65) yields the required 1.34 + wire half-width.
    m3_obs = []
    for inst, (cell, ox, oy, _) in pl.items():
        for (x1, y1, x2, y2) in cell_layer_rects(cell, "metal3"):
            m3_obs.append((x1 + ox, y1 + oy, x2 + ox, y2 + oy))
        for (x1, y1, x2, y2) in cell_layer_rects(cell, "mimcap"):
            m3_obs.append((x1 + ox - 1.05, y1 + oy - 1.05,
                           x2 + ox + 1.05, y2 + oy + 1.05))

    return terms, abs_bb, m3_obs, cap_seeds


# ---------------------------------------------------------------------
# grid maze router
# ---------------------------------------------------------------------

GRID = 1.0
XMIN, XMAX = -10, 320
YMIN, YMAX = -10, 228
# Wires paint MW/2=0.3um beyond their routed centerline (tools/asm_top.py
# paint()) and must then keep the met3.2/met4.2 0.3um spacing rule to
# any foreign shape: a centerline is only "clear" if the obstacle is
# at least 0.3+0.3 away, plus a hair of slack.
DILATE = 0.65


def gx(v):
    return round(v / GRID)


def ux(i):
    return i * GRID


NX = gx(XMAX) - gx(XMIN) + 1
NY = gx(YMAX) - gx(YMIN) + 1
IX0 = gx(XMIN)
IY0 = gx(YMIN)


class Router:
    def __init__(self, abs_bb, m3_obs):
        def build_mask(rlist, dilate):
            mask = bytearray(NX * NY)
            for (x1, y1, x2, y2) in rlist:
                x1, y1, x2, y2 = (x1 - dilate, y1 - dilate,
                                  x2 + dilate, y2 + dilate)
                i1, i2 = max(0, gx(x1) - IX0), min(NX - 1, gx(x2) - IX0)
                j1, j2 = max(0, gx(y1) - IY0), min(NY - 1, gx(y2) - IY0)
                for i in range(i1, i2 + 1):
                    base = i * NY
                    for j in range(j1, j2 + 1):
                        mask[base + j] = 1
            return mask

        self.abs_bb = abs_bb
        # h-moves (met3): keep off every instance's REAL m3 geometry
        self.m3_mask = build_mask(m3_obs, DILATE)
        # v-moves (met4): blanket over cap bboxes (top-plate m4 pickups
        # plus mim-cap-adjacent rules; caps are compact, blanket is
        # cheap and safe)
        self.m4_mask = build_mask([abs_bb[n] for n in CAP_NAMES], DILATE)
        # owner net name per cell, separately for h-corridor (m3) and
        # v-corridor (m4) use -- a cell owned by net X is only an
        # obstacle for a DIFFERENT net's move of the same kind;
        # crossing layers is always free.
        self.m3_owner = [None] * (NX * NY)
        self.m4_owner = [None] * (NX * NY)

    def seed_rect(self, net, kind, rect):
        """Own all cells within DILATE of `rect` on `kind` for `net`
        (first owner wins; existing owners are left alone)."""
        x1, y1, x2, y2 = rect
        i1 = max(0, gx(x1 - DILATE) - IX0)
        i2 = min(NX - 1, gx(x2 + DILATE) - IX0)
        j1 = max(0, gx(y1 - DILATE) - IY0)
        j2 = min(NY - 1, gx(y2 + DILATE) - IY0)
        for i in range(i1, i2 + 1):
            for j in range(j1, j2 + 1):
                self._mark(i, j, kind, net)

    def seed_terminals(self, term_net, terms, m4_terms, block_home):
        """Three-pass terminal seeding. Pass 1: each terminal's own
        grid cell, both kinds, so its net can always reach it. Pass 2:
        the painted via-pad footprint (exact +-0.25) dilated, on the
        terminal's own layer kind, so foreign runs keep real spacing
        from pads that sit off-grid (the collinear switch/resistor
        rows). Pass 3: for BLOCK ports, the whole potential escape
        column (own cell +-1, full block height +-2) on the v kind --
        escapes ride the exact staggered port x through the block
        (see attach), and a foreign grid-aligned column one cell over
        would sit only ~0.6um from that exact-riding metal. First
        owner wins throughout, so the passes must run in this order.
        `block_home`: member -> block bbox for its BLOCK-port terminals."""
        for member, net in term_net.items():
            x, y = terms[member]
            i, j = gx(x) - IX0, gx(y) - IY0
            self._mark(i, j, 'h', net)
            self._mark(i, j, 'v', net)
        for member, net in term_net.items():
            x, y = terms[member]
            kind = 'v' if member in m4_terms else 'h'
            self.seed_rect(net, kind, (x - 0.25, y - 0.25,
                                       x + 0.25, y + 0.25))
        # group ports per block: adjacent ports are only 1.0um apart,
        # so their +-1 cell zones overlap -- each contested cell goes
        # to the NEAREST port's net (their exact-riding escapes are
        # mutually compatible at 0.4um; the zone only needs to keep
        # THIRD-party grid columns 2 cells away)
        per_block = {}
        for member, net in term_net.items():
            if member in block_home:
                per_block.setdefault(id(block_home[member]), (
                    block_home[member], []))[1].append(
                        (terms[member][0], net))
        for _, (bbox, plist) in per_block.items():
            (bx1, by1, bx2, by2) = bbox
            cells = {}
            for (px, net) in plist:
                ci = gx(px)
                for i in (ci - 1, ci, ci + 1):
                    d = abs(px - ux(i))
                    if i not in cells or d < cells[i][0]:
                        cells[i] = (d, net)
            for i, (_, net) in cells.items():
                ii = i - IX0
                if not (0 <= ii < NX):
                    continue
                for j in range(max(0, gx(by1) - IY0 - 2),
                               min(NY - 1, gx(by2) - IY0 + 2) + 1):
                    self._mark(ii, j, 'v', net)

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

    def route(self, start, end, net=None, v_start=False, v_end=False):
        """v_start/v_end: force the first/last move at that terminal to
        be vertical. Used for BLOCK ports: they sit on 0.8um-pitch
        staggered track rows where any two adjacent ports' horizontal
        wire pieces (0.6 wide) would violate the 0.3 spacing rule, but
        their staggered x positions give vertical escape columns a
        clean 0.4um gap."""
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
                if v_start and at_start and kind != 'v':
                    continue
                if v_end and (ni, nj) == ei and kind != 'v':
                    continue
                if not clear(ni, nj, kind, at_start):
                    continue
                # the painted segment occupies the SOURCE cell too --
                # a bend must not turn onto a layer another net owns
                # at the current cell (e.g. arrive horizontally on a
                # cell inside a foreign port's protected v-column,
                # then leave vertically)
                sidx = i * NY + j
                sown = (self.m3_owner if kind == 'h'
                        else self.m4_owner)[sidx]
                if sown is not None and sown != net:
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
 "vcm": ["ota.INP", "comp.INM", "sm.S", "bufc.OUT", "cdec1.C1"],
 "UA1": ["ota.OUT", "cint.C1", "comp.INP"],
 "clk33": ["comp.CLK", "dff.CLK", "sm.G", "lvl.CLK33"],
 "clkb33": ["lvl.CLKB33", "st2.G", "sb2.G"],
 "cq": ["comp.QB", "dff.D"],
 "q33": ["dff.Q", "odrvq.IN33", "st1.G"],
 "qb33": ["dff.QB", "odrvb.IN33", "sb1.G"],
 "dac": ["rdac.R1", "sm.D", "st2.S", "sb2.S"],
 "xt": ["st1.S", "st2.D"],
 "xb": ["sb1.S", "sb2.D"],
 "vrefp": ["st1.D", "bufp.OUT", "cdec3.C1"],
 "vrefn": ["sb1.D", "bufn.OUT", "cdec2.C1"],
 "lad_p": ["rlt.R2", "rlp.R1", "bufp.IN"],
 "lad_c": ["rlp.R2", "rlc.R1", "bufc.IN"],
 "lad_n": ["rlc.R2", "rlb.R1", "bufn.IN"],
 "irefp": ["ota.IREFP", "bias.IREFP", "bufp.IREFP", "bufc.IREFP", "bufn.IREFP"],
 "irefn": ["ota.IREFN", "bias.IREFN"],
 "vbnc": ["ota.VBNC", "bias.VBNC", "cflt1.C1"],
 "vbpc": ["ota.VBPC", "bias.VBPC", "cflt2.C1"],
 "VGND": ["ota.VSS", "comp.VSS", "cdec2.C2", "lvl.VSS", "dff.VSS",
          "bias.VSS", "bufn.VSS", "bufc.VSS", "bufp.VSS", "odrvq.VSS",
          "odrvb.VSS", "rin.B", "rdac.B", "rlt.B", "rlp.B", "rlc.B",
          "rlb.B", "rlb.R2", "sm.B", "st1.B", "st2.B", "sb1.B", "sb2.B",
          "cdec1.C2", "cdec3.C2", "cflt1.C2", "cflt2.C2"],
 "VAPWR": ["ota.VDD", "lvl.VDD33", "comp.VDD", "dff.VDD", "bias.VDD",
           "bufn.VDD", "bufc.VDD", "bufp.VDD", "rlt.R1"],
 "VDPWR": ["lvl.VDD18", "odrvq.VDD18", "odrvb.VDD18"],
}

# routing order matters: earlier nets get first pick of the congested
# corridors (the y~151 gap past cdec1/cint, the y~189 gap past
# cdec2/cdec3, etc). This order was tuned empirically -- see DESIGN.md
# 2026-07-20 for which reorderings fixed which failures.
ORDER = ["xt", "xb", "dac", "clk33", "VDPWR", "clkb33", "UA1", "vcm",
         "cq", "VGND", "VAPWR", "q33", "qb33",
         "irefp", "irefn", "vbnc", "vbpc", "sum",
         "vrefp", "vrefn", "lad_p", "lad_c", "lad_n"]

# signal pins at the EXACT tt_analog_2x2_3v3.def positions (met4
# pin geometry there is placed by `def read` in the frame build, so a
# wire arriving vertically at these coordinates lands on the frame
# pin): ua[0] / ua[1] on the bottom edge, uo_out[0] / uo_out[1] / clk
# on the top edge. Supply labels stay project-internal at the top --
# the frame script connects them to its own full-height met4 stripes.
LABELS_REQ = {
    "UA0": (136.62, 0.5), "UA1": (117.30, 0.5),
    "UO0": (78.66, 225.26), "UO1": (75.90, 225.26),
    "CLK": (128.34, 225.26), "VGND": (138, 218),
    "VAPWR": (233, 218), "VDPWR": (134, 218),
}
PASSTHRU = {"UA0": "rin.R1", "UO0": "odrvq.OUT18", "UO1": "odrvb.OUT18",
            "CLK": "lvl.CLK18"}

# a handful of legs the auto-router can't currently thread through
# (see the module docstring); routed by hand instead and skipped here
SKIP_OK = {("VAPWR", "lvl.VDD33"), ("vcm", "cdec1.C1"),
           ("VGND", "bias.VSS"), ("VGND", "lvl.VSS")}

# the hand routes for the SKIP_OK legs, in asm_wires polyline form.
# These are pre-committed into the router grid before any auto routing
# so the auto-routed nets keep clear of them.
#
# VAPWR -> lvl.VDD33: sits inside lvl's own bbox behind the congested
# cdec1-vs-lvl/comp escape corridor VDPWR/VGND already fill. Tap it
# from bias.VDD instead (dff.VDD was tried first, but its x=145.4
# column sat only 0.6um from VGND's x=146 dff.VSS column -- the two
# dff supply ports are 1.0um apart): m4 column up at x=149.9 (2.3um
# clear of q33's x=147 column), across dff (blocks carry no m4) into
# the y=172 street (above dff's 170.65 top, below odrvb's 175 bottom
# -- a y=187 crossing would run through odrvb's internal m3), west to
# x=127 (clear of lvl's east edge at 125.95), north to y=187 in the
# lvl/cdec3 gap, west above lvl, then the m4 drop onto the port.
#
# vcm -> cdec1.C1 (the vcm reference decap's top-plate m4 bus at
# y=150.6): the auto route from sm.S grabbed the y=152 corridor and
# cascaded VGND's lvl.VSS leg into failure. Instead: ride vcm's
# existing x~61 column up to y=126 (below cint), cross to the x=71
# street between cint and cdec1, up to y=151 (0.4um clear of clkb33's
# y=150 run and clk33's y=152 run), east to the bus x, and drop onto
# the bus through the terminal's own via3.
#
# VGND -> lvl.VSS: the port sits 1.4um inside lvl's bbox and its only
# northern entry rows (y186-188) are all claimed by cq (whichever
# order cq routes in, y188 is its cheapest corridor). Enter through
# the comp/lvl street instead: comp.VSS column up over comp (m4) to
# y=190 (clear: VDPWR is y189, VAPWR patch starts x104), east to the
# x=82 street, down to the port's own y, and a short m3 entry stub
# east into lvl -- legitimate, it's reaching lvl's own VSS port.
HAND_PATCHES = {
    "VAPWR": [[("T", "bias", "VDD"), (149.9, 172), (127, 172),
               (127, 187), (103.9, 187), ("T", "lvl", "VDD33")]],
    # vcm -> cdec1.C1: the capm.11 halo killed the old y=151 approach
    # (unrelated m3 must keep 1.34um from the cap top plates). The C1
    # bus is met4, so approach on met4 instead: east under the caps at
    # y=126, north up the cdec1/dff street at x=136, west at y=188
    # (row 187 belongs to the VAPWR patch), then drop the met4 column
    # straight THROUGH lvl (blocks carry no m4) onto the bus.
    "vcm": [[("T", "sm", "S"), (61.345, 126), (138, 126), (138, 188),
             (117.19, 188), ("T", "cdec1", "C1")]],
    "VGND": [# comp.VSS -> lvl.VSS: enter through the comp/lvl street
             # (the port sits 1.4um inside lvl; the m3 entry stub is
             # reaching lvl's own VSS port)
             [("T", "comp", "VSS"), (29.4, 189), (82, 189),
              (82, 182.77), ("T", "lvl", "VSS")],
             # dff.VSS -> bias.VSS: their ports sit 1.0um from dff.VDD
             # / bias.VDD, whose VAPWR leg must ride the same
             # dff-to-bias corridor -- both nets must stay
             # exact-aligned the whole way (0.4um apart) because any
             # grid-riding stretch of one sits 0.6um from the other's
             # exact ride. Ride x=146.4 from dff.VSS down into bias,
             # one 0.5um jog at y=132.9 (clear of bias' internal m3
             # columns at x145.1-145.5 ending y132.25 and x146.6-147.0
             # ending y129.05), then straight down x=146.9 to the port.
             [("T", "dff", "VSS"), (146.4, 132.9), (146.9, 132.9),
              ("T", "bias", "VSS")]],
}


def plan(rt, terms, cap_seeds):
    result = {}
    labels_out = []

    def vport(member):
        # BLOCK ports live on 0.8um-pitch staggered track rows --
        # force vertical entry/exit there (see Router.route)
        return member.split(".")[0] in BLOCKS

    def do_net(name, members):
        pts_all = []
        placed = []
        m0 = members[0]
        x0, y0 = terms[m0]
        pts_all.append(("T", m0, (x0, y0)))
        placed.append((m0, (x0, y0)))
        for m in members[1:]:
            cur = terms[m]
            if (name, m) in SKIP_OK:
                print(f"--- {name}: skipping {m}{cur} (hand-patched)")
                continue
            path = None
            frm = None
            for pm, pxy in sorted(placed, key=lambda p:
                                  abs(p[1][0] - cur[0]) + abs(p[1][1] - cur[1])):
                path = rt.route(pxy, cur, net=name,
                                v_start=vport(pm), v_end=vport(m))
                if path is not None:
                    frm = pm
                    break
            if path is None:
                print(f"*** {name}: NO PATH (any) -> {m}{cur}")
                result[name] = None
                return False
            # cap-terminal legs ride the off-grid bus line for their
            # whole last segment (ride_of returns 1e6) -- the painted
            # metal leans up to half a cell off the committed row, so
            # own the neighboring rows too or a foreign jog validates
            # right against the lean
            rt.commit(path, name,
                      perp=1 if m.split(".")[0] in CAP_NAMES else 0)
            pts_all.append(("PATH", frm, m, path))
            placed.append((m, cur))
        result[name] = pts_all
        print(f"{name}: OK ({len(members)} terms)")
        return True

    def do_label(name, fromterm):
        lx, ly = LABELS_REQ[name]
        x, y = terms[fromterm]
        # v_end: the final move must be vertical so the wire arrives
        # at the label point on met4 -- the label layer. (An earlier
        # standoff-and-append scheme made a switchback that the
        # collinear prune collapsed into a horizontal m3 arrival,
        # leaving the m4 label floating: UA0/VGND had no LVS pins.)
        p = rt.route((x, y), (lx, ly), net=name,
                     v_start=vport(fromterm), v_end=True)
        if p is None:
            print(f"*** {name}: label leg failed")
            return
        rt.commit(p, name)
        result[name].append(("LABELPATH", fromterm, None, p))
        labels_out.append((name, lx, ly))

    term_net = {}
    for name, members in NETS.items():
        for m in members:
            term_net[m] = name
    for net, term in PASSTHRU.items():
        term_net[term] = net
    m4_terms = {t for t in term_net if t.split(".")[0] in CAP_NAMES
                and (t.endswith(".C1") or t.endswith(".C2"))}
    block_home = {t: rt.abs_bb[t.split(".")[0]] for t in term_net
                  if t.split(".")[0] in BLOCKS}
    rt.seed_terminals(term_net, terms, m4_terms, block_home)
    for termname, kind, rect in cap_seeds:
        rt.seed_rect(term_net[termname], kind, rect)

    # pre-commit the hand-patched routes so auto routing avoids them
    for net, polys in HAND_PATCHES.items():
        for poly in polys:
            pts = [terms[f"{p[1]}.{p[2]}"]
                   if isinstance(p, tuple) and p and p[0] == "T" else p
                   for p in poly]
            rt.commit([(round(x), round(y)) for x, y in pts], net)

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


RIDE = 2.0   # default exact-coordinate ride length at a terminal (um)


def attach(exact, a, b, ride=RIDE, jogok=None):
    """Points joining the exact terminal coordinate to the on-grid
    corner `b`, where a->b is the terminal-adjacent grid segment
    (a = the terminal's own rounded cell). The wire RIDES the exact
    coordinate for `ride` um before jogging onto the grid line: near
    the terminal the exact track is the safe one (neighboring foreign
    terminals -- the 0.8um port staircase, the switch row, the sibling
    ports of the same block -- sit at fixed real offsets from it),
    while far from the terminal the grid line is the safe one (every
    other net's runs are grid-aligned). For BLOCK ports the caller
    passes ride = distance to the block edge + 1, so the whole
    in-block stretch stays exact-aligned. `jogok(i, j)`: cell test for
    the jog site (the jog paints via3 pads on BOTH layers, so it must
    not land on another net's crossing run); the jog slides further
    along the ride until it passes."""
    import math
    ex, ey = exact

    def first_int(v, d):
        return math.ceil(v) if d > 0 else math.floor(v)

    if abs(a[1] - b[1]) < 1e-6:      # horizontal segment
        gy = a[1]
        if abs(ey - gy) < 1e-9:
            return [exact, b]
        d = 1 if b[0] > ex else -1
        # jog candidates on integer columns (a fractional jog can sit
        # <0.9um from the next column's run even when its own cell is
        # clear), staggered by the terminal ROW's parity so adjacent
        # terminals -- whose escapes both pass validation because jogs
        # are not committed to the ownership grid -- still land their
        # jog pieces on different columns
        # the jog piece spans from the grid line to the exact
        # coordinate (plus paint/pad width) -- validate every cell
        # that span touches, including one beyond the exact side
        ecells = sorted({gx(ey), gx(2 * ey - gy)})
        xj = first_int(ex + d * ride, d) + d * (gx(ey) % 2)
        ok = False
        while (b[0] - xj) * d > 0.5:
            if jogok is None or all(jogok(xj, cy)
                                    for cy in ecells + [gx(gy)]):
                ok = True
                break
            xj += d
        if not ok:
            # no validated jog site before the corner: turn AT the
            # exact coordinate instead. The corner grid point is
            # collinear with the continuing run and gets pruned by
            # fixup, so the neighboring escape's clearance is the full
            # terminal stagger (0.4um), not eaten by a backtracking
            # jog piece.
            return [exact, (b[0], ey), b]
        return [exact, (xj, ey), (xj, gy), b]
    gx_ = a[0]                       # vertical segment
    if abs(ex - gx_) < 1e-9:
        return [exact, b]
    d = 1 if b[1] > ey else -1
    ecells = sorted({gx(ex), gx(2 * ex - gx_)})
    yj = first_int(ey + d * ride, d) + d * (gx(ex) % 2)
    ok = False
    while (b[1] - yj) * d > 0.5:
        if jogok is None or all(jogok(cx, yj)
                                for cx in ecells + [gx(gx_)]):
            ok = True
            break
        yj += d
    if not ok:
        return [exact, (ex, b[1]), b]
    return [exact, (ex, yj), (gx_, yj), b]


def fixup(path, start_exact, end_exact, ride_s=RIDE, ride_e=RIDE,
          jogok=None):
    """Replace the path's grid endpoints with the exact terminal
    coordinates via bounded exact-rides (see attach). All resulting
    off-grid geometry stays within the ride length of a terminal;
    painted jog blobs are >= 0.36 um^2 (> the 0.24 met3.6/met4.4a
    minimum)."""
    pts = [tuple(p) for p in path]
    if end_exact is None:
        end_exact = pts[-1]
    if len(pts) < 2:
        out = [start_exact, end_exact]
    elif len(pts) == 2:
        # single straight segment terminal-to-terminal. When the whole
        # run fits within the two exact-ride budgets, keep it straight
        # at the exact coordinate (e.g. the stacked buf blocks' supply
        # columns, whose rides span the blocks). Otherwise a long run
        # at an off-grid coordinate (e.g. the VGND switch-B row hops at
        # y+0.325) leans into the neighboring grid cells' clearance the
        # whole way -- grid-ride the middle like any other run, with
        # validated jogs at both ends.
        sx, sy = start_exact
        ex, ey = end_exact
        horiz = abs(pts[0][1] - pts[1][1]) < 1e-6
        span = abs(ex - sx) if horiz else abs(ey - sy)
        gridc = pts[0][1] if horiz else pts[0][0]
        offs = abs(sy - gridc) if horiz else abs(sx - gridc)
        aligned = abs((sy - ey) if horiz else (sx - ex)) < 1e-9
        if aligned and (span <= ride_s + ride_e + 2 or offs <= 0.16):
            out = [start_exact, end_exact]
        elif span <= ride_s + ride_e + 2:
            if horiz:
                mx = (sx + ex) / 2
                out = [start_exact, (mx, sy), (mx, ey), end_exact]
            else:
                my = (sy + ey) / 2
                out = [start_exact, (sx, my), (ex, my), end_exact]
        else:
            head = attach(start_exact, pts[0], pts[1], ride_s, jogok)
            tail = attach(end_exact, pts[1], pts[0], ride_e, jogok)
            out = head[:-1] + list(reversed(tail))[1:]
    else:
        head = attach(start_exact, pts[0], pts[1], ride_s, jogok)
        tail = attach(end_exact, pts[-1], pts[-2], ride_e, jogok)
        out = head + pts[2:-2] + list(reversed(tail))
    dedup = [out[0]]
    for p in out[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    # prune collinear interior points: a router corner made collinear
    # by a turn-at-exact is a BACKTRACK (e.g. exact x15.4 turning east
    # through grid corner x15 -- keeping it would extend the painted
    # run 0.4um the wrong way and eat the neighboring escape's whole
    # clearance)
    pruned = [dedup[0]]
    for k in range(1, len(dedup) - 1):
        p, q, r = pruned[-1], dedup[k], dedup[k + 1]
        if (abs(p[0] - q[0]) < 1e-6 and abs(q[0] - r[0]) < 1e-6) or \
           (abs(p[1] - q[1]) < 1e-6 and abs(q[1] - r[1]) < 1e-6):
            continue
        pruned.append(q)
    pruned.append(dedup[-1])
    fixed = [pruned[0]]
    for k in range(1, len(pruned)):
        x0, y0 = fixed[-1]
        x1, y1 = pruned[k]
        if abs(x0 - x1) < 1e-6 or abs(y0 - y1) < 1e-6:
            fixed.append((x1, y1))
        else:
            fixed.append((x1, y0))
            fixed.append((x1, y1))
    return fixed



def build_wires(terms, abs_bb, result, rt):
    def ride_of(member, a, b):
        """Exact-ride length for this terminal's escape: BLOCK ports
        ride to just past the block edge in the escape direction so
        the whole in-block stretch stays on the staggered exact x;
        cap C1/C2 bus terminals ride the whole terminal-adjacent
        segment so the approach lands exactly on the bus line instead
        of running parallel to it a fraction of a grid cell away."""
        inst = member.split(".")[0]
        if inst in CAPS:
            return 1e6
        if inst not in BLOCKS:
            return RIDE
        (bx1, by1, bx2, by2) = abs_bb[inst]
        x, y = terms[member]
        if abs(a[1] - b[1]) < 1e-6:      # horizontal escape
            edge = bx2 if b[0] > a[0] else bx1
            return abs(edge - x) + 1.0
        edge = by2 if b[1] > a[1] else by1
        return abs(edge - y) + 1.0

    def jogok_for(net):
        def ok(ci, cj):
            i, j = int(round(ci)) - IX0, int(round(cj)) - IY0
            if not (0 <= i < NX and 0 <= j < NY):
                return False
            idx = i * NY + j
            if rt.m3_mask[idx] or rt.m4_mask[idx]:
                return False
            return (rt.m3_owner[idx] in (None, net)
                    and rt.m4_owner[idx] in (None, net))
        return ok

    nets_out = {}
    for name, legs in result.items():
        polylines = []
        jok = jogok_for(name)
        for leg in legs:
            if leg[0] == 'T':
                continue
            kind, frm, to, path = leg
            tfrom, xyfrom = exact(terms, frm)
            tto, xyto = (None, None) if to is None else exact(terms, to)
            rs = ride_of(frm, path[0], path[1]) if len(path) > 1 else RIDE
            re_ = (ride_of(to, path[-1], path[-2])
                   if to is not None and len(path) > 1 else RIDE)
            fixed = fixup(path, xyfrom, xyto, rs, re_, jok)
            poly = [tfrom] + fixed[1:-1] + ([tto] if tto else [fixed[-1]])
            polylines.append(poly)
        nets_out[name] = polylines

    # append the hand-patched routes (see HAND_PATCHES for rationale)
    for net, polys in HAND_PATCHES.items():
        nets_out.setdefault(net, []).extend(polys)
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
    terms, abs_bb, m3_obs, cap_seeds = compute_terms_and_bb()
    rt = Router(abs_bb, m3_obs)
    result, labels_out = plan(rt, terms, cap_seeds)
    nets_out = build_wires(terms, abs_bb, result, rt)
    write_asm_wires(nets_out, labels_out)
    print(f"wrote tools/asm_wires.py ({len(nets_out)} nets, "
          f"{len(labels_out)} labels)")


if __name__ == "__main__":
    main()

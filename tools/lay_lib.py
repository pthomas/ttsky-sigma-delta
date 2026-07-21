#!/usr/bin/env python3
"""Shared block-layout library: golden-driven placement, straps, routing.

Generalizes tools/gen_ota_layout.py + tools/route_ota.py (the OTA keeps
its own scripts; every other block uses this). A block layout is driven
entirely by its golden netlist (spice/golden/<b>.spice) plus a row plan:

  build(block, rows)  -- gencell placement (fets: w per golden finger,
                         nf = golden m; res: snake per res_geom) into
                         mag/<b>_layout.mag + a manifest json
  route(block)        -- straps + taps + m3 risers + m1 tracks, net
                         labels from the golden, ports made for the
                         golden's subckt ports; saves ONLY the parent
                         (writeall-force gotcha, DESIGN.md 2026-07-19),
                         then fresh-process DRC (select top cell;
                         expand) and a structural device compare
  lvs(block)          -- netgen vs the golden subckt

Router facts (inherited from the OTA camp): strap ys at ty +- dy where
dy = 1.5 um for fingers >= 4 um tall, 0.55 um for 2-4 um (w=1 fingers
are BANNED -- gate contact sits too low to clear the drain strap);
riser slots on a 1 um grid with progressive widening; nf >= 2 gencells
leave the rightmost diffusion column unported (parity D if nf even else
S) -- inferred from the port grid; res gencell ports R1/R2/B tap with
mcon+via1 (poly-contact li level, same recipe as fet bulk).
"""

import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.bias_tb import res_geom

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
U = 200.0          # magic internal units and .ext coordinates per um
MW = 0.6           # met wire width um
VIA = 0.34         # via/contact square um
PAD = 0.50         # metal pad enclosing a via/contact cut, um
WRES = 1.41        # res_high_po_1p41 drawn width

ENCLOSING_LAYERS = {
    "mcon": ["m1"],
    "via1": ["m1", "m2"],
    "via2": ["m2", "m3"],
}


def magic_run(script, timeout=600):
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=script, capture_output=True, text=True,
                       cwd="mag", timeout=timeout,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    return r.stdout + r.stderr


def parse_golden(block):
    """(ports, devices) from spice/golden/<block>.spice.

    devices: name (golden card name sans leading X) -> dict(kind, model,
    nodes, w, l, m [, nx, seg for res])."""
    txt = open(f"spice/golden/{block}.spice").read()
    sub = re.search(rf"^\.subckt {block}\b.*?^\.ends", txt,
                    re.M | re.S).group(0)
    lines = [ln for ln in sub.splitlines()
             if ln.strip() and not ln.startswith("*")]
    ports = lines[0].split()[2:]
    devs = {}
    for ln in lines[1:]:
        t = ln.split()
        if t[0][0].upper() != "X":
            continue
        mi = next(i for i, tok in enumerate(t) if "sky130_fd_pr__" in tok)
        model, nodes = t[mi], t[1:mi]
        par = {k.lower(): v for k, v in
               (tok.split("=", 1) for tok in t[mi + 1:] if "=" in tok)}
        name = t[0][1:]
        if "fet" in model:
            devs[name] = dict(kind="fet", model=model, nodes=nodes,
                              w=float(par["w"]), l=float(par["l"]),
                              m=int(float(par.get("m", 1))))
        elif "res_high_po" in model:
            ltot = float(par["l"])
            nx = max(1, round(ltot / 20))   # same rule as res_geom
            devs[name] = dict(kind="res", model=model, nodes=nodes,
                              l=ltot, nx=nx, seg=round(ltot / nx, 3))
        else:
            sys.exit(f"lay_lib: unsupported device in {block}: {ln}")
    return ports, devs


def gencell_cmd(name, d):
    if d["kind"] == "fet":
        assert d["w"] >= 2, f"{name}: w={d['w']} fingers banned (see doc)"
        return (f"magic::gencell sky130::{d['model']} {name} "
                f"w {d['w']:g} l {d['l']:g} nf {d['m']} guard 1 "
                f"conn_gates 1 doports 1")
    return (f"magic::gencell sky130::{d['model']} {name} "
            f"w {WRES} l {d['seg']:g} nx {d['nx']} snake 1 doports 1")


def build(block, rows, gap=3.0):
    """Place the block's devices in rows (bottom-up list of name lists)."""
    ports, devs = parse_golden(block)
    placed = [n for row in rows for n in row]
    assert sorted(placed) == sorted(devs), \
        f"{block}: rows {sorted(placed)} != golden {sorted(devs)}"
    cell = f"{block}_layout"
    # pass 1: sizer
    probe = ["drc off", "cellname create sizer", "load sizer"]
    for n in placed:
        probe += [gencell_cmd(f"U{n}", devs[n]), f"select cell U{n}",
                  f'puts "BBOX {n} [box values]"', "delete"]
    probe.append("quit -noprompt")
    out = magic_run("\n".join(probe) + "\n")
    dims = {}
    for mm in re.finditer(r"BBOX (\S+) (-?\d+) (-?\d+) (-?\d+) (-?\d+)", out):
        n, x1, y1, x2, y2 = mm.group(1), *map(int, mm.groups()[1:])
        dims[n] = ((x2 - x1) / U, (y2 - y1) / U)
    if len(dims) != len(placed):
        print("sizer pass failed:", out[-800:])
        sys.exit(1)
    # pass 2: place
    y = 0.0
    pos = {}
    for row in rows:
        x, hmax = 0.0, 0.0
        for n in row:
            wd, ht = dims[n]
            pos[n] = (x, y)
            x += wd + gap
            hmax = max(hmax, ht)
        y += hmax + gap
    lines = ["drc off", f"cellname create {cell}", f"load {cell}"]
    for n in placed:
        px, py = pos[n]
        lines += [gencell_cmd(f"U{n}", devs[n]), f"select cell U{n}",
                  f"move to {px:.2f}um {py:.2f}um"]
    lines += ["writeall force", "extract all",
              "ext2spice merge conservative", "ext2spice lvs", "ext2spice",
              "quit -noprompt"]
    manifest = {n: dict(x=p[0], y=p[1], w=dims[n][0], h=dims[n][1])
                for n, p in pos.items()}
    json.dump(manifest, open(f"mag/{cell}.json", "w"), indent=1)
    magic_run("\n".join(lines) + "\n")
    wtot = max(p[0] + dims[n][0] for n, p in pos.items())
    print(f"{block}: placed {len(placed)} devices, floorplan "
          f"{wtot:.0f} x {y:.0f} um")
    return wtot, y


def mag_units(cell):
    """Coordinate units per um in this .mag file. Magic only writes
    `magscale 1 2` (units of 0.005 um -> 200/um) when the cell needs
    the half-lambda grid; cells whose geometry happens to land on the
    0.01 grid are written WITHOUT it at 100/um (e.g. cflt, w=22.2).
    Every parser of .mag coordinates must use this per-file value --
    assuming 200 everywhere silently misplaces such cells' children
    by half their coordinates (DESIGN.md 2026-07-20)."""
    head = open(f"mag/{cell}.mag").read(300)
    mm = re.search(r"^magscale (\d+) (\d+)", head, re.M)
    if mm:
        return 100 * int(mm.group(2)) / int(mm.group(1))
    return 100


def parse_parent(cell):
    txt = open(f"mag/{cell}.mag").read()
    uu = mag_units(cell)
    inst = {}
    for mm in re.finditer(r"^use (\S+)\s+(\S+).*?\ntransform (-?\d+) (-?\d+) "
                          r"(-?\d+) (-?\d+) (-?\d+) (-?\d+)",
                          txt, re.M | re.S):
        c, name = mm.group(1), mm.group(2)
        a, b, tx, cc, d, ty = map(int, mm.groups()[2:])
        inst[name] = (c, tx / uu, ty / uu)
    return inst


def cell_layer_rects(cell, layer, depth=1):
    """All <layer> rects of a cell in cell coordinates, including
    subcells to `depth` levels (translation-only transforms, which is
    all these layouts use). Used by the top-level assembly to build a
    PRECISE per-instance obstacle map -- e.g. blocks carry hundreds of
    internal metal3 riser pads a top wire must keep 0.3 um from, while
    the poly-resistor/switch passives carry no metal3 at all."""
    txt = open(f"mag/{cell}.mag").read()
    uu = mag_units(cell)
    out = []
    mm = re.search(rf"<< {layer} >>\n((?:rect [^\n]+\n)+)", txt)
    if mm:
        for r in re.finditer(r"rect (-?\d+) (-?\d+) (-?\d+) (-?\d+)",
                             mm.group(1)):
            out.append(tuple(int(v) / uu for v in r.groups()))
    if depth > 0:
        for name, (ccell, ctx, cty) in parse_parent(cell).items():
            for (x1, y1, x2, y2) in cell_layer_rects(ccell, layer,
                                                     depth - 1):
                out.append((x1 + ctx, y1 + cty, x2 + ctx, y2 + cty))
    return out


def subcell_layer_bbox(cell, layer, px, py, win=0.5):
    """Union bbox of the subcell's <layer> rects near (px, py)
    (subcell coords, um): rects that intersect the window AND are
    vertically local to it (excludes shapes running far up/down, like
    S/D column m1 or guard rings). Used to center tap vias on the
    gencell's own contact pads."""
    txt = open(f"mag/{cell}.mag").read()
    uu = mag_units(cell)
    mm = re.search(rf"<< {layer} >>\n(.*?)\n<<", txt, re.S)
    bb = None
    for r in re.finditer(r"rect (-?\d+) (-?\d+) (-?\d+) (-?\d+)",
                         mm.group(1)):
        x1, y1, x2, y2 = (int(v) / uu for v in r.groups())
        # rects near the port AND vertically local to it -- the S/D
        # column m1 overlaps the pad region in x but extends far down
        # the finger, and the guard ring far up; both must not drag
        # the union away from the actual contact pad
        if x1 < px + win and px - win < x2 and y1 < py + win \
                and py - win < y2 and y1 >= py - win and y2 <= py + win \
                + 0.1:
            bb = (x1, y1, x2, y2) if bb is None else (
                min(bb[0], x1), min(bb[1], y1),
                max(bb[2], x2), max(bb[3], y2))
    return bb


def parse_ports(cell):
    ports = defaultdict(list)
    for line in open(f"mag/{cell}.ext"):
        mm = re.match(r'port "(\S+)" \d+ (-?\d+) (-?\d+) (-?\d+) (-?\d+)',
                      line)
        if mm:
            ports[mm.group(1)].append(
                ((int(mm.group(2)) + int(mm.group(4))) / 2 / U,
                 (int(mm.group(3)) + int(mm.group(5))) / 2 / U))
    return ports


def route(block):
    cell = f"{block}_layout"
    if "<< metal2 >>" in open(f"mag/{cell}.mag").read():
        sys.exit(f"mag/{cell}.mag already routed -- re-run build() first")
    man = json.load(open(f"mag/{cell}.json"))
    inst = parse_parent(cell)
    gports, gold = parse_golden(block)

    tcl = ["drc off", f"load {cell}"]
    audit = []
    cur_net = [None]

    def paint(x1, y1, x2, y2, layers, pad_skip=()):
        # snap to the 0.005 um grid -- off-grid boxes round per-edge at
        # format time and can shave a via below minimum width
        x1, y1, x2, y2 = (round(v * U) / U for v in (x1, y1, x2, y2))
        tcl.append(f"box {x1:.3f}um {y1:.3f}um {x2:.3f}um {y2:.3f}um")
        for l in layers:
            tcl.append(f"paint {l}")
            audit.append((l, x1, y1, x2, y2, cur_net[0]))
        contacts = [l for l in layers if l in ENCLOSING_LAYERS]
        if contacts:
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            p1, p2 = cx - PAD / 2, cx + PAD / 2
            q1, q2 = cy - PAD / 2, cy + PAD / 2
            pads = sorted({mm for l in contacts
                           for mm in ENCLOSING_LAYERS[l]
                           if mm not in pad_skip})
            tcl.append(f"box {p1:.3f}um {q1:.3f}um {p2:.3f}um {q2:.3f}um")
            for mm in pads:
                tcl.append(f"paint {mm}")
                audit.append((mm, p1, q1, p2, q2, cur_net[0]))

    taps = []   # (net, x_lo, x_hi, anchor_x, y)

    for name, g in gold.items():
        cellname, tx, ty = inst[f"U{name}"]
        ports = parse_ports(cellname)
        if g["kind"] == "res":
            n1, n2, nb = g["nodes"]
            cy = man[name]["y"] + man[name]["h"] / 2
            for pname, net in (("R1", n1), ("R2", n2), ("B", nb)):
                (px, py) = ports[pname][0]
                ax, ay = tx + px, ty + py
                cur_net[0] = net
                if pname == "B":
                    paint(ax - VIA / 2, ay - VIA / 2, ax + VIA / 2,
                          ay + VIA / 2, ["mcon", "via1"])
                    taps.append((net, ax - 3.0, ax + 3.0, ax, ay))
                    continue
                # the res gencell already lifts its ends to m1 (a
                # 1.25 x 2.0 um viali region at each end) -- just drop
                # via1 centered on it; painting mcon/li here would
                # abut the subcell's own contact (illegal) or short
                # into the substrate rail
                bb = subcell_layer_bbox(cellname, "viali", px, py,
                                        win=2.3)
                vx = round((tx + (bb[0] + bb[2]) / 2) * U) / U
                vy = round((ty + (bb[1] + bb[3]) / 2) * U) / U
                paint(vx - VIA / 2, vy - VIA / 2, vx + VIA / 2,
                      vy + VIA / 2, ["via1"], pad_skip=("m1",))
                taps.append((net, vx - 3.0, vx + 3.0, vx, vy))
            continue
        # fet: build the S/D column grid, including the unported column
        nd, ng, ns, nb = g["nodes"]
        nets = {"D": nd, "G": ng, "S": ns, "B": nb}
        cols = defaultdict(list)
        for pname, plist in ports.items():
            mm = re.match(r"([SD])\d*$", pname)
            if mm:
                for (px, py) in plist:
                    cols[mm.group(1)].append((tx + px, ty + py))
        allc = sorted((x, t) for t in ("S", "D") for x, _ in cols[t])
        if g["m"] >= 2:
            # rightmost column is unported; parity continues D,S,D,...
            pitch = allc[1][0] - allc[0][0]
            miss_par = "D" if g["m"] % 2 == 0 else "S"
            cols[miss_par].append((allc[-1][0] + pitch, cols["D"][0][1]))
        dy = 1.5 if g["w"] >= 4 else 0.55
        for t, ybar in (("S", ty - dy), ("D", ty + dy)):
            if not cols[t]:
                continue
            xs = sorted(x for x, _ in cols[t])
            cur_net[0] = nets[t]
            paint(xs[0] - MW / 2, ybar - MW / 2, xs[-1] + MW / 2,
                  ybar + MW / 2, ["m2"])
            for x in xs:
                paint(x - VIA / 2, ybar - VIA / 2, x + VIA / 2,
                      ybar + VIA / 2, ["via1"])
            taps.append((nets[t], xs[0], xs[-1], xs[0], ybar))
        if ports["G"]:
            gx, gy = ports["G"][0]
            # the gencell's G-contact m1 is a mosaic of sub-via1-sized
            # rects hemmed in left/right by the S/D column m1: no legal
            # via fits inside it and it cannot be widened. Extend it
            # UPWARD (the only clear direction) with an m1 flag no wider
            # than the mosaic itself, and via up inside the flag.
            bb = subcell_layer_bbox(cellname, "metal1", gx, gy)
            x1, y1, x2, y2 = bb
            # snap via centers to the grid: half-widths are grid
            # multiples, so off-grid centers shave the via below
            # minimum width when edges quantize
            cx = round((tx + (x1 + x2) / 2) * U) / U
            gyv = round((ty + y2 + 0.25) * U) / U
            gv = 0.26 / 2
            cur_net[0] = nets["G"]
            paint(tx + x1, ty + y2 - 0.05, tx + x2, ty + y2 + 0.55,
                  ["m1"])
            paint(cx - gv, gyv - gv, cx + gv, gyv + gv,
                  ["via1", "m2"], pad_skip=("m1",))
            taps.append((nets["G"], cx - 4.0, cx + 4.0, cx, gyv))
        if ports["B"]:
            bx, by = ports["B"][0]
            bx, by = tx + bx, ty + by
            cur_net[0] = nets["B"]
            paint(bx - VIA / 2, by - VIA / 2, bx + VIA / 2, by + VIA / 2,
                  ["mcon", "via1"])
            taps.append((nets["B"], bx - 4.0, bx + 4.0, bx, by))

    # merge same-net taps sharing a y line into one m2 bar with a
    # single riser (supply taps are ~70% of all taps; unmerged they
    # exhaust the 1-per-um riser slot budget and their jogs collide)
    groups = defaultdict(list)
    for t in taps:
        groups[(t[0], round(t[4], 2))].append(t)
    taps = []
    for (net, yq), group in groups.items():
        if len(group) == 1:
            taps.extend(group)
            continue
        group.sort(key=lambda t: t[3])
        obs = [(a, c) for (l, a, b, c, d, n) in audit
               if l == "m2" and n != net and n is not None
               and b < yq + 0.48 and yq - 0.48 < d]
        runs = [[group[0]]]
        for t in group[1:]:
            prev = runs[-1][-1]
            # margin: the painted bar extends 0.2 past the anchors and
            # needs 0.14 clearance on top of that
            s1, s2 = prev[3] - 0.35, t[3] + 0.35
            if any(a < s2 and s1 < c for a, c in obs):
                runs.append([t])
            else:
                runs[-1].append(t)
        for run in runs:
            if len(run) == 1:
                taps.append(run[0])
                continue
            xs = [t[3] for t in run]
            xlo, xhi = min(xs), max(xs)
            cur_net[0] = net
            paint(xlo - 0.25, yq - 0.25, xhi + 0.25, yq + 0.25, ["m2"])
            taps.append((net, xlo, xhi, (xlo + xhi) / 2, yq))

    # risers + tracks (STAGE=straps: stop after straps/taps, for debug)
    if os.environ.get("STAGE") == "straps":
        taps = []
    used = set()
    ymax = max(v["y"] + v["h"] for v in man.values())
    nets = sorted({t[0] for t in taps})
    track_y = {net: round((ymax + 3 + i * 0.8) * U) / U
               for i, net in enumerate(nets)}
    net_slots = defaultdict(list)
    taps.sort(key=lambda t: t[2] - t[1])
    for net, xlo, xhi, anchor, yt in taps:
        cur_net[0] = net
        # nearest free 0.5um slot to the anchor (keeps jogs short); m3
        # risers are 0.4 wide with 0.3 spacing, so used slots must stay
        # >= 1.0 um apart
        slot = None
        for widen in (0, 2, 4, 6, 8):
            cands = [c / 2 for c in
                     range(int(math.ceil((xlo - widen) * 2)),
                           int((xhi + widen) * 2) + 1)]
            cands.sort(key=lambda c: abs(c - anchor))
            jog_obs = [(a, b, c, d) for (l, a, b, c, d, n) in audit
                       if l == "m2" and n != net and n is not None
                       and b < yt + 0.48 and yt - 0.48 < d]
            for cand in cands:
                if not all(abs(cand - u) >= 1.0 for u in used):
                    continue
                # the m2 jog to this slot (+0.14 clearance) must not
                # come near other-net m2
                j1 = min(anchor, cand) - 0.34
                j2 = max(anchor, cand) + 0.34
                if any(a < j2 and j1 < c for (a, b, c, d) in jog_obs):
                    continue
                slot = cand
                break
            if slot is not None:
                break
        if slot is None:
            print(f"NO SLOT for tap of {net} in [{xlo:.1f},{xhi:.1f}]")
            continue
        used.add(slot)
        ytr = track_y[net]
        paint(min(anchor, slot) - 0.25, yt - 0.25,
              max(anchor, slot) + 0.25, yt + 0.25, ["m2"])
        paint(slot - VIA / 2, yt - VIA / 2, slot + VIA / 2, yt + VIA / 2,
              ["via2"])
        paint(slot - 0.2, yt - 0.2, slot + 0.2, ytr + 0.2, ["m3"])
        paint(slot - VIA / 2, ytr - VIA / 2, slot + VIA / 2,
              ytr + VIA / 2, ["via2", "via1"])
        net_slots[net].append(slot)
    for net, slots in net_slots.items():
        cur_net[0] = net
        ytr = track_y[net]
        paint(min(slots) - MW / 2, ytr - MW / 2, max(slots) + MW / 2,
              ytr + MW / 2, ["m1"])
        tcl.append(f"box {min(slots):.3f}um {ytr - 0.2:.3f}um "
                   f"{min(slots) + 0.2:.3f}um {ytr + 0.2:.3f}um")
        tcl.append(f"label {net} FreeSans 0.25um 0 0 0 c m1")
        if net.upper() in [p.upper() for p in gports]:
            tcl.append("port make")

    # same-layer cross-net collision audit
    bad = 0
    for i in range(len(audit)):
        l1, a1, b1, c1, d1, n1 = audit[i]
        for j in range(i + 1, len(audit)):
            l2, a2, b2, c2, d2, n2 = audit[j]
            if l1 != l2 or n1 == n2 or n1 is None or n2 is None:
                continue
            if a1 < c2 and a2 < c1 and b1 < d2 and b2 < d1:
                print(f"COLLISION {l1}: {n1} "
                      f"({a1:.2f},{b1:.2f})-({c1:.2f},{d1:.2f}) vs {n2} "
                      f"({a2:.2f},{b2:.2f})-({c2:.2f},{d2:.2f})")
                bad += 1
    if bad:
        print(f"{bad} same-layer cross-net collisions -- aborting "
              f"before paint")
        sys.exit(1)

    if os.environ.get("LAYDBG"):
        json.dump(audit, open(f"mag/{cell}_audit.json", "w"))
    tcl += [f"save {cell}", "extract all",
            "ext2spice lvs", "ext2spice hierarchy off",
            "ext2spice subcircuit top on",
            "ext2spice merge conservative", "ext2spice",
            "quit -noprompt"]
    magic_run("\n".join(tcl) + "\n")

    # the number that counts: fresh process on the SAVED files
    out2 = magic_run(f"load {cell}\nselect top cell\nexpand\n"
                     "drc on\ndrc check\ndrc catchup\n"
                     'puts "DRCCOUNT [drc listall count total]"\n'
                     "quit -noprompt\n")
    m2 = re.search(r"DRCCOUNT (\d+)", out2)
    drc = int(m2.group(1)) if m2 else -1
    print(f"{block}: DRC errors (fresh reload of saved files): {drc}")

    # structural compare by net names
    got = []
    for mm in re.finditer(r"^X(\S+) (.*?) (sky130\S+)( .*)?$",
                          open(f"mag/{cell}.spice").read(), re.M):
        got.append((mm.group(3), [n.lower() for n in mm.group(2).split()]))
    matched = 0
    for name, g in gold.items():
        if g["kind"] == "fet":
            nd, ng, ns, nb = [n.lower() for n in g["nodes"]]
            hit = [d for d in got if d[0] == g["model"]
                   and len(d[1]) == 4
                   and {d[1][0], d[1][2]} == {nd, ns} and d[1][1] == ng]
        else:
            n1, n2 = [n.lower() for n in g["nodes"][:2]]
            hit = [d for d in got if d[0] == g["model"]
                   and {d[1][0], d[1][1]} == {n1, n2}]
        matched += bool(hit)
        if not hit:
            print(f"  {name}: MISSING "
                  f"({g['model'].split('__')[1]} {g['nodes']})")
    print(f"{block}: {matched}/{len(gold)} golden devices matched")
    return drc, matched, len(gold)


def lvs(block):
    cell = f"{block}_layout"
    r = subprocess.run(
        ["netgen", "-batch", "lvs",
         f"mag/{cell}.spice {cell}",
         f"spice/golden/{block}.spice {block}",
         f"{PDK_ROOT}/sky130A/libs.tech/netgen/sky130A_setup.tcl",
         f"spice/lvs_{block}.out"],
        capture_output=True, text=True,
        env={**os.environ, "PDK_ROOT": PDK_ROOT})
    out = r.stdout + r.stderr
    ok = "Circuits match uniquely" in out
    print(f"{block}: LVS {'match' if ok else 'MISMATCH'}")
    if not ok:
        tail = out[-1500:]
        print(tail)
    return ok

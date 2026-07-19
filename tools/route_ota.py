#!/usr/bin/env python3
"""OTA layout phase 2: finger straps + net routing, driven by the golden netlist.

Reads mag/ota_layout.json (placement manifest), the parent .mag (instance ->
gencell subcell mapping + transforms) and each subcell's .ext (port columns),
then emits magic tcl that:
  1. straps each device's S columns (met1 bar low), D columns (met1 bar
     high) and gate contacts (met1 bar at the pc row) with mcon vias;
  2. routes every net of the golden subckt (spice/ota_top.spice): met2
     vertical risers over one of the terminal's own contact columns, met1
     horizontal tracks in the channels between rows, via1 at junctions;
  3. labels each net on met2 so extraction names match the golden netlist.

Result saved back into mag/ota_layout.mag (parent cell only -- see the
writeall-force gotcha in DESIGN.md 2026-07-19), extracted, DRC-verified in a
fresh magic process, and structurally compared.
Usage: python3 tools/route_ota.py   (after tools/gen_ota_layout.py)
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
RC = f"{PDK_ROOT}/sky130A/libs.tech/magic/sky130A.magicrc"
U = 200.0     # parent transforms, runtime boxes, AND .ext ports per um
U_EXT = 200.0 # (subcell .mag rect files are 100/um -- not used here)
MW = 0.6                  # met wire width um
VIA = 0.34                # via/contact square um
PAD = 0.50                # metal pad enclosing a via/contact cut, um (safely
                          # above the largest required enclosure: via2/met2
                          # needs 0.045um/side -> VIA+2*0.045=0.43 minimum)

# contact/via type -> metal layers that must enclose it with a PAD-sized box
ENCLOSING_LAYERS = {
    "mcon": ["m1"],
    "via1": ["m1", "m2"],
    "via2": ["m2", "m3"],
}


def magic_run(script):
    r = subprocess.run(["magic", "-dnull", "-noconsole", "-rcfile", RC],
                       input=script, capture_output=True, text=True,
                       cwd="mag", timeout=600,
                       env={**os.environ, "PDK_ROOT": PDK_ROOT})
    return r.stdout + r.stderr


def parse_parent():
    """instance -> (subcell base name, tx, ty) in um."""
    txt = open("mag/ota_layout.mag").read()
    inst = {}
    for m in re.finditer(r"^use (\S+)\s+(\S+).*?\ntransform (-?\d+) (-?\d+) "
                         r"(-?\d+) (-?\d+) (-?\d+) (-?\d+)", txt, re.M | re.S):
        cell, name = m.group(1), m.group(2)
        a, b, tx, c, d, ty = map(int, m.groups()[2:])
        inst[name] = (cell, tx / U, ty / U)
    return inst


def parse_ports(cell):
    """port name -> (x um, y um) relative to subcell origin."""
    ports = {}
    for line in open(f"mag/{cell}.ext"):
        m = re.match(r'port "(\S+)" \d+ (-?\d+) (-?\d+) (-?\d+) (-?\d+) (\S+)',
                     line)
        if m:
            ports[m.group(1)] = ((int(m.group(2)) + int(m.group(4))) / 2 / U_EXT,
                                 (int(m.group(3)) + int(m.group(5))) / 2 / U_EXT)
    return ports


def golden():
    """device -> dict(model, D, G, S, B) from the xschem netlist."""
    sub = re.search(r"^\.subckt ota .*?^\.ends",
                    open("spice/ota_top.spice").read(), re.M | re.S).group(0)
    dev = {}
    for m in re.finditer(r"^X(M\S+|MDN|MDP) (\S+) (\S+) (\S+) (\S+) (sky130\S+)",
                         sub, re.M):
        dev[m.group(1)] = dict(model=m.group(6), D=m.group(2), G=m.group(3),
                               S=m.group(4), B=m.group(5))
    return dev


def main():
    man = json.load(open("mag/ota_layout.json"))
    inst = parse_parent()
    gold = golden()

    tcl = ["drc off", "load ota_layout"]
    audit = []            # (layer, x1, y1, x2, y2, net) for collision check
    cur_net = [None]

    def paint(x1, y1, x2, y2, layers):
        tcl.append(f"box {x1:.3f}um {y1:.3f}um {x2:.3f}um {y2:.3f}um")
        for l in layers:
            tcl.append(f"paint {l}")
            audit.append((l, x1, y1, x2, y2, cur_net[0]))
        # any via/contact cut gets a PAD-sized enclosing box on every metal
        # layer it must be enclosed by, regardless of what nearby wire
        # geometry happens to provide -- undersized/absent enclosure was the
        # dominant DRC violation class before this.
        contacts = [l for l in layers if l in ENCLOSING_LAYERS]
        if contacts:
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            px1, py1 = cx - PAD / 2, cy - PAD / 2
            px2, py2 = cx + PAD / 2, cy + PAD / 2
            pads = sorted({m for l in contacts for m in ENCLOSING_LAYERS[l]})
            tcl.append(f"box {px1:.3f}um {py1:.3f}um {px2:.3f}um {py2:.3f}um")
            for m in pads:
                tcl.append(f"paint {m}")
                audit.append((m, px1, py1, px2, py2, cur_net[0]))

    # taps: (net, x_lo, x_hi, y) ranges where a riser may drop
    taps = []

    for name, g in gold.items():
        cell, tx, ty = inst[name]
        ports = parse_ports(cell)
        cols = defaultdict(list)
        for pname, (px, py) in ports.items():
            m = re.match(r"([SDG])\d*$", pname)
            if m:
                cols[m.group(1)].append((tx + px, ty + py))
        # 13th (port-less) outer column: same parity as D group
        allx = sorted(x for t in ("S", "D") for x, _ in cols[t])
        if len(allx) >= 2 and os.environ.get("STAGE") != "bars":
            pitch = allx[1] - allx[0]
            cols["D"].append((allx[-1] + pitch, cols["D"][0][1]))
        bulk = [(tx + px, ty + py) for pn, (px, py) in ports.items()
                if pn == "B"]
        ys = {"S": ty - 1.5, "D": ty + 1.5}
        cur_net[0] = None
        for t in ("S", "D"):
            if not cols[t]:
                continue
            xs = sorted(x for x, _ in cols[t])
            yb = ys[t]
            cur_net[0] = g[t]
            paint(xs[0] - MW / 2, yb - MW / 2, xs[-1] + MW / 2, yb + MW / 2,
                  ["m2"])
            for x, _ in cols[t]:
                paint(x - VIA / 2, yb - VIA / 2, x + VIA / 2, yb + VIA / 2,
                      ["via1"])
            taps.append((g[t], xs[0], xs[-1], xs[0], yb))
        if cols["G"] and os.environ.get("STAGE") != "bars":
            gx, gy = cols["G"][0]
            cur_net[0] = g["G"]
            paint(gx - VIA / 2, gy - VIA / 2, gx + VIA / 2, gy + VIA / 2,
                  ["via1", "m2"])
            taps.append((g["G"], gx - 4.0, gx + 4.0, gx, gy))
        if bulk and os.environ.get("STAGE") != "bars":
            bx, by = bulk[0]
            cur_net[0] = g["B"]
            paint(bx - VIA / 2, by - VIA / 2, bx + VIA / 2, by + VIA / 2,
                  ["mcon", "via1"])
            taps.append((g["B"], bx - 4.0, bx + 4.0, bx, by))

    if os.environ.get("STAGE") in ("straps", "bars"):
        taps = []

    # globally unique riser x slots on a 1 um grid, inside each tap range
    used = set()
    ymax = max(v["y"] + v["h"] for v in man.values())
    nets = sorted({t[0] for t in taps})
    track_y = {net: ymax + 3 + i * 0.8 for i, net in enumerate(nets)}
    net_slots = defaultdict(list)
    import math
    taps.sort(key=lambda t: t[2] - t[1])   # narrowest ranges pick slots first
    for net, xlo, xhi, anchor, yt in taps:
        cur_net[0] = net
        slot = None
        for cand in range(int(math.ceil(xlo)), int(xhi) + 1):
            if cand not in used:
                slot = cand
                break
        if slot is None:
            print(f"NO SLOT for tap of {net} in [{xlo:.1f},{xhi:.1f}]")
            continue
        used.add(slot)
        ytr = track_y[net]
        # m2 jog from the tap anchor to the slot, m3 riser up
        paint(min(anchor, slot) - 0.2, yt - 0.2, max(anchor, slot) + 0.2,
              yt + 0.2, ["m2"])
        paint(slot - VIA / 2, yt - VIA / 2, slot + VIA / 2, yt + VIA / 2,
              ["via2"])
        paint(slot - 0.2, yt - 0.2, slot + 0.2, ytr + 0.2, ["m3"])
        paint(slot - VIA / 2, ytr - VIA / 2, slot + VIA / 2, ytr + VIA / 2,
              ["via2", "via1"])
        net_slots[net].append(slot)
    for net, slots in net_slots.items():
        cur_net[0] = net
        ytr = track_y[net]
        paint(min(slots) - MW / 2, ytr - MW / 2, max(slots) + MW / 2,
              ytr + MW / 2, ["m1"])
        tcl.append(f"box {min(slots):.3f}um {ytr - 0.2:.3f}um "
                   f"{min(slots) + 0.2:.3f}um {ytr + 0.2:.3f}um")
        tcl.append(f"label {net} FreeSans 0.25um 0 0 0 c m1")
        if net in ("INP", "INM", "OUT", "VDD", "VSS", "IREFP", "IREFN",
                   "VBNC", "VBPC"):
            tcl.append("port make")

    bad = 0
    for i in range(len(audit)):
        l1, a1, b1, c1, d1, n1 = audit[i]
        for j in range(i + 1, len(audit)):
            l2, a2, b2, c2, d2, n2 = audit[j]
            if l1 != l2 or n1 == n2 or n1 is None or n2 is None:
                continue
            if a1 < c2 and a2 < c1 and b1 < d2 and b2 < d1:
                print(f"COLLISION {l1}: {n1} ({a1:.2f},{b1:.2f})-({c1:.2f},{d1:.2f})"
                      f" vs {n2} ({a2:.2f},{b2:.2f})-({c2:.2f},{d2:.2f})")
                bad += 1
    if bad:
        print(f"{bad} same-layer cross-net collisions -- fix before painting")

    # save ONLY the modified parent: "writeall force" in magic 8.3.676
    # rewrites the (unmodified) gencell subcells lambda-normalized without
    # their magscale header, halving odd 0.005um coordinates lossily -- on
    # the next load the rounding error shows up as hundreds of fake
    # spacing/width DRC violations inside the devices (licon.9+psdm.5a etc.)
    tcl += ["save ota_layout", "extract all",
            "ext2spice lvs", "ext2spice hierarchy off",
            "ext2spice subcircuit top on",
            "ext2spice merge conservative", "ext2spice",
            "drc on", "select top cell", "expand", "drc check", "drc catchup",
            'puts "DRCCOUNT [drc listall count total]"', "quit -noprompt"]
    out = magic_run("\n".join(tcl) + "\n")
    m = re.search(r"DRCCOUNT (\d+)", out)
    print(f"routing painted; DRC errors (in-session): {m.group(1) if m else '?'}")

    # the number that counts: re-check the SAVED files in a fresh process
    # (catches save/reload grid-quantization damage the in-session check
    # cannot see -- see DESIGN.md 2026-07-19 writeall gotcha)
    out2 = magic_run("load ota_layout\nselect top cell\nexpand\n"
                     "drc check\ndrc catchup\n"
                     'puts "DRCCOUNT [drc listall count total]"\n'
                     "quit -noprompt\n")
    m2 = re.search(r"DRCCOUNT (\d+)", out2)
    print(f"DRC errors (fresh reload of saved files): "
          f"{m2.group(1) if m2 else '?'}")

    # structural compare by net names
    got = []
    for mm in re.finditer(r"^X(\S+) (\S+) (\S+) (\S+) (\S+) (sky130\S+)(.*)$",
                          open("mag/ota_layout.spice").read(), re.M):
        got.append((mm.group(6), mm.group(2), mm.group(3), mm.group(4),
                    mm.group(5), mm.group(7).strip()))
    print(f"extracted devices after merge: {len(got)}")
    want = golden()
    matched = 0
    for name, g in want.items():
        hit = [d for d in got if d[0] == g["model"] and
               {d[1].lower(), d[3].lower()} == {g["D"].lower(), g["S"].lower()}
               and d[2].lower() == g["G"].lower()]
        status = "ok" if hit else "MISSING"
        matched += bool(hit)
        print(f"  {name:>4s} {g['model'].split('__')[1]:<18s} "
              f"D={g['D']:<6s} G={g['G']:<6s} S={g['S']:<6s} {status}")
    print(f"{matched}/{len(want)} golden devices matched")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Canonical equivalence: xschem-netlisted block schematics vs goldens.

For each block, extract .subckt <b> from the xschem netlist
(spice/<b>_top.spice) and from the golden (spice/golden/<b>.spice),
then compare:
  - port list (order matters -- it is the .sym/LVS contract), and
  - the device multiset, canonicalized to (model, nodes, geometry):
      fet: (model, (d,g,s,b), W, L, m)   -- m from m= else mult=
      res: (model, {end,end}, body, L)   -- ends unordered (symmetric)
      cap: (model, {c0,c1}, W, L)
Names and drawing-only params (ad/as/pd/ps/nrd/nrs/nf/MF) are ignored;
node comparison is case-insensitive. This is stronger than a sim-match
tolerance check: the netlists must be device-for-device identical.

comp is included (its sim-level equivalence stays in make compcheck).

Usage: python3 tools/xcheck_blocks.py [blocks...]   (after gen_golden,
gen_sch/gen_comp_sch and xschem --netlist of each <b>_top.sch)
"""

import os
import re
import sys

BLOCKS = ["comp", "dff", "bias", "buf", "lvl", "odrv"]


def parse_subckt(path, name):
    txt = open(path).read()
    mm = re.search(rf"^\.subckt {name}\b.*?^\.ends", txt,
                   re.M | re.S | re.I)
    if not mm:
        sys.exit(f"no .subckt {name} in {path}")
    # join continuation lines, drop comments
    lines = []
    for ln in mm.group(0).splitlines():
        if ln.startswith("+") and lines:
            lines[-1] += " " + ln[1:]
        elif ln.strip() and not ln.startswith("*"):
            lines.append(ln)
    ports = lines[0].split()[2:]
    devs = []
    for ln in lines[1:]:
        t = ln.split()
        if t[0][0].upper() != "X":
            continue
        mi = next((i for i, tok in enumerate(t)
                   if "sky130_fd_pr__" in tok), None)
        if mi is None:
            sys.exit(f"{path}: no sky130 model in card: {ln}")
        model = t[mi].lower()
        nodes = [n.lower() for n in t[1:mi]]
        par = {}
        for tok in t[mi + 1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                par[k.lower()] = v
        # xschem trims trailing digits when netlisting (3.235 ->
        # 3.23): compare dimensions at 0.01 um resolution
        num = lambda k, d=None: round(float(par.get(k, d)), 2)
        if "fet" in model:
            devs.append(("fet", model, tuple(nodes), num("w"), num("l"),
                         float(par.get("m", par.get("mult", 1)))))
        elif "res" in model:
            devs.append(("res", model, frozenset(nodes[:2]), nodes[2],
                         num("l"), float(par.get("m", par.get("mult", 1)))))
        elif "cap" in model:
            devs.append(("cap", model, frozenset(nodes[:2]), num("w"),
                         num("l"), float(par.get("m", par.get("mult", 1)))))
        else:
            sys.exit(f"{path}: unclassified device: {ln}")
    return [p.lower() for p in ports], sorted(devs, key=repr)


def check(name):
    gp, gd = parse_subckt(f"spice/golden/{name}.spice", name)
    xp, xd = parse_subckt(f"spice/{name}_top.spice", name)
    ok = True
    if gp != xp:
        print(f"  PORT ORDER drifted: golden {gp} vs xschem {xp}")
        ok = False
    gonly = [d for d in gd if d not in xd]
    xonly = [d for d in xd if d not in gd]
    for d in gonly:
        print(f"  golden only: {d}")
    for d in xonly:
        print(f"  xschem only: {d}")
    if gonly or xonly:
        ok = False
    print(f"{name}: {len(gd)} devices, "
          f"{'MATCH' if ok else 'MISMATCH'}")
    return ok

def main():
    blocks = sys.argv[1:] or BLOCKS
    ok = all([check(b) for b in blocks])
    print("ALL MATCH" if ok else "MISMATCH -- fix gen_sch tables")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

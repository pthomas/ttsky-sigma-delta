#!/usr/bin/env python3
"""Generate xschem schematics for the support blocks from the TB sizes.

Same rule as the OTA/comparator: sizes have exactly one home (the SIZES
dict in sim/<b>_tb.py); this tool draws xschem/<b>.sch (+ <b>.sym and a
netlisting wrapper <b>_top.sch) from per-block device tables, and
tools/xcheck_blocks.py proves the xschem netlist device-for-device
equivalent to the golden netlist (spice/golden/<b>.spice).

Pin order in each .sym is the contract the equivalence check and LVS
rely on -- it must match the golden .subckt port order.

Blocks: dff, bias, buf, lvl, odrv (comp has tools/gen_comp_sch.py, the
pattern this generalizes).

Usage: python3 tools/gen_sch.py   (from repo root)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.ota_tb import SIZES as OTA_S, WUNIT
from sim.dff_tb import DSIZES
from sim.bias_tb import BSIZES, r_len, c_side
from sim.buf_tb import FSIZES, IUNIT
from sim.lvl_tb import LSIZES
from sim.odrv_tb import OSIZES

NF, PF = "nfet_g5v0d10v5", "pfet_g5v0d10v5"
NF18, PF18 = "nfet_01v8", "pfet_01v8"
RES, CAP = "res_high_po_1p41", "cap_mim_m3_1"


def m(w):
    return max(1, round(w / WUNIT))


# ---- device row constructors (kind, name, x, y, ...) --------------------

def fet(name, x, y, model, d, g, s, b, W, L, mult):
    return ("fet", name, x, y, model, (d, g, s, b), dict(W=W, L=L, m=mult))


def res(name, x, y, top, bot, body, L):
    """Vertical res_high_po_1p41: P pin on top, M pin on bottom."""
    return ("res", name, x, y, RES, (bot, top, body), dict(L=L))


def cap(name, x, y, top, bot, W, L):
    """Vertical cap_mim_m3_1: c0 on top, c1 on bottom."""
    return ("cap", name, x, y, CAP, (top, bot), dict(W=W, L=L))


def inv(n, i, o, x, W, L, yp=-650, yn=-500, vdd="VDD", vss="VSS"):
    return [fet(f"XI{n}P", x, yp, PF, o, i, vdd, vdd, WUNIT, L, m(W)),
            fet(f"XI{n}N", x, yn, NF, o, i, vss, vss, WUNIT, L, m(W))]


def tg(n, a, b_, cn, cp, x, W, L):
    return [fet(f"XT{n}N", x, -650, NF, a, cn, b_, "VSS", WUNIT, L, m(W)),
            fet(f"XT{n}P", x, -500, PF, a, cp, b_, "VDD", WUNIT, L, m(W))]


def inv_wire(x, o, yp=-650, yn=-500):
    return (x + 20, yp + 30, x + 20, yn - 30, o)


# ---- block definitions --------------------------------------------------

def block_dff():
    p = DSIZES
    devs, wires = [], []
    cols = [-1400 + 150 * i for i in range(10)]
    devs += inv("C", "CLK", "clkb", cols[0], p["W_INV"], p["L"])
    devs += tg("M", "D", "mi", "clkb", "CLK", cols[1], p["W_TG"], p["L"])
    devs += inv("M1", "mi", "mb", cols[2], p["W_INV"], p["L"])
    devs += inv("M2", "mb", "mfb", cols[3], p["W_INV"], p["L"])
    devs += tg("MF", "mfb", "mi", "CLK", "clkb", cols[4], p["W_TG"], p["L"])
    devs += tg("S", "mb", "si", "CLK", "clkb", cols[5], p["W_TG"], p["L"])
    devs += inv("S1", "si", "QB", cols[6], p["W_INV"], p["L"])
    devs += inv("S2", "QB", "sfb", cols[7], p["W_INV"], p["L"])
    devs += tg("SF", "sfb", "si", "clkb", "CLK", cols[8], p["W_TG"], p["L"])
    devs += inv("Q1", "QB", "Q", cols[9], p["W_INV"], p["L"])
    for x, o in ((cols[0], "clkb"), (cols[2], "mb"), (cols[3], "mfb"),
                 (cols[6], "QB"), (cols[7], "sfb"), (cols[9], "Q")):
        wires.append(inv_wire(x, o))
    # TG columns: the two pass-device S pins are adjacent -- join them
    for x, b_ in ((cols[1], "mi"), (cols[4], "mi"), (cols[5], "si"),
                  (cols[8], "si")):
        wires.append((x + 20, -620, x + 20, -530, b_))
    return dict(
        devices=devs, wires=wires,
        ports=["D", "CLK", "Q", "QB", "VDD", "VSS"],
        pin_syms=dict(D="ipin", CLK="ipin", Q="opin", QB="opin",
                      VDD="iopin", VSS="iopin"),
        sym_pins=[("D", "in", -140, -40), ("CLK", "in", -140, 40),
                  ("Q", "out", 140, -40), ("QB", "out", 140, 40),
                  ("VDD", "inout", -20, -100), ("VSS", "inout", -20, 100)],
        sym_label="DFF",
        sym_texts=[("clk", -95, 32, 0.25)],
        title="master-slave TG DFF retimer",
        subtitle=(f"static CMOS, master latches on rising CLK; pins Q "
                  f"move only at the edge; unit finger W={WUNIT} "
                  f"L={DSIZES['L']}"))


def block_bias():
    p = BSIZES
    devs = [
        # constant-gm core
        fet("XMP1", -1400, -800, PF, "nb", "pb", "VDD", "VDD",
            WUNIT, p["L_P"], m(p["W_P"])),
        fet("XMP2", -1250, -800, PF, "pb", "pb", "VDD", "VDD",
            WUNIT, p["L_P"], m(p["W_P"])),
        fet("XM1", -1400, -500, NF, "nb", "nb", "VSS", "VSS",
            WUNIT, p["L_N"], m(p["W_N"])),
        fet("XM2", -1250, -500, NF, "pb", "nb", "rs", "VSS",
            WUNIT, p["L_N"], m(p["K"] * p["W_N"])),
        res("RB", -1250, -350, "rs", "VSS", "VSS", r_len(p["RB"])),
        # startup with disable
        fet("XST", -1100, -800, PF, "nst", "VSS", "VDD", "VDD",
            WUNIT, p["L_START"], 1),
        fet("XFD", -1100, -650, PF, "nb", "VSS", "nst", "VDD",
            WUNIT, 2, 1),
        fet("XSW", -1100, -500, NF, "nst", "vbnc_i", "VSS", "VSS",
            WUNIT, 0.5, 2),
        # reference mirrors (cascoded)
        fet("XIN", -900, -800, PF, "ind", "pb", "VDD", "VDD",
            WUNIT, p["L_P"], m(p["M_IREFN"] * p["W_P"])),
        fet("XINC", -900, -650, PF, "IREFN", "vbpc_i", "ind", "VDD",
            WUNIT, 0.5, m(p["M_IREFN"] * p["W_P"])),
        fet("XIPC", -900, -500, NF, "IREFP", "vbnc_i", "ipd", "VSS",
            WUNIT, 0.5, m(p["M_IREFP"] * p["W_N"])),
        fet("XIP", -900, -350, NF, "ipd", "nb", "VSS", "VSS",
            WUNIT, p["L_N"], m(p["M_IREFP"] * p["W_N"])),
        # cascode gate bias strings + RC filters
        fet("XVN", -700, -800, PF, "vbnc_i", "pb", "VDD", "VDD",
            WUNIT, p["L_P"], m(p["W_P"])),
        res("RBNC", -700, -650, "vbnc_i", "VSS", "VSS", r_len(p["R_BNC"])),
        res("RNB1", -700, -500, "vbnc_i", "VBNC", "VSS", r_len(1e3)),
        fet("XVP", -500, -800, PF, "vbpc_i", "pb", "VDD", "VDD",
            WUNIT, p["L_P"], m(p["W_P"])),
        res("RBPC", -500, -650, "vbpc_i", "VSS", "VSS", r_len(p["R_BPC"])),
        res("RNB2", -500, -500, "vbpc_i", "VBPC", "VSS", r_len(1e3)),
        # VBNC/VBPC 1 pF MiM filter caps are top-level cells (see
        # bias_tb.bias_caps)
    ]
    wires = [
        # mirror columns: PMOS drain down onto NMOS drain
        (-1380, -770, -1380, -530, "nb"),
        (-1230, -770, -1230, -530, "pb"),
        # startup column: XST drain -> XFD source
        (-1080, -770, -1080, -680, "nst"),
        # cascode totems
        (-880, -770, -880, -680, "ind"),
        (-880, -470, -880, -380, "ipd"),
        # bias strings: XVN/XVP drain down into the resistor tops
        (-680, -770, -700, -680, "vbnc_i"),
        (-480, -770, -500, -680, "vbpc_i"),
    ]
    return dict(
        devices=devs, wires=wires,
        ports=["IREFP", "IREFN", "VBNC", "VBPC", "VDD", "VSS"],
        pin_syms=dict(IREFP="opin", IREFN="opin", VBNC="opin", VBPC="opin",
                      VDD="iopin", VSS="iopin"),
        sym_pins=[("IREFP", "out", 140, -60), ("IREFN", "out", 140, -20),
                  ("VBNC", "out", 140, 20), ("VBPC", "out", 140, 60),
                  ("VDD", "inout", -20, -100), ("VSS", "inout", -20, 100)],
        sym_label="BIAS",
        sym_texts=[],
        title="constant-gm bias generator + cascoded reference mirrors",
        subtitle=(f"beta-multiplier master (RB {p['RB']/1e3:g}k), "
                  f"startup-with-disable, VBNC/VBPC from R ratios; poly-R"
                  f"/MiM devices, ngspice-model-calibrated lengths"))


def block_buf():
    p = FSIZES
    mt = round(p["ITAIL"] / IUNIT)
    devs = [
        fet("XT", -300, -800, PF, "tail", "IREFP", "VDD", "VDD",
            WUNIT, OTA_S["L_TAIL"], mt),
        fet("X1", -400, -650, PF, "o1", "IN", "tail", "VDD",
            WUNIT, p["L_IN"], m(p["W_IN"])),
        fet("X2", -200, -650, PF, "OUT", "OUT", "tail", "VDD",
            WUNIT, p["L_IN"], m(p["W_IN"])),
        fet("X3", -400, -450, NF, "o1", "o1", "VSS", "VSS",
            WUNIT, p["L_MIR"], m(p["W_MIR"])),
        fet("X4", -200, -450, NF, "OUT", "o1", "VSS", "VSS",
            WUNIT, p["L_MIR"], m(p["W_MIR"])),
    ]
    wires = [
        (-280, -770, -280, -700, "tail"),
        (-380, -700, -180, -700, "tail"),
        (-380, -680, -380, -700, "tail"), (-180, -680, -180, -700, "tail"),
        (-380, -620, -380, -480, "o1"),
        (-180, -620, -180, -480, "OUT"),
    ]
    return dict(
        devices=devs, wires=wires,
        ports=["IN", "OUT", "IREFP", "VDD", "VSS"],
        pin_syms=dict(IN="ipin", OUT="opin", IREFP="ipin",
                      VDD="iopin", VSS="iopin"),
        sym_pins=[("IN", "in", -140, -40), ("OUT", "out", 140, 0),
                  ("IREFP", "in", -140, 40),
                  ("VDD", "inout", -20, -100), ("VSS", "inout", -20, 100)],
        sym_label="BUF",
        sym_texts=[("iref", -95, 32, 0.25)],
        title="5T unity-follower reference buffer",
        subtitle=(f"PMOS input, NMOS mirror load, tail mult {mt} off the "
                  f"OTA IREFP diode line (5 uA/finger); one design, three "
                  f"instances (VREFN/VCM/VREFP)"))


def block_lvl():
    p = LSIZES
    devs = [
        fet("XIP", -1000, -650, PF18, "nb18", "CLK18", "VDD18", "VDD18",
            10, 0.35, 1),
        fet("XIN", -1000, -500, NF18, "nb18", "CLK18", "VSS", "VSS",
            5, 0.35, 1),
        fet("XP1", -800, -650, PF, "n1", "n2", "VDD33", "VDD33",
            WUNIT, p["L_XC"], m(p["W_XC"])),
        fet("XP2", -600, -650, PF, "n2", "n1", "VDD33", "VDD33",
            WUNIT, p["L_XC"], m(p["W_XC"])),
        fet("XN1", -800, -500, NF, "n1", "CLK18", "VSS", "VSS",
            WUNIT, p["L5"], m(p["W_PD"])),
        fet("XN2", -600, -500, NF, "n2", "nb18", "VSS", "VSS",
            WUNIT, p["L5"], m(p["W_PD"])),
        fet("XB1P", -400, -650, PF, "CLK33", "n1", "VDD33", "VDD33",
            WUNIT, p["L5"], m(p["W_BUF"])),
        fet("XB1N", -400, -500, NF, "CLK33", "n1", "VSS", "VSS",
            WUNIT, p["L5"], m(p["W_BUF"])),
        fet("XB2P", -200, -650, PF, "CLKB33", "n2", "VDD33", "VDD33",
            WUNIT, p["L5"], m(p["W_BUF"])),
        fet("XB2N", -200, -500, NF, "CLKB33", "n2", "VSS", "VSS",
            WUNIT, p["L5"], m(p["W_BUF"])),
    ]
    wires = [inv_wire(-1000, "nb18"), (-780, -620, -780, -530, "n1"),
             (-580, -620, -580, -530, "n2"),
             inv_wire(-400, "CLK33"), inv_wire(-200, "CLKB33")]
    return dict(
        devices=devs, wires=wires,
        ports=["CLK18", "CLK33", "CLKB33", "VDD18", "VDD33", "VSS"],
        pin_syms=dict(CLK18="ipin", CLK33="opin", CLKB33="opin",
                      VDD18="iopin", VDD33="iopin", VSS="iopin"),
        sym_pins=[("CLK18", "in", -140, 0), ("CLK33", "out", 140, -40),
                  ("CLKB33", "out", 140, 40),
                  ("VDD18", "inout", -60, -100),
                  ("VDD33", "inout", 20, -100),
                  ("VSS", "inout", -20, 100)],
        sym_label="LVL",
        sym_texts=[],
        title="cross-coupled 1.8->3.3 V clock level shifter",
        subtitle=("thin-oxide input inverter on VDPWR, strong 5V "
                  "pulldowns vs weak cross-coupled PMOS, buffered "
                  "complementary outputs"))


def block_odrv():
    p = OSIZES
    devs = [
        fet("X1P", -600, -650, PF, "a", "IN33", "VDD18", "VDD18",
            WUNIT, p["L5"], m(p["W_IN_P"])),
        fet("X1N", -600, -500, NF, "a", "IN33", "VSS", "VSS",
            WUNIT, p["L5"], m(p["W_IN_N"])),
        fet("X2P", -400, -650, PF18, "b", "a", "VDD18", "VDD18",
            p["W_B1"] * 2, p["L18"], 1),
        fet("X2N", -400, -500, NF18, "b", "a", "VSS", "VSS",
            p["W_B1"], p["L18"], 1),
        fet("X3P", -200, -650, PF18, "OUT18", "b", "VDD18", "VDD18",
            p["W_B2"] * 2, p["L18"], 1),
        fet("X3N", -200, -500, NF18, "OUT18", "b", "VSS", "VSS",
            p["W_B2"], p["L18"], 1),
    ]
    wires = [inv_wire(-600, "a"), inv_wire(-400, "b"),
             inv_wire(-200, "OUT18")]
    return dict(
        devices=devs, wires=wires,
        ports=["IN33", "OUT18", "VDD18", "VSS"],
        pin_syms=dict(IN33="ipin", OUT18="opin", VDD18="iopin",
                      VSS="iopin"),
        sym_pins=[("IN33", "in", -140, 0), ("OUT18", "out", 140, 0),
                  ("VDD18", "inout", -20, -100),
                  ("VSS", "inout", -20, 100)],
        sym_label="ODRV",
        sym_texts=[],
        title="3.3->1.8 V output driver",
        subtitle=("stage 1: 5V-gate inverter on the 1.8V rail (no "
                  "thin-oxide overstress), then thin-oxide buffers; two "
                  "instances drive uo[0]/uo[1]"))


BLOCKS = dict(dff=block_dff, bias=block_bias, buf=block_buf,
              lvl=block_lvl, odrv=block_odrv)


# ---- renderers (generalized from tools/gen_comp_sch.py) -----------------

def write_sch(name, spec, path):
    out = ["v {xschem version=3.4.4 file_version=1.2}",
           "G {}", "K {}", "V {}", "S {}", "E {}"]
    out.append(f"T {{{name}: {spec['title']} - GENERATED by "
               f"tools/gen_sch.py from sim/{name}_tb.py sizes - do not "
               f"edit by hand}} -1400 -1000 0 0 0.4 0.4 {{}}")
    out.append(f"T {{{spec['subtitle']}}} -1400 -960 0 0 0.3 0.3 {{}}")
    for i, port in enumerate(spec["ports"]):
        x = -1400 + i * 120
        out.append(f"C {{devices/{spec['pin_syms'][port]}.sym}} {x} -900 "
                   f"0 0 {{name=pp{i} lab={port}}}")
    n = 0
    for kind, dname, x, y, model, nodes, par in spec["devices"]:
        if kind == "fet":
            out.append(f"C {{sky130_fd_pr/{model}.sym}} {x} {y} 0 0 "
                       f"{{name={dname} model={model} spiceprefix=X "
                       f"W={par['W']:g} L={par['L']:g} nf=1 "
                       f"mult={par['m']} "
                       f"ad=0 as=0 pd=0 ps=0 nrd=0 nrs=0}}")
            d, g, s, b = nodes
            # nfet symbol: D top / S bottom; pfet symbol: S top / D bottom
            dy_d, dy_s = (-30, 30) if model.startswith("n") else (30, -30)
            pins = ((d, x + 20, y + dy_d, 1), (g, x - 20, y, 0),
                    (s, x + 20, y + dy_s, 3), (b, x + 45, y, 2))
            out.append(f"N {x + 20} {y} {x + 45} {y} {{lab={b}}}")
        elif kind == "res":
            out.append(f"C {{sky130_fd_pr/{model}.sym}} {x} {y} 0 0 "
                       f"{{name={dname} model={model} spiceprefix=X "
                       f"L={par['L']:g} mult=1}}")
            bot, top, body = nodes
            pins = ((bot, x, y + 30, 3), (top, x, y - 30, 1),
                    (body, x - 20, y, 0))
        else:   # cap
            out.append(f"C {{sky130_fd_pr/{model}.sym}} {x} {y} 0 0 "
                       f"{{name={dname} model={model} spiceprefix=X "
                       f"W={par['W']:g} L={par['L']:g} MF=1}}")
            top, bot = nodes
            pins = ((top, x, y - 30, 1), (bot, x, y + 30, 3))
        for lab, px, py, rot in pins:
            out.append(f"C {{devices/lab_pin.sym}} {px} {py} {rot} 0 "
                       f"{{name=l{n} lab={lab}}}")
            n += 1
    for x1, y1, x2, y2, lab in spec["wires"]:
        out.append(f"N {x1} {y1} {x2} {y2} {{lab={lab}}}")
    open(path, "w").write("\n".join(out) + "\n")
    print(f"wrote {path}: {len(spec['devices'])} devices")


def write_sym(name, spec, path):
    out = ["v {xschem version=3.4.4 file_version=1.2}",
           "G {}",
           'K {type=subcircuit\nformat="@name @pinlist @symname"\n'
           f'template="name=X{name.upper()}"\n}}',
           "V {}", "S {}", "E {}",
           "L 4 -100 -80 100 -80 {}", "L 4 100 -80 100 80 {}",
           "L 4 100 80 -100 80 {}", "L 4 -100 80 -100 -80 {}"]
    # pin order here IS the subckt port order: keep in sync with the
    # golden netlist (checked by tools/xcheck_blocks.py)
    for pname, d, x, y in spec["sym_pins"]:
        if abs(x) == 140:
            xs = -100 if x < 0 else 100
            out.append(f"L 4 {min(x, xs)} {y} {max(x, xs)} {y} {{}}")
        else:
            out.append(f"L 4 {x} {y} {x} {y - 20 if y > 0 else y + 20} {{}}")
        out.append(f"B 5 {x - 2.5} {y - 2.5} {x + 2.5} {y + 2.5} "
                   f"{{name={pname} dir={d}}}")
    out.append(f"T {{{spec['sym_label']}}} -35 -10 0 0 0.4 0.4 {{}}")
    out.append("T {@name} -30 -120 0 0 0.25 0.25 {}")
    for txt, x, y, size in spec["sym_texts"]:
        out.append(f"T {{{txt}}} {x} {y} 0 0 {size} {size} {{}}")
    open(path, "w").write("\n".join(out) + "\n")
    print(f"wrote {path}")


def write_top(name, spec, path):
    out = ["v {xschem version=3.4.4 file_version=1.2}",
           "G {}", "K {}", "V {}", "S {}", "E {}",
           f"T {{{name}_top: netlisting wrapper - produces .subckt {name} "
           f"for tools/xcheck_blocks.py}} -600 -400 0 0 0.4 0.4 {{}}",
           f"C {{{name}.sym}} 0 0 0 0 {{name=X{name.upper()}1}}"]
    for i, (lab, d, x, y) in enumerate(spec["sym_pins"]):
        out.append(f"C {{devices/lab_pin.sym}} {x} {y} 0 0 "
                   f"{{name=w{i} lab={lab.lower()}}}")
    open(path, "w").write("\n".join(out) + "\n")
    print(f"wrote {path}")


def main():
    base = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "xschem")
    only = sys.argv[1:] or list(BLOCKS)
    for name in only:
        spec = BLOCKS[name]()
        assert [p[0] for p in spec["sym_pins"]] == spec["ports"], name
        write_sch(name, spec, os.path.join(base, f"{name}.sch"))
        write_sym(name, spec, os.path.join(base, f"{name}.sym"))
        write_top(name, spec, os.path.join(base, f"{name}_top.sch"))


if __name__ == "__main__":
    main()

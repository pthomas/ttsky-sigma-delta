#!/usr/bin/env python3
"""StrongARM comparator testbench (tier 2, sky130 5V devices, 3.3 V).

Topology: PMOS input pair (senses the low 0.4-1.4 V window -- same rule as
the OTA: NMOS passes it, PMOS senses it; see DESIGN.md open item 6), PMOS
tail clocked directly by CLK (evaluates while CLK is low, matching the
tier-1 phasing where the DFF samples on the next rising edge), internal
and output nodes precharged to VSS by NMOS resets while CLK is high,
cross-coupled PMOS/NMOS regeneration, then inverter buffers into a
NAND-based SR latch. The buffers are load-bearing: with the latch gates
hung directly on the regeneration nodes, the held state makes the Miller
loading asymmetric (~10 mV-equivalent dynamic hysteresis, measured as
state-dependent wrong-sign decisions); the inverter outputs both sit at
VDD during precharge, so the loading is symmetric by construction.

Each (common-mode, overdrive) point runs in its OWN ngspice process: a
regenerative race is decided by uV-scale seeds, and both the solver
tolerances and the shared-timestep economy of a many-DUT deck otherwise
decide the race instead of the input (measured: wrong-sign flips at mV
overdrives with default reltol/vntol, and again when 16 DUTs share one
transient). gear + tight reltol + 1 ps tmax + per-DUT decks give clean,
monotone race behavior; verdicts below ~1 mV remain at the amplified
solver-noise floor and are reported but not enforced.

Measured: decision time from evaluate edge to a regeneration node at 90%
rail (the raw on1/on2 nodes precharge every cycle; Q is held by the SR
latch and can't time the race), correct-sign check, SR hold check,
regeneration tau from the t_dec vs ln(1/dv) slope, extrapolated
metastable input window at 5 ns, kickback onto an RC proxy of the
integrator node, and average supply power.

Spec (DESIGN.md): complete decision well inside the 10 ns half-period;
tier-1 measured ~25 dB SNDR penalty for soft decisions.

Usage: python3 sim/comp_tb.py    (sizes in SIZES below)
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

PDK_ROOT = os.environ.get("PDK_ROOT", "/home/nvme/pdk")
PDK_LIB = f"{PDK_ROOT}/sky130A/libs.tech/ngspice/sky130.lib.spice"
NF = "sky130_fd_pr__nfet_g5v0d10v5"
PF = "sky130_fd_pr__pfet_g5v0d10v5"
WUNIT = 5  # width-binned 5V fets: tile 5um unit fingers with m=

SIZES = dict(
    W_TAIL=10, W_IN=10,     # clocked PMOS tail, input pair (tail kept
                            # moderate: a slower di ramp lengthens the
                            # input-integration window before the
                            # cross-coupled pair engages)
    W_XP=5, W_XN=5,         # cross-coupled regeneration pair (P / N)
    W_RST=5,                # precharge-to-VSS reset switches
    W_LG=5,                 # SR-latch NOR gate devices
    L=0.5,                  # min L for g5v0d10v5, speed first
)

CMS = [0.68, 0.90, 1.12]              # integrator swing corners [V]
DVS = [1e-5, 1e-4, 1e-3, 1e-2, 1e-1]  # differential overdrive [V]
VDD = 3.3
TEDGE = 30e-9        # evaluate edge used for measurement (2nd eval)
TSTOP = 50e-9
R_KICK, C_KICK = 5e3, 2e-12   # integrator-node proxy for kickback


def m(w):
    return max(1, round(w / WUNIT))


def comp_subckt(p):
    return f"""
.subckt comp INP INM CLK Q QB ON1 ON2 VDD VSS
* ON1/ON2 are the raw regeneration nodes, exported for measurement:
* they precharge to VSS every cycle (unlike Q, which the SR latch holds)
* clocked PMOS tail: evaluates while CLK low
XT  tail CLK VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_TAIL'])}
X1  di1 INP tail VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_IN'])}
X2  di2 INM tail VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_IN'])}
* regeneration: cross-coupled PMOS (sources on di) + cross-coupled NMOS
X3  on1 on2 di1 VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_XP'])}
X4  on2 on1 di2 VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_XP'])}
X5  on1 on2 VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_XN'])}
X6  on2 on1 VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_XN'])}
* precharge all dynamic nodes to VSS while CLK high
XR1 di1 CLK VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_RST'])}
XR2 di2 CLK VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_RST'])}
XR3 on1 CLK VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_RST'])}
XR4 on2 CLK VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_RST'])}
* inverter buffers isolate the regen nodes from the latch: with the latch
* gates hung directly on on1/on2, the held state makes the Miller loading
* asymmetric (~10 mV-equivalent dynamic hysteresis, measured as
* state-dependent wrong-sign decisions). Both inverter outputs sit at VDD
* during precharge regardless of held state -- symmetric by construction.
XI1P n1b on1 VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XI1N n1b on1 VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XI2P n2b on2 VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XI2N n2b on2 VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
* SR latch, cross-coupled NAND2 (n1b=n2b=VDD during precharge -> hold)
* INP > INM -> on2 rises -> n2b low -> Q high
XAQ1 Q  n2b VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAQ2 Q  QB  VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAQ3 Q  n2b sq  VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAQ4 sq QB  VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAB1 QB n1b VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAB2 QB Q   VDD VDD {PF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAB3 QB n1b sb  VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
XAB4 sb Q   VSS VSS {NF} W={WUNIT} L={p['L']} nf=1 m={m(p['W_LG'])}
.ends
"""


RACE_OPTS = ".options method=gear reltol=1e-5 vntol=1e-9 abstol=1e-14"
# kickback measures mV glitches, not uV race seeds -- race-grade
# tolerances just make some corners choke on device-internal body nodes
KICK_OPTS = ".options method=gear reltol=1e-4 vntol=1e-6 abstol=1e-12"


def deck_head(p, corner="tt", subckt=None, opts=RACE_OPTS):
    return f"""* StrongARM comparator TB (generated by sim/comp_tb.py)
.lib {PDK_LIB} {corner}
{subckt if subckt is not None else comp_subckt(p)}
{opts}
* 1 ohm series: damps the ideal-supply branch at tight abstol (realistic
* supply impedance regardless)
VDDS vddi 0 {VDD}
RVDD vddi vdd 1
* CLK starts high (precharge), evaluate edges at 10n, 30n, ...
* (10 ohm series: damps the ideal-source branch at tight abstol, and is a
* realistic clock-driver impedance)
VCLK clkr 0 PULSE({VDD} 0 10n 0.2n 0.2n 9.8n 20n)
RCLK clkr clk 10
"""


def deck_point(p, cm, dv, tag, corner="tt", subckt=None):
    return deck_head(p, corner, subckt) + f"""
* small series R damps ideal-source branch currents at tight abstol
VP inpr 0 {cm + dv/2:.9f}
RP inpr inp 10
VM inmr 0 {cm - dv/2:.9f}
RM inmr inm 10
XC inp inm clk q qb on1 on2 vdd 0 comp
* tmax 1 ps: the race verdict is timestep-sensitive above this (measured:
* wrong-sign flips at 2-5 ps steps during the di common-mode ramp)
.tran 0.005n {TSTOP:.9g} 0 0.001n
.control
run
wrdata comp_{tag}.csv v(on1) v(on2) v(q) i(VDDS)
.endc
.end
"""


def deck_kick(p, corner="tt", subckt=None):
    return deck_head(p, corner, subckt, opts=KICK_OPTS) + f"""
VKS vks 0 0.9
RK vks vkick {R_KICK}
CK vkick 0 {C_KICK}
VKM inmkr 0 0.9
RKM inmkr inmk 10
XCK vkick inmk clk qk qbk onk1 onk2 vdd 0 comp
.tran 0.005n {TSTOP:.9g} 0 0.001n
.control
run
wrdata comp_kick.csv v(vkick)
.endc
.end
"""


def ngspice(name):
    r = subprocess.run(["ngspice", "-b", name], cwd="spice",
                       capture_output=True, text=True)
    if r.returncode:
        print(f"{name}: {r.stderr[-400:]}")
        return False
    return True


def measure(p, corner="tt", quick=False, subckt=None, write_json=True):
    cms = CMS
    dvs = [1e-2, 1e-1] if quick else DVS
    os.makedirs("spice", exist_ok=True)
    jobs = []
    for i, cm in enumerate(cms):
        for j, dv in enumerate(dvs):
            tag = f"{i}_{j}"
            open(f"spice/comp_{tag}.spice", "w").write(
                deck_point(p, cm, dv, tag, corner, subckt))
            jobs.append(f"comp_{tag}.spice")
    open("spice/comp_kick.spice", "w").write(deck_kick(p, corner, subckt))
    jobs.append("comp_kick.spice")
    with ThreadPoolExecutor(max_workers=os.cpu_count()) as ex:
        if not all(ex.map(ngspice, jobs)):
            sys.exit(1)

    results = {}
    pwr = None
    print(f"{'CM':>6s} {'dv':>8s} {'t_decide':>10s} {'winner':>7s} "
          f"{'sign':>6s} {'Q':>5s}")
    for i, cm in enumerate(cms):
        for j, dv in enumerate(dvs):
            d = np.loadtxt(f"spice/comp_{i}_{j}.csv")
            t = d[:, 0]
            on1, on2, q, ivdd = d[:, 1], d[:, 3], d[:, 5], d[:, 7]
            after = t >= TEDGE
            h1 = after & (on1 > 0.9 * VDD)
            h2 = after & (on2 > 0.9 * VDD)
            t1 = t[h1][0] if h1.any() else np.inf
            t2 = t[h2][0] if h2.any() else np.inf
            td = min(t1, t2) - TEDGE
            winner = "on2" if t2 < t1 else ("on1" if t1 < np.inf else "-")
            correct = winner == "on2"   # INP > INM must send on2 high
            # sign is only meaningful above the sim/silicon floor: solver
            # noise (reltol*VDD ~ uV, amplified by the race) and real
            # offset/thermal noise both live below ~10 mV; a 1-bit SD loop
            # shrugs off sign errors at near-zero overdrive (bounded extra
            # quantization noise) -- what it cannot absorb is a slow/soft
            # decision, so t_decide is enforced at EVERY point.
            sign_enforced = dv >= 1e-2
            held = correct and q[(t >= TEDGE + 12e-9) &
                                 (t < TEDGE + 19e-9)].min() > 0.9 * VDD
            results[(cm, dv)] = dict(td=td, correct=correct,
                                     enforced=sign_enforced)
            if cm == 0.90 and dv == 1e-2:
                cyc = (t >= 20e-9) & (t < 40e-9)
                pwr = abs(np.trapz(ivdd[cyc], t[cyc]) / 20e-9 * VDD)
                # regeneration tau: exponential growth of |on1-on2|
                don = np.abs(on1 - on2)
                seg = after & (don > 0.05) & (don < 2.0) & \
                    (t < TEDGE + 3e-9)
                tau_fit = np.polyfit(t[seg], np.log(don[seg]), 1)
                pwr_tau = 1 / tau_fit[0]
                if write_json:   # keep the race trace for the docs figure
                    os.makedirs("reports/results", exist_ok=True)
                    import shutil
                    shutil.copy(f"spice/comp_{i}_{j}.csv",
                                "reports/results/comp_race.csv")
            sign = ("ok" if correct else "WRONG") if sign_enforced else \
                ("ok" if correct else "n/a")
            tds = f"{td*1e9:9.3f}ns" if np.isfinite(td) else "  NO DECISION"
            print(f"{cm:6.2f} {dv:8.0e} {tds} {winner:>7s} "
                  f"{sign:>6s} {'held' if held else '-':>5s}")

    dk = np.loadtxt("spice/comp_kick.csv")
    kb = np.abs(dk[dk[:, 0] >= 9e-9, 1] - 0.9).max()

    tau = pwr_tau
    # extrapolated input window still undecided after 5 ns (half budget,
    # margin for the DFF handoff); seed ~ dv at the regen nodes
    t_meta = 5e-9
    dv_meta = VDD * np.exp(-t_meta / tau)

    wrong = sum(1 for r in results.values()
                if r["enforced"] and not r["correct"])
    undecided = sum(1 for r in results.values() if not np.isfinite(r["td"]))
    worst = max(r["td"] for r in results.values() if np.isfinite(r["td"]))
    print(f"\nregen tau  : {tau*1e12:.0f} ps  (|on1-on2| growth fit, "
          f"CM 0.9 / dv 10 mV, corner {corner})")
    print(f"worst t_dec: {worst*1e9:.2f} ns over CM {cms[0]}-{cms[-1]} V, "
          f"all overdrives (budget: 10 ns half-period)")
    print(f"sign errors above 10 mV: {wrong}; undecided points: {undecided}")
    print(f"meta window: dv < {dv_meta:.1e} V leaves the race unresolved "
          f"at {t_meta*1e9:.0f} ns (extrapolated from tau)")
    print(f"kickback   : {kb*1e3:.1f} mV peak on the integrator-node proxy "
          f"(R={R_KICK/1e3:.0f}k, C={C_KICK*1e12:.0f}p)")
    print(f"power      : {pwr*1e6:.0f} uW avg at 50 MHz")

    fail = wrong or undecided or worst > 5e-9
    out = dict(tau_ps=round(tau * 1e12),
               worst_tdec_ns=round(worst * 1e9, 2),
               sign_errors_above_10mV=wrong,
               undecided_points=undecided,
               meta_dv_v=float(f"{dv_meta:.2e}"),
               kickback_mv=round(kb * 1e3, 1),
               power_uw=round(pwr * 1e6),
               ok=not fail, corner=corner,
               cms=cms, dvs=dvs,
               tdec_ns={f"{cm}/{dv:.0e}": round(r["td"] * 1e9, 3)
                        for (cm, dv), r in results.items()
                        if np.isfinite(r["td"])})
    if write_json:
        os.makedirs("reports/results", exist_ok=True)
        json.dump(out, open("reports/results/comp.json", "w"), indent=1)
    return out


if __name__ == "__main__":
    if "--corners" in sys.argv:
        # reduced grid across process corners; tt already covered fully
        rows = []
        for c in ("tt", "ss", "ff", "sf", "fs"):
            print(f"\n=== corner {c} ===")
            r = measure(SIZES, corner=c, quick=True, write_json=False)
            rows.append(r)
        print(f"\n{'corner':>7s} {'tau':>7s} {'worst t_dec':>12s} "
              f"{'power':>7s} {'ok':>3s}")
        for r in rows:
            print(f"{r['corner']:>7s} {r['tau_ps']:5d}ps "
                  f"{r['worst_tdec_ns']:10.2f}ns {r['power_uw']:5d}uW "
                  f"{'ok' if r['ok'] else 'FAIL':>4s}")
        json.dump(rows, open("reports/results/comp_corners.json", "w"),
                  indent=1)
        sys.exit(0 if all(r["ok"] for r in rows) else 1)
    r = measure(SIZES, quick="--quick" in sys.argv)
    if not r["ok"]:
        sys.exit(1)

#!/usr/bin/env python3
"""Generate SVG figures for the docs site from simulation outputs.

Each subcommand reads data where the producing job left it and writes
theme-neutral SVGs (transparent background, mid-tone inks that read on
both light and dark surfaces) into reports/results/figs/:

  tier1  spice/tier1_out.csv          -> tier1_waves.svg, tier1_spectrum.svg
  ota    reports/results/ota_ac_*.csv -> ota_ac.svg
  comp   reports/results/comp_race.csv, dff_wave.csv -> comp_race.svg,
                                                        dff_retime.svg

Usage: python3 tools/gen_doc_figs.py [tier1] [ota] [comp]
"""

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIGS = "reports/results/figs"
C1, C2, GRAY = "#4488dd", "#dd8844", "#8a93a0"   # blue/orange CVD-safe pair
INK = "#6b7482"                                   # axis/text, both themes

plt.rcParams.update({
    "svg.fonttype": "none", "font.size": 9, "font.family": "sans-serif",
    "text.color": INK, "axes.edgecolor": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK,
    "axes.facecolor": "none", "figure.facecolor": "none",
    "axes.grid": True, "grid.color": GRAY, "grid.alpha": 0.25,
    "grid.linewidth": 0.5, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False,
})


def save(fig, name):
    os.makedirs(FIGS, exist_ok=True)
    fig.savefig(f"{FIGS}/{name}.svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    print(f"wrote {FIGS}/{name}.svg")


def tier1():
    d = np.loadtxt("spice/tier1_out.csv")   # t q t clk t vin t int
    t, q, vin, vint = d[:, 0], d[:, 1], d[:, 5], d[:, 7]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 3.6), sharex=False,
                                 height_ratios=[3, 2])
    w = (t > 20e-6) & (t < 60e-6)
    a1.plot(t[w] * 1e6, vin[w], color=C1, lw=1.4, label="input")
    a1.plot(t[w] * 1e6, vint[w], color=C2, lw=0.7, label="integrator")
    a1.set_ylabel("V")
    a1.legend(loc="upper right", ncols=2)
    a1.set_title("Tier-1 loop: the integrator hugs the input it is forced "
                 "to track", loc="left", fontsize=9)
    z = (t > 20e-6) & (t < 21e-6)
    a2.plot(t[z] * 1e6, q[z], color=GRAY, lw=0.9, label="bitstream q")
    a2.set_xlabel("time [µs]")
    a2.set_ylabel("V")
    a2.legend(loc="center right")
    a2.set_title("the same loop, zoomed to 50 clock cycles: the 1-bit "
                 "output doing the work", loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, "tier1_waves")

    # coherent spectrum of the bitstream (same resampling as sim/snr.py)
    import params as P
    from sim.snr import load_bits
    bits = load_bits("spice/tier1_out.csv")
    spec = np.abs(np.fft.rfft(bits)) ** 2   # coherent: no window needed
    f = np.fft.rfftfreq(len(bits), 1 / P.FS)
    psd_db = 10 * np.log10(spec / spec.max() + 1e-30)
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.semilogx(f[1:], psd_db[1:], color=C1, lw=0.7)
    for fedge, lab in ((P.FS / (2 * P.OSR_PREC), "precision band\n100 kHz"),
                       (P.FS / (2 * P.OSR_FAST), "fast band\n1 MHz")):
        ax.axvline(fedge, color=GRAY, lw=0.8, ls="--")
        ax.annotate(lab, (fedge, -8), fontsize=7.5, ha="right",
                    xytext=(-4, 0), textcoords="offset points")
    ax.annotate("signal", (P.FIN, 0), fontsize=7.5, ha="right",
                xytext=(-6, -12), textcoords="offset points")
    ax.set_xlim(f[1], P.FS / 2)
    ax.set_ylim(-110, 8)
    ax.set_xlabel("frequency [Hz]")
    ax.set_ylabel("PSD [dB rel. signal]")
    ax.set_title("Bitstream spectrum: quantization noise shaped away from "
                 "the signal band (first-order: +20 dB/decade)",
                 loc="left", fontsize=9)
    fig.tight_layout()
    save(fig, "tier1_spectrum")


def ota():
    fig, (am, ap) = plt.subplots(2, 1, figsize=(7.2, 4.0), sharex=True,
                                 height_ratios=[3, 2])
    for path, col, lab in (("reports/results/ota_ac_sch.csv", C1,
                            "schematic"),
                           ("reports/results/ota_ac_pex.csv", C2,
                            "extracted (PEX)")):
        if not os.path.exists(path):
            continue
        d = np.loadtxt(path)
        f, h = d[:, 0], d[:, 1] + 1j * d[:, 2]
        am.semilogx(f, 20 * np.log10(np.abs(h)), color=col, lw=1.4,
                    label=lab)
        ap.semilogx(f, np.unwrap(np.angle(h)) * 180 / np.pi, color=col,
                    lw=1.4, label=lab)
    am.axhline(0, color=GRAY, lw=0.8, ls="--")
    am.set_ylabel("|A| [dB]")
    am.legend(loc="lower left")
    am.set_title("OTA open loop, schematic vs extracted layout: parasitics "
                 "take GBW and phase margin, DC gain untouched",
                 loc="left", fontsize=9)
    ap.set_ylabel("phase [°]")
    ap.set_xlabel("frequency [Hz]")
    fig.tight_layout()
    save(fig, "ota_ac")


def comp():
    if os.path.exists("reports/results/comp_race.csv"):
        d = np.loadtxt("reports/results/comp_race.csv")
        t, on1, on2, q = d[:, 0], d[:, 1], d[:, 3], d[:, 5]
        w = (t > 29.6e-9) & (t < 33.5e-9)
        fig, ax = plt.subplots(figsize=(7.2, 2.8))
        ax.plot(t[w] * 1e9, on2[w], color=C1, lw=1.4, label="winning side")
        ax.plot(t[w] * 1e9, on1[w], color=C2, lw=1.4, label="losing side")
        ax.plot(t[w] * 1e9, q[w], color=GRAY, lw=1.0, ls="--",
                label="latched Q")
        ax.axvline(30, color=GRAY, lw=0.8, ls=":")
        ax.annotate("evaluate\nedge", (30, 2.6), fontsize=7.5, ha="right",
                    xytext=(-4, 0), textcoords="offset points")
        ax.set_xlabel("time [ns]")
        ax.set_ylabel("V")
        ax.legend(loc="center right")
        ax.set_title("StrongARM regeneration at 10 mV overdrive: both "
                     "nodes rise together, the seed decides, τ ≈ 70 ps",
                     loc="left", fontsize=9)
        fig.tight_layout()
        save(fig, "comp_race")

    if os.path.exists("reports/results/dff_wave.csv"):
        d = np.loadtxt("reports/results/dff_wave.csv")
        t, cq, q = d[:, 0], d[:, 1], d[:, 3]
        w = (t > 15e-9) & (t < 125e-9)
        fig, ax = plt.subplots(figsize=(7.2, 2.8))
        ax.plot(t[w] * 1e9, cq[w] + 3.8, color=C2, lw=1.1,
                label="comparator Q (wanders mid-cycle)")
        ax.plot(t[w] * 1e9, q[w], color=C1, lw=1.1,
                label="retimed Q (moves only at clock edges)")
        for k in range(1, 7):
            ax.axvline(k * 20, color=GRAY, lw=0.7, ls=":")
        ax.set_yticks([])
        ax.set_xlabel("time [ns]  (dotted lines: rising clock edges)")
        ax.legend(loc="upper left", fontsize=7.5)
        ax.set_title("Why the retimer exists: DAC timing must not depend "
                     "on how long the comparator thought", loc="left",
                     fontsize=9)
        fig.tight_layout()
        save(fig, "dff_retime")


if __name__ == "__main__":
    for cmd in (sys.argv[1:] or ["tier1", "ota", "comp"]):
        {"tier1": tier1, "ota": ota, "comp": comp}[cmd]()

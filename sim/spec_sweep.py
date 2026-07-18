#!/usr/bin/env python3
"""OTA requirements sweep: how much gain / GBW / slew does the loop need?

Sweeps one OTA parameter at a time (others at baseline) on the tier-1
modulator, measuring SNDR for both decimation paths. Dither with a pinned
seed makes runs paired; precision-path values still carry the ~+-1 dB
pattern-noise scatter documented in DESIGN.md, so read knees, not digits.

Writes reports/ota_specs.html.  Usage: make specs
"""

import os
import re
import subprocess
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import params as P
from sim.snr import sndr
from sim.compare_dac import style_axes, fig_to_b64, C_SURF, C_TEXT, C_TEXT2

NFFT, NSETTLE, SIG_BIN = 16384, 256, 9
FIN = SIG_BIN * P.FS / NFFT
TSTOP = (NFFT + NSETTLE) * P.TS
SPICE_DIR = "spice"

BASE = {"AOL": P.AOL, "GBW": P.GBW, "SR": P.SR}
SWEEPS = {
    "AOL": [30, 100, 300, 1e3, 3e3, 1e4],
    "GBW": [25e6, 50e6, 100e6, 150e6, 200e6, 400e6],
    "SR":  [1.25e7, 2.5e7, 5e7, 1e8, 2e8, 4e8],
}
UNITS = {"AOL": ("V/V", 1), "GBW": ("MHz", 1e6), "SR": ("V/us", 1e6)}
C_FAST, C_PREC = "#2a78d6", "#1baf7a"


def write_variant(tag, overrides):
    par = open(os.path.join(SPICE_DIR, "params.spice")).read()
    par = re.sub(r"\.param FIN=\S+", f".param FIN={FIN:.6g}", par)
    par = re.sub(r"\.param TSTOP=\S+", f".param TSTOP={TSTOP:.6g}", par)
    for k, v in overrides.items():
        par = re.sub(rf"\.param {k}=\S+", f".param {k}={v:.6g}", par)
    open(os.path.join(SPICE_DIR, f"params_{tag}.spice"), "w").write(par)

    txt = open(os.path.join(SPICE_DIR, "tier1_headless.spice")).read()
    txt = txt.replace(".include params.spice", f".include params_{tag}.spice")
    txt = txt.replace("VIN vin GND SIN({VCM} {AMP} {FIN})",
                      "VIN vind GND SIN({VCM} {AMP} {FIN})\n"
                      "VDITH vin vind DC 0 TRNOISE(0.5m 2n 0 0)")
    txt = txt.replace("write tier1_sdm.raw\n", "")
    txt = txt.replace(".control\nrun", ".control\nset rndseed=17\nrun")
    txt = txt.replace("wrdata tier1_out.csv v(q) v(clk) v(vin) v(int)",
                      f"wrdata out_{tag}.csv v(q)")
    path = os.path.join(SPICE_DIR, f"sw_{tag}.spice")
    open(path, "w").write(txt)
    return path


def run_variant(tag, overrides):
    net = write_variant(tag, overrides)
    subprocess.run(["ngspice", "-b", os.path.basename(net)], cwd=SPICE_DIR,
                   check=True, capture_output=True)
    d = np.loadtxt(os.path.join(SPICE_DIR, f"out_{tag}.csv"))
    ts = (np.arange(NSETTLE, NSETTLE + NFFT) + 0.5) * P.TS
    bits = np.where(np.interp(ts, d[:, 0], d[:, 1]) > 1.65, 1.0, -1.0)
    return (sndr(bits, P.OSR_FAST, SIG_BIN), sndr(bits, P.OSR_PREC, SIG_BIN))


def main():
    results = {}   # param -> list of (value, fast, prec)
    for pname, values in SWEEPS.items():
        results[pname] = []
        for v in values:
            tag = f"{pname}_{v:.3g}".replace("+", "").replace(".", "p")
            fast, prec = run_variant(tag, {**BASE, pname: v})
            results[pname].append((v, fast, prec))
            u, scale = UNITS[pname]
            print(f"{pname}={v/scale:8.3g} {u:5s}  fast {fast:5.1f} dB  "
                  f"precision {prec:5.1f} dB", flush=True)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.0), sharey=True)
    fig.patch.set_facecolor(C_SURF)
    for ax, pname in zip(axes, SWEEPS):
        style_axes(ax)
        u, scale = UNITS[pname]
        arr = np.array(results[pname])
        ax.semilogx(arr[:, 0] / scale, arr[:, 1], "o-", color=C_FAST, lw=1.8,
                    ms=4)
        ax.semilogx(arr[:, 0] / scale, arr[:, 2], "o-", color=C_PREC, lw=1.8,
                    ms=4)
        ax.axvline(BASE[pname] / scale, color="#e5e4e0", lw=1.0)
        ax.set_xlabel(f"{pname} [{u}]", color=C_TEXT2, fontsize=9)
        ax.set_title(f"sweep {pname} (others at baseline)", color=C_TEXT,
                     fontsize=10, loc="left")
    axes[0].set_ylabel("SNDR [dB]", color=C_TEXT2, fontsize=9)
    axes[0].text(0.05, 0.28, "fast (1 MHz)", color=C_TEXT, fontsize=9,
                 weight="bold", transform=axes[0].transAxes)
    axes[0].text(0.05, 0.85, "precision (100 kHz)", color=C_TEXT, fontsize=9,
                 weight="bold", transform=axes[0].transAxes)
    fig.tight_layout()
    b64 = fig_to_b64(fig)

    rows = []
    for pname in SWEEPS:
        u, scale = UNITS[pname]
        for v, fast, prec in results[pname]:
            rows.append(f"<tr><td>{pname}</td><td>{v/scale:.3g} {u}</td>"
                        f"<td>{fast:.1f} dB</td><td>{prec:.1f} dB</td></tr>")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>OTA requirements sweep</title>
<style>
 body {{ background:{C_SURF}; color:{C_TEXT}; font-family:sans-serif;
        max-width:1000px; margin:2em auto; padding:0 1em; }}
 h1 {{ font-size:1.3em; }}
 p {{ color:{C_TEXT2}; font-size:0.92em; line-height:1.5; }}
 table {{ border-collapse:collapse; margin:1em 0; }}
 th,td {{ border:1px solid #e5e4e0; padding:0.35em 0.9em; font-size:0.88em; }}
 th {{ color:{C_TEXT2}; font-weight:600; }}
 img {{ max-width:100%; }}
</style></head><body>
<h1>OTA requirements sweep &mdash; tier-1 modulator</h1>
<p>One parameter varied at a time; baseline AOL = {P.AOL:.0f},
GBW = {P.GBW/1e6:.0f} MHz, SR = {P.SR/1e6:.0f} V/&mu;s (gray verticals).
fs = {P.FS/1e6:.0f} MHz, {NFFT} bits, pinned dither seed. Precision-path
values scatter ~&plusmn;1 dB run to run (pattern noise) &mdash; read knees,
not digits.</p>
<img src="data:image/png;base64,{b64}">
<table>
<tr><th>param</th><th>value</th><th>SNDR @ 1 MHz</th><th>SNDR @ 100 kHz</th></tr>
{os.linesep.join(rows)}
</table>
</body></html>
"""
    os.makedirs("reports", exist_ok=True)
    open("reports/ota_specs.html", "w").write(html)
    print("wrote reports/ota_specs.html")


if __name__ == "__main__":
    main()

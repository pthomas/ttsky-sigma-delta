#!/usr/bin/env python3
"""Build the public/ site: docs/*.md -> single-page HTML with live results.

Placeholders ({{name}}) in the markdown are substituted from
reports/results/*.json before rendering. A result that is missing renders
as an explicit "not verified in this build" marker -- numbers are never
hand-written and never stale.

Usage: python3 tools/gen_docs.py    (from repo root; needs python3-markdown)
Output: public/index.html (+ copied reports, GDS, geometry JSON)
"""

import glob
import html
import json
import os
import re
import shutil
import sys
import time

import markdown

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = "reports/results"


def load(name):
    try:
        return json.load(open(f"{RESULTS}/{name}.json"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def missing(what):
    return (f'<span class="chip warn">&#9888; {what}: '
            f'not verified in this build</span>')


def chip(ok, text):
    cls, mark = ("pass", "&#10003;") if ok else ("fail", "&#10007;")
    return f'<span class="chip {cls}">{mark} {text}</span>'


# ---------------------------------------------------------------- fragments

def build_stamp():
    sha = os.environ.get("CI_COMMIT_SHORT_SHA")
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    if sha:
        url = os.environ.get("CI_PIPELINE_URL", "")
        pipe = os.environ.get("CI_PIPELINE_ID", "?")
        link = f'<a href="{url}">pipeline #{pipe}</a>' if url \
            else f"pipeline #{pipe}"
        return (f'<p class="stamp">Built {when} from commit '
                f'<code>{sha}</code> by {link} &mdash; every number below '
                f'was produced by that run.</p>')
    return (f'<p class="stamp">Built {when} (local build, no CI '
            f'metadata).</p>')


def snr_table():
    r = load("snr")
    if not r:
        return missing("tier-1 SNDR")
    rows = "".join(
        f"<tr><td>{name}</td><td>{p['osr']}</td>"
        f"<td>{p['bw_hz']/1e3:.0f} kHz</td>"
        f"<td>{p['sndr_db']:.1f} dB</td><td>{p['enob']:.1f}</td></tr>"
        for name, p in r["paths"].items())
    return (f"<table><thead><tr><th>Path</th><th>OSR</th><th>Bandwidth</th>"
            f"<th>SNDR</th><th>ENOB</th></tr></thead><tbody>{rows}</tbody>"
            f"</table>\n<p class='fineprint'>{r['nbits']} bits analyzed at "
            f"f<sub>s</sub> = {r['fs_hz']/1e6:.0f} MHz, ones density "
            f"{r['ones_density']:.3f}.</p>")


def report_links(names):
    out = []
    for path, label in names:
        if os.path.exists(f"reports/{path}"):
            out.append(f'<a class="report" href="reports/{path}">{label}</a>')
        else:
            out.append(missing(label))
    return " ".join(out)


def sizes_table():
    from sim.ota_tb import SIZES
    roles = [("input pair M1/M2", "W_IN", "L_IN"),
             ("tail + mirror diode MT/MDP", "W_TAIL", "L_TAIL"),
             ("folded-branch sinks M3/M4 + diode MDN", "W_SINK", "L_SINK"),
             ("NMOS cascodes M5/M6", "W_CAS", "L_CAS"),
             ("PMOS mirror M9/M10", "W_MIR", "L_MIR"),
             ("PMOS cascodes M7/M8", "W_PCAS", "L_PCAS")]
    rows = "".join(
        f"<tr><td>{role}</td><td>{SIZES[w]} µm</td><td>{SIZES[l]} µm</td>"
        f"</tr>" for role, w, l in roles)
    return (f"<table><thead><tr><th>Role</th><th>Total W</th><th>L</th></tr>"
            f"</thead><tbody>{rows}</tbody></table>"
            f"<p class='fineprint'>Bias: IREFP {SIZES['IREFP']*1e6:.0f} µA, "
            f"IREFN {SIZES['IREFN']*1e6:.0f} µA; load "
            f"{SIZES['CL']*1e12:.1f} pF; devices tiled as 5 µm unit "
            f"fingers.</p>")


def fmt_ota(r):
    return dict(a0=f"{r['a0_db']:.1f} dB", gbw=f"{r['gbw_hz']/1e6:.0f} MHz",
                pm=f"{r['pm_deg']:.0f}°",
                sr=f"+{r['sr_up']/1e6:.0f} / &minus;{r['sr_dn']/1e6:.0f} V/µs",
                pw=f"{r['power_w']*1e3:.1f} mW",
                rng=f"{r['range_lo_v']:.2f}–{r['range_hi_v']:.2f} V")


def ota_sch_table():
    r = load("ota_sch")
    if not r:
        return missing("OTA schematic testbench")
    f = fmt_ota(r)
    rows = [("DC gain A<sub>0</sub>", f["a0"]), ("GBW", f["gbw"]),
            ("Phase margin", f["pm"]), ("Slew rate", f["sr"]),
            ("Power", f["pw"]), ("Buffer range", f["rng"])]
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (f"<table><thead><tr><th>Metric</th><th>Measured</th></tr>"
            f"</thead><tbody>{body}</tbody></table>")


def ota_compare_table():
    s, p = load("ota_sch"), load("ota_pex")
    if not s or not p:
        return missing("schematic-vs-extracted comparison")
    fs, fp = fmt_ota(s), fmt_ota(p)
    knees = dict(a0="&ge; 49.5 dB", gbw="&ge; 50 MHz", pm="&mdash;",
                 sr="&ge; 100 V/µs", pw="&mdash;", rng="0.4–1.4 V window")
    labels = dict(a0="DC gain A<sub>0</sub>", gbw="GBW", pm="Phase margin",
                  sr="Slew rate", pw="Power", rng="Buffer range")
    body = "".join(
        f"<tr><td>{labels[k]}</td><td>{fs[k]}</td><td>{fp[k]}</td>"
        f"<td>{knees[k]}</td></tr>" for k in labels)
    return (f"<table><thead><tr><th>Metric</th><th>Schematic</th>"
            f"<th>Extracted</th><th>Tier-1 knee</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def layout_status():
    r = load("layout")
    if not r:
        return missing("layout verification")
    d, l, p = r["drc"], r["lvs"], r.get("pex")
    out = [chip(d["count"] == 0, f"DRC: {d['count']} errors "
               "(fresh process, hierarchy expanded)")]
    dev = f", {l['devices'][0]}/{l['devices'][1]} devices" if l["devices"] \
        else ""
    net = f", {l['nets'][0]}/{l['nets'][1]} nets" if l["nets"] else ""
    out.append(chip(l["match"], f"LVS: {l['verdict']}{dev}{net}"))
    if p:
        out.append(f'<span class="chip info">PEX: {p["ncaps"]} parasitic '
                   f'caps, {p["ctotal_f"]*1e12:.2f} pF total</span>')
    return "<p>" + " ".join(out) + "</p>"


def gds_link():
    if not os.path.exists("reports/ota_layout.gds"):
        return missing("GDS export")
    kb = os.path.getsize("reports/ota_layout.gds") / 1024
    return (f'<p><a class="report" href="ota_layout.gds" download>Download '
            f'the GDSII ({kb:.0f} kB)</a> &mdash; open it in KLayout or '
            f'magic and poke around.</p>')


def viewer3d():
    if not os.path.exists(f"{RESULTS}/ota_geom.json"):
        return missing("3D geometry")
    return VIEWER_HTML


def fig(name, caption):
    if not os.path.exists(f"{RESULTS}/figs/{name}.svg"):
        return missing(f"figure {name}")
    return (f'<figure><img src="figs/{name}.svg" alt="{caption}" '
            f'loading="lazy"><figcaption>{caption}</figcaption></figure>')


def comp_table():
    r = load("comp")
    if not r:
        return missing("comparator testbench")
    c = load("comp_corners")
    mc = load("comp_mc")
    rows = [("Regeneration τ", f"{r['tau_ps']} ps"),
            ("Worst decision time (CM 0.68–1.12 V, dv ≥ 10 µV)",
             f"{r['worst_tdec_ns']} ns  (budget 10 ns)"),
            ("Metastable input window @ 5 ns",
             f"&lt; {r['meta_dv_v']:.0e} V (extrapolated)"),
            ("Kickback onto integrator-node proxy",
             f"{r['kickback_mv']} mV peak"),
            ("Power @ 50 MHz", f"{r['power_uw']} µW")]
    if c:
        taus = [x["tau_ps"] for x in c]
        worst = max(x["worst_tdec_ns"] for x in c)
        okc = all(x["ok"] for x in c)
        rows.append(("Corners tt/ss/ff/sf/fs",
                     f"τ {min(taus)}–{max(taus)} ps, worst "
                     f"{worst} ns{'' if okc else ' — FAIL'}"))
    if mc:
        rows.append((f"Input offset (mismatch MC, N={mc['n']})",
                     f"σ = {mc['sigma_mv']} mV (benign in a 1-bit ΣΔ: "
                     f"a DC shift, not an SNDR term)"))
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return (f"<table><thead><tr><th>Metric</th><th>Measured</th></tr>"
            f"</thead><tbody>{body}</tbody></table>")


def dff_line():
    r = load("dff")
    if not r:
        return missing("DFF testbench")
    text = (f"retimer: clk-to-Q {r['clk_to_q_ns']} ns, {r['flips']} "
            f"consecutive alternating decisions retimed, "
            f"{r['violations']} mid-cycle output transitions")
    return f"<p>{chip(r['ok'], text)}</p>"


# ------------------------------------------------------------------- page

VIEWER_HTML = """
<div id="v3d-wrap">
  <div id="v3d-controls">
    <span id="v3d-layers"></span>
    <label class="v3d-z">z-exaggeration
      <input id="v3d-zex" type="range" min="1" max="20" value="8">
    </label>
  </div>
  <div id="v3d" aria-label="Interactive 3D view of the OTA mask geometry">
    <p id="v3d-fallback">Loading 3D viewer (needs WebGL and CDN access)…</p>
  </div>
</div>
<script type="importmap">
{"imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const el = document.getElementById('v3d');
const fallback = el.querySelector('#v3d-fallback');
const data = await (await fetch('ota_geom.json')).json();

const scene = new THREE.Scene();
const W = el.clientWidth, H = el.clientHeight;
const camera = new THREE.PerspectiveCamera(40, W / H, 1, 5000);
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
} catch (e) {
  fallback.textContent = 'WebGL is unavailable in this browser — ' +
    'download the GDSII below and open it in KLayout instead.';
  throw e;
}
fallback.remove();
renderer.setSize(W, H);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
el.appendChild(renderer.domElement);

scene.add(new THREE.AmbientLight(0xffffff, 0.65));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(1, 2, 1.5);
scene.add(sun);

// bounds
let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
for (const l of data.layers)
  for (const r of l.rects) {
    x0 = Math.min(x0, r[0]); y0 = Math.min(y0, r[1]);
    x1 = Math.max(x1, r[2]); y1 = Math.max(y1, r[3]);
  }
const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;

const group = new THREE.Group();
scene.add(group);
const meshes = [];
for (const l of data.layers) {
  const n = l.rects.length;
  const pos = new Float32Array(n * 24 * 3);
  const idx = new Uint32Array(n * 36);
  const faces = [[0,1,2,3],[5,4,7,6],[4,0,3,7],[1,5,6,2],[3,2,6,7],[4,5,1,0]];
  for (let i = 0; i < n; i++) {
    const [ax, ay, bx, by] = l.rects[i];
    const c = [[ax,ay,l.z0],[bx,ay,l.z0],[bx,by,l.z0],[ax,by,l.z0],
               [ax,ay,l.z1],[bx,ay,l.z1],[bx,by,l.z1],[ax,by,l.z1]];
    for (let f = 0; f < 6; f++) {
      const o = i * 24 + f * 4;
      for (let v = 0; v < 4; v++) {
        const p = c[faces[f][v]];
        pos.set([p[0] - cx, p[2], -(p[1] - cy)], (o + v) * 3);
      }
      const j = i * 36 + f * 6;
      idx.set([o, o + 1, o + 2, o, o + 2, o + 3], j);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({
    color: l.color }));
  m.userData.name = l.name;
  group.add(m);
  meshes.push(m);
}

const span = Math.max(x1 - x0, y1 - y0);
camera.position.set(span * 0.55, span * 0.5, span * 0.75);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

const zex = document.getElementById('v3d-zex');
const applyZ = () => { group.scale.y = parseFloat(zex.value); };
zex.addEventListener('input', applyZ);
applyZ();

const lc = document.getElementById('v3d-layers');
for (const m of meshes) {
  const lab = document.createElement('label');
  lab.className = 'v3d-layer';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = true;
  cb.addEventListener('change', () => { m.visible = cb.checked; });
  const sw = document.createElement('span');
  sw.className = 'swatch';
  sw.style.background = '#' + m.material.color.getHexString();
  lab.append(cb, sw, m.userData.name);
  lc.appendChild(lab);
}

(function tick() {
  requestAnimationFrame(tick);
  controls.update();
  renderer.render(scene, camera);
})();
</script>
"""

CSS = """
:root{--bg:#ffffff;--ink:#1a2330;--muted:#5b6a78;--line:#e3e7ee;
--accent:#2563b0;--surface:#f5f7fa;--pass:#1a7f4e;--passbg:#e7f5ec;
--fail:#b3261e;--failbg:#fbeae9;--warn:#8a6100;--warnbg:#fdf3d8;
--info:#3b4a5a;--infobg:#eef1f5}
@media(prefers-color-scheme:dark){:root{--bg:#12161c;--ink:#e8ebf0;
--muted:#9aa5b1;--line:#2a3340;--accent:#6aa5e8;--surface:#1a2029;
--pass:#5fd39a;--passbg:#15301f;--fail:#f2867e;--failbg:#3a1a17;
--warn:#e8c35a;--warnbg:#332a10;--info:#b9c4d0;--infobg:#222a34}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
#layout{display:flex;max-width:1200px;margin:0 auto}
nav{position:sticky;top:0;align-self:flex-start;flex:0 0 240px;
padding:2rem 1rem;font-size:.85rem;max-height:100vh;overflow-y:auto}
nav a{display:block;padding:.28rem .5rem;color:var(--muted);
text-decoration:none;border-left:2px solid var(--line)}
nav a:hover{color:var(--ink)}
main{flex:1;min-width:0;padding:2rem 2.5rem 6rem;max-width:52rem}
h1{font-size:1.7rem;line-height:1.25;margin:3.5rem 0 1rem;
padding-top:1rem;border-top:1px solid var(--line);scroll-margin-top:1rem}
section:first-child h1{margin-top:.5rem;border-top:none}
h2{font-size:1.15rem;margin:2rem 0 .6rem}
code{background:var(--surface);padding:.1em .35em;border-radius:4px;
font-size:.9em}
pre{background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:1rem;overflow-x:auto}
pre code{background:none;padding:0}
table{border-collapse:collapse;margin:1rem 0;width:100%;font-size:.92rem}
th{text-align:left;color:var(--muted);font-weight:600}
th,td{padding:.45rem .7rem;border-bottom:1px solid var(--line)}
figure{margin:1.5rem 0;color:var(--ink)}
figure img{width:100%;height:auto}
figcaption,.fineprint{font-size:.82rem;color:var(--muted)}
.stamp{background:var(--surface);border:1px solid var(--line);
border-radius:8px;padding:.6rem .9rem;font-size:.88rem}
.chip{display:inline-block;border-radius:999px;padding:.15rem .7rem;
font-size:.85rem;margin:.1rem .15rem;white-space:nowrap}
.chip.pass{color:var(--pass);background:var(--passbg)}
.chip.fail{color:var(--fail);background:var(--failbg)}
.chip.warn{color:var(--warn);background:var(--warnbg)}
.chip.info{color:var(--info);background:var(--infobg)}
a.report{display:inline-block;background:var(--surface);
border:1px solid var(--line);border-radius:8px;padding:.35rem .8rem;
margin:.15rem .2rem;text-decoration:none;font-size:.9rem}
#v3d{height:520px;border:1px solid var(--line);border-radius:8px;
overflow:hidden;position:relative}
#v3d-fallback{position:absolute;inset:0;display:grid;place-items:center;
color:var(--muted)}
#v3d-controls{display:flex;flex-wrap:wrap;gap:.2rem .6rem;
align-items:center;font-size:.8rem;padding:.4rem 0}
.v3d-layer{display:inline-flex;align-items:center;gap:.25rem;
color:var(--muted)}
.v3d-z{margin-left:auto;display:inline-flex;align-items:center;gap:.4rem;
color:var(--muted)}
.swatch{width:.75rem;height:.75rem;border-radius:3px;display:inline-block}
@media(max-width:900px){#layout{flex-direction:column}
nav{position:static;flex:none;display:flex;flex-wrap:wrap;gap:.2rem}
nav a{border-left:none}main{padding:1rem 1.2rem 4rem}}
"""


def slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-",
                                     text.lower())).strip("-")


def main():
    frags = {
        "build_stamp": build_stamp(),
        "snr_table": snr_table(),
        "report_links": report_links(
            [("dac_compare.html", "NRZ vs RZ comparison"),
             ("fet_char.html", "sky130 device characterization")]),
        "report_links_specs": report_links(
            [("ota_specs.html", "OTA requirement sweeps")]),
        "sizes_table": sizes_table(),
        "ota_sch_table": ota_sch_table(),
        "ota_compare_table": ota_compare_table(),
        "layout_status": layout_status(),
        "gds_link": gds_link(),
        "viewer3d": viewer3d(),
        "comp_table": comp_table(),
        "dff_line": dff_line(),
        "fig_tier1_waves": fig(
            "tier1_waves",
            "Tier-1 behavioral loop (this build): the input and the "
            "integrator output that tracks it."),
        "fig_tier1_spectrum": fig(
            "tier1_spectrum",
            "Coherent FFT of this build's bitstream. First-order noise "
            "shaping rises at +20 dB/decade; both decimation bands marked."),
        "fig_ota_ac": fig(
            "ota_ac",
            "OTA open-loop response, schematic vs extracted, from this "
            "build's testbench runs."),
        "fig_comp_race": fig(
            "comp_race",
            "The regeneration race at 10 mV overdrive (this build): both "
            "nodes lift off the precharge rail together; the input-seeded "
            "imbalance amplifies at τ ≈ 70 ps until the loser is pulled "
            "back down. The dashed trace is the SR-latched output."),
        "fig_tier1_loop_trip": fig(
            "tier1_loop_trip",
            "One loop trip through the four schematic nodes (this build): "
            "int → comp → q → dac, each on its own axis in real volts."),
        "fig_sch_tier1": fig(
            "sch_tier1",
            "The tier-1 xschem schematic as simulated: integrator, "
            "comparator, retiming flip-flop, totem-pole RZ DAC, with the "
            "behavioral models inline (right)."),
        "fig_sch_ota": fig(
            "sch_ota",
            "The generated OTA schematic (tools/gen_ota_sch.py) — the "
            "LVS golden reference, regenerated from SIZES on every "
            "change."),
        "fig_sch_comp": fig(
            "sch_comp",
            "The generated comparator schematic (tools/gen_comp_sch.py): "
            "StrongARM core, inverter buffers, NAND SR latch."),
        "fig_dff_retime": fig(
            "dff_retime",
            "Comparator output (upper) vs retimed output (lower) with an "
            "alternating input: the comparator commits mid-cycle, the DFF "
            "releases it only on the clock edge the DAC sees."),
    }

    md = markdown.Markdown(extensions=["tables", "fenced_code"])
    sections, toc = [], []
    for path in sorted(glob.glob("docs/[0-9]*.md")):
        src = open(path).read()
        src = re.sub(r"\{\{(\w+)\}\}",
                     lambda m: frags.get(m.group(1),
                                         missing(m.group(1))), src)
        title = re.search(r"^# (.+)$", src, re.M).group(1)
        plain = re.sub(r"<[^>]+>", "", title)
        sid = slug(plain)
        body = md.reset().convert(src)
        # id on the heading itself (most robust anchor target), section
        # kept id-less to avoid duplicates
        body = body.replace("<h1>", f'<h1 id="{sid}">', 1)
        sections.append(f"<section>{body}</section>")
        toc.append(f'<a href="#{sid}">{plain}</a>')

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A continuous-time sigma-delta ADC, designed as code</title>
<meta name="description" content="Open-source first-order CT sigma-delta
ADC for TinyTapeout sky130: every artifact generated, every number
CI-verified.">
<style>{CSS}</style>
</head>
<body>
<div id="layout">
<nav aria-label="Contents">{"".join(toc)}</nav>
<main>{"".join(sections)}</main>
</div>
</body>
</html>
"""
    os.makedirs("public/reports", exist_ok=True)
    open("public/index.html", "w").write(page)
    for f in glob.glob("reports/*.html"):
        shutil.copy(f, "public/reports/")
    for src, dst in [("reports/ota_layout.gds", "public/ota_layout.gds"),
                     (f"{RESULTS}/ota_geom.json", "public/ota_geom.json")]:
        if os.path.exists(src):
            shutil.copy(src, dst)
    if os.path.isdir(f"{RESULTS}/figs"):
        shutil.copytree(f"{RESULTS}/figs", "public/figs",
                        dirs_exist_ok=True)
    n_missing = len(re.findall(r'class="chip warn"', page))
    print(f"public/index.html written ({len(page)/1024:.0f} kB, "
          f"{len(sections)} chapters, {n_missing} unverified markers)")


if __name__ == "__main__":
    main()

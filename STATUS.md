# Project status & session handoff

Snapshot 2026-07-19 (OTA layout DRC clean + LVS clean). DESIGN.md holds
requirements, decisions and their rationale (append-only log); this file
holds *where things stand and how to drive them*. Update both at the end of
significant work sessions.

**Trust note:** two magic gotchas have burned this project's DRC numbers in
both directions (see DESIGN.md 2026-07-19 decision log entries): (1) fresh
`load` without `select top cell; expand` silently skips hierarchy-crossing
checks (false clean); (2) `writeall force` after `load` rewrites unmodified
gencell subcells with halved coordinates, manufacturing hundreds of fake
sub-0.005um violations on the *next* load (false dirty — the entire "894
remaining" saga was this artifact). The only trustworthy number is a fresh
process on the saved files with expand; route_ota.py now prints exactly
that ("DRC errors (fresh reload of saved files)").

## Where we are

**Shuttle: TTSKY26c (sky130A), deadline 2026-09-07.** Repo pushed to
git@gitlab.com:pthomas1/sigma-delta.git.

| Area | State |
|---|---|
| Tier 0 (python model) | done — sim/tier0.py; pattern-noise statistics understood |
| Tier 1 (behavioral xschem/ngspice) | done — full modulator with realistic OTA model (AOL/GBW/SR), RZ totem-pole DAC, interactive scope workflow |
| NRZ-vs-RZ decision | done — RZ confirmed by data (reports/dac_compare.html) |
| Block spec table | done — measured knees in DESIGN.md (AOL≥300, GBW≥50M, SR≥100V/µs) |
| Tier 2 OTA schematic | done — folded cascode sized & corner-flat (A0 65dB, GBW 209MHz, PM 58°, ±195V/µs, 4.5mW); xschem/ota.sch GENERATED from sim/ota_tb.py SIZES; equivalence proven (make xcheck) |
| Tier 2 other blocks | **StrongARM comparator DONE** (PMOS input; inverter-buffered NAND SR latch after a real hysteresis bug — see DESIGN.md; tau 77 ps tt / 63–97 ps corners, worst decision 1.18 ns, 71 µW, offset σ 13.6 mV MC N=19; schematic generated + equivalence proven via make compcheck). **DFF retimer DONE** (master-slave TG, verified in-chain behind the real comparator: clk-to-Q 0.37 ns, zero mid-cycle transitions). **Bias generator DONE** (sim/bias_tb.py: constant-gm + cascoded mirrors + startup-disable; OTA acceptance A0 65.4/GBW 194M/PM 57° with real bias, corners tighter than ideal — see DESIGN.md; open: sch gen + layout, poly R). Not started: vref/VCM buffers (25µA RZ pulses; spec via tier-1 ref-sensitivity knee sweep), clk level shifter 1.8→3.3V, output drivers + 2-phase demux |
| Tier 3 layout cells | done — mag/rin, rdac, cint, sw_nmos (extraction-verified values) |
| Tier 3 OTA layout | **DRC CLEAN + LVS CLEAN + PEX done** (fresh-process verified, fast & full DRC styles; make lvs: "Circuits match uniquely", 13/13 devices, 15/15 nets). Extracted (0.72 pF parasitics): A0 65.2 dB / GBW 119 MHz / PM 46° / SR +128/-508 V/µs / Ivdd 1.37 mA — all tier-1 knees (A0≥49.5 dB, GBW≥50 MHz, SR≥100 V/µs) still met ≥2×; PM 46° (was 58° pre-PEX) is the open question — see below |
| Tier 1 params | params.py: fs=50MHz, CINT=2pF (swing fix), refs still 1.65V-centered — move to 0.4/0.9/1.4V window is open item 6, do at comparator/buffer design time |
| CI | 4 sim jobs (smoke/reports) + new **layout-verify** job (xcheck → ota_tb → pex → layout_report; fails on DRC≠0 or LVS mismatch) + **pages** job publishing the generated design doc. Runner VM needs rebuild from updated ci/lxd/cloud-init.yml (source-builds magic 8.3.676 + netgen 1.5.323) before layout-verify can pass |
| Pages site | `make site` → public/index.html: 10-chapter narrative (docs/*.md) with CI-injected numbers via tools/gen_docs.py, interactive three.js 3D stack-up of the OTA GDS, verdict chips, GDS download. Set Pages visibility to "everyone" in GitLab project settings for the public showcase |

## OTA layout DRC — resolved (2026-07-19)

**DRC 0, LVS clean.** The "894 remaining" from the mid-cleanup snapshot
(and both of its root-cause hypotheses — strap `ty ± 1.5um` landing in the
finger structure, bulk-tap guard-ring geometry) turned out to be wrong: all
894 were fake, manufactured by magic's `writeall force` halving the
coordinates of unmodified gencell subcell files on save (grid-quantization
of odd 0.005um coordinates; full mechanism + proof in DESIGN.md 2026-07-19
entry). The violation slivers sat between *device-internal* shapes (poly
contact row vs S/D diffusion top), which no strap-height change could ever
have fixed. The met1/met2/met3 via-enclosure violations (~4140) were real
and remain fixed via the `ENCLOSING_LAYERS`/`PAD` auto-padding in
route_ota.py. route_ota.py now writes only the parent cell (`save
ota_layout`) and self-verifies DRC via a fresh magic process on the saved
files — expect "DRC errors (fresh reload of saved files): 0".

## OTA post-PEX numbers (2026-07-19)

`make pex` = tools/pex_ota.py (magic C-only extraction, cthresh 0, no R)
-> spice/ota_pex.spice, then sim/ota_tb.py --pex (same 3-DUT deck, layout
netlist wrapped to the 5-pin interface with ideal refs).

| Metric | Schematic | Extracted | Tier-1 knee | Verdict |
|---|---|---|---|---|
| A0 | 65.2 dB | 65.2 dB | ≥49.5 dB | ok |
| GBW | 209 MHz | 119 MHz | ≥50 MHz | ok (2.4×) |
| PM | 58° | 46° | no knee down to 28° | ok — **closed 2026-07-19** |
| SR | +197/−253 | +128/−508 | ≥100 V/µs | ok |
| Ivdd | 1.37 mA | 1.37 mA | — | 4.5 mW |

The GBW/PM hit is self-load from the auto-router's generous metal (0.50 µm
via pads, 0.8 µm-pitch m1 track bus, m3 risers): 0.72 pF total parasitic on
top of CL=1.5 pF. **Resolved 2026-07-19:** the FP2 sweep in `make specs`
measured no SNDR knee down to PM 28° (see DESIGN.md decision log) — 46°
extracted is accepted, OTA layout closed for v1. Note the tier-1 deck now
runs gear integration and the precision baseline reads 64.8 dB (the old
77.8 was a lucky deterministic window; long-run truth is ~66).

## Toolchain (dev machine)

- ngspice 42, xschem 3.4.4 (apt) — fine.
- magic **8.3.676 source-built** (`/usr/local/bin/magic`) — noble's 8.3.105 is
  too old for the PDK. Runner VM still has the old one (cloud-init needs a
  source-build step before layout CI).
- netgen **1.5.323 source-built** at /usr/local/bin (apt mesher removed).
- PDK: sky130A via ciel at `PDK_ROOT=/home/nvme/pdk` (pinned hash in
  ci/lxd/cloud-init.yml and DESIGN.md); `/opt/pdk` on the runner.
- glab installed but **no token stored** — `glab auth login` with api scope
  would enable pipeline debugging from the session.
- **magic batch DRC gotcha** (see DESIGN.md 2026-07-19 entry): always
  `select top cell; expand` before `drc check`/`drc listall ...` on anything
  loaded from a saved .mag file, or hierarchy-crossing violations are
  silently skipped and you'll see a false "0 errors".

## How to drive everything

From repo root (xschemrc auto-loads; PDK_ROOT defaults to /home/nvme/pdk):

- `make` / `make snr` — tier-1 sim + SNDR table (~10 s)
- `make report` — NRZ/RZ comparison → reports/dac_compare.html (~70 s)
- `make char` — device curves → reports/fet_char.html (~15 s)
- `make specs` — OTA requirement sweeps → reports/ota_specs.html (~6 min)
- `python3 sim/ota_tb.py` — OTA testbench (edit SIZES dict to resize)
- `make xcheck` — regenerate xschem/ota.sch from SIZES + prove equivalence
- `make layout` — regenerate the four passive/switch cells in magic
- `make lvs` — netgen LVS, mag/ota_layout.spice vs spice/ota_top.spice
- `python3 tools/gen_ota_layout.py && python3 tools/route_ota.py` — regenerate
  + route the OTA layout, extraction-compare vs golden (expect 13/13); the
  trustworthy DRC number is the "fresh reload of saved files" line (expect 0)
- `make pex` — parasitic-extract the routed layout + run the OTA TB on it
- `make layout-report` — fresh-process DRC + LVS + GDS export + 3D geometry
  (fails if DRC ≠ 0 or LVS mismatch; feeds the site)
- `make site` — build public/ from docs/*.md + reports/results/*.json
  (preview: `cd public && python3 -m http.server`)
- GUI schematic: `xschem xschem/tier1_sdm.sch` → Netlist → Simulate (silent
  ~10 s) → Ctrl-click LOAD WAVES; f=fit, right-drag=zoom, a/b=cursors
- GUI layout: `magic -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc mag/ota_layout.mag`

## Next actions (priority order)

1. Reference window move (open item 6): retune params.py + tier-1 rerun —
   comparator/buffer common-mode design is now underway, so this is due.
2. vref/VCM buffers (25 µA RZ pulses) and bias generator (replace the
   ideal IREFP/IREFN/VBNC/VBPC sources; corner spread re-check after).
3. Comparator + DFF layout (gen/route pattern from the OTA), then clk
   level shifter and output drivers.
4. Top-level assembly in the ttsky-analog-template frame — see the TT
   submission gap list (docs/STATUS 2026-07-19): repo is NOT yet in TT
   template form (no info.yaml, no tt_um macro/pinout, no precheck run);
   tile purchase decision (2 vs 4) still open.
5. Drive comp_tb.py sim runtime down or promote corners/MC into CI when
   the runner has headroom (currently dev-bench only; their page rows
   appear only on builds that ran them).

## Open questions for the user

- Source impedance/range/bandwidth of the real input signal (open item 7 —
  decides whether the passive virtual-ground network suffices).
- 2 vs 4 tiles purchase (area budget in DESIGN.md says: 2 works for 1st
  order, buy 4 if 2nd order/differential is the ambition).

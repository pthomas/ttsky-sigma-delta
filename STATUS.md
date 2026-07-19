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
| Tier 2 other blocks | **not started**: StrongARM comparator (+10ns regeneration TB), vref/VCM buffers (25µA RZ pulses), bias generator (replaces ideal IREFP/IREFN/VBNC/VBPC), clk level shifter 1.8→3.3V, output drivers + 2-phase demux DFF |
| Tier 3 layout cells | done — mag/rin, rdac, cint, sw_nmos (extraction-verified values) |
| Tier 3 OTA layout | **DRC CLEAN + LVS CLEAN** (fresh-process verified, fast & full DRC styles; make lvs: "Circuits match uniquely", 13/13 devices, 15/15 nets). Next: PEX + re-run ota_tb.py analyses on extracted netlist |
| Tier 1 params | params.py: fs=50MHz, CINT=2pF (swing fix), refs still 1.65V-centered — move to 0.4/0.9/1.4V window is open item 6, do at comparator/buffer design time |
| CI | runner VM up; **a separate Sonnet instance is working on .gitlab-ci.yml / ci/ — do not touch those files until it lands** |

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
  + route the OTA layout, extraction-compare vs golden (expect 13/13) and
  report a DRC count (**re-verify independently per the gotcha above before
  trusting the printed number**)
- GUI schematic: `xschem xschem/tier1_sdm.sch` → Netlist → Simulate (silent
  ~10 s) → Ctrl-click LOAD WAVES; f=fit, right-drag=zoom, a/b=cursors
- GUI layout: `magic -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc mag/ota_layout.mag`

## Next actions (priority order)

1. PEX (extract parasitics from mag/ota_layout) and re-run sim/ota_tb.py
   analyses on the extracted netlist — phase margin (58° pre-parasitics) is
   the number at risk.
2. StrongARM comparator: schematic + the metastability testbench (spec:
   full regeneration in 10 ns; tier-1 showed soft decisions cost ~25 dB).
3. Reference window move (open item 6): retune params.py + tier-1 rerun
   when comparator/buffer common-mode design starts.
4. Remaining blocks per the tier-2 list above, then top-level assembly in
   the ttsky-analog-template frame.

## Open questions for the user

- Source impedance/range/bandwidth of the real input signal (open item 7 —
  decides whether the passive virtual-ground network suffices).
- 2 vs 4 tiles purchase (area budget in DESIGN.md says: 2 works for 1st
  order, buy 4 if 2nd order/differential is the ambition).

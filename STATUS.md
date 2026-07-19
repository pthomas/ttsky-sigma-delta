# Project status & session handoff

Snapshot 2026-07-19. DESIGN.md holds requirements, decisions and their
rationale (append-only log); this file holds *where things stand and how to
drive them*. Update both at the end of significant work sessions.

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
| Tier 3 OTA layout | **connectivity done, 13/13 devices match golden netlist** (mag/ota_layout.mag); ~4.2k DRC violations pending (routing min-width/space — mechanical); LVS pending netgen install; PEX + re-sim after that |
| Tier 1 params | params.py: fs=50MHz, CINT=2pF (swing fix), refs still 1.65V-centered — move to 0.4/0.9/1.4V window is open item 6, do at comparator/buffer design time |
| CI | runner VM up; **a separate Sonnet instance is working on .gitlab-ci.yml / ci/ — do not touch those files until it lands** |

## Toolchain (dev machine)

- ngspice 42, xschem 3.4.4 (apt) — fine.
- magic **8.3.676 source-built** (`/usr/local/bin/magic`) — noble's 8.3.105 is
  too old for the PDK. Runner VM still has the old one (cloud-init needs a
  source-build step before layout CI).
- **netgen LVS still missing**: `/usr/bin/netgen` is the MESH GENERATOR
  (name collision). Install `github.com/RTimothyEdwards/netgen`
  (./configure && make && sudo make install → /usr/local/bin shadows it).
- PDK: sky130A via ciel at `PDK_ROOT=/home/nvme/pdk` (pinned hash in
  ci/lxd/cloud-init.yml and DESIGN.md); `/opt/pdk` on the runner.
- glab installed but **no token stored** — `glab auth login` with api scope
  would enable pipeline debugging from the session.

## How to drive everything

From repo root (xschemrc auto-loads; PDK_ROOT defaults to /home/nvme/pdk):

- `make` / `make snr` — tier-1 sim + SNDR table (~10 s)
- `make report` — NRZ/RZ comparison → reports/dac_compare.html (~70 s)
- `make char` — device curves → reports/fet_char.html (~15 s)
- `make specs` — OTA requirement sweeps → reports/ota_specs.html (~6 min)
- `python3 sim/ota_tb.py` — OTA testbench (edit SIZES dict to resize)
- `make xcheck` — regenerate xschem/ota.sch from SIZES + prove equivalence
- `make layout` — regenerate the four passive/switch cells in magic
- `python3 tools/gen_ota_layout.py && python3 tools/route_ota.py` — regenerate
  + route the OTA layout, extraction-compare vs golden (expect 13/13)
- GUI schematic: `xschem xschem/tier1_sdm.sch` → Netlist → Simulate (silent
  ~10 s) → Ctrl-click LOAD WAVES; f=fit, right-drag=zoom, a/b=cursors
- GUI layout: `magic -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc mag/ota_layout.mag`

## Next actions (priority order)

1. DRC cleanup in tools/route_ota.py (legalize wire/via geometry — widths,
   spacings, enclosures; the violations are uniform classes, fix in the
   painter not per-instance).
2. netgen install → wire `make lvs` target (compare mag/ota_layout.spice vs
   spice/ota_top.spice with the PDK setup file) → then PEX and re-run
   sim/ota_tb.py analyses on the extracted netlist (phase margin is the
   number at risk, currently 58° pre-parasitics).
3. StrongARM comparator: schematic + the metastability testbench (spec:
   full regeneration in 10 ns; tier-1 showed soft decisions cost ~25 dB).
4. Reference window move (open item 6): retune params.py + tier-1 rerun
   when comparator/buffer common-mode design starts.
5. Remaining blocks per the tier-2 list above, then top-level assembly in
   the ttsky-analog-template frame.

## Open questions for the user

- Source impedance/range/bandwidth of the real input signal (open item 7 —
  decides whether the passive virtual-ground network suffices).
- 2 vs 4 tiles purchase (area budget in DESIGN.md says: 2 works for 1st
  order, buy 4 if 2nd order/differential is the ambition).

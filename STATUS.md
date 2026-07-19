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
| Tier 2 other blocks | **StrongARM comparator DONE** (PMOS input; inverter-buffered NAND SR latch after a real hysteresis bug — see DESIGN.md; tau 77 ps tt / 63–97 ps corners, worst decision 1.18 ns, 71 µW, offset σ 13.6 mV MC N=19; schematic generated + equivalence proven via make compcheck). **DFF retimer DONE** (master-slave TG, verified in-chain behind the real comparator: clk-to-Q 0.37 ns, zero mid-cycle transitions). **Bias generator DONE** (sim/bias_tb.py: constant-gm + cascoded mirrors + startup-disable; OTA acceptance A0 65.4/GBW 194M/PM 57° with real bias, corners tighter than ideal — see DESIGN.md; open: sch gen + layout, poly R). **Reference buffers DONE** (sim/buf_tb.py: 3× 5T unity followers, Zout 754Ω vs ≤1k spec = 10× under breakage, bit-dep residuals ≤6.9mV, 3.2mW, corners flat — see DESIGN.md; open: sch gen, bias tap, layout+decap). **Clock level shifter DONE** (sim/lvl_tb.py: cross-coupled 1.8→3.3V, full swing, <1ns, duty ≤2.42% vs 3% gate — static duty = benign gain shift; ~300µW; corners × VDPWR sweep). **Output drivers DONE** (sim/odrv_tb.py: 5V-gate stage on the 1.8V rail — no thin-oxide overstress — + thin-oxide buffers; full swing, ≤0.4ns, Q/QB skew ≤407ps, ~180µW; corners × VDPWR). Demux REJECTED, no differential, no true LVDS (see DESIGN.md IO decisions). **ALL BLOCKS DESIGNED — next: top-level assembly** |
| Tier 3 layout cells | done — mag/rin, rdac, cint, sw_nmos (extraction-verified values) |
| Tier 3 OTA layout | **DRC CLEAN + LVS CLEAN + PEX done** (fresh-process verified, fast & full DRC styles; make lvs: "Circuits match uniquely", 13/13 devices, 15/15 nets). Extracted (0.72 pF parasitics): A0 65.2 dB / GBW 119 MHz / PM 46° / SR +128/-508 V/µs / Ivdd 1.37 mA — all tier-1 knees (A0≥49.5 dB, GBW≥50 MHz, SR≥100 V/µs) still met ≥2×; PM 46° (was 58° pre-PEX) is the open question — see below |
| Tier 1 params | params.py: fs=50MHz, CINT=2pF; **refs at 0.4/0.9/1.4V (open item 6 done 2026-07-19)** — tier-1 39.1/66.6 dB at the new window; comp_beh output now pinned to the digital mid-rail (domain-split bug, see DESIGN.md) |
| CI | 4 sim jobs (smoke/reports) + new **layout-verify** job (xcheck → ota_tb → pex → layout_report; fails on DRC≠0 or LVS mismatch) + **pages** job publishing the generated design doc. Runner VM rebuilt with source-built magic/netgen — layout-verify green. New **comparator** job (comp_tb --quick + compcheck + dff_tb + figures) |
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
  too old for the PDK. Runner VM source-builds the same version (cloud-init).
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

## Next actions — ASSEMBLY CAMPAIGN (all blocks -> layout -> TT frame)

User directive (2026-07-19): "do all the things" — lay out every block,
assemble the top level into the TT frame, per-component report sub-pages,
report when TT-ready. Commit per milestone. Ordered plan with the key
context a fresh session needs:

1. **Reference plan fix (IN PROGRESS, immediate next step).** Discovered:
   3x20 pF decap = ~30,000 um^2 of MiM — does NOT fit the 1x2 tile
   (~32.8k um^2 interior). Validate small decaps in tier-1: monkeypatch
   `sim.spec_sweep.CDEC` and run `run_variant` at RREF=754 (the measured
   buffer Zout) with CDEC 20/10/5/2 pF; expect small C to be FINE or
   better (larger droop but faster recovery; droop is bit-independent =
   benign). Then pick decap size (likely 5 pF -> ~2.5k um^2 each), log in
   DESIGN.md (the buf entry's reopen condition explicitly triggers).
   ALSO: nothing yet defines the 0.4/0.9/1.4 V levels — add a poly
   resistor ladder (e.g. 190k/50k/50k/40k from VAPWR, ~10 uA) feeding the
   buffer inputs; VDD-referenced refs = gain error = benign class; extend
   sim/bias_tb.py or buf_tb.py to include it.
2. **Golden netlists + xschem schematics for remaining blocks.** Golden
   .spice per block emitted from the TB subckt functions (single source =
   SIZES dicts): comp has spice/comp_top.spice via make compcheck; need
   emitters for dff/bias/buf/lvl/odrv (write spice/golden/<b>.spice).
   One tools/gen_sch.py with per-block device tables (gen_comp_sch.py is
   the pattern: DEVICES table + WIRES list + lab_pins; pin geometry:
   xschem y is DOWN; pfet S=(x+20,y-30) D=(x+20,y+30), nfet mirrored,
   G=(x-20,y), B=(x+20,y)) for the report sub-pages + equivalence.
3. **Block layouts** (order: comp, dff, bias, buf, lvl, odrv). Refactor
   gen_ota_layout.py/route_ota.py into a shared library (parametrize:
   golden file+subckt name, device-name regex, placement rows, cellname).
   Router facts a fresh session must know: strap ys at ty+-1.5; riser
   slots on a 1 um grid with progressive widening; ALWAYS regen placement
   before re-routing (route saves into the same .mag — guard exists);
   DRC truth = fresh process + `select top cell; expand`; never
   `writeall force` after load (magscale halving gotcha — save only the
   painted cell). bias needs new poly R cells (RB 4.6k, 75k, 25k + the
   ladder) via the gen_layout_cells.py pattern; buffers need decap MiM
   cells (cint pattern); lvl/odrv are mixed 01v8+g5v0 cells (gencells
   exist for both flavors; both rails in one cell).
4. **Top assembly** (tools/asm_top.py): place blocks + rin/rdac/cint/
   sw_nmos x3 + decaps in the frame (tt_frame/build_frame.tcl pattern,
   `getcell child 0um 0um` to anchor ORIGINS); top nets: ua[0]->RIN->sum;
   sum->OTA.INM (INP=vcm); OTA.OUT=int; CINT int<->sum; int->comp.INP
   (INM=vcm); comp.Q->DFF.D; DFF q/qb -> DAC switches (S_TOP q&clk,
   S_BOT qb&clk, S_MID clk -> vcm) -> RDAC -> sum; ladder->buffers->
   vrefp/vcm/vrefn; lvl: TT clk (1.8V) -> clk33/clkb33; odrv x2:
   q/qb -> uo[0]/uo[1]; ua[1] = int monitor (decide/confirm). Hand wire
   lists like the v0 pad wiring (worked well; check crossings on the
   same layer!). Power: met4 stripes exist (VDPWR/VGND/VAPWR); per-block
   taps met3->via3->met4. Top DRC + top LVS vs a stitched golden netlist.
5. **Extracted acceptance**: PEX the top, shortened modulator transient
   (>=512 bits), fast-path SNDR sanity (>=35 dB floor).
6. **Report sub-pages**: public/blocks/<name>.html per component
   (schematic SVG + its own 3D geometry json + metrics from its
   reports/results/<b>.json); main page: ONE combined top-level 3D
   (replace the OTA-only viewer), links to sub-pages. layout_report.py's
   geometry() generalizes (flatten per block cell); the three.js viewer
   JS is reusable (parametrize the json path). User explicitly wants:
   sub-page = schematic + 3D per component; combined geometry once.
7. **TT final**: make tt with the assembled top, info.yaml pinout update
   (clk 50MHz, uo[0]/uo[1] = Q/QB live, ua[0]=VIN, ua[1]=monitor),
   analog_pins stays 2, push (single `git push` feeds GitLab + GitHub
   mirror via dual push-urls already in .git/config), precheck green =
   "TT ready" — then TELL THE USER explicitly.

Standing context: user handles repo creation/settings; Pages
unique-domain toggle still pending on user side (then add the clean URL
to README); CI locked to push-only pipelines; support-blocks CI job
gates bias/buf/lvl/odrv; DESIGN.md decision log is append-only and has
today's 15+ entries (magic gotchas, race-sim methodology, PM/RREF/SR
knees, IO decisions — READ IT before re-deriving anything).
## Open questions for the user

- Source impedance/range/bandwidth of the real input signal (open item 7 —
  decides whether the passive virtual-ground network suffices).
- 2 vs 4 tiles purchase (area budget in DESIGN.md says: 2 works for 1st
  order, buy 4 if 2nd order/differential is the ambition).

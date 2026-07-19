# Continuous-Time Sigma-Delta ADC for Tiny Tapeout

Living design document. The **decision log** at the bottom is append-only: decisions
are superseded by new dated entries, never rewritten. Exact numeric values live in
`params.py` (single source of truth, imported by every simulation tier) once created.

## Requirements

One modulator, one bitstream, two concurrent use modes selected by decimation
filters in the companion FPGA (PolarFire SoC):

| Path | Bandwidth | Target resolution | Use |
|---|---|---|---|
| Fast | ~1 MHz | ≥ 6–7 ENOB | protection / trip |
| Precision | ~100 kHz | 10–12 ENOB | measurement |

Platform: Tiny Tapeout analog tile(s), sky130A, 3.3 V analog supply.
Companion system provides a clean low-jitter clock and receives the bitstream
(LVDS-capable I/O on the FPGA side).

## Architecture (current)

- **1st-order, 1-bit, continuous-time** modulator: active-RC integrator
  (single-ended OTA), clocked comparator, DFF retimer, resistive feedback DAC.
  2nd order is the planned upgrade once the flow is proven end-to-end — it adds
  one integrator and reuses every block.
- **fs target ≈ 50 MHz** (pending verification of TT mux clock and output
  toggle limits — open item 1). Loop coefficient k = Ts/(R·C) ≈ 0.5 →
  RC ≈ 40 ns, e.g. ~40 kΩ high-res poly + ~1 pF MiM. Both small on-chip.
- **Feedback DAC: RZ presumed default, NRZ kept as a parameter.** Pulse shape
  is a knob in the behavioral model at every tier; the four-corner sim matrix
  ({NRZ, RZ} × {edge asymmetry, jitter}) confirms or overturns the presumption
  (see decision log).
- The loop model includes **one full clock cycle of feedback (DAC) delay**
  from day one — at 50 MHz, excess loop delay is a first-order effect, not a
  refinement.
- **Output:** complementary bitstream (Q / Q̄) on two digital outputs into a
  terminated differential receiver on the FPGA ("pseudo-LVDS"). A true
  current-mode LVDS driver is a stretch goal, not on the critical path.

## Performance budget — 1st order @ fs = 50 MHz

Ideal 1-bit SQNR: 6.02 + 1.76 − 10·log10(π²/3) + 30·log10(OSR) dB.

| Bandwidth | OSR | Ideal SQNR | Expected (measured, tiers 0+1) |
|---|---|---|---|
| 1 MHz | 25 | 44.6 dB | ~6 ENOB (confirmed: 38–39 dB SNDR) |
| 100 kHz | 250 | 74.5 dB | ~10 ENOB long-run; ±1 ENOB per-window scatter |

The linear-model formula is ~8 dB optimistic on the precision path: 1st-order
in-band noise is pattern tones, not white shaped noise (tier-0 long-run
converges to ~66 dB SNDR at −4.4 dBFS; 16k-bit windows scatter 54–67 dB with
dither seed). This is the strongest quantitative argument yet for the
2nd-order upgrade if the 12-bit target is firm.

Non-idealities ranked by expected impact (clean external clock retires jitter
from the top of the usual list):

1. Feedback DAC ISI / edge asymmetry (single-ended, NRZ) — threatens the
   precision path; motivates the RZ option.
2. Excess loop delay (comparator + DFF + DAC settling within 20 ns).
3. OTA finite gain and GBW (needs ~40 dB gain, GBW a few × fs).
4. Thermal noise (input R ~40 kΩ: comfortably below 12-bit level at 100 kHz).
5. Clock jitter (retired by PolarFire clock; returns ×2 if RZ is chosen —
   budget exists).

## Block requirements (measured, tier-1 sweeps 2026-07-18)

From `make specs` (reports/ota_specs.html): one OTA parameter swept at a
time, knees read against the plateau (precision values carry ±1–2 dB
pattern-noise scatter).

| OTA parameter | measured knee | spec (margin) | design target |
|---|---|---|---|
| DC gain AOL | degraded at 30, recovered by 100–300 | ≥ 300 (50 dB) | 1000 (60 dB) |
| GBW | **no knee down to 25 MHz** (see note) | ≥ 50 MHz | 150–200 MHz |
| Slew rate | broken at 3, degraded at 6 V/µs (2026-07-19, CINT=2p; the older "broken at 12.5" was at CINT=1p — knee scales with k) | ≥ 100 V/µs | 200 V/µs |
| Phase margin (2nd pole) | **no knee down to PM 28°** (FP2 sweep 50 MHz–2 GHz, 2026-07-19) | none needed; 46° extracted accepted | — |

GBW note: the loop is insensitive to single-pole bandwidth because finite-GBW
settling errors are *linear* — the same every cycle per bit value — so they
appear as gain error, not noise/distortion, and delayed-RZ leaves a half
period for residual settling. Caveat: a real multi-pole OTA adds phase (ELD)
the single-pole model doesn't capture, hence the 150–200 MHz target rather
than 50. Slew errors are the nonlinear ones, and the SR knee (~2× the naive
pulse-edge estimate) is the binding constraint.

Other blocks (from earlier findings): comparator+DFF must fully regenerate
within the 10 ns half-period (soft decisions leak through the DAC as
unshaped noise, ~25 dB penalty observed); DAC switches per open item 6
(ron flat 229–441 Ω at W=10 µm across the low window); VCM buffer must
absorb ~25 µA RZ return pulses at 50 MHz.

First-cut OTA feasibility against the gm/Id data: gm ≈ 1.9 mA/V into ~1.5 pF
gives 200 MHz; at gm/Id ≈ 15 that's ~250 µA tail → folded cascode at
~1.7 mW, slew ~170 V/µs — all targets reachable with room.

**OTA v1 sized (2026-07-18, sim/ota_tb.py, tt corner):** folded cascode,
PMOS input pair at CM 0.9 V, cascoded PMOS mirror load, tail/sink from 1:1
mirrors (cascode gate biases still ideal sources — bias generator pending).
Achieved: **A0 65 dB, GBW 209 MHz, PM 58°, slew +197/−253 V/µs, output
range 0.31–2.28 V, 4.5 mW** (power driven by the slew target: 380 µA tail).
**Corners (2026-07-18):** tt/ss/ff/sf/fs all within A0 64.6–65.4 dB,
GBW 199–220 MHz, PM 56–59°, SR+ 190–204 V/µs, 4.5 mW — sizes frozen for
layout. Caveats: cascode gate biases and reference currents are still ideal
sources (real bias gen will add spread), temperature not yet swept, PM
consistently ~2–4° under the 60° bar (accepted for v1, revisit with PEX). Sizing lessons (they cost iterations, don't relearn them):
- sky130 5 V fets are **width-binned** — arbitrary W is rejected; tile
  parallel unit fingers (WUNIT = 5 µm) with `m=`.
- Thick-oxide devices have **soft saturation**: a cascode at normal current
  density burns 0.5 V of overdrive and sits in triode at Vds ≈ 0.35 V. Run
  cascodes at ~1 µA/µm *and* L = 1 µm (gds at short L is poor even in
  saturation; measured 17× boost at L=0.5 vs ~40× at L=1 low-density).
- The single-ended **mirror pole** (two PMOS gates on the diode node) set
  the phase margin; small/short mirror devices bought back ~6°.
- Diagnose with `@m.x...msky130_...[gm]/[gds]/[vdsat]` op saves, not theory.

**New coupling for open item 6:** the cascoded output floor is ~0.55 V
(sink Vdsat + cascode Vdsat + margin), so the integrator swing cannot reach
the 0.4 V window edge. Fix **confirmed in tier 1 (2026-07-18)**: CINT
1 pF → 2 pF halves the feedback step (k = 0.125); measured integrator swing
VCM ± 0.22 V (→ 0.68–1.12 V at the 0.9 V CM), SNDR unchanged on both paths,
and — important — **input full scale is untouched** (±0.5 V, set by
RIN/RDAC and the reference span, independent of the internal swing).

## Area budget (vs TTSKY26c tiles)

1x2 analog tile = 160×225 µm = 36,000 µm²; 2x2 = 334×225 µm = 75,150 µm².
Estimate for the 1st-order chip (placed area ≈ 3–4× gate area for actives):

| Block | est. placed area |
|---|---|
| OTA (≈2,000 µm² gate) | ~8,000 µm² |
| C_INT 2 pF MiM (2 fF/µm², M3–M4 — M5 ban doesn't bite) | 1,000 µm² |
| R_IN + R_DAC (high-res poly, wide for matching) | <1,000 µm² |
| comparator + DFF + level shifter + output drivers | ~2,000 µm² |
| VCM + reference buffers | ~4,000 µm² |
| bias, DAC switches, misc | ~1,500 µm² |
| **total** | **~18,000 µm² ≈ 50% of 1x2** |

So the 1st-order design fits a **1x2 (two tiles) with ~50% margin** (rest
becomes decap, which VCM/refs want anyway). The 2nd-order upgrade adds
roughly +10,000 µm² (second OTA + cap) → ~75% of a 1x2: possible but tight.
**If the 2nd order (or differential) is the ambition, buy 2x2 (four
tiles);** a pure 1st-order chip is comfortable in two.

## Layout notes (tier 3, learned on the OTA cell)

- OTA layout is fully generated: `tools/gen_ota_layout.py` (placement from
  SIZES, bbox-measured rows) + `tools/route_ota.py` (straps/routing derived
  from the golden xschem netlist; extraction-verified 13/13 devices matched).
- sky130 gencells with `full_metal` come with every contact column already
  strapped in met1 full-height — group columns on **met2** (via1 down), run
  risers on **met3**, tracks met1 above the array. Any met1 painted across a
  device shorts everything.
- Unit zoo: parent .mag transforms and runtime `box values` are 200/µm;
  subcell .mag rects 100/µm; .ext port coords 200/µm. Layout gencell `w` is
  per-finger (schematic W is total).
- The router self-audits: same-layer overlaps between different-net paint
  boxes are reported before painting. Jogs must anchor at the tap point,
  not the slot-search range edge.
- Status: connectivity done; ~4k DRC violations (min width/space of painted
  routing) to clean, then netgen LVS (install pending) and PEX.

## Toolflow

Four tiers, all generated from `params.py` so they cannot drift apart:

0. **Python behavioral model** — discrete-time equivalent difference equations;
   the only tier where SNR is measured (coherent-FFT SNDR of ≥64k-sample
   bitstreams, sub-second runs). Non-ideality knobs: RC error, ELD, finite
   gain/GBW, ISI, jitter, hysteresis.
1. **Behavioral ngspice** — same topology from ideal elements (B-sources,
   switches). Validates that the circuit implements the math; thousands of
   clocks in seconds–minutes.
2. **Transistor-level ngspice** (sky130, PDK install pending) — block specs
   only (integrator swing/settling, comparator offset/metastability, DAC
   symmetry) + short full-loop sanity runs; measured non-idealities are
   back-annotated into tier 0 to predict SNR.
3. **magic layout** — LVS vs xschem netlist via netgen, PEX re-runs of tier-2
   block tests.

Schematics: **xschem** (text format generates reliably, netlists straight to
ngspice, standard sky130/TT flow, LVS path to magic). KiCad and LTspice were
tried in past sessions and rejected. lcapy/schemdraw only for documentation
figures.

xschem authoring notes (learned 2026-07-05, tier-1 build):
- Literal braces in attribute strings (spice params like `{RIN}`) must be
  escaped `\{RIN\}` — unescaped they silently truncate the attribute.
- `vsource_arith.sym` netlists `VOL='expr'` E-source syntax → instance names
  must start with `E`, not `B`.
- In symbol `format=` strings, `@@PIN` references need surrounding spaces
  (`v( @@PLUS )`), otherwise substitution truncates the card.
- Custom symbols whose .subckt lives in a code block need `type=primitive`
  (not `subcircuit`, which makes xschem descend looking for a .sch).
- Headless: `xschem --netlist --spice -q -x`, PNG via `--png --plotfile`
  (needs a DISPLAY); project `xschemrc` in cwd supplies library paths.
- Behavioral convergence: keep hard `u()` steps out of feedback paths that
  drive switch controls — use steep `tanh` instead; give the comparator very
  high gain (soft comparator output + smoothed DFF = analog-valued feedback
  pulses, which quietly cost ~25 dB of in-band SNDR).

## Target shuttle (2026-07-18)

**TTSKY26c** (sky130A, via ChipFoundry), submission deadline **2026-09-07**.
Template: `TinyTapeout/ttsky-analog-template`. Measured TT platform specs
(tinytapeout.com/specs/, single-die measurements):
- Clock/inputs: max **66 MHz** in; ~10 ns pad→project insertion delay;
  demo board RP2040 generates 1 Hz–66.5 MHz (we'll drive clk externally).
- Outputs: max **33 MHz** toggle — a 50 Mbit/s bitstream needs two-phase
  demux (open item 1b). Mux round-trip latency ~20 ns, pin-to-pin skew <2 ns.
- Digital I/O domain is **VDPWR = 1.8 V** → on-chip 1.8→3.3 level shifter
  needed for clk; bitstream output driven back at 1.8 V.
- Analog: 6 `ua` pins (use in order), path <500 Ω / <5 pF / 4 mA;
  40 €/pin (first two), 100 €/pin after; VAPWR 3.3 V available with the
  analog template; analog projects min 2 tiles high (1x2 = 160×225 µm, 140 €).
- Input path check: 500 Ω / 5 pF against RIN = 40 kΩ → 1.25 % gain error,
  64 MHz pole — fine for both bandwidth targets.

## Open items

1. ~~Verify TT I/O limits~~ — **resolved 2026-07-18**, numbers above.
   Successor: **1b — output strategy**: keep fs = 50 MHz and demux the
   bitstream onto two output pins at 25 MHz each (recommended; PolarFire
   re-interleaves; complementary pairs would use 4 of the 8 outputs), vs.
   drop fs to ~33 MHz single-pin (costs ~0.5–1 ENOB at 1 MHz BW). Also new:
   clk level shifter (1.8→3.3 V) joins the block list.
2. ~~NRZ vs RZ DAC~~ — **resolved 2026-07-11**, RZ confirmed (see decision
   log); remaining sub-item: quantify RZ's jitter penalty once a realistic
   clock-jitter number for the PolarFire→TT path exists.
3. Install sky130 PDK (ciel/volare) + xschem sky130 symbol library for tier 2.
4. Criteria for revisiting differential: if tier-2 shows ISI or supply/substrate
   coupling capping the precision path below ~10 ENOB despite RZ.
5. Prior transistor-level 1st-order blocks live in `backup/` (excluded from
   git); pull individual files in as needed.
6. **Choose the exact reference window** (follows from the 2026-07-18
   all-NMOS DAC decision). **Measured 2026-07-18** (sim/char_fets.py,
   reports/fet_char.html, tt corner): nfet_g5v0d10v5 Vth(cc) = 0.86 V,
   pfet 1.10 V; NMOS pass-switch ron (W=10 µm, gate 3.3 V) =
   229/290/441 Ω at 0.4/0.9/1.4 V — flat — vs **35 kΩ at the old
   VREFP = 2.15 V** (80× cliff starting ~1.8 V). 0.4/0.9/1.4 V adopted
   provisionally; remaining sub-questions before locking params.py: OTA
   input CM at 0.9 V (PMOS pair headroom fine, verify swing), comparator CM,
   buffer headroom, input mapping. Also confirmed: 1.8 V gate drive is
   useless even for the low window (1.8 − 0.86 < 1.4) — the clk level
   shifter is mandatory, not optional. gm/Id sizing curves in the same
   report (weak-inversion plateau ≈19/V nfet, ≈21/V pfet, |Vds|=1.65 V).
7. **Input conditioning / scaling.** The virtual-ground input is itself a
   passive conditioner: any external range maps onto the ±0.5 V full scale
   with a scaled R_IN (gain <1) plus one offset resistor from a reference
   into the summing node — linear, low-noise, no new block (e.g. 0–3.3 V
   external ↦ full scale with R_IN ≈ 132k + shift R). An *active* input
   op-amp (buffer/PGA) is only warranted if the source can't drive ~40 kΩ
   or needs gain >1 — it would sit unshaped in the signal path and must
   out-perform the ADC's noise, i.e. it's another OTA-class design; prefer
   external conditioning on the PolarFire carrier for v1. Blocking
   question: what is the actual source (impedance, range, bandwidth)?
8. **OTA 1/f noise in the precision band** — sky130 flicker corners can reach
   the 100 kHz band. First response: PMOS input pair, generous device area.
   If tier-2 noise sims show 1/f still dominating the 10–12 ENOB budget,
   consider chopping the OTA (distinct from the differential-topology
   question; see 2026-07-05 terminology entry).

## Toolchain versions

- ngspice 42, xschem 3.4.4 (noble packages) — fine.
- **magic: noble's 8.3.105 is too old for the PDK tech file (requires
  ≥ 8.3.411) — build from source** (github.com/RTimothyEdwards/magic).
  Applies to the dev machine AND the CI runner (ci/lxd/cloud-init.yml
  needs a source-build step before layout jobs can run there).
- netgen-lvs 1.5.133 (noble) — version vs PDK unverified, check at first LVS.

## Decision log

- **2026-07-05 — Toolflow: xschem + ngspice + Python, four tiers.** Why:
  xschem's text format is machine-generatable and connects to both ngspice and
  magic/netgen; KiCad/LTspice schematic generation failed in past sessions and
  has no LVS path. Reopen if: xschem generation proves as fragile as KiCad's.
- **2026-07-05 — Clean external clock from PolarFire SoC, fs ≈ 50 MHz.** Why:
  sub-ps source jitter removes the classic CT-ΣΔ limiter and enables high-OSR
  operation; FPGA hosts decimators. Reopen if: TT I/O verification (open item
  1) caps the clock well below 50 MHz.
- **2026-07-05 — One bitstream, two decimation paths (1 MHz and 100 kHz).**
  Why: bandwidth/resolution tradeoff belongs to the FPGA decimator, not the
  silicon; both requirements served by one modulator.
- **2026-07-05 — Single-ended analog core.** Why: half the area/power, no CMFB
  design, matches available single-ended blocks in backup/. Cost accepted: DAC
  ISI and supply-noise sensitivity; mitigations are RZ DAC and decoupled
  VCM/refs. Reopen per open item 4.
- **2026-07-05 — 1st order first, 2nd order as upgrade.** Why: meets both
  targets' floors (~6 / ~10 ENOB), all blocks exist, 2nd order is a strict
  superset (one more OTA + passives) once the flow works end-to-end.
- **2026-07-05 — NRZ DAC initially, RZ as parameterized alternative.** Why:
  NRZ is simplest and matches prior blocks; RZ eliminates ISI at the cost of
  2× jitter sensitivity (affordable with the clean clock) and ~2× DAC
  current/slew demand. Decide from data (open item 2).
- **2026-07-05 — Output as complementary pair into FPGA differential
  receiver.** Why: DFF already provides Q/Q̄; improves 50 Mbit/s capture
  margin at near-zero silicon cost. True LVDS driver deferred to stretch goal.
- **2026-07-05 — RZ presumed default for the feedback DAC** (supersedes
  "NRZ initially" above). Why: ISI is the top-ranked threat to the precision
  path and RZ removes it structurally; the clean external clock pre-pays RZ's
  2× jitter cost. Both pulse shapes remain parameterized at every tier; the
  four-corner matrix (pulse shape × measured edge asymmetry × clock jitter)
  must confirm before silicon. Reopen if: OTA slew/GBW cost of the 2× DAC
  pulse amplitude proves expensive in tier 2, or sims show NRZ ISI is benign
  at our edge-asymmetry levels.
- **2026-07-07 — RZ rationale, ranked (clarifies the RZ entry above).**
  (1) ISI elimination — the original and primary reason. (2) Excess-loop-delay
  tolerance — delayed-RZ (decide at rising edge, fire during clk-low) makes
  total feedback charge per period exact for any decision/settling delay up to
  Ts/2, instead of splitting charge across periods as NRZ does. This reason is
  minor for 1st order (a single-integrator loop absorbs even a full-period
  delay gracefully) but becomes stability-critical for the 2nd-order upgrade,
  where uncompensated ELD erodes phase margin and degrades/destabilizes the
  loop. RZ thus pre-solves a 2nd-order problem the NRZ design would need an
  extra compensation DAC path for.
- **2026-07-11 — RZ confirmed as DAC default, from tier-1 data**
  (sim/compare_dac.py, reports/dac_compare.html). Paired comparison, equal
  feedback charge, ~190 ps injected edge asymmetry (ron 100/2000 Ω against
  100 fF): NRZ precision path drops 57.9 → 48.4 dB SNDR (in-band harmonics +
  raised floor); RZ moves 61.4 → 58.0 dB, within pattern-noise scatter. Even
  symmetric NRZ trails RZ — its error scales with data-dependent transition
  count. Cost side (OTA slew, jitter ×2) still owed a tier-2 check.
- **2026-07-11 — 1st-order pattern noise dominates the precision path.**
  In-band "noise" is limit-cycle tones: flat in-band plateau, extremely
  sensitive to DC operating point; SNDR of any single 16k-bit window is a
  ±7 dB lottery, and the white-noise SQNR formula is ~8 dB optimistic
  long-run. Consequences: (a) testbenches must dither the input (0.5 mV
  TRNOISE, pinned rndseed for paired A/B runs); (b) quiet near-DC inputs in
  silicon will tone in-band — real risk for the precision path; (c) 2nd order
  largely decorrelates these tones — added to its justification. Tier-0 model
  (sim/tier0.py) cross-checks tier-1 within the scatter band.
- **2026-07-18 — DAC switches: all-NMOS with a lowered reference window**
  (option 2 of the high-side-drive discussion). NMOS switch strength depends
  on the passed potential; with the 3.3 V-centered refs the high-side NMOS
  has only ~0.45 V overdrive. Lowering the window (≈0.4/0.9/1.4 V, exact
  values = open item 6) gives both switches ≥1.9 V overdrive — symmetric and
  low-impedance by construction — and fixes S_MID's marginal VCM drive too.
  Fallback: oversized weak high-side NMOS at the old refs. Stretch:
  bootstrapped gate drive (SAR-style, all on-chip in sky130). T-gates
  rejected as default (RZ tolerates their asymmetry, but option 2 is cleaner).
  Reopen if: low-VCM OTA input stage proves awkward in sky130, or the input
  range mapping doesn't suit the application.
- **2026-07-05 — Terminology note (differential vs chopping).** "Differential"
  in open item 4 means a fully differential signal path (differential-output
  OTA + CMFB, mirrored passives, cross-coupled DAC) — a static topology choice
  that cancels supply/substrate coupling, DAC edge asymmetry, and even-order
  distortion. Chopping is a separate dynamic technique (periodically swapping
  OTA input/output polarity) that shifts offset and 1/f noise out of band; it
  does not fix ISI or supply rejection. Orthogonal decisions; chopping tracked
  in open item 6.
- **2026-07-19 - magic batch-DRC gotcha: a freshly-loaded cell with no
  in-session paint reports 0 errors even when real violations exist,**
  because subcell instances default to unexpanded (collapsed bbox) and
  `drc check` silently skips hierarchy-crossing checks against them; a cell
  painted fresh in the same session (e.g. gen_ota_layout.py's own gencell
  placement) does not have this problem. Always do `select top cell; expand`
  before `drc check`/`drc listall count total` on anything loaded from disk,
  and don't trust a suspiciously-clean number without independently
  reproducing it in a fresh process. Confirmed the checker itself works via
  a deliberately-injected spacing violation. tools/route_ota.py's own final
  check now does this; STATUS.md's DRC figures going forward should all be
  from this method. Why this matters: an earlier session's LVS-fix commit
  (a6dbfdb) reported "~4.2k DRC violations pending" from before this gotcha
  was known - that number was never independently re-verified and turned out
  to undercount; true count when properly checked was 5034 pre-fix. Reopen
  if: a magic version upgrade changes default expand behavior.
- **2026-07-19 - Via/contact painting must always draw its own enclosing
  metal pad, never rely on incidental overlap from nearby wire geometry.**
  Root cause of ~4140 of the 5034 real DRC violations above: route_ota.py
  painted bare via/contact-sized cuts (via1, via2, mcon) and depended on
  whatever metal happened to already be nearby - zero, in the case of the
  bulk-tap mcon+via1 stack landing on an li-only guard ring with no m1 at
  all. Fixed with a PAD-sized (0.50 um, safely above the largest required
  enclosure of 0.045 um/side) box auto-painted on every metal layer a given
  contact type must be enclosed by (ENCLOSING_LAYERS dict), any time that
  contact type appears in a paint() call. Took DRC 5034 -> 894, LVS still
  clean. Reopen if: a future contact type is added to paint() calls without
  a matching ENCLOSING_LAYERS entry.
- **2026-07-19 - magic `writeall force` after `load` corrupts unmodified
  gencell subcells (grid halving) - the "remaining 894" DRC violations were
  entirely this artifact, and the layout is actually DRC clean.** Mechanism,
  proven by isolated experiment (plain `load ota_layout; writeall force`
  with no editing reproduces it): magic 8.3.676 writes cells it considers
  unmodified lambda-normalized *without* their `magscale 1 2` header,
  halving every internal coordinate into 100/um file units. Gencell devices
  contain odd internal coordinates (e.g. the licon.9+psdm.5a poly-contact to
  P-diff gap of exactly 47 units = 0.235 um), so the halving rounds them
  (47 -> 23 -> 46 on reload = 0.230 um < 0.235 um), manufacturing hundreds
  of fake sub-0.005um spacing/width violations inside every device. Modified
  cells (the painted parent) are written exact with `magscale 1 2`, which is
  why only subcells were hit. Evidence that convicted it: violation slivers
  sat between device-internal shapes (poly contact row vs S/D diffusion top,
  pfet rows only), not at anything route_ota.py paints - falsifying the
  earlier "strap ty±1.5 lands in the finger structure" hypothesis (that
  root-cause entry in STATUS.md was wrong); gen-written subcells carry
  `magscale 1 2` with exact coords, route-written ones were coordinate-halved
  copies; and a freshly generated+routed layout DRCs clean in-session but
  showed 894 only after the lossy write+reload. Also retroactively taints
  the "5034 real violations pre-fix" number above: the ~890 licon/width
  portion of it was this artifact (the ~4140 metal-enclosure portion was
  real). Fix: tools/route_ota.py now uses `save ota_layout` (writes only the
  cell it painted) instead of `writeall force`, and re-verifies DRC on the
  saved files in a *fresh* magic process (expand + full-cell check) - that
  reload count is the only number to trust. Result: DRC 0 (fast and full
  styles, independent processes), LVS still "Circuits match uniquely",
  13/13 devices from a fresh-load extraction. Reopen if: magic changes
  writeall unit handling, or any new tool step rewrites mag/ gencell files
  (watch for "Scaled magic input cell ... geometry by factor of 2" on load -
  that warning means a lossy rewrite already happened).
- **2026-07-19 - PM knee measured: none exists; extracted OTA layout (PM
  46°) accepted, OTA closed for v1.** Method: the tier-1 behavioral OTA
  gained a buffered second pole (FP2 param, baseline 100 GHz ≈ none), and
  `make specs` now sweeps it 50 MHz–2 GHz with each point labeled by the
  equivalent OTA unity-gain phase margin (28°–84°). Result: SNDR flat
  within pattern-noise scatter on both paths all the way down to PM 28°.
  Physics: same mechanism as the GBW non-result — *linear* settling error
  of any pole order is identical every cycle per bit value and aliases to
  gain error; only nonlinear (slew) errors demodulate into the band. Slew
  sensitivity re-validated in the same session: knee now at ~3–6 V/µs
  (was 12.5 at CINT=1p; scales with the halved loop coefficient, resolving
  the apparent contradiction with the 2026-07-18 table). Two supporting
  changes: (1) tier-1 deck now uses `.options method=gear` — default
  trapezoidal integration rings on the FP2 stage's fast state and read as
  ~2/8 dB (fast/precision) of fake SNDR loss; gear is L-stable and damps
  it; (2) precision-path baseline now reads 64.8 dB (was 77.8 pre-gear) —
  the old number was one lucky deterministic window, the new one sits at
  the documented long-run ~66 dB. Reopen if: the OTA is reused outside the
  integrator role (a unity-gain buffer DOES care about PM), the 2nd-order
  loop changes the phase budget, or fs moves.
- **2026-07-19 - StrongARM comparator v1: PMOS input pair, electrically
  validated in sim/comp_tb.py.** Topology decision: the 0.4-1.4 V window
  (open item 6) was chosen so NMOS *passes* it — the complementary rule is
  that PMOS *senses* it, same reasoning that gave the OTA its PMOS input
  pair. NMOS-input StrongARM at the 0.68 V swing floor would have ~zero
  overdrive against the ~0.8 V thick-oxide Vth; PMOS input gets ~1.5 V and
  speeds up at exactly the corner where NMOS dies. Mirrored StrongARM:
  PMOS clocked tail (evaluates CLK-low, matching tier-1 DFF phasing),
  precharge-to-VSS resets, cross-coupled regeneration, NOR SR latch;
  single-phase clock, no inverters. Measured (tt): regeneration tau 69 ps,
  worst decision 1.01 ns over CM 0.68-1.12 V and dv 10 uV-100 mV (10 ns
  budget), 0 sign errors at >=10 mV, SR latch holds through precharge,
  metastable window ~1e-31 V at 5 ns, kickback 10.6 mV peak on an RC proxy
  of the integrator node, 61 uW at 50 MHz. Open: xschem schematic gen +
  equivalence check, mismatch/offset MC, corners, kickback re-check in the
  closed loop. Reopen if: reference window moves, or fs changes.
- **2026-07-19 - Simulating regenerative races: the solver picks the
  winner unless you take it seriously.** Lessons from comp_tb.py, all
  measured: (1) default ngspice tolerances (reltol 1e-3, vntol 1 uV) are
  larger than mV-scale race seeds - wrong-sign decisions at 10 mV
  overdrive; (2) many DUTs sharing one transient share one timestep
  controller - the most active DUT under-resolves everyone else's seed;
  one ngspice process per measurement point; (3) even per-point, the
  verdict was timestep-dependent until tmax was forced to 1 ps through the
  violent di-ramp (5 ps and 2 ps steps gave opposite winners); (4) ideal
  V-sources choke ("timestep too small, trouble with node v*#branch") at
  tight abstol - 10 ohm series resistors on every ideal source; (5) gear,
  per the tier-1 finding. Even then, sub-mV sign verdicts sit at the
  amplified-solver-noise floor and are NOT meaningful - the TB enforces
  sign only >=10 mV (silicon offset/thermal noise owns that regime anyway,
  and a 1-bit SD loop tolerates near-zero-overdrive sign errors as bounded
  quantization noise; what it cannot absorb - measured 25 dB - is a soft
  mid-rail decision, so decision TIME is enforced at every point).
- **2026-07-19 - Comparator output chain corrected: inverter buffers +
  NAND SR latch (the NOR latch wired straight to the regeneration nodes
  was a real hysteresis bug).** Symptom: state-dependent wrong-sign
  decisions surviving every solver-tolerance fix, including at 10 mV
  overdrive, with decision times that shifted when supply series R was
  added. Mechanism: the latch holds the previous decision through
  precharge, so its gate loading on on1/on2 is asymmetric (the NMOS on
  the held-high side sees its drain at VDD, the other at 0) - a
  ~10 mV-equivalent dynamic hysteresis seeded by the PREVIOUS bit. This
  is why the textbook StrongARM buffers its outputs before the latch:
  both inverter outputs sit at VDD during precharge regardless of held
  state, so the loading is symmetric by construction. After the fix the
  race is monotone in overdrive and sign-correct at every enforced point
  in all five corners (tau 63-97 ps, worst decision 1.18 ns). Verified
  metrics (tt): tau 77 ps, worst 0.96 ns, 71 uW, kickback 10.5 mV,
  offset MC (tt_mm, N=19) sigma 13.6 mV - benign DC shift in a 1-bit
  loop, and it justifies the >=10 mV sign-enforcement floor in the TB.
  Reopen if: the latch or its loading changes, or a hysteretic
  comparator is ever intentionally wanted.
- **2026-07-19 - DFF retimer v1 (transistor level) verified in-chain:**
  static CMOS master-slave with transmission gates, driven by the real
  comparator in sim/dff_tb.py with an alternating-sign input (hardest
  retiming pattern). 9/9 decisions retimed, clk-to-Q 0.37 ns, zero
  mid-cycle output transitions (the property the DAC needs - ISI is the
  #1 ranked non-ideality). Open: drive strength vs actual DAC switch +
  level-shifter load at assembly time.
- **2026-07-19 - Open item 6 executed: reference window moved to
  0.4/0.9/1.4 V (VREFN/VCM/VREFP).** Spans preserved (VREFP-VCM = 0.5 V)
  so k and input full scale are untouched. Tier-1 result: fast 39.1 dB /
  precision 66.6 dB, ones density 0.500, integrator swing 0.685-1.117 V -
  exactly the designed VCM +-0.22 window. One latent bug flushed out: the
  behavioral comparator output was centered on {VCM} (analog) while the
  DFF thresholds at 1.65 (digital mid-rail) - symmetric only by
  coincidence at the old 1.65-centered window; moving VCM to 0.9 shifted
  the effective decision threshold ~24 mV and biased soft decisions,
  costing ~15/18 dB (fast/precision). comp_beh.sym now pins its output to
  the digital mid-rail explicitly: analog common mode and digital levels
  are independent domains. Reopen if: supply or digital levels change.
- **2026-07-19 - Bias generator v1 (sim/bias_tb.py): constant-gm core,
  cascoded mirrors, startup-with-disable - ACCEPTED against the golden
  OTA.** Beta-multiplier (K=4, RB=4.6k) gives a ~19 uA master; IREFP/
  IREFN are 19x/17x cascoded mirrors (cascode gates reuse the block's own
  VBNC/VBPC - the 1.5 V rail is exactly an NMOS-sink cascode bias);
  VBNC/VBPC are master x R ratios (R/RB - process-flat to first order).
  Three measured lessons: (1) uncascoded 5V mirrors at L=1 ran 43% hot
  and tracked VDD (soft saturation again); (2) a "weak" always-on PMOS
  startup leaker at Vsg=2.45 V injects 3.4 uA = 17% master error - now a
  stolen-away startup (leaker -> nst, VBNC-gated NMOS steals it once
  running, PMOS pass feeds nb only when the core is off); (3) the PMOS
  pass bulk must be VDD - tied to VSS its source junction forward-biases
  and the core never starts. Acceptance (golden OTA, real bias vs ideal):
  tt A0 65.4 dB / GBW 194 MHz / PM 57 deg (ideal: 65.2/209/58); corners
  ss/ff within A0 64.3-66.2, PM 57-58 - tighter than ideal-bias corners
  because the constant-gm master tracks the devices. VDD +-10%: currents
  +-5%. Startup verified from a 0->3.3 V ramp. Open: schematic gen +
  equivalence (gen_ota_sch pattern), layout, ideal-R -> poly R at layout
  time. Reopen if: OTA sizing changes (mirror ratios follow SIZES).
- **2026-07-19 - Reference-buffer spec measured (tier-1 RREF knee): soft.**
  New RREF axis in `make specs`: each of VREFP/VREFN/VCM driven through a
  source impedance with 20 pF decap to ground (the buffer model). Result:
  fast path flat to 10 kohm; precision path within its normal scatter to
  ~1 kohm, marginal at 3 kohm, broken at 10 kohm (45 dB). Physics: the
  decap sources each 10 ns DAC pulse (~12.5 mV droop at 25 uA); the buffer
  only recharges it between pulses, and droop is largely bit-independent
  until recovery spans many periods. Spec: Rout <= 300 ohm with >= 20 pF
  decap per reference (target <= 100 ohm) - a modest one-stage buffer
  suffices; don't burn power on a fast one. Reopen if: CDEC shrinks below
  ~10 pF in layout, fs changes, or the DAC pulse current grows.

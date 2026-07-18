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
| Slew rate | broken at 12.5, marginal at 50 V/µs | ≥ 100 V/µs | 200 V/µs |

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
7. **OTA 1/f noise in the precision band** — sky130 flicker corners can reach
   the 100 kHz band. First response: PMOS input pair, generous device area.
   If tier-2 noise sims show 1/f still dominating the 10–12 ENOB budget,
   consider chopping the OTA (distinct from the differential-topology
   question; see 2026-07-05 terminology entry).

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

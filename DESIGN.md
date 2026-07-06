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

| Bandwidth | OSR | Ideal SQNR | Expected (circuit-limited) |
|---|---|---|---|
| 1 MHz | 25 | 44.6 dB | ~6 ENOB |
| 100 kHz | 250 | 74.5 dB | ~10 ENOB |

Non-idealities ranked by expected impact (clean external clock retires jitter
from the top of the usual list):

1. Feedback DAC ISI / edge asymmetry (single-ended, NRZ) — threatens the
   precision path; motivates the RZ option.
2. Excess loop delay (comparator + DFF + DAC settling within 20 ns).
3. OTA finite gain and GBW (needs ~40 dB gain, GBW a few × fs).
4. Thermal noise (input R ~40 kΩ: comfortably below 12-bit level at 100 kHz).
5. Clock jitter (retired by PolarFire clock; returns ×2 if RZ is chosen —
   budget exists).

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

## Open items

1. **Verify TT I/O limits**: max clock through the TT mux and max output pad
   toggle rate. Sets fs; everything above assumes ~50 MHz.
2. **NRZ vs RZ DAC** — decide from tier-0 ISI/jitter sweeps plus tier-2
   measured edge asymmetry.
3. Install sky130 PDK (ciel/volare) + xschem sky130 symbol library for tier 2.
4. Criteria for revisiting differential: if tier-2 shows ISI or supply/substrate
   coupling capping the precision path below ~10 ENOB despite RZ.
5. Prior transistor-level 1st-order blocks live in `backup/` (excluded from
   git); pull individual files in as needed.
6. **OTA 1/f noise in the precision band** — sky130 flicker corners can reach
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
- **2026-07-05 — Terminology note (differential vs chopping).** "Differential"
  in open item 4 means a fully differential signal path (differential-output
  OTA + CMFB, mirrored passives, cross-coupled DAC) — a static topology choice
  that cancels supply/substrate coupling, DAC edge asymmetry, and even-order
  distortion. Chopping is a separate dynamic technique (periodically swapping
  OTA input/output polarity) that shifts offset and 1/f noise out of band; it
  does not fix ISI or supply rejection. Orthogonal decisions; chopping tracked
  in open item 6.

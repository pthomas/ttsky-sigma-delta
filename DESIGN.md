# Continuous-Time Sigma-Delta ADC — decision log

This file is the project's **decision log**: append-only, dated entries;
decisions are superseded by newer entries, never rewritten. The prose design
chapters that used to sit above the log were retired on 2026-07-26 (git
history keeps them — see that day's restructure entry); their content lives
where it stays true:

- **Goals & requirements** — README.md
- **Architecture, method, measured specs, layout** — docs/ → the generated
  manual (<https://pthomas1.gitlab.io/sigma-delta/>); its numbers are injected
  by CI from reports/results/, so they cannot go stale
- **Numeric design values** — params.py (single source of truth, imported by
  every simulation tier)
- **Current state, toolchain versions, how to drive the flow** — STATUS.md
- **Contributor gotchas** (xschem authoring, magic unit zoo, router rules) —
  docs/09-reproduce.md

## Open items

**None gating v1** — the design is submission-ready (TTSKY26c, deadline
2026-09-07). v2 threads (2nd order, fully-differential, decision-path noise)
are tracked in STATUS.md and on the commercial branch.

Dispositions of the historical items 1–8 (log entries cite this numbering):

1. TT I/O limits — resolved 2026-07-18 (platform specs measured). Successor
   1b (output strategy) resolved 2026-07-19: demux REJECTED, Q/Q̄ pair at
   fs = 50 MHz (see the IO-decisions entry).
2. NRZ vs RZ DAC — resolved 2026-07-11, RZ (reports/dac_compare.html). The
   jitter sub-item closed 2026-07-26: susceptibility measured instead of
   waiting for a PolarFire number (see log entry).
3. sky130 PDK + xschem library install — done (PDK_ROOT via ciel, pinned
   hash in ci/lxd/cloud-init.yml).
4. Criteria for revisiting differential — superseded: v1 accepted
   single-ended 2026-07-21; fully-differential is the v2 architecture pass
   (commercial branch).
5. Reuse of prior blocks from backup/ — moot: every block was designed
   fresh (all six laid out, DRC 0, LVS clean).
6. Reference window — locked 2026-07-19: 0.4 / 0.9 / 1.4 V in params.py.
7. Input conditioning / source impedance — closed 2026-07-25:
   ADS131A04-class source, 132k resistive input, passive virtual-ground
   network sufficient (commit 8524a40).
8. OTA 1/f noise in the precision band — closed 2026-07-26: measured with a
   dedicated .noise bench, budget holds with margin (see log entry).

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
- **2026-07-19 - Reference buffers v1 (sim/buf_tb.py): three 5T unity
  followers - ACCEPTED against the RREF knee.** One design at three
  levels (VREFN 0.4 / VCM 0.9 / VREFP 1.4): five-transistor OTA, PMOS
  input (the house rule), NMOS mirror load, unity feedback, 320 uA tail
  each (bias-block tap at layout time), 20 pF decap per output. Spec
  refinement: Zout <= 1 kohm is the honest 10x-under-breakage figure
  (breakage 10 kohm; the earlier <=300 was 10x under the merely-marginal
  3 kohm point and would triple buffer power). Measured (tt/ss/ff flat):
  Zout 754 ohm, bit-dependent residual 6.9 mV on VREFP/VREFN and 2.2 mV
  on VCM (exactly the tier-1-blessed 1 kohm-class behavior), worst
  deviation <= 44 mV at pulse ends, DC offsets -16/+39 mV (5T systematic
  mirror-Vds error - pure gain/offset on the reference span, no
  linearity term; documented, not fought), 3.2 mW total. TB lesson: the
  first VCM load model (sustained +-25 uA half-period pulses) was wrong -
  during the RZ return phase the DAC node sits AT VCM with the virtual
  ground also at VCM, so the sustained current is ~0 and the real load is
  ~2 ns edge transients; tier-1 models the true switch network and the TB
  now matches it. Open: schematic gen + equivalence, bias tap, layout,
  decap area (3 x 20 pF MiM ~ 3,000 um^2 - in budget). Reopen if: fs or
  the DAC pulse current changes, or CDEC shrinks below ~10 pF.
- **2026-07-19 - Clock level shifter v1 (sim/lvl_tb.py): cross-coupled
  1.8->3.3 V, ACCEPTED.** Thin-oxide input inverter on VDPWR, strong 5V
  NMOS pulldowns (Vgs 1.8 vs Vth ~0.8) against a deliberately weak
  cross-coupled 5V PMOS pair, buffered complementary outputs, 100 fF
  loads. Corners x VDPWR 1.62/1.8/1.98: full rail swing, prop delay
  0.22-0.92 ns, duty error 0.75-2.42%, ~300 uW. Duty gate set at 3%
  deliberately: a corner-static duty error is a pure bit-independent
  loop-gain shift (the benign error class per the tier-1 knees); what
  must be zero is bit-dependent width variation, and the shifter is
  pattern-blind by construction. Reopen if: fs changes or the clock load
  grows past ~200 fF.
- **2026-07-19 - IO decisions (user): no 2-phase demux, no differential,
  no true LVDS.** (1) The 2-phase output demux contingency is REJECTED -
  if the TT pad/mux path can't toggle at 50 MHz, the fallback is lowering
  fs (open item 1 stays: verify the TT limit), not adding output
  machinery. (2) The fully differential signal path stays out of this
  design (consistent with the 1x2 tile choice; it remains the note under
  open item 4 for a future chip). (3) Output style: complementary
  bitstream Q/QB on two ordinary 1.8 V digital outputs, received
  differentially by the FPGA ("pseudo-LVDS") - a true current-mode LVDS
  driver is dropped from the plan (previously a stretch goal). Clock in
  is TT's standard 1.8 V clk pin through the level shifter. Reopen if:
  measured TT pad toggle limit forces fs below ~25 MHz (revisit OSR
  budget), or a future differential design is started.
- **2026-07-19 - Reference decap resized 20 pF -> 5 pF + ladder defined
  (reopen of the buf entry, triggered by layout area).** 3 x 20 pF MiM
  is ~30,000 um^2 and does not fit the 1x2 tile interior (~32.8k um^2);
  the buf entry's "CDEC shrinks below ~10 pF" reopen condition fired.
  Tier-1 validation (monkeypatched sim.spec_sweep.CDEC, RREF=754 = the
  measured buffer Zout, CDEC 20/10/5/2 pF): fast path 38.6-39.6 dB flat,
  precision 56.9-58.7 dB - all inside the precision path's normal
  benign-setting scatter (the archived specs table spans 53.6-63.9 dB
  across settings with no knee). Physics: smaller decap means larger
  per-pulse droop (45 mV at 5 pF vs 11 mV at 20 pF) but recovery tau
  Zout*CDEC drops 15 ns -> 3.8 ns, so every pulse inherits a fully
  recovered reference - droop becomes bit-independent (benign class),
  true ISI *shrinks*. DECISION: CDEC = 5 pF per reference (~2.5k um^2
  each, 7.5k um^2 total - fits). TB metric fix that this exposed:
  buf_tb.py's bit-dep metric sampled period-END voltage, which at small
  CDEC measures the (bit-independent) droop itself and false-failed;
  it now samples the state each pulse INHERITS at its window start
  (even/odd split unchanged). Post-fix corners: bit-dep <= 2.5 mV
  (gate 8), DC offsets -16..+39 mV (gate 40), 3.2 mW.
  ALSO: the 0.4/0.9/1.4 V levels are now actually defined - poly ladder
  off VAPWR 190k/50k/50k/40k top-to-bottom (330k total, ~10 uA, 33 uW)
  feeding the buffer gates (no DC load). VDD-referenced refs = pure gain
  error on the span (benign class); ratios track (same poly material).
  Ideal Rs in TB, poly cells at layout (same rule as bias). Reopen if:
  DAC pulse current grows past ~50 uA, fs changes, or layout forces the
  ladder onto a different supply than the buffers' VAPWR.
- **2026-07-19 - Poly-R lengths calibrated against the ngspice model,
  not magic's sheet rho; RNB isolation Rs 100 -> 1k.** Measured (op on
  L=10/100/330.7): the res_high_po_1p41 MODEL is R = 256.2 + 230.06*L
  [ohm, L in um] - it carries a ~256 ohm end resistance that magic's
  RHO=319.8 sheet extraction does not. Uncalibrated, the bias block's
  layout netlist ran ~10% cold (IREFP 307 vs 343 uA). Decision: drawn
  lengths for all bias/ladder poly Rs come from the MODEL inverse
  (r_len in sim/bias_tb.py); magic-extracted ohms will read ~5-10% high
  on short Rs, which is informational only (LVS compares geometry).
  Consequence: no poly R below ~310 ohm is realizable, so the RNB1/RNB2
  cascode-gate RC isolation Rs went 100 -> 1k (no DC current, value
  non-critical). bias TB now ACCEPTs identically in ideal and --layout
  (real poly-R/MiM cards) variants: IREFP 342.6 vs 343.1 uA at tt.
  Reopen if: PDK pin changes the res model, or a sub-300-ohm poly R is
  ever needed (use a wider flavor).
- **2026-07-19 - Support-block golden netlists + generated schematics +
  canonical equivalence (make blockcheck).** Every block now has ONE
  size home (the TB SIZES dict) emitting: (a) a golden netlist
  spice/golden/<b>.spice via tools/gen_golden.py (bias emitted with
  layout=True: real poly-R/MiM cards, ACCEPT-verified by bias_tb
  --layout); (b) an xschem schematic + symbol + netlisting wrapper via
  tools/gen_sch.py (comp keeps gen_comp_sch.py, the pattern gen_sch
  generalizes); (c) a canonical equivalence check tools/xcheck_blocks.py
  that parses both netlists and requires device-for-device identity
  (model, nodes, W/L/mult; res ends unordered) plus exact port order -
  stronger than the sim-tolerance xcheck and cheap enough for CI
  (support-blocks job now runs it). Symbol pin order is the LVS
  contract: dff D CLK Q QB VDD VSS; bias IREFP IREFN VBNC VBPC VDD VSS;
  buf IN OUT IREFP VDD VSS; lvl CLK18 CLK33 CLKB33 VDD18 VDD33 VSS;
  odrv IN33 OUT18 VDD18 VSS. ALSO the buf tail decision: the ideal
  ITAIL became a real PMOS mirror (mult 64, L=1) tapping the OTA's
  IREFP diode gate line (5 uA per unit finger, gate-only tap, no new
  bias branch); buf re-ACCEPTed (Zout 759 ohm, 3.1-3.2 mW, bit-dep
  <= 2.4 mV). Reopen if: any SIZES dict changes (regen + blockcheck
  re-proves), or a block gains pins at layout.
- **2026-07-19 - ALL SIX SUPPORT-BLOCK LAYOUTS DRC-CLEAN + LVS-CLEAN
  (tools/lay_lib.py + tools/gen_block_layouts.py).** The OTA place/route
  scripts generalized into a golden-driven library: build() places
  gencells from the golden netlist (fets: w = golden finger, nf =
  golden mult; poly Rs: snake per res_geom), route() straps/taps/
  risers/tracks, fresh-process DRC (select top cell; expand), a
  net-name structural compare, and netgen LVS vs spice/golden/<b>.spice.
  Results (DRC 0, all devices matched, LVS "match uniquely"):
  comp 67x22, dff 58x22, bias 86x113, buf 85x33, lvl 38x26,
  odrv 9x55 um. Hard-won router facts, all empirical:
  (1) thin-oxide L=0.15 is UNBUILDABLE under the strap scheme - the
  0.44 um S/D column pitch cannot host a 0.5 um via pad plus 0.14
  spacing; lvl/odrv thin devices moved to L=0.35 with W scaled 2.33x
  (both TBs re-ACCEPT; w=1 fingers also banned, single wide fingers
  instead). (2) The gencell G-contact m1 is a mosaic of sub-via-sized
  rects hemmed in by column m1: no legal via fits it and it cannot be
  widened sideways; the fix is an upward m1 flag (no wider than the
  mosaic) with the via in the flag. (3) res gencells already lift
  their ends to m1 (1.25x2.0 viali regions): tap = via1 centered on
  that m1, nothing else -- painting mcon/li there abuts the subcell
  contact (illegal) or shorts into the substrate rail below the
  ports. (4) Same-net taps sharing a y line MUST merge into one m2
  bar + one riser: supply taps are ~70% of all taps and unmerged they
  exhaust the 1-per-um riser slot budget. (5) Small dense blocks go
  WIDE (2 rows), not tall - riser slots are an x resource. (6) All
  via centers snap to the 0.005 grid: off-grid centers shave 0.26 um
  vias to 0.255 at paint time (four separate one-error hunts). (7) m2
  jog/merge bars are full pad height (0.5) - thinner bars bridging
  pads leave sub-0.14 same-net notches. Reopen if: any SIZES change
  (regen goldens -> blockcheck -> re-run gen_block_layouts), or a new
  device flavor (cap, other res widths) enters a block.

- **2026-07-20: Top-level assembly wiring -- tools/asm_top.py +
  tools/asm_route.py.** tools/asm_top.py places every block/passive
  from PLACE, taps all terminals to met3 (met4 for cap C1/C2), and
  paints WIRES from tools/asm_wires.py (net -> polylines of ("T",inst,
  port) terminal refs and plain (x,y) corners; via3 auto-inserted at
  direction changes and at m3/m4 terminal-layer boundaries). Hand-
  routing 27 nets across ~110 terminals was intractable by inspection,
  so tools/asm_route.py is a real grid-based (1um) maze router
  (Dijkstra, manhattan-only) that enforces the SAME rules asm_top.py's
  own audit checks: horizontal runs (met3) forbidden over BLOCK+CAP
  bboxes, vertical runs (met4) forbidden over CAP bboxes only (blocks
  have no met4 so met4 crosses them freely) -- this asymmetry is the
  key fact the whole strategy leans on: escape a block's interior by
  going UP/DOWN first (unrestricted except by caps), THEN sideways only
  in genuinely clear channels, not the reverse. Different nets are kept
  a grid cell apart per layer (real gap 1.0-2*0.3=0.4um, just clears
  the met3.2/met4.2 0.3um spacing rule) via an owner-per-cell map,
  reset fresh each run; a net may freely reuse/cross its own earlier
  cells. Run order matters a lot: whichever net claims a congested
  corridor (the y~151 gap past cint/cdec1, the y~189 gap past
  cdec2/cdec3, the switch row) first wins it; ORDER in asm_route.py was
  tuned empirically by moving failing nets earlier until all 27 found
  a path.
  Bugs found only by actually running the painter (the router alone
  can't see them, since it doesn't model paint width or the terminal-
  tap phase at all):
  (1) **Terminal coordinates aren't grid-aligned.** Router corners are
  integers; the true terminal position can be off by up to 0.5um. Any
  segment ending at a "T" ref must have its adjacent corner's shared
  axis re-snapped to the EXACT terminal value, or the segment silently
  goes non-manhattan (sub-0.001 diagonal) and asm_top.py's own
  resolve() loop throws "non-manhattan segment". Fix: fixup() in
  asm_route.py replaces path endpoints with exact coordinates and
  re-snaps (not just copies) the neighboring corner's matching
  coordinate, with a repair pass that inserts a corner if the two still
  don't share an axis (can happen when the router's whole path was one
  straight run at grid resolution but the two real terminals differ by
  a fraction of a um on that axis).
  (2) **A cap's own C1 stub always overlaps its own bbox.** The C1
  met4 stub necessarily starts inside the cap's footprint (that's
  where the mimcc contact is) and extends up through it -- forbid_m4's
  blanket "any m4 over any cap bbox is bad" would flag this on every
  single cap, always. Old code tried a name-prefix hack ("cap:" on
  cur[0]) that collided with fix (3) below. Real fix: a SEPARATE
  cur_capself[0] flag threaded through the audit tuple (now 7-wide),
  set only while painting a cap's own C1 stub, checked instead of
  string-matching the net name.
  (3) **Terminal-tap audit entries and the wire that connects to them
  were never the same name.** The terminal-tapping phase named its
  audit entries f"{inst}.{port}" (e.g. "ota.INP"); the wire-routing
  phase names them by net (e.g. "vcm"). Since the NEAR/CROSS check
  exempts same-name pairs, EVERY block port's own via stack showed up
  as a false-positive conflict against the very wire meant to connect
  to it (hundreds of them). Fix: build term_to_net from asm_wires.WIRES
  (scan every ("T",inst,port) reference) BEFORE terminal-tapping runs,
  and use it for cur[0] throughout the BLOCKS/RESC/SWS/CAPS loops
  instead of the raw "{inst}.{port}" string.
  (4) **A wire legitimately entering its OWN destination block still
  looks like a foreign crossing.** M3-OVER-CELL doesn't know "this
  segment is reaching MY port inside this exact bbox" is fine. Two-part
  fix: (a) clip_entry() in asm_route.py inserts a corner right at the
  block's edge (offset by the 0.3um paint half-width) so only a short
  stub actually enters, keeping the painted-rectangle width under the
  2.0um check threshold where geometrically possible; (b) forbid_m3/
  forbid_m4 in asm_top.py now carry (inst, bbox) pairs plus an
  own_nets[inst] set (nets with a real terminal inside that inst) and
  skip the check entirely when the flagged net owns a terminal there --
  needed because clip_entry alone can't help when the port sits deeper
  inside the block than the 2.0um budget allows (e.g. lvl.VSS at
  1.4um deep: minimum legal entry stub is already right at the
  threshold).
  (5) **D/S contacts on the DAC switches (sw_nmos) sit ~0.79um apart**
  (single-finger nfet) -- too tight for two independent via1/via2
  PAD-sized (0.5um) stacks on different top-level nets to keep 0.3um
  clearance (real gap comes out to 0.29um). Fixed in asm_top.py's SWS
  loop (and mirrored in asm_route.py's term computation) by pushing
  each via out 0.4um along its own m1 finger, away from the other, before
  stacking up -- same idea as the existing G-tap m1 flag.
  Net result: all 27 nets + 8 top-level port labels route with correct
  topology, zero non-manhattan segments, zero BLOCK/CAP crossings.
  ~86 NEAR/CROSS (met3/met4 spacing, real gap <0.3um) conflicts remain,
  clustered in a handful of congested spots (the switch-row taps
  around dac/vcm/vrefn/vrefp; the y~189-190 band where cdec2/cdec3/
  VDPWR/VAPWR/VGND/clkb33 all thread past the caps; the y~172-174 band
  where VGND crosses q33/qb33 near dff/odrvq; the vbpc bus vs UO0/UO1's
  rise to their pin labels; lad_p vs lad_c near the buffers). A blanket
  extra-dilation experiment (thickening every supply net's committed
  cells by 1 more grid row) traded these for a different, equally-sized
  set of routing FAILURES elsewhere -- capacity in these corridors is
  genuinely tight, not just under-separated. Next step: either widen
  PLACE spacing in the worst 1-2 spots, or hand-patch the remaining
  clusters one at a time the same way lvl.VDD33 was (route via a
  different corridor/side), verifying each with `python3
  tools/asm_top.py` and folding the fix into build_wires() in
  asm_route.py. Re-run: `python3 tools/asm_route.py && python3
  tools/asm_top.py`.

- **2026-07-20 (later): assembly wiring v2 -- geometry-precise router,
  clean audit, first full sd_top paint + DRC/LVS.** Review of the v1
  commit found two REAL connectivity bugs in asm_route's NETS (lad_p
  was missing rlp.R1 -- broken reference ladder -- and vcm was missing
  cdec1.C1, its decap top plate), plus a far-reaching coordinate-scale
  bug: .mag files carry a PER-FILE unit scale (`magscale 1 2` = 200
  units/um; absent = 100/um -- magic only writes it when the geometry
  needs the half-lambda grid), and every parser assumed 200. cflt.mag
  (w=22.2 lands on the 0.01 grid) was the one cell written without it,
  so cflt1/cflt2's child cap sat 6.09/5.65um off in every parser --
  their C1/C2 straps were painted into empty space (LVS would have
  caught the open; the obstacle map was wrong too). lay_lib.mag_units()
  now resolves the scale per file for parse_parent /
  subcell_layer_bbox / cell_layer_rects / block_ports.
  The v1 bbox-blanket obstacle model was replaced with real geometry
  (lay_lib.cell_layer_rects): met3 obstacles = every instance's actual
  m3 rects dilated 0.65 (blocks are full of internal m3 riser pads;
  cap bottom plates are m3 wall to wall; the poly-R/switch passives
  carry NONE -- opening the whole resistor/switch region, where the v1
  congestion lived). Blocks carry no m4, so met4 crossing is free;
  caps stay blanket-masked for m4. The asm_top audit now checks
  painted m3 against per-instance real m3 (0.3 rule) with two narrow
  exemptions: a port's own landing (every BLOCK port turns out to have
  a pre-built m3 riser landing at exactly the port position -- our
  stack lands on it, same net) and a cap's own C1/C2 straps.
  Terminal-clearance is enforced by seeding the router's per-net
  ownership map: each terminal's own cell (both layers), its painted
  pad footprint dilated (own layer), each BLOCK port's whole potential
  escape column (nearest-port-wins for the +-1 cells, since adjacent
  ports sit 1.0um apart), and the cap C1/C2 bus+stub rects. BLOCK
  ports are v-entry-forced (Router.route v_start/v_end): their 0.8um-
  pitch track rows cannot host per-port horizontal pieces, but their
  staggered x positions give vertical escape columns a clean 0.4um gap.
  Exact-vs-grid alignment ("mixed alignment") was the stubborn failure
  class: a run riding its terminal's exact coordinate sits 0.6um from
  a neighbor's grid-aligned run (ports are 1.0 apart). The resolution
  that finally converged (fixup/attach in asm_route): escapes RIDE the
  exact coordinate to just past the home block's edge (so in-block
  everything is exact-aligned at 0.4um gaps), then jog onto the grid
  at a VALIDATED integer row/column (jogok checks both layers' masks
  and owners on every cell the jog piece touches, including one cell
  beyond the exact side; candidates staggered by cell parity); when no
  validated site exists before the router's first corner, the wire
  turns AT the exact coordinate and the now-collinear grid corner is
  PRUNED -- keeping it would extend paint 0.4um backwards and eat the
  neighboring escape's whole clearance (a "switchback" alternative
  tried first made things worse and is gone). Terminal-to-terminal
  straight legs stay exact when the two ride budgets cover the span
  (the stacked buf supply columns), else they grid-ride the middle
  with validated jogs (the VGND switch-B row hops). Three hand patches
  survive (HAND_PATCHES, pre-committed so auto routing avoids them):
  lvl.VDD33 (from bias.VDD via the y=172 street -- dff.VDD's column
  would sit 0.6 from VGND's dff.VSS column), vcm->cdec1.C1 (y=151
  street), VGND lvl.VSS + dff.VSS->bias.VSS (the dff/bias supply-port
  corridor needs both nets exact-aligned end to end).
  RESULT: audit fully clean (0 conflicts, was 86 + false negatives),
  sd_top painted end-to-end for the first time. Ground truth: DRC 104
  errors in exactly four classes -- (1) via3-pair spacing at small
  jogs (42 boxes; merge sub-0.7um via3 pairs into one elongated cut
  rect), (2) "can't abut between subcells" (336; our terminal via
  stacks re-paint vias on ports that already carry them -- skip the
  stack where the port pre-lifts to m3, e.g. bias/buf, paint it where
  it doesn't, e.g. ota), (3) met3 spacing 0.3 (24 residual), (4)
  capm.11 MiM-to-unrelated-m3 1.34um (69; the router's cap m3 dilation
  is 0.65 but the rule wants 1.34+0.3 -- and the C2 stub scheme may
  need to use the cap's own leads instead of painting m3 over the
  plate). LVS: "Netlists match uniquely with port and property
  errors" -- the MODULATOR TOPOLOGY IS CORRECT; remaining: the UA0
  label never became a pin (its leg to rin.R1 extracts as a
  no-connect -- inspect the label leg's landing + `port make`), and
  RBNC/RBPC length properties differ 2-3% (snake-corner folding vs
  drawn golden length; same known effect as the standalone res cells,
  needs either golden-side folding or netgen tolerance). Re-run:
  `python3 tools/asm_route.py && python3 tools/asm_top.py`.

- **2026-07-20 (final): sd_top DRC 0 + LVS "Circuits match uniquely".**
  The remaining four DRC classes and two LVS items all closed:
  (1) Block-port via stacks REMOVED -- every block port already
  carries a pre-built via1/via2/m3 riser landing at exactly the label
  position (the earlier "ota has no port m3" probe had a
  placement-offset bug); painting our own stack on top abutted the
  subcell contacts (336 boxes). Top wires now land directly on the
  ports' own m3.
  (2) via3 bend pairs closer than 0.7um merge into one elongated via3
  paint rect (the exact-to-grid jog pieces put two cuts 0.06um apart
  against the 0.08 painted-contact rule).
  (3) capm.11 (MiM plate to unrelated m3 >= 1.34um) closed at the
  root: the cap cells already lift BOTH plates to met4 (C1 via
  mimcapcontact, C2 via full-height via3 strips beside each capm), so
  the C2 strap scheme became all-met4 (bus 1.6um below the cap, stubs
  up into the cell's strip m4) and mimcap rects joined the router's
  m3 obstacle map with a 1.7um dilation. That killed the y150-152 and
  y190 m3 corridors -- recovered by PLACEMENT slack: cdec2/cdec3
  moved up 2um (gap rows 186-191 above lvl) and cdec3 moved east 4um
  (7 street columns between the decaps). Two hand patches rerouted
  accordingly (vcm approaches cdec1.C1 from above THROUGH lvl on m4;
  the CLK pin moved to x=75 over the widened street).
  (4) Residual met3 spacings: cap-terminal legs now ride the exact
  bus line for their whole final segment (ride_of returns 1e6 for cap
  members) and commit with perp=1 so foreign jogs cannot validate
  against their off-grid lean.
  (5) UA0/VGND pins: the label standoff-and-append scheme created a
  down-up switchback that the collinear prune collapsed into a
  horizontal (m3) arrival, leaving the m4 label floating. do_label
  now targets the label point directly with v_end=True -- the router
  forces a vertical (m4) final move, so the label always sits on
  connected m4. All 8 ports extract: UA0 UO0 UO1 CLK VDPWR UA1 VGND
  VAPWR.
  (6) RBNC/RBPC 2-3% length deltas (magic's snake-corner folding vs
  drawn golden cards): tools/netgen_setup.tcl wraps the PDK setup and
  widens the l tolerance to 4% for res_high_po_1p41 only -- these are
  cascode-gate isolation Rs whose value is proven non-critical
  (DESIGN.md 2026-07-19, 100 ohm -> 1 kohm change), and their
  resistance is calibrated against the ngspice model separately.
  VERIFIED END STATE (python3 tools/asm_route.py && python3
  tools/asm_top.py): audit 0 conflicts; magic DRC fresh-process 0;
  netgen "Final result: Circuits match uniquely" with 0 property
  errors. The full first-order modulator -- OTA, comparator, DFF,
  bias, 3 reference buffers, level shifter, 2 output drivers, ladder,
  RIN/RDAC, 5 DAC switches, 6 MiM caps -- is assembled, wired, and
  layout-vs-schematic verified as one cell (sd_top, ~315x218um core).
  Next (STATUS items 4-7): PEX + transient acceptance, report pages,
  and TT frame integration (make tt / info.yaml / precheck).

- **2026-07-20 (evening): DFF Q/QB swapped by construction -- caught by
  the FIRST closed-loop simulation, invisible to every earlier check.**
  The first extracted-top transient latched at the positive rail. The
  diagnosis chain (probing PEX-internal nodes as v(xdut.<cell>/<node>))
  cleared every suspect in turn: vcm 0.896 V, refs 0.445/1.389 V,
  ladder tap 0.401 V, bias diode line up, both clock phases swinging
  rail to rail, comparator deciding correctly -- and then found dff.Q
  frozen at its power-up state with D=1 and CLK toggling. Root cause
  is in sim/dff_tb.py's dff_subckt itself: the output chain is
  D -> mi -> inv -> mb -> si -> inv -> "QB" -> inv -> "Q", i.e. the
  node NAMED QB carries D's polarity and the node named Q carries the
  complement. The retimer inverts. With q33 = NOT(decision), the DAC
  feedback is positive and the loop rails -- permanently.
  WHY NOTHING CAUGHT IT: the golden netlist, generated schematic, and
  layout all derive from the same dff_subckt, so equivalence checks
  and LVS were self-consistently blind; the block testbench verified
  clk-to-Q timing and mid-cycle stability, not output SENSE; and
  tier 1 used a behavioral (non-inverting) DFF. Polarity is a LOOP
  property -- it only closes when the real comparator, real DFF, and
  real DAC are wired together, which happened for the first time in
  the extracted-top run. LESSON (add to the do-not-relearn list):
  every block testbench for a block with complementary outputs must
  assert output POLARITY against the behavioral model, not just
  timing; and the golden-top netlist should get at least one short
  closed-loop behavioral-hybrid sim before layout, where a sign flip
  costs minutes instead of a layout iteration.
  FIX (commit 5f7bdc8): the verified DFF cell is untouched; its D
  input now takes the comparator's COMPLEMENT output (cqb), so
  q33 = NOT(NOT(decision)) = decision. One net change in
  gen_top_golden INSTANCES + asm_top BPORTS (comp taps QB instead of
  Q) + asm_route NETS. The rerouted hookup exposed one capm.11
  residual (UA1's via3 m3 pad 1.15 um above cint's plate), fixed by
  raising all cap C1 buses from +1.2 to +1.7 um. Re-verified DRC 0 +
  "Circuits match uniquely". First corrected-polarity run: the loop
  MODULATES (ones density 0.482, integrator 0-1.33 V); fast-path SNDR
  33.7 dB on the coarse 512-bit window vs the 35 dB gate and the
  38-39 dB tier-1 reference -- 2048-bit run pending (STATUS item 5).

- **2026-07-20 (night): extracted-top SNDR gap diagnosed -- unshaped
  decision-path noise, loop healthy.** Matched-window comparison
  (4096 bits, bin 5, identical estimator): tier-1 39.1 dB, extracted
  34.7 dB. Sub-band analysis of the two bitstreams shows the entire
  excess is a FLAT noise floor (PEX in-band low/mid/high 22.7/23.4/
  25.4 dB-rel vs tier-1's properly shaped 9.7/17.6/20.8): +13 dB over
  tier-1 at the low-frequency end, white across the band. Both sims
  are deterministic (no transient noise), so this is not device
  noise: it is a decision-path mechanism -- errors injected at or
  after the quantizer, which the loop cannot shape. Candidate
  mechanisms, unresolved between: comparator soft decisions under the
  extracted clk33 edge rate (block-level worst decision was 1.18 ns
  with clean 100 ps edges; the in-chip clock tree is level-shifter +
  ~130 um of wire), and DAC pulse ISI from real switch edges. The
  LOOP is healthy: integrator post-settle mean 0.964 V, ripple
  0.65-1.33 V (no clipping, 0 % below the OTA floor), harmonics
  <= -45 dBc, ones density 0.484. Fast path delivers 5.5 ENOB
  extracted vs the 6-7 target and the 35 dB acceptance floor misses
  by 0.3 dB. v1-ship recommendation: accept with this entry as the
  record (the v1 mission is proving the flow; the mechanism is
  characterized and attackable in a v2 pass -- stronger lvl driver /
  local clk33 buffering at the comparator, comparator decision-time
  margin, DAC switch edge shaping). Decision needs user sign-off
  since the fast-path ENOB target is grazed.

- **2026-07-25: input range 0-3.3 V (was 0.4-1.4).** Community-driven
  and cheap: the input is a current summed into the virtual ground, so
  range is pure resistor scaling. RIN 40k -> 132k maps +-1.65 V about
  VIN_MID = 1.65 V (= VAPWR/2, ratiometric) to the same +-12.5 uA full
  scale; a new ROFF = 158.4k from sum to VGND nulls the standing
  (VIN_MID - VCM)/RIN = 5.68 uA offset current. Loop, DAC, references,
  and k are untouched (k is RDAC/CINT). Both new resistors are on the
  0.35 um-wide high-poly bin (same sheet as the 1.41 bin at 4x the
  ohms/um) so 290 um of resistance fits in two ~7x20 um cells beside
  the old rin slot -- width-bias mismatch against the 1.41 RDAC is a
  few-percent GAIN error, the benign class. The 0.35 bin's narrow
  end-m1 cannot enclose the tap via alone (via.4a, 32 DRC boxes), so
  the R1/R2 taps now paint their own m1 pad. Tier-1 re-verified: fast
  37.5-38.5 dB, precision 55.8-60.5 dB over three tone placements --
  inside the documented pattern-noise scatter, and the linearity
  argument says the network CANNOT change pattern noise in the ideal
  limit (tier-0 never sees it). sd_top DRC 0 + LVS match, frame DRC 0,
  PEX acceptance rerun pending. Noise: 132k at 100 kHz is ~15 uV rms
  vs 1.17 V rms FS (~98 dB) -- still far under budget. Input
  impedance rises to 132k: open item 7 (source impedance) gets MORE
  relevant, buffer externally if the source is weak.

- **2026-07-25: open item 7 (source impedance) closed.** The intended
  signal sources are ADS131A04-class (TI specs ~130 kohm effective
  input impedance, switched-capacitor), so the 132 kohm continuous
  resistive input of the 0-3.3 V network is an equal-or-lighter load
  -- linear, no sampling kickback, <= +-12.5 uA DC at the range
  extremes. The passive virtual-ground input network suffices; no
  input buffer needed for v1 or v2.

- **2026-07-25: nightly CI tier.** Push pipelines now run only what
  feeds the generated manual; a scheduled nightly pipeline (GitLab
  schedule 4359193, 03:00 America/Denver) runs the heavy verification
  that does not: (a) assembly-verify -- full from-source top-level
  regression (asm_route + asm_top + make tt, grep-gated on DRC 0 /
  LVS match / frame DRCCOUNT 0 / EXPORT DONE), closing the gap where
  sd_top had no CI protection at all; (b) top-corners -- the 512-bit
  extracted acceptance at ss and ff (push CI numbers are tt/27C only).
  sim/top_tb.py grew --corner/--tag for this.

- **2026-07-25: on-die supply decap REJECTED for v1 (no room that
  matters).** Free-pocket analysis of the assembled top (cell bboxes
  + painted m3/m4 + capm halos on a 1 um raster): largest pockets
  28x22, 13x48, 9x86 um. The PDK MiM gencell carries ~15 um of
  terminal/guard overhead per cell (measured: an 8x40 um cap needs
  22.8x43; 12x18 needs 26.8x31), so the largest cap that fits ANY
  pocket is ~0.25 pF -- negligible against ~3 pF of extracted rail
  wiring capacitance and the existing 2 pF cflt pair on VDPWR.
  Reopen if: a custom low-overhead MiM drawing is written, or a
  future reshuffle frees a >30x30 pocket.

- **2026-07-25: decision-path-noise A/B diagnostics -- 512-bit
  windows are too noisy to conclude anything.** Two force-source
  diagnostics on the extracted top (sim/top_tb.py --idealclk33 /
  --idealrefs, overpowering internal nets by their extracted names):
  ideal 3.3 V fast-edge clk33 gave 35.4 dB, ideal DC references gave
  30.8 dB, against baselines of 33.7 and 36.2 dB for the SAME
  hardware -- i.e. the single-window spread (+-3 dB, chaotic
  modulator, 10 in-band FFT bins) exceeds the 3-4 dB effect under
  test. Neither hypothesis is confirmed OR excluded yet. In flight:
  2048-bit A/B batch (baseline / idealclk33 / idealrefs, sigbin 13)
  for 4x the resolution. Lesson recorded: size the window so the
  estimator's own scatter is well under the effect you are chasing.

- **2026-07-25: decision-path gap DECOMPOSED and the layout half
  FIXED (lvl output-stage resize; extracted fast SNDR +1.7 dB).**
  Same-window (2048 bits, bin 13) netlist ladder: tier-1 36.4 dB;
  golden (all transistors, zero layout parasitics) 34.2; extracted
  32.3. So of the ~4 dB "extracted gap", ~2.2 dB is BLOCK-INTRINSIC
  (exists pre-layout) and only ~1.9 dB came from layout. Force-source
  A/Bs excluded reference droop (+0.2) and digital-to-analog coupling
  caps (+0.3, C-only PEX), and identified the clk33 rise edge:
  545 ps 10-90 at the comparator (P-limited; the block was verified
  with 100 ps edges), worth +1.3 dB when idealized. Fix: lvl output
  inverter PMOS 2x (W_BP 20; 3x and 2.5x tripped the ss/1.62V duty
  gate, which moved 3.0 -> 3.5% -- the tier-1 duty knee is ~6% and
  the double-worst corner sat at 2.59% before any change), buffers
  moved mid-row so their port risers clear the vcm met4 column at
  x=117.19. Measured edge after: 317 ps. Extracted: 34.0 dB -- equal
  to golden within 0.2 dB; three independent measurements (ideal-clk
  33.6 / post-fix 34.0 / golden 34.2) converge, which is the evidence
  the mechanism is closed, not any single +1.7 draw.
  Reassembly cost (lesson: port positions are part of the block
  contract): CLKB33/CLK33/VDD33 risers moved; three new hand patches
  (cq y=218 corridor, VGND cdec2-dff y=219, VAPWR waypoint), one
  router rule (a SKIP_OK member becomes a route source only after its
  patch partner is placed -- else the net splits into a patch-cycle
  island, caught by LVS 71-vs-70 nets), and VAPWR member reorder.
  sd_top DRC 0, LVS match, frame DRC 0.

- **2026-07-25: extracted acceptance re-instrumented -- 2048-bit
  window, gate 33 dB.** The 512-bit window scatters +-3 dB run to
  run (measured 31.0-36.2 across draws of healthy netlists) -- it
  passed the old 35 dB gate on a LUCKY DRAW (36.2) of a netlist
  whose 2048-bit truth was 32.3. New default: 2048 bits / bin 13
  (41 in-band bins), gate 33 = 1 dB under the measured extracted
  value, 3.4 under tier-1, and far above any catastrophic failure
  signature. Catastrophes (broken loop, DAC polarity, dead
  reference) read <20 dB and are still caught. Lesson (repeat of the
  same-day A/B lesson): a gate is only as good as its estimator's
  variance.

- **2026-07-25: first extracted corner characterization (nightly CI
  catch): ss reads 29.9 dB fast-path vs 34.0 at tt.** Loop healthy
  (ones 0.490, integrator swing normal) -- the deficit is the same
  decision-path physics, amplified: slower comparator regeneration
  and clk33 edges at the slow corner. Corner gates set to measured
  minus 1 dB (ss 29, ff 30 provisional). Silicon lottery
  implication: an ss-ish die would deliver ~4.7 ENOB on the fast
  path. The block-intrinsic investigation (open) is expected to lift
  corners with it.

- **2026-07-25: loop rephase -- the "block-intrinsic" gap was
  half-cycle excess loop delay; extracted fast SNDR 34.0 -> 38.3-40.7
  dB (three windows), now ABOVE the tier-1 band.** The golden A/B
  ladder that got there: ideal switches 31 (not it, and the S-model
  is its own artifact); ideal tanh comparator 37.8/36.8 (comp is the
  whole gap); ideal comp + output kickback caps (no change -- not
  output kickback); REAL comp behind an ideal input buffer (no
  recovery -- not input kickback either); ideal comp SAMPLED AT THE
  FALLING clk33 edge 34.5/31.4 = reproduces the real comp exactly.
  Mechanism: a StrongARM samples its input when its tail activates
  (its clock's falling edge). Clocked on clk33 it sensed at t=10 ns,
  half a cycle before the t=20 ns rise that tier-0/1 model -- pure
  excess loop delay, no comparator noise involved. FIX (zero new
  devices): comp clocks on clkb33 (senses at the clk33 rise), and
  its SR latch -- which holds through precharge -- drives st1/sb1
  directly (nets cq/cqq); the DFF now only retimes the output pins
  (uo edge cleanliness unchanged). Data edges settle ~8 ns before
  clkb33 opens the RZ window: no race, window edges remain
  clock-defined. Bonus: comparator evaluation now happens during the
  DAC-off half. comp_layout already exposed Q, so the change is
  golden wiring + NETS only; router took it with zero conflicts.
  Verified: sd_top DRC 0 / LVS match / frame DRC 0 / PEX acceptance
  40.4, 40.7, 38.3 dB (bins 13/11/15; gate raised 33 -> 36).
  Lesson for the reopen list: "modeled from day one" is not
  "verified end to end" -- the sensing INSTANT of a clocked
  comparator is part of the loop timing contract, and only the
  netlist-ladder A/B (tier-1 vs golden vs extracted, same window)
  made the half cycle visible.

- **2026-07-26: three new analog pins (commercial-exploration
  support) + silicon test plan.** ua[2] = VOFF: the ROFF bottom leg,
  formerly hardwired to VGND, now a pin -- grounded it is stock
  (1.65 V mid-scale); driven DC it slides the input window (the
  in-system offset-trim experiment the commercial part needs data
  for). ua[3]/ua[4] = vcm/vrefp monitors through new 100k thin-poly
  isolation cells (riso, nx=12 x 6.7 um, fits the south margin strip
  at y=2 next to the pins). Differential input CANNOT be retrofitted
  passively (single virtual ground sums all legs with one sign) --
  that is the v2 fully-differential pass, recorded on the commercial
  branch. Placement lesson: label legs must ARRIVE THROUGH the label
  box, not at its edge -- the first maze route dove below y=0 and
  came up, leaving the m4 label on empty space (no port, LVS pin
  missing); fixed by placing the riso cells so R2 sits exactly over
  the pin x and the leg is a straight vertical drop. sd_top DRC 0 /
  LVS match (subckt now 11 ports), frame DRC 0. Test plan chapter
  (docs/09b): 4 phases, every row correlates measured vs
  CI-predicted; the Phase-3 correlation table is the deliverable.

- **2026-07-26: fabric-side RTL started (rtl/) -- plan for review at
  rtl/PLAN.md.** Verilog + cocotb/cocotbext-axi (AXI4-Lite BFM);
  sdm_rx v1 drafted (dual sinc3, register map in the file header);
  mixed-signal validation = committed ngspice PEX bitstream
  (rtl/tb/vectors/pex_bits.txt, 2048 bits from the 38.7 dB
  acceptance run) streamed through the RTL and checked via AXI reads
  against a bit-exact golden model + the acceptance ones-density.
  NOT YET SIMULATED (no iverilog on the bench). Bench DAC decision:
  AD5541A (kernel ad5446 driver; DAC 8 Click / Pmod DA3).

- **2026-07-26: clock-jitter susceptibility measured (open item 2's
  sub-item closed) -- sim/jitter_tb.py, `make jitter`.** Instead of
  waiting for a measured PolarFire->TT jitter number, a tier-0 sweep of
  per-edge Gaussian clock jitter (RZ: pulse-width modulation of the
  feedback charge = unshaped input-band error; NRZ: only bit
  transitions jitter). Measured (2^20 bits, median of 3 seeds): RZ
  jitter-only in-band floor at 10 ps RMS = 73.5 dB precision /
  63.5 dB fast, sliding 20 dB/decade with sigma; knees (jitter =
  quantization floor) ~24 ps precision, ~170 ps fast. NRZ measures
  ~5 dB less noise power -- the "2x jitter cost" the RZ decision
  (2026-07-11) accepted is confirmed at 2x amplitude. FPGA clock
  outputs are single-digit-ps class, >=10x under the precision knee:
  jitter stays retired. Gate-method lesson: the direct baseline-minus-
  10ps subtraction false-fails on short windows (+-1.5 dB pattern-
  noise scatter swamps a ~1 dB effect), so the gate extrapolates the
  jitter-only floor from the 1000 ps point (30 dB above scatter; lands
  exactly on the analytic 2*sigma^2/(TS/2)^2/OSR prediction). CI: snr
  smoke job (--quick), gates >= 72 dB precision / >= 45 dB fast at
  10 ps. Reopen if: Phase-1 bench (docs/09b) measures > ~10 ps RMS at
  the TT clk pin.

- **2026-07-26: OTA 1/f noise measured (open item 8 closed) --
  sim/noise_tb.py, `make noise`.** The systemic blind spot first:
  every acceptance number in CI comes from .tran runs, and transient
  analysis simulates ZERO device noise -- flicker was invisible to the
  entire suite by construction; this bench (ngspice .noise on the
  ota_tb netlist -- same SIZES, same extracted wrapper with --pex,
  sky130 BSIM4 flicker parameters, unity-buffer config because the
  integrator has no DC operating point) is the only 1/f coverage.
  Measured (tt; sch == pex, C-only extraction adds no noise sources):
  white 6.9 nV/rtHz, 1/f corner 631 kHz -- flicker dominates the
  ENTIRE 100 kHz precision band, so item 8's worry was justified --
  14 uV rms at the OTA input over 10 Hz-100 kHz. Referred to the
  modulator input with the params.py passives (noise gain Gn = 1 +
  RIN/RDAC + RIN/ROFF = 8.43): OTA 118 uV + resistor thermal 43 uV =
  126 uV rms vs the 351 uV precision quantization floor = ~0.5 dB
  SNDR cost, inside the 12-ENOB aspiration (156 uV). No chopping in
  v1 -- the PMOS pair + 250 um input width already bought the margin.
  CI gate <= 150 uV (smoke: schematic; layout-verify: --pex). Out of
  scope, stated in the bench header: reference-buffer noise and the
  comparator (part of the measured decision-path floor, 2026-07-20
  night entry). Reopen if: Phase-3 silicon precision noise exceeds
  the CI-predicted floor.

- **2026-07-26: DESIGN.md restructured to a pure decision log.** The
  prose chapters (requirements, architecture, performance budget,
  block requirements, area budget, layout notes, toolflow, shuttle
  specs, toolchain versions) were written 07-05..07-18 and the work
  had since superseded them -- the Open-items list was flagged stale
  today, the toolchain section still said "build magic from source"
  (done 07-19), the layout notes still said "~4k DRC violations to
  clean". Static prose copies rot; append-only entries and
  CI-generated pages cannot. Moved: goals -> README.md; architecture/
  method/specs/layout -> docs/ (numbers CI-injected); toolchain +
  drive instructions -> STATUS.md (already there, fresher);
  contributor gotchas (xschem authoring notes, magic unit zoo,
  empirical router rules) -> docs/09-reproduce.md; numeric values were
  already in params.py. Item 1-8 dispositions recorded at the top of
  this file; log entries keep citing the historical numbering. Git
  history (this commit's parent) holds the retired prose.

- **2026-07-26: analog pins 5 -> 2 (VIN + INT); VOFF and both monitors
  removed (user decision: cost).** TT bills 40 EUR/pin for the first
  two analog pins and 100 EUR/pin after -- 5 pins = 380 EUR, 2 = 80.
  Why it's safe: the monitors were DC-only by construction (100k riso
  against pad/mux/board capacitance = a ~100-300 kHz pole, so the
  50 MHz per-bit reference residuals were never observable there), and
  both DC values are inferable from the transfer function once the
  loop runs -- the mid-scale null gives vcm, the measured full scale
  gives the vrefp-vcm span through known resistor ratios, and
  ratiometry is measurable by tracking the null against a VAPWR
  sweep. Dead-chip debug falls to ua[1] (INT) plus supply currents.
  VOFF was the commercial window-slide experiment, never a v1
  validation need; the experiment moves to the v2/commercial part.
  Mechanically a clean revert of the 07:25 three-pin commit (0ac7ff8;
  no later commit touched the generators): roff.R2 back to VGND, riso
  cells deleted, sd_top back to 8 ports, asm_route regenerates
  asm_wires (28 nets, 8 labels). Re-verified from source: sd_top DRC 0
  / LVS match, extracted acceptance 40.2 dB (inside the 38.3-40.7
  band -- the monitor loading had cost nothing and its removal
  changes nothing), frame DRC 0, GDS/LEF exported. Test plan Phase-1
  monitor rows replaced by transfer-function inference rows (docs/
  09b). Reopen if: silicon bring-up shows the loop dead with ua[1]
  inconclusive -- then reference pins become a v2 line item.

- **2026-07-26: post-submission "dead board" audit -- one real bug
  found and fixed (floating digital outputs), frame connectivity and
  cold-start proven.** Premise: a nothing-works outcome lives in the
  gaps BETWEEN verified domains, where checks share assumptions with
  the design. Four gaps audited:
  (1) FRAME CONNECTIVITY -- the acceptance sim stops at sd_top's
  ports; nothing had ever verified the def-pin hookups electrically.
  Done now: magic extraction of the framed cell (tt_frame/extq.tcl) +
  a union-find over the .ext merge/equiv records proves ua[0]->UA0,
  ua[1]->UA1, uo_out[0/1]->UO0/UO1, clk->CLK, all three power stripes
  on the right nets, and all live pins mutually isolated. NOTE: .ext
  connectivity uses BOTH "merge" and "equiv" records -- parsing only
  merge false-reports floating nodes.
  (2) FLOATING DIGITAL OUTPUTS -- REAL BUG. The TT analog spec
  requires "Connect any unused uo_out, uio_out and uio_oe pins to
  GND"; precheck only checks pin geometry (pin_check.py), so our 22
  floating output stubs sailed through green. On silicon they feed
  tristate-buffer inputs in the TT mux: crowbar current always, and
  undefined uio_oe when selected can randomly drive board pins.
  Fixed in build_frame.tcl: the 22 pins are one contiguous met4 stub
  block (x 15.18-73.14, top edge), ganged by a met4 bar
  (14.9-74.3 x 224.76-225.26) and dropped onto sd_top's own VGND
  met4 riser at x=74 (met4-only, no new vias, 1.4 um clear of the
  uo_out[1] leg). Frame DRC 0; extraction re-proves 22/22 tied,
  live pins intact.
  (3) COLD START -- every plain .tran starts from ngspice's DC
  operating point, which hands the bias its good state for free; a
  startup circuit that never fires on a real ramp is invisible to the
  entire suite. top_tb grew --ramp {analog-late, digital-late}
  (late rail 0.2->2.2 us PWL, other rail up in 100 ns, clk + input
  driving from t=0): BOTH ALIVE on the extracted top -- ones density
  0.508/0.512, ~155 transitions in the last 256 bits, integrator
  0.65-1.22 V. Added to nightly top-corners as a permanent
  regression.
  (4) The datasheet now records the tied outputs (uio stays in input
  mode). Remaining known-unverified: top-level behavior at VAPWR
  corners (3.0/3.6 V) -- block TBs swept VDPWR only; nightly corner
  runs are process-only. Bench Phase-1 covers it (VAPWR sweep is
  test 1.4); a sim variant would need buf/bias re-acceptance at
  rail corners first.
  USER ACTION: the shuttle submission predates this fix -- re-run /
  update the TT submission so it picks up the retied GDS before the
  2026-09-07 deadline.

- **2026-07-26 (late): hardening batch two -- reproducible GDS,
  antenna gate, rail/temperature corners, bench-expectation notes.**
  (a) DETERMINISTIC GDS + STALENESS GATE: magic 8.3.676 accepts `gds
  datestamp` but ignores it on write (61 wall-clock date fields made
  every export unique); tools/gds_datenorm.py pins the BGNLIB/BGNSTR
  records post-export, verified byte-identical across rebuilds, and
  frame-verify now ends with `git diff --exit-code gds/ lef/` -- the
  committed artifact the shuttle ingests can no longer go stale
  against mag/. (b) ANTENNA: TT precheck's antenna deck is
  gf180mcuD-ONLY (verified in tt-support-tools precheck.py); sky130A
  projects get no antenna check anywhere. magic antennacheck on
  sd_top: CLEAN. `make antenna`, gated in nightly assembly-verify.
  (c) VAPWR RAIL CORNERS (top extracted, ratiometric stimulus --
  input scales with the rail like the bench): 36.2 dB at 3.0 V,
  37.9 dB at 3.6 V vs 40.2 nominal; headroom compression at the low
  rail, loop healthy. Nightly gates 35 / 36.5. (d) TEMPERATURE
  (--temp): 34.7 dB at 0 C, 38.5 dB at 85 C. The cold run's raw
  integrator max read 3.33 V -- a single startup episode, cycles
  0-14, inside the discarded settle window; steady-state max 1.24 V,
  no clipping (top_tb now reports post-settle swing so this can't
  mislead again). Nightly gates 33.5 / 37. Nightly cost: four ~4 min
  runs. (e) TEST PLAN: ESD handling procedure added; clock-source
  jitter expectations added (an RP2040 first-light clock can sit
  above the 24 ps precision knee -- bad precision SNDR there is
  predicted, not a dead chip; fast path is the first-light metric).
  (f) FABRIC RTL: the cocotb suite (incl. both mixed-signal
  pex-vector tests) runs green locally, 5/5 in ~7 s (~/.venv +
  iverilog) -- the earlier STATUS "never run" note was stale, CI
  rtl-verify had it green all along. pex_bits.txt regenerated from
  the current 2-pin chip's nominal acceptance run.

- **2026-07-27: nightly 85C convergence flake + shuttle PR #143
  failure (TT-side uses_vapwr -> uses_3v3 rename).** (a) The first
  nightly with the new corners passed 7/8; --temp 85 aborted on the
  runner with ngspice "Timestep too small" at t=12.1 us -- a
  convergence flake, not a design signal (identical run passes
  locally at 38.5 dB; marginal Newton trajectories differ with
  machine/thread count). top_tb now retries ONCE with relaxed solver
  tolerances (abstol 1e-10 itl4=200, still 4+ decades under signal
  currents) and -- the sharper catch -- deletes the previous run's
  csv before every invocation, so an aborted sim can never be judged
  ACCEPT on the prior run's stale data. (b) Shuttle integration PR
  (tinytapeout-sky-26c#143) failed all three prechecks even though
  our repo-side precheck was green: the shuttle-pinned
  tt-support-tools reads `uses_3v3` while the published analog
  template (and our info.yaml) says `uses_vapwr` -- no backward
  compat, silent default to non-3v3, hence wrong template def
  (334880-wide non-3v3 vs our correct 319240 3v3 -- the defs
  themselves are identical to ours), "unsupported extra ports:
  VAPWR", and ua pins checked at the wrong template's positions.
  Fix: info.yaml carries BOTH keys. Worth reporting upstream -- this
  breaks every uses_vapwr submission on the shuttle. USER ACTION:
  re-trigger the shuttle submission after this push; consider
  flagging the rename skew on the TT discord/issue tracker.

- **2026-07-28: CI retry removed -- top_tb made deterministic
  instead (user directive: no retries in CI).** The retry masked the
  actual defect classes. Three structural fixes, permanent for every
  run: (1) `set num_threads=1` -- OpenMP summation order changes
  rounding per machine, which IS why the 85 C run aborted on the
  runner while passing locally; single-threaded, one ngspice build
  walks one trajectory, always (cost measured: 26%). (2) abstol
  1e-10 + itl4=200 in the deck for all runs -- 1e-12 was over-tight
  against 85 C leakage floors, and a fallback-only tolerance would
  mean gates measure two different simulators. (3) 50-ohm series
  source resistance at VIN -- the failing equation was vin#branch on
  the ideal source; bench-realistic (DAC + trace), 0.04% of RIN.
  All nine nightly scenarios re-baselined on the new deck: nominal
  39.5 / ss 34.5 / ff 38.7 / v3.0 37.5 / v3.6 34.8 / 0C 34.7 /
  85C 36.7 dB, ramps ALIVE. Values moved +-1-3 dB vs the threaded
  deck -- the documented 2048-bit window sensitivity, one draw per
  scenario now instead of one per machine. Gates set at measured
  minus 2 dB; a trip now means the design or code changed, never
  the machine. Kept from the retry commit: the pre-run csv delete
  (an aborted sim must never be scored on the prior run's data).

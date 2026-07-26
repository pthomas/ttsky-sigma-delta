# Silicon test plan

The bring-up and validation plan for the TTSKY26c silicon. Its
organizing principle mirrors the repo's: **every measurement has a
CI-generated prediction to correlate against**, and the deliverable
of each test is a measured-vs-predicted row, not just a number. The
correlation table is the credibility artifact for everything this
design methodology claims.

## Equipment

- TinyTapeout demo board (RP2040 breakout) for first-light only;
  an FPGA board (iCE40/ECP5/Zynq — anything with a spare PLL and two
  LVCMOS inputs) for all bitstream capture.
- Clean 50 MHz clock source (FPGA PLL output is fine; avoid RC
  oscillators — RZ feedback doubles jitter sensitivity).
- Signal source: **AD5541A** (kernel `ad5446` driver; MikroE DAC 8
  Click on the Icicle mikroBUS, or Pmod DA3) for all DC work —
  **referenced to the same cleaned 3.3 V rail that feeds VAPWR**,
  not the breakout's onboard 2.5 V ref (lift/bypass it, or put a
  bare AD5541A on the carrier). Rail-as-reference makes the bench
  ratiometric end-to-end: DAC code → ADC reading is a pure ratio,
  independent of rail drift, and full scale covers the whole 0–3.3 V
  window. VOFF's DC drive can be a trimpot from the same rail (also
  ratiometric). For AC SNDR tones: audio-grade DAC or generator,
  ≤−60 dBc THD preferred (the measurement floor should be the chip,
  not the source); SPI-rate updates cap clean AD5541A tones to
  roughly the precision band.
- DMM (6.5-digit preferred) for the DC/monitor-pin tests;
  oscilloscope ≥200 MHz for output-eye and clock checks.
- Bench supplies: 3.3 V (VAPWR) and 1.8 V (VDPWR), current-limited.

## Phase 0 — first light (minutes, RP2040 board is enough)

| # | Test | Procedure | Pass = |
|---|---|---|---|
| 0.1 | Power | Apply 1.8/3.3 V, no clock | VAPWR current ~3 mA class, VDPWR <1 mA, nothing hot |
| 0.2 | Alive | 50 MHz clock, VIN grounded | Q/Q̄ toggling, complementary, ones density well below 0.5 |
| 0.3 | Rails respond | VIN to 3.3 V, then to VGND | ones density near 1, then near 0; recovery immediate |
| 0.4 | Mid-scale | VIN = 1.65 V (divider from VAPWR), ua[2] grounded | ones density 0.50 ± 0.03 (CI predicts 0.486–0.495) |

## Phase 1 — DC operating point (DMM, no capture needed)

| # | Test | Pins | Predicted (CI, tt corner) | Notes |
|---|---|---|---|---|
| 1.1 | vcm monitor | ua[3] vs VGND | 0.900 V × (ladder ratio; ratiometric to VAPWR) | ≥1 MΩ meter; the 100 kΩ isolation makes a ~10% divider against a 1 MΩ input — correct for it or use a buffer |
| 1.2 | vrefp monitor | ua[4] | 1.400 V ratiometric | same caveat |
| 1.3 | Ratiometry | sweep VAPWR 3.0–3.6 V | ua[3]/VAPWR and ua[4]/VAPWR constant to <1% | the no-bandgap design claim, measured |
| 1.4 | Integrator DC | ua[1] | ~0.9 V mean, activity visible | high-Z probe |
| 1.5 | VOFF null | find VIN where ones = 0.5, ua[2] grounded | 1.65 V ± gain error (thin-poly width bias predicts a few %) | this measures the input-network gain error directly |
| 1.6 | Window slide | ua[2] = 0.9 V, repeat 1.5 | null moves to ≈ 0.9 + 0.75·(0.9−0.833·0.9)... measured curve vs `(VCM − 0.833·VOFF)` model | the commercial offset-trim experiment |

## Phase 2 — bitstream capture and SNDR (FPGA)

Capture setup: clock the chip from the FPGA; latch Q (and Q̄) on the
same clock's opposite edge or a phase-shifted copy (source-synchronous;
scan the phase until the eye is clean — this doubles as test 2.1).
Store ≥2²⁰ bits per run to allow many analysis windows.

| # | Test | Procedure | Predicted (extracted, tt) |
|---|---|---|---|
| 2.1 | Capture eye | phase-scan the capture clock | ≥120° of clean eye at 50 MHz |
| 2.2 | Fast-path SNDR | −4.4 dBFS tone ≈317 kHz, 2048-bit coherent windows (bin 13 at 50 MHz), sinc/FFT per `sim/snr.py` | 38–41 dB (measured 38.3–40.7 across windows); window scatter ±1.5 dB is EXPECTED — report the ensemble, not one window |
| 2.3 | Precision-path SNDR | same capture, OSR 250, 4096-bit windows | tier-1 band 54–67 dB (pattern-noise scatter documented); silicon adds thermal noise — expect the band's lower half |
| 2.4 | Ones-density linearity | DC sweep VIN 0→3.3 V in 0.1 V steps | straight line, slope = 1/3.3 per volt ± gain error from 1.5; INL from residuals |
| 2.5 | Clock sensitivity | repeat 2.2 at 25 and 60 MHz | loop scales with clock (ratiometric k); SNDR within ~2 dB of 50 MHz value |
| 2.6 | Jitter sensitivity | repeat 2.2 with a deliberately dirty clock (ring-osc or spread-spectrum) | degradation consistent with RZ 2× jitter model — a *characterization* row, no gate |

## Phase 3 — the correlation table (the point of the exercise)

Assemble every Phase 1–2 row into measured-vs-CI-predicted with:
prediction source (tier-1 / extracted / corner), measured value,
deviation, and verdict. Corner inference: if the DC points (1.1–1.5)
and SNDR sit consistently high or low, compare against the nightly
ss/ff corner runs (ss 33.4 dB, ff 35.3 dB extracted) to estimate
which corner the die drew. Publish the table as a site chapter —
it becomes the "silicon correlated" stamp on the datasheet and the
first hard evidence for the commercial-exploration thesis.

## Phase 4 — stretch / debug (only if something disagrees)

- ua[1] (integrator) waveform vs the extracted transient — shape,
  swing, and startup match.
- ua[3]/ua[4] under load steps: reference droop signature (buffer
  Zout ~750 Ω × decap corner).
- VOFF modulation while capturing: dynamic window-slide behavior
  (bandwidth of the offset path — undocumented, characterize).
- Duty-cycle stress: feed asymmetric clock (45/55), verify pure gain
  error (predicted ≤ ~7% gain shift at the 3.5% duty gate limit,
  zero SNDR penalty) — the RZ edge-immunity claim, measured.

## Risks / known unknowns

- Monitor pins load their nets by 100 kΩ + pad; predicted shift is
  <0.1% on vcm/vrefp (buffer-driven) — verify in 1.1/1.2 rather than
  assume.
- The TT mux and board add series resistance and leakage to analog
  pins; the ua[2] leg is ratio-critical (158.4 kΩ) — measure the mux
  path resistance on an unused analog pin first and correct 1.5/1.6.
- Thermal drift is uncharacterized (all sims 27 °C): note ambient
  for every row; a hot-air rework station sweep (25–85 °C) is the
  cheap version of a temperature characterization.

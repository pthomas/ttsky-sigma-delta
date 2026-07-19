# Block specs: sweeping until it breaks

With the loop trusted at tier 1, each analog block's requirement is
*measured*: sweep that block's non-ideality alone, plot SNDR on both
decimation paths, and read the knee — then set the spec a safety factor
above it. `make specs` regenerates the sweep report ({{report_links_specs}}).

| OTA parameter | Measured knee | Spec (with margin) | Design target |
|---|---|---|---|
| DC gain A<sub>OL</sub> | degraded at 30, recovered by 100–300 | ≥ 300 (50 dB) | 1000 (60 dB) |
| GBW | **no knee down to 25 MHz** | ≥ 50 MHz | 150–200 MHz |
| Slew rate | broken at 12.5 V/µs, marginal at 50 | ≥ 100 V/µs | 200 V/µs |

Two of these rows carry lessons:

**The GBW non-result.** The loop is insensitive to single-pole bandwidth
because finite-GBW settling error is *linear* — identical every cycle for
a given bit value — so it aliases to gain error rather than noise or
distortion, and the delayed-RZ pulse leaves a half period of quiet for
residual settling. The 150–200 MHz design target exists anyway because a
real multi-pole OTA adds phase (excess loop delay) that the single-pole
behavioral model can't see. Knowing *why* the sweep shows no knee is what
lets that target be set honestly instead of superstitiously.

**Slew is the binding constraint.** Slew errors are the nonlinear ones —
they depend on the step being taken, which depends on bit history — so
they show up directly as in-band distortion. The measured knee sits ~2×
above the naive pulse-edge estimate, and it, not GBW, ended up sizing the
OTA's tail current (and therefore its power).

Beyond the OTA: the comparator + DFF must fully regenerate in the 10 ns
half-period (soft decisions cost ~25 dB, measured), DAC switch
on-resistance is flat at 229–441 Ω across the low reference window at
W = 10 µm, and the VCM buffer must absorb ~25 µA RZ return pulses at
50 MHz. Each of those becomes a testbench when its block is designed.

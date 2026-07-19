# What is a sigma-delta modulator?

An ADC's job is to turn a voltage into a number. The obvious way — a flash
or SAR converter — compares the input against many reference levels at
once and needs component matching as good as the resolution you want:
16 bits means parts matched to ~0.002%. On an open-source shuttle with no
trimming, that's not happening.

A ΣΔ modulator takes the opposite trade: **use one terrible 1-bit
quantizer, but use it very fast, and shape where its error goes.**

<figure>
<svg viewBox="0 0 640 150" role="img" aria-label="First-order sigma-delta modulator block diagram" style="max-width:640px;width:100%">
  <defs>
    <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="currentColor"/>
    </marker>
  </defs>
  <g fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="120" cy="55" r="16"/>
    <rect x="185" y="30" width="90" height="50" rx="6"/>
    <rect x="325" y="30" width="110" height="50" rx="6"/>
    <rect x="255" y="105" width="130" height="34" rx="6"/>
    <line x1="30" y1="55" x2="102" y2="55" marker-end="url(#arr)"/>
    <line x1="136" y1="55" x2="183" y2="55" marker-end="url(#arr)"/>
    <line x1="275" y1="55" x2="323" y2="55" marker-end="url(#arr)"/>
    <line x1="435" y1="55" x2="530" y2="55" marker-end="url(#arr)"/>
    <path d="M 480 55 L 480 122 L 387 122" marker-end="url(#arr)"/>
    <path d="M 255 122 L 120 122 L 120 73" marker-end="url(#arr)"/>
  </g>
  <g fill="currentColor" font-size="13" font-family="inherit">
    <text x="30" y="45">v<tspan baseline-shift="sub" font-size="10">in</tspan></text>
    <text x="230" y="60" text-anchor="middle">∫ dt</text>
    <text x="380" y="52" text-anchor="middle" font-size="12">1-bit</text>
    <text x="380" y="68" text-anchor="middle" font-size="12">quantizer @ f<tspan baseline-shift="sub" font-size="9">s</tspan></text>
    <text x="320" y="126" text-anchor="middle" font-size="12">1-bit DAC</text>
    <text x="535" y="50">bitstream</text>
    <text x="106" y="43" font-size="14">−</text>
    <text x="99" y="78" font-size="14">+</text>
  </g>
</svg>
<figcaption>The whole modulator: an integrator, a clocked comparator, and
a 1-bit DAC closing the loop.</figcaption>
</figure>

The comparator's output — the only thing the digital world ever sees — is
fed back through the DAC and subtracted from the input, and the integrator
accumulates the difference. Negative feedback around an integrator forces
the *average* of the feedback to track the input: any persistent error
would make the integrator ramp away, flipping decisions until the error is
driven back to zero. So a DC input at 30% of full scale produces a
bitstream whose *density of ones* is 30%. Digital filtering (decimation)
then averages N successive bits into one high-resolution sample.

Averaging alone would only buy √N. The integrator is what makes it a ΣΔ:
in the loop's signal transfer function the input passes through, but the
quantizer's error sees a **high-pass** response — it gets pushed up in
frequency, away from the signal band. This is *noise shaping*. For a
first-order loop, in-band quantization noise falls **9 dB for every
doubling of the oversampling ratio** (OSR = f<sub>s</sub>/2 per Hz of
signal bandwidth): 1.5 bits per octave, on top of the plain averaging.

The price is time — resolution is bought with clock cycles — and the
reward is that **precision comes from a clock and a reference, not from
matching**. One comparator, one integrator, two reference levels. That is
why a ΣΔ is the natural ADC for an open-source PDK with no factory
trimming, and why it fits in a TinyTapeout-sized analog area budget.

This project's loop runs at f<sub>s</sub> = 50 MHz and is decimated two
ways simultaneously: a *fast* path (low OSR, more bandwidth) and a
*precision* path (high OSR, more resolution) — one modulator, two output
qualities. Measured results are in the [tier-1 chapter](#tier-1-the-modulator-as-a-behavioral-circuit).

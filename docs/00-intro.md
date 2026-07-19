# A continuous-time ΣΔ ADC, designed as code

{{build_stamp}}

This is the living design document for a **first-order continuous-time
sigma-delta (ΣΔ) modulator ADC** targeting the
[TinyTapeout](https://tinytapeout.com) TTSKY26c shuttle on SkyWater
**sky130**. It reads top to bottom: from *what a sigma-delta modulator is*,
through every architecture decision and its supporting data, down to the
mask geometry you can spin in 3D at the bottom of the layout chapter.

Two properties set this project apart:

1. **The design is code.** The schematic is generated from a Python sizing
   dictionary. The layout is placed and routed by Python scripts driving
   magic. The testbenches, the spec derivations, and this document are all
   generated. `git clone`, `make` — every artifact regenerates.
2. **Every number on this page was produced by the CI pipeline that
   published the page.** Nothing here is hand-copied. If a verification
   step didn't run, you'll see an explicit "not verified in this build"
   marker instead of a stale number. The methodology sections describe not
   just what passed, but what *lied to us* along the way and how the
   checks evolved to catch it.

The toolchain is entirely open source: [ngspice](https://ngspice.sourceforge.io)
for simulation, [xschem](https://xschem.sourceforge.io) for schematic capture,
[magic](http://opencircuitdesign.com/magic/) for layout,
[netgen](http://opencircuitdesign.com/netgen/) for LVS, and the
[open_pdks](http://opencircuitdesign.com/open_pdks/) sky130A PDK.

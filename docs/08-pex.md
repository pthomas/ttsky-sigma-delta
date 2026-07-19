# Parasitic extraction: what the layout costs

Passing the design-rule check (DRC) and layout-versus-schematic (LVS)
comparison proves the geometry is *legal* and *connected
correctly* — not that it still meets spec. The layout's metal has
capacitance, and parasitic extraction (PEX, `make pex`) measures it: magic
re-extracts the layout with every node-to-node and node-to-substrate
capacitor kept, and the identical three-DUT testbench runs on the
extracted netlist.

**Schematic vs. extracted, same testbench, this build:**

{{ota_compare_table}}

{{fig_ota_ac}}

The story the numbers tell: DC quantities (gain, operating point, power)
don't move — parasitics are capacitors, and the netlists are LVS-identical.
The dynamics pay: the auto-router's deliberately generous metal (0.5 µm
via enclosure pads, a wide track bus) adds self-load, taking GBW and phase
margin down with it.

Judged against the *measured* tier-1 knees, the extracted OTA passes
everything with ≥2× margin — the knee methodology is what makes this a
quantified statement rather than a hope. Phase margin initially had no
measured knee (the behavioral sweep was single-pole by construction), so
instead of arguing about whether 46° "feels" safe, the model was extended
with a second pole and the loop was asked directly. Answer: **no SNDR
knee down to 28° of phase margin** — excess phase is linear dynamics, and
this loop demonstrably doesn't care (details in the block-specs chapter).
The 46° extracted OTA is accepted and the layout is closed for v1. The
one caveat worth remembering: this holds for the OTA *as an integrator*
in this loop — reusing the same OTA as a unity-gain buffer elsewhere
would re-open the question.

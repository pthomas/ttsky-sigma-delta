# PEX: what the layout costs

Passing DRC and LVS proves the geometry is *legal* and *connected
correctly* — not that it still meets spec. The layout's metal has
capacitance, and parasitic extraction (`make pex`) measures it: magic
re-extracts the layout with every node-to-node and node-to-substrate
capacitor kept, and the identical three-DUT testbench runs on the
extracted netlist.

**Schematic vs. extracted, same testbench, this build:**

{{ota_compare_table}}

The story the numbers tell: DC quantities (gain, operating point, power)
don't move — parasitics are capacitors, and the netlists are LVS-identical.
The dynamics pay: the auto-router's deliberately generous metal (0.5 µm
via enclosure pads, a wide track bus) adds self-load, taking GBW and phase
margin down with it.

Judged against the *measured* tier-1 knees, the extracted OTA still passes
everything with ≥2× margin — the knee methodology is what makes this a
quantified statement rather than a hope. The honest open item is phase
margin, which has no measured knee yet (the behavioral sweep was
single-pole by construction). The candidate resolutions, in order of
preference: extend the tier-1 OTA model with a second pole and *measure*
what phase margin the loop actually needs; slim the routing; resize for
margin. That decision is parked in the repository's STATUS.md — this
document will update itself when it lands.

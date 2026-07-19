# Method: tiers, golden references, and honest numbers

The project climbs four tiers of fidelity. Each tier produces a
machine-checkable artifact that the next tier is verified *against* — the
design never advances on optimism.

| Tier | Model | Tool | Verified by |
|---|---|---|---|
| 0 | difference equations | Python/NumPy | SNDR statistics vs theory |
| 1 | behavioral circuit (ideal blocks + measured non-idealities) | xschem + ngspice | SNDR floors asserted in CI |
| 2 | transistor schematics | ngspice, sky130 models | specs from tier-1 knee sweeps; corner matrix |
| 3 | mask geometry | magic + netgen | DRC, LVS vs tier-2 netlist, PEX re-simulation |

Three practices are worth stealing:

**Specs are measured, not asserted.** The OTA requirements were found by
sweeping one non-ideality at a time in the tier-1 loop and reading the
SNDR knee (the [block specs chapter](#block-specs-sweeping-until-it-breaks)
shows the curves). The result is sometimes surprising — finite GBW turned
out to have *no knee down to 25 MHz* because single-pole settling error is
linear and the loop doesn't care — and the surprise is documented next to
the number that encodes it.

**Generated views, proven equivalent.** The OTA schematic that humans look
at in xschem is *generated* from the same Python `SIZES` dictionary the
testbench simulates, and an equivalence check (`make xcheck`) proves the
generated schematic netlists to the simulated circuit. The layout is then
LVS'd against that schematic's netlist. There is one source of truth and
an unbroken chain of checks from it to the mask geometry.

**Distrust your checkers.** Twice, a verification tool reported clean
when things weren't (or dirty when they were), and both incidents are now
regression-guarded and logged:

- magic's batch DRC silently skips hierarchy-crossing checks on unexpanded
  subcells — a fresh `load` + `drc check` prints a false **0 errors**.
  Every DRC number here comes from a fresh process with explicit cell
  expansion.
- magic's `writeall force` rewrites *unmodified* subcells with
  lambda-normalized (halved) coordinates, silently corrupting odd 0.005 µm
  spacings on disk. The result was 894 phantom DRC violations that
  survived two wrong root-cause theories before an isolated experiment
  convicted the file writer, not the geometry. The router now saves only
  the cell it painted, and re-verifies DRC on the *saved files* in a
  separate process.

Both war stories are told in full in the layout chapter — they shaped the
verification flow more than any textbook rule did.

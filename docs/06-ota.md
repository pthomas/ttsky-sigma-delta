# The OTA: a folded cascode, sized in code

The first transistor-level block is the integrator's OTA: a folded cascode
with a PMOS input pair (input common mode 0.9 V), NMOS folded branch with
cascodes, and a cascoded PMOS mirror load driving a single-ended output.
All devices are sky130 5 V (g5v0d10v5) thick-oxide FETs on the 3.3 V
analog supply.

The circuit exists as a Python dictionary first — `SIZES` in
`sim/ota_tb.py` — and everything else is derived from it:

{{sizes_table}}

The testbench simulates three DUT copies in one deck (AC open-loop for
gain/GBW/phase margin, a unity buffer driven with a step for slew, and a
DC sweep for usable range). The xschem schematic humans read is
*generated* from the same dictionary (`make xcheck` proves netlist
equivalence), and the layout in the next chapter is placed from it too.

**Schematic-level results (tt corner):**

{{ota_sch_table}}

Corners tt/ss/ff/sf/fs stay within A0 64.6–65.4 dB, GBW 199–220 MHz,
PM 56–59°, SR+ 190–204 V/µs at 4.5 mW — the sizing was frozen for layout
on that flatness. Known caveats, tracked openly: cascode gate biases and
reference currents are still ideal sources (the bias generator is a
pending block), and phase margin sits a few degrees under the 60° bar —
accepted for v1 and revisited with extracted parasitics in the
[PEX chapter](#pex-what-the-layout-costs).

Sizing lessons that cost real iterations (recorded so nobody relearns
them): sky130 5 V FETs are width-binned, so devices tile 5 µm unit fingers
with `m=` multipliers; thick-oxide cascodes at normal current density have
soft saturation and want ~1 µA/µm *and* L = 1 µm to actually deliver
their output resistance; and the single-ended mirror pole — two PMOS gates
hanging on the diode node — is what sets the phase margin, so the mirror
devices stay small and short.

# The comparator: a StrongARM latch, sensed the right way up

The comparator gets one hard spec from tier 1: **decide completely within
its 10 ns half-period**, because a soft, mid-rail decision reaching the
DAC costs ~25 dB of SNDR (measured). A StrongARM latch<sup>[[4]](#references)</sup> is the natural
choice — zero static power, and its speed is set by the regeneration time
constant of a cross-coupled pair.

The interesting question was the input pair's flavor. The reference window
sits deliberately *low* (0.4–1.4 V on a 3.3 V supply) so that NMOS
switches pass it with healthy gate drive — but our 5 V thick-oxide FETs
have V<sub>th</sub> ≈ 0.8 V, so an NMOS *sensing* pair at the 0.68 V swing
floor would sit at essentially zero overdrive, slowest exactly where the
modulator lives. The rule that falls out, and that this chip now applies
twice (the OTA made the same call): **NMOS passes the low window, PMOS
senses it.** A PMOS input pair gets ~1.5 V of overdrive at the 0.9 V
common mode — and speeds *up* at the low corner where NMOS would die.

{{fig_sch_comp}}

{{fig_comp_race}}

**Measured (this build):**

{{comp_table}}

Two design details earned their place the hard way. First, the SR latch
that holds the decision through precharge is fed through **inverter
buffers**, not wired directly to the regeneration nodes — wired directly,
the latch's held state presents asymmetric Miller loading and acts as a
~10 mV dynamic hysteresis seeded by the *previous* decision (measured as
state-dependent wrong-sign flips before the buffers went in). Second, the
testbench itself had to be engineered: a regenerative race is decided by
µV-scale seeds, and at default simulator tolerances *the solver picks the
winner, not the input*. Each measurement point runs in its own ngspice
process with Gear integration, tightened tolerances, and a 1 ps timestep
cap — the full set of lessons is in the repository's decision log.

## The retimer behind it

The comparator's output wanders mid-cycle as each decision completes.
The feedback DAC must never see that — pulse timing that depends on how
long the comparator thought is inter-symbol interference (ISI), the
modulator's top-ranked non-ideality<sup>[[2]](#references)</sup>. A transistor-level master-slave DFF pins the DAC
drive to the clock edge:

{{fig_dff_retime}}

{{dff_line}}

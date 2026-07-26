# Reproduce it, break it, extend it

Everything on this page regenerates from a clone:

```
git clone https://gitlab.com/pthomas1/sigma-delta.git
cd sigma-delta
make snr      # tier-1 loop + SNDR table            (~10 s)
make report   # NRZ vs RZ four-corner comparison    (~70 s)
make specs    # OTA requirement knee sweeps         (~6 min)
make jitter   # clock-jitter susceptibility sweep   (~30 s)
make noise    # OTA 1/f + thermal noise budget      (~5 s)
python3 sim/ota_tb.py            # OTA testbench (edit SIZES to resize)
python3 tools/gen_ota_layout.py  # regenerate placement
python3 tools/route_ota.py       # regenerate routing + verify
make pex      # parasitic extraction + extracted-netlist TB
make lvs      # netgen LVS vs golden netlist
```

Toolchain: ngspice 42, xschem 3.4.4, magic 8.3.676 and netgen 1.5.323
(both source-built — distribution packages are too old for the PDK), and
the sky130A PDK installed via `ciel` at a pinned hash. The CI runner
provisions itself from `ci/lxd/cloud-init.yml`, which is the executable
form of this paragraph.

**Roadmap** (STATUS.md in the repo is the live version): v1 is assembled,
verified, and submitted to the TTSKY26c shuttle. Next comes silicon
bring-up against the [test plan](#silicon-test-plan) — every phase
correlates bench measurements with the CI-predicted numbers — and the v2
threads: second-order loop, fully-differential core, and the
decision-path noise floor characterized during v1 acceptance.

## Working notes (gotchas that cost real sessions)

xschem authoring, learned generating the tier-1 schematic:

- Literal braces in attribute strings (spice params like `{RIN}`) must be
  escaped `\{RIN\}` — unescaped they silently truncate the attribute.
- `vsource_arith.sym` netlists `VOL='expr'` E-source syntax → instance
  names must start with `E`, not `B`.
- In symbol `format=` strings, `@@PIN` references need surrounding spaces
  (`v( @@PLUS )`), otherwise substitution truncates the card.
- Custom symbols whose .subckt lives in a code block need
  `type=primitive` (not `subcircuit`, which makes xschem descend looking
  for a .sch).
- Headless: `xschem --netlist --spice -q -x`; PNG via `--png --plotfile`
  (needs a DISPLAY); a project `xschemrc` in cwd supplies library paths.
- Behavioral convergence: keep hard `u()` steps out of feedback paths
  that drive switch controls — use steep `tanh`; give behavioral
  comparators very high gain (soft decisions become analog-valued
  feedback pulses and quietly cost ~25 dB of in-band SNDR).

magic + PDK gencells, learned on the OTA layout:

- sky130 gencells with `full_metal` arrive with every contact column
  strapped in met1 full-height — group columns on **met2** (via1 down),
  run risers on **met3**; met1 painted across a device shorts it.
- Unit zoo: parent .mag transforms and runtime `box values` are 200/µm;
  subcell .mag rects 100/µm; .ext port coordinates 200/µm. Layout
  gencell `w` is per-finger (schematic W is total width).
- Diagnose operating points with `@m.x...msky130_...[gm]/[gds]/[vdsat]`
  op saves, not theory.
- The DRC "false clean" and "false dirty" traps are described in the
  [layout chapter](#layout-mask-geometry-generated-and-interrogated) —
  inherit them before trusting any DRC number.

Questions, ideas, or want to point a student at it?
Open an issue on the [GitLab project](https://gitlab.com/pthomas1/sigma-delta).

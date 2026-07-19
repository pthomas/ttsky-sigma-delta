# Reproduce it, break it, extend it

Everything on this page regenerates from a clone:

```
git clone https://gitlab.com/pthomas1/sigma-delta.git
cd sigma-delta
make snr      # tier-1 loop + SNDR table            (~10 s)
make report   # NRZ vs RZ four-corner comparison    (~70 s)
make specs    # OTA requirement knee sweeps         (~6 min)
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

**Roadmap** (STATUS.md in the repo is the live version): StrongARM
comparator with a metastability testbench next, then reference/VCM
buffers sized for the RZ pulse loads, bias generation to replace the ideal
sources, clock level shifting, output drivers, and top-level assembly into
the TinyTapeout analog template — with the second-order upgrade as the
stretch goal the area budget was written for.

Questions, ideas, or want to point a student at it?
Open an issue on the [GitLab project](https://gitlab.com/pthomas1/sigma-delta).

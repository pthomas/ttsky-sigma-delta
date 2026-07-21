SCH = xschem/tier1_sdm.sch
NET = spice/tier1_sdm.spice

all: snr

spice/params.spice: params.py
	python3 params.py

$(NET): $(SCH) $(wildcard xschem/*.sym) spice/params.spice
	xschem --netlist --spice -q -x $(SCH)

# headless netlist: no interactive plot windows
spice/tier1_headless.spice: $(NET)
	grep -v '^plot' $(NET) > $@

spice/tier1_out.csv: spice/tier1_headless.spice
	cd spice && ngspice -b tier1_headless.spice > ngspice_run.log 2>&1

netlist: $(NET)

report: spice/tier1_headless.spice
	python3 sim/compare_dac.py

# sky130 device characterization (needs PDK at /home/nvme/pdk)
char:
	python3 sim/char_fets.py

# OTA requirements sweep (gain / GBW / slew vs SNDR)
specs: spice/tier1_headless.spice
	python3 sim/spec_sweep.py

# generate + verify layout cells in magic (needs magic >= 8.3.411)
layout:
	python3 tools/gen_layout_cells.py

# parasitic extraction of the routed OTA layout, then TB on the extracted
# netlist (compare against plain `python3 sim/ota_tb.py`)
pex:
	python3 tools/pex_ota.py
	python3 sim/ota_tb.py --pex

# layout verification bundle: fresh-process DRC + LVS + GDS export + 3D
# geometry JSON (fails if DRC != 0 or LVS mismatches)
layout-report:
	python3 tools/layout_report.py

# build the public/ design-document site from docs/*.md + reports/results/
site:
	python3 tools/gen_docs.py

# rebuild the TinyTapeout submission frame (gds/ + lef/) from mag/
tt: export PDK_ROOT ?= /home/nvme/pdk
tt:
	cd tt_frame && rm -f tt_um_pthomas_sigma_delta.mag && \
	  PDK_ROOT=$(PDK_ROOT) SIGMA_DELTA_MAG=$(CURDIR)/mag magic -dnull -noconsole \
	  -rcfile $(PDK_ROOT)/sky130A/libs.tech/magic/sky130A.magicrc \
	  build_frame.tcl && \
	  PDK_ROOT=$(PDK_ROOT) SIGMA_DELTA_MAG=$(CURDIR)/mag magic -dnull -noconsole \
	  -rcfile $(PDK_ROOT)/sky130A/libs.tech/magic/sky130A.magicrc \
	  export.tcl

# netgen LVS: routed OTA layout vs xschem golden netlist
lvs:
	PDK_ROOT=$${PDK_ROOT:-/home/nvme/pdk} netgen -batch lvs \
	  "mag/ota_layout.spice ota_layout" "spice/ota_top.spice ota" \
	  $${PDK_ROOT:-/home/nvme/pdk}/sky130A/libs.tech/netgen/sky130A_setup.tcl \
	  spice/lvs_report.out

# regenerate OTA schematic from sizes and verify equivalence
xcheck:
	mkdir -p spice
	python3 tools/gen_ota_sch.py
	xschem --netlist --spice -q -x xschem/ota_top.sch
	python3 sim/ota_xcheck.py

# regenerate comparator schematic from sizes and verify equivalence
compcheck:
	mkdir -p spice
	python3 tools/gen_comp_sch.py
	xschem --netlist --spice -q -x xschem/comp_top.sch
	python3 sim/comp_xcheck.py

# golden netlists + generated schematics for all support blocks, then
# canonical (device-for-device) equivalence of the xschem netlists
blockcheck:
	mkdir -p spice
	python3 tools/gen_golden.py
	python3 tools/gen_comp_sch.py
	python3 tools/gen_sch.py
	for b in comp dff bias buf lvl odrv; do \
	  xschem --netlist --spice -q -x xschem/$${b}_top.sch || exit 1; done
	python3 tools/xcheck_blocks.py

asm:
	mkdir -p spice
	python3 tools/gen_golden.py
	python3 tools/gen_top_golden.py
	python3 tools/asm_route.py
	python3 tools/asm_top.py

pextop:
	python3 tools/pex_top.py

topaccept:
	python3 sim/top_tb.py

snr: spice/tier1_out.csv
	python3 sim/snr.py

view:
	xschem $(SCH) &

clean:
	rm -rf spice

.PHONY: all netlist report specs char layout pex layout-report site tt lvs xcheck compcheck blockcheck asm pextop topaccept snr view clean

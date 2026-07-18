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

snr: spice/tier1_out.csv
	python3 sim/snr.py

view:
	xschem $(SCH) &

clean:
	rm -rf spice

.PHONY: all netlist report snr view clean

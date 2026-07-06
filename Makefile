SCH = xschem/tier1_sdm.sch
NET = spice/tier1_sdm.spice

all: snr

spice/params.spice: params.py
	python3 params.py

$(NET): $(SCH) $(wildcard xschem/*.sym) spice/params.spice
	xschem --netlist --spice -q -x $(SCH)

# headless run: strip interactive plot lines so no windows pop up
spice/tier1_out.csv: $(NET)
	grep -v '^plot' $(NET) > spice/tier1_headless.spice
	cd spice && ngspice -b tier1_headless.spice > ngspice_run.log 2>&1

snr: spice/tier1_out.csv
	python3 sim/snr.py

view:
	xschem $(SCH) &

clean:
	rm -rf spice

.PHONY: all snr view clean

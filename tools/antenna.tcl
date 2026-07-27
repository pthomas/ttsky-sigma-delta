# Antenna-rule check on the assembled top (magic antennacheck, sky130A
# tech antenna parameters). Run from mag/: magic ... ../tools/antenna.tcl
#
# Why this exists: TT precheck runs an antenna deck for gf180mcuD ONLY
# -- sky130A submissions get no antenna check anywhere in the shuttle
# flow (verified against tt-support-tools precheck.py, 2026-07-27),
# and fab-time antenna damage is invisible to every electrical sim.
load sd_top
select top cell
expand
extract all
antennacheck
puts "ANTENNA CHECK DONE"
quit -noprompt

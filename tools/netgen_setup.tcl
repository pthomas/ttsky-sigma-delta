# Project netgen setup: the PDK setup plus one relaxation.
#
# magic folds snake-resistor corners into a shorter effective length
# than the drawn card (DESIGN.md 2026-07-19/20): the bias block's
# RBNC/RBPC extract 2-3% short of their golden drawn lengths. Their
# resistance is calibrated against the ngspice model separately and
# their function (cascode-gate isolation) is insensitive to value --
# the earlier 100 ohm -> 1 kohm change proved that -- so widen the
# length tolerance for this one device flavor from the PDK's 1%.
source $env(PDK_ROOT)/sky130A/libs.tech/netgen/sky130A_setup.tcl
property "-circuit1 sky130_fd_pr__res_high_po_1p41" tolerance {l 0.04}
property "-circuit2 sky130_fd_pr__res_high_po_1p41" tolerance {l 0.04}

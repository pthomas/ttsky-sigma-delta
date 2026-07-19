# Export GDS + LEF for the TT frame (fresh process: current cell is
# unambiguous after a plain load). Run after build_frame.tcl.
set TOP_LEVEL_CELL tt_um_pthomas_sigma_delta
addpath $env(SIGMA_DELTA_MAG)
load $TOP_LEVEL_CELL
file mkdir ../gds
gds write ../gds/${TOP_LEVEL_CELL}.gds
file mkdir ../lef
lef write ../lef/${TOP_LEVEL_CELL}.lef -hide -pinonly
# our own DRC gate on the hand-drawn pad wiring (fresh process + expand,
# per the design repo's DRC methodology)
select top cell
expand
drc euclidean on
drc style drc(full)
drc check
drc catchup
puts "DRCCOUNT [drc listall count total]"
puts "EXPORT DONE"
quit -noprompt

addpath $env(SIGMA_DELTA_MAG)
load tt_um_pthomas_sigma_delta
select top cell
expand
drc euclidean on
drc style drc(full)
drc check
drc catchup
puts "WHY [drc listall why]"
quit -noprompt

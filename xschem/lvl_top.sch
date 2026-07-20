v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {lvl_top: netlisting wrapper - produces .subckt lvl for tools/xcheck_blocks.py} -600 -400 0 0 0.4 0.4 {}
C {lvl.sym} 0 0 0 0 {name=XLVL1}
C {devices/lab_pin.sym} -140 0 0 0 {name=w0 lab=clk18}
C {devices/lab_pin.sym} 140 -40 0 0 {name=w1 lab=clk33}
C {devices/lab_pin.sym} 140 40 0 0 {name=w2 lab=clkb33}
C {devices/lab_pin.sym} -60 -100 0 0 {name=w3 lab=vdd18}
C {devices/lab_pin.sym} 20 -100 0 0 {name=w4 lab=vdd33}
C {devices/lab_pin.sym} -20 100 0 0 {name=w5 lab=vss}

v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {dff_top: netlisting wrapper - produces .subckt dff for tools/xcheck_blocks.py} -600 -400 0 0 0.4 0.4 {}
C {dff.sym} 0 0 0 0 {name=XDFF1}
C {devices/lab_pin.sym} -140 -40 0 0 {name=w0 lab=d}
C {devices/lab_pin.sym} -140 40 0 0 {name=w1 lab=clk}
C {devices/lab_pin.sym} 140 -40 0 0 {name=w2 lab=q}
C {devices/lab_pin.sym} 140 40 0 0 {name=w3 lab=qb}
C {devices/lab_pin.sym} -20 -100 0 0 {name=w4 lab=vdd}
C {devices/lab_pin.sym} -20 100 0 0 {name=w5 lab=vss}

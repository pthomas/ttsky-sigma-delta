v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {comp_top: netlisting wrapper - produces .subckt comp for sim/comp_xcheck.py} -600 -400 0 0 0.4 0.4 {}
C {comp.sym} 0 0 0 0 {name=XCOMP1}
C {devices/lab_pin.sym} -140 -40 0 0 {name=w0 lab=inp}
C {devices/lab_pin.sym} -140 0 0 0 {name=w1 lab=inm}
C {devices/lab_pin.sym} -140 40 0 0 {name=w2 lab=clk}
C {devices/lab_pin.sym} 140 -40 0 0 {name=w3 lab=q}
C {devices/lab_pin.sym} 140 0 0 0 {name=w4 lab=qb}
C {devices/lab_pin.sym} 140 40 0 0 {name=w5 lab=on1}
C {devices/lab_pin.sym} 140 60 0 0 {name=w6 lab=on2}
C {devices/lab_pin.sym} -20 -100 0 0 {name=w7 lab=vdd}
C {devices/lab_pin.sym} -20 100 0 0 {name=w8 lab=vss}

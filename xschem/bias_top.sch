v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {bias_top: netlisting wrapper - produces .subckt bias for tools/xcheck_blocks.py} -600 -400 0 0 0.4 0.4 {}
C {bias.sym} 0 0 0 0 {name=XBIAS1}
C {devices/lab_pin.sym} 140 -60 0 0 {name=w0 lab=irefp}
C {devices/lab_pin.sym} 140 -20 0 0 {name=w1 lab=irefn}
C {devices/lab_pin.sym} 140 20 0 0 {name=w2 lab=vbnc}
C {devices/lab_pin.sym} 140 60 0 0 {name=w3 lab=vbpc}
C {devices/lab_pin.sym} -20 -100 0 0 {name=w4 lab=vdd}
C {devices/lab_pin.sym} -20 100 0 0 {name=w5 lab=vss}

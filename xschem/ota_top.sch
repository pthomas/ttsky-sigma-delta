v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {ota_top: netlisting wrapper - produces .subckt ota for sim/ota_xcheck.py} -600 -400 0 0 0.4 0.4 {}
C {ota.sym} 0 0 0 0 {name=XOTA1}
C {devices/lab_pin.sym} -140 -40 0 0 {name=w1 lab=inp}
C {devices/lab_pin.sym} -140 0 0 0 {name=w2 lab=inm}
C {devices/lab_pin.sym} 140 0 0 1 {name=w3 lab=out}
C {devices/lab_pin.sym} -20 -100 1 0 {name=w4 lab=vdd}
C {devices/lab_pin.sym} -20 100 1 1 {name=w5 lab=vss}
C {devices/lab_pin.sym} -140 40 0 0 {name=w6 lab=irefp}
C {devices/lab_pin.sym} -60 100 1 1 {name=w7 lab=irefn}
C {devices/lab_pin.sym} 20 100 1 1 {name=w8 lab=vbnc}
C {devices/lab_pin.sym} 60 100 1 1 {name=w9 lab=vbpc}

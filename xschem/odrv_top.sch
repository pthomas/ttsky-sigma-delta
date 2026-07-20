v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {odrv_top: netlisting wrapper - produces .subckt odrv for tools/xcheck_blocks.py} -600 -400 0 0 0.4 0.4 {}
C {odrv.sym} 0 0 0 0 {name=XODRV1}
C {devices/lab_pin.sym} -140 0 0 0 {name=w0 lab=in33}
C {devices/lab_pin.sym} 140 0 0 0 {name=w1 lab=out18}
C {devices/lab_pin.sym} -20 -100 0 0 {name=w2 lab=vdd18}
C {devices/lab_pin.sym} -20 100 0 0 {name=w3 lab=vss}

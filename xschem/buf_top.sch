v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {buf_top: netlisting wrapper - produces .subckt buf for tools/xcheck_blocks.py} -600 -400 0 0 0.4 0.4 {}
C {buf.sym} 0 0 0 0 {name=XBUF1}
C {devices/lab_pin.sym} -140 -40 0 0 {name=w0 lab=in}
C {devices/lab_pin.sym} 140 0 0 0 {name=w1 lab=out}
C {devices/lab_pin.sym} -140 40 0 0 {name=w2 lab=irefp}
C {devices/lab_pin.sym} -20 -100 0 0 {name=w3 lab=vdd}
C {devices/lab_pin.sym} -20 100 0 0 {name=w4 lab=vss}

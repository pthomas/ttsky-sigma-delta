v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {1st-order CT sigma-delta modulator - tier 1 behavioral (RZ feedback DAC)} -1560 -660 0 0 0.5 0.5 {}
T {values from spice/params.spice - run: python3 params.py} -1560 -620 0 0 0.3 0.3 {}
T {RC integrator} -1200 -500 0 0 0.35 0.35 {}
T {comparator} -860 -500 0 0 0.35 0.35 {}
T {DFF (master/slave sample of comparator)} -640 -500 0 0 0.35 0.35 {}
T {RZ DAC: VCM while clk high, +-VREF while clk low} -100 -500 0 0 0.35 0.35 {}
T {DOUT = QB (bitstream, inverted encoding)} 60 -360 0 0 0.3 0.3 {}
C {devices/res.sym} -1360 -300 3 0 {name=R_IN value=\{RIN\}}
N -1440 -300 -1390 -300 {lab=vin}
C {devices/lab_pin.sym} -1440 -300 0 0 {name=p1 lab=vin}
N -1330 -300 -1280 -300 {lab=sum}
C {devices/lab_pin.sym} -1280 -300 0 1 {name=p2 lab=sum}
C {devices/capa.sym} -1060 -440 3 0 {name=C_INT value=\{CINT\}}
N -1140 -440 -1090 -440 {lab=sum}
C {devices/lab_pin.sym} -1140 -440 0 0 {name=p3 lab=sum}
N -1030 -440 -980 -440 {lab=int}
C {devices/lab_pin.sym} -980 -440 0 1 {name=p4 lab=int}
C {devices/vcvs.sym} -1060 -300 1 0 {name=E_OTA value=\{AOL\}}
N -1140 -300 -1090 -300 {lab=GND}
C {devices/gnd.sym} -1140 -300 0 0 {name=g1 lab=GND}
N -1030 -300 -980 -300 {lab=int}
C {devices/lab_pin.sym} -980 -300 0 1 {name=p5 lab=int}
C {devices/lab_pin.sym} -1080 -340 0 0 {name=p6 lab=sum}
C {devices/lab_pin.sym} -1040 -340 0 1 {name=p7 lab=vcm}
C {devices/vsource_arith.sym} -800 -260 0 0 {name=E_COMP VOL=\{VCM\}+1.6*tanh(50*(v(int)-\{VCM\}))}
N -800 -320 -800 -290 {lab=comp}
C {devices/lab_pin.sym} -800 -320 1 0 {name=p8 lab=comp}
C {devices/gnd.sym} -800 -230 0 0 {name=g2 lab=GND}
C {devices/switch_ngspice.sym} -560 -300 0 0 {name=S_M model=SW}
N -560 -360 -560 -330 {lab=comp}
C {devices/lab_pin.sym} -560 -360 1 0 {name=p9 lab=comp}
N -560 -270 -560 -240 {lab=m}
C {devices/lab_pin.sym} -560 -240 1 1 {name=p10 lab=m}
N -640 -300 -600 -300 {lab=vddl}
C {devices/lab_pin.sym} -640 -300 0 0 {name=p11 lab=vddl}
N -640 -280 -600 -280 {lab=clk}
C {devices/lab_pin.sym} -640 -280 0 0 {name=p12 lab=clk}
C {devices/capa.sym} -460 -180 0 0 {name=C_M value=100f}
N -460 -240 -460 -210 {lab=m}
C {devices/lab_pin.sym} -460 -240 1 0 {name=p13 lab=m}
C {devices/gnd.sym} -460 -150 0 0 {name=g3 lab=GND}
C {devices/switch_ngspice.sym} -300 -300 0 0 {name=S_S model=SW}
N -300 -360 -300 -330 {lab=m}
C {devices/lab_pin.sym} -300 -360 1 0 {name=p14 lab=m}
N -300 -270 -300 -240 {lab=qraw}
C {devices/lab_pin.sym} -300 -240 1 1 {name=p15 lab=qraw}
N -380 -300 -340 -300 {lab=clk}
C {devices/lab_pin.sym} -380 -300 0 0 {name=p16 lab=clk}
N -380 -280 -340 -280 {lab=GND}
C {devices/gnd.sym} -380 -280 0 0 {name=g4 lab=GND}
C {devices/capa.sym} -180 -180 0 0 {name=C_Q value=100f}
N -180 -240 -180 -210 {lab=qraw}
C {devices/lab_pin.sym} -180 -240 1 0 {name=p17 lab=qraw}
C {devices/gnd.sym} -180 -150 0 0 {name=g5 lab=GND}
C {devices/vsource_arith.sym} -40 -260 0 0 {name=E_Q VOL=3.3*u(v(qraw)-1.65)}
N -40 -320 -40 -290 {lab=q}
C {devices/lab_pin.sym} -40 -320 1 0 {name=p18 lab=q}
C {devices/gnd.sym} -40 -230 0 0 {name=g6 lab=GND}
C {devices/vsource_arith.sym} 120 -260 0 0 {name=E_QB VOL=3.3-v(q)}
N 120 -320 120 -290 {lab=qb}
C {devices/lab_pin.sym} 120 -320 1 0 {name=p19 lab=qb}
C {devices/gnd.sym} 120 -230 0 0 {name=g7 lab=GND}
C {devices/vsource_arith.sym} 280 -260 0 0 {name=E_DAC VOL=v(clk)>1.65?\{VCM\}:(v(q)>1.65?\{VREFP\}:\{VREFN\})}
N 280 -320 280 -290 {lab=dac}
C {devices/lab_pin.sym} 280 -320 1 0 {name=p20 lab=dac}
C {devices/gnd.sym} 280 -230 0 0 {name=g8 lab=GND}
C {devices/res.sym} 480 -300 3 0 {name=R_DAC value=\{RDAC\}}
N 400 -300 450 -300 {lab=dac}
C {devices/lab_pin.sym} 400 -300 0 0 {name=p21 lab=dac}
N 510 -300 560 -300 {lab=sum}
C {devices/lab_pin.sym} 560 -300 0 1 {name=p22 lab=sum}
T {sources} -1420 -160 0 0 0.35 0.35 {}
C {devices/vsource.sym} -1400 -40 0 0 {name=VCLK value="PULSE(0 3.3 0 \{TR\} \{TR\} \{PWH\} \{TS\})"}
N -1400 -100 -1400 -70 {lab=clk}
C {devices/lab_pin.sym} -1400 -100 1 0 {name=p23 lab=clk}
C {devices/gnd.sym} -1400 -10 0 0 {name=g9 lab=GND}
C {devices/vsource.sym} -1200 -40 0 0 {name=VIN value="SIN(\{VCM\} \{AMP\} \{FIN\})"}
N -1200 -100 -1200 -70 {lab=vin}
C {devices/lab_pin.sym} -1200 -100 1 0 {name=p24 lab=vin}
C {devices/gnd.sym} -1200 -10 0 0 {name=g10 lab=GND}
C {devices/vsource.sym} -1000 -40 0 0 {name=VCM_S value=\{VCM\}}
N -1000 -100 -1000 -70 {lab=vcm}
C {devices/lab_pin.sym} -1000 -100 1 0 {name=p25 lab=vcm}
C {devices/gnd.sym} -1000 -10 0 0 {name=g11 lab=GND}
C {devices/vsource.sym} -800 -40 0 0 {name=VDDL value=3.3}
N -800 -100 -800 -70 {lab=vddl}
C {devices/lab_pin.sym} -800 -100 1 0 {name=p26 lab=vddl}
C {devices/gnd.sym} -800 -10 0 0 {name=g12 lab=GND}
C {devices/code_shown.sym} 660 -200 0 0 {name=CONTROL only_toplevel=false value=".include params.spice
.model SW sw vt=1.65 vh=0.1 ron=100 roff=1e9
.ic v(int)=\{VCM\}
.tran \{TSTEP\} \{TSTOP\} uic
.control
run
wrdata tier1_out.csv v(q) v(clk) v(vin) v(int)
plot v(vin) v(int)
plot v(q) v(clk) v(dac) xlimit 0 2u
.endc
"}

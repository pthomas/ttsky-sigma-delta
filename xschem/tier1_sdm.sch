v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {1st-order CT sigma-delta modulator - tier 1 behavioral (RZ totem-pole feedback DAC)} -1700 -680 0 0 0.5 0.5 {}
T {values from spice/params.spice - run: python3 params.py (or make)} -1700 -640 0 0 0.3 0.3 {}
T {integrator} -1400 -260 0 0 0.35 0.35 {}
T {comparator} -1080 -240 0 0 0.35 0.35 {}
T {1-bit DAC (totem-pole, RZ: VCM while clk high)} -700 -600 0 0 0.35 0.35 {}
T {DOUT} -480 -260 0 0 0.35 0.35 {}
C {devices/lab_pin.sym} -1700 -200 0 0 {name=p1 lab=vin}
N -1700 -200 -1660 -200 {lab=vin}
C {devices/res.sym} -1630 -200 1 0 {name=R_IN value=\{RIN\}}
N -1600 -200 -1450 -200 {lab=sum}
N -1450 -200 -1400 -200 {lab=sum}
N -1450 -320 -1450 -200 {lab=sum}
N -1450 -450 -1450 -320 {lab=sum}
C {devices/lab_pin.sym} -1500 -200 0 0 {name=p2 lab=sum}
C {opamp_beh.sym} -1320 -180 0 0 {name=X_OTA AOL=\{AOL\} GBW=\{GBW\} SR=\{SR\}}
N -1440 -160 -1400 -160 {lab=vcm}
C {devices/lab_pin.sym} -1440 -160 0 0 {name=p3 lab=vcm}
N -1450 -320 -1360 -320 {lab=sum}
C {devices/capa.sym} -1330 -320 1 0 {name=C_INT value=\{CINT\}}
N -1300 -320 -1160 -320 {lab=int}
N -1160 -320 -1160 -180 {lab=int}
N -1240 -180 -1160 -180 {lab=int}
N -1160 -180 -1100 -180 {lab=int}
C {devices/lab_pin.sym} -1200 -180 0 0 {name=p4 lab=int}
C {comp_beh.sym} -1020 -160 0 0 {name=E_COMP}
N -1140 -140 -1100 -140 {lab=vcm}
C {devices/lab_pin.sym} -1140 -140 0 0 {name=p5 lab=vcm}
N -940 -160 -880 -160 {lab=comp}
N -880 -220 -880 -160 {lab=comp}
N -880 -220 -820 -220 {lab=comp}
C {devices/lab_pin.sym} -900 -160 0 0 {name=p6 lab=comp}
C {dff_beh.sym} -700 -180 0 0 {name=X_DFF}
N -860 -140 -820 -140 {lab=clk}
C {devices/lab_pin.sym} -860 -140 0 0 {name=p7 lab=clk}
N -580 -220 -500 -220 {lab=q}
C {devices/lab_pin.sym} -500 -220 0 1 {name=p8 lab=q}
N -580 -140 -520 -140 {lab=qb}
C {devices/lab_pin.sym} -520 -140 0 1 {name=p9 lab=qb}
N -300 -560 -300 -530 {lab=vrefp}
C {devices/lab_pin.sym} -300 -560 1 0 {name=p10 lab=vrefp}
C {devices/switch_ngspice.sym} -300 -500 0 0 {name=S_TOP model=SW}
N -400 -500 -340 -500 {lab=q}
C {devices/lab_pin.sym} -400 -500 0 0 {name=p11 lab=q}
N -460 -480 -340 -480 {lab=clk}
C {devices/lab_pin.sym} -460 -480 0 0 {name=p12 lab=clk}
N -300 -470 -300 -430 {lab=dac}
C {devices/switch_ngspice.sym} -300 -400 0 0 {name=S_BOT model=SW}
N -400 -400 -340 -400 {lab=qb}
C {devices/lab_pin.sym} -400 -400 0 0 {name=p13 lab=qb}
N -460 -380 -340 -380 {lab=clk}
C {devices/lab_pin.sym} -460 -380 0 0 {name=p14 lab=clk}
N -300 -370 -300 -340 {lab=vrefn}
C {devices/lab_pin.sym} -300 -340 1 1 {name=p15 lab=vrefn}
N -530 -450 -300 -450 {lab=dac}
C {devices/lab_pin.sym} -380 -450 0 0 {name=p16 lab=dac}
N -300 -450 -190 -450 {lab=dac}
C {devices/switch_ngspice.sym} -160 -450 1 0 {name=S_MID model=SW}
N -130 -450 -100 -450 {lab=vcm}
C {devices/lab_pin.sym} -100 -450 0 1 {name=p17 lab=vcm}
N -160 -520 -160 -490 {lab=clk}
C {devices/lab_pin.sym} -160 -520 1 0 {name=p18 lab=clk}
N -240 -490 -180 -490 {lab=GND}
C {devices/gnd.sym} -240 -490 0 0 {name=g1 lab=GND}
C {devices/res.sym} -560 -450 1 0 {name=R_DAC value=\{RDAC\}}
N -1450 -450 -590 -450 {lab=sum}
T {sources} -1780 100 0 0 0.35 0.35 {}
C {devices/vsource.sym} -1650 100 0 0 {name=VCLK value="PULSE(0 3.3 0 \{TR\} \{TR\} \{PWH\} \{TS\})"}
N -1650 40 -1650 70 {lab=clk}
C {devices/lab_pin.sym} -1650 40 1 0 {name=p19 lab=clk}
C {devices/gnd.sym} -1650 130 0 0 {name=g2 lab=GND}
C {devices/vsource.sym} -1450 100 0 0 {name=VIN value="SIN(\{VCM\} \{AMP\} \{FIN\})"}
N -1450 40 -1450 70 {lab=vin}
C {devices/lab_pin.sym} -1450 40 1 0 {name=p20 lab=vin}
C {devices/gnd.sym} -1450 130 0 0 {name=g3 lab=GND}
C {devices/vsource.sym} -1250 100 0 0 {name=VCM_S value=\{VCM\}}
N -1250 40 -1250 70 {lab=vcm}
C {devices/lab_pin.sym} -1250 40 1 0 {name=p21 lab=vcm}
C {devices/gnd.sym} -1250 130 0 0 {name=g4 lab=GND}
C {devices/vsource.sym} -1050 100 0 0 {name=VREFP_S value=\{VREFP\}}
N -1050 40 -1050 70 {lab=vrefp}
C {devices/lab_pin.sym} -1050 40 1 0 {name=p22 lab=vrefp}
C {devices/gnd.sym} -1050 130 0 0 {name=g5 lab=GND}
C {devices/vsource.sym} -850 100 0 0 {name=VREFN_S value=\{VREFN\}}
N -850 40 -850 70 {lab=vrefn}
C {devices/lab_pin.sym} -850 40 1 0 {name=p23 lab=vrefn}
C {devices/gnd.sym} -850 130 0 0 {name=g6 lab=GND}
C {devices/code_shown.sym} 40 -560 0 0 {name=CONTROL only_toplevel=false value=".include params.spice
.model SW sw vt=1.65 vh=0.1 ron=100 roff=1e9
* behavioral OTA: single-pole, slew-limited (AOL, GBW [Hz], SR [V/s])
.subckt ota_beh PLUS MINUS OUT AOL=10000 GBW=200e6 SR=2e8
.param CI=100f
.param GMI=\{6.2831853*GBW*CI\}
.param ILIM=\{SR*CI\}
.param RO=\{AOL/GMI\}
B_GM 0 x I=\{ILIM\}*tanh(\{GMI\}*(v(PLUS)-v(MINUS))/\{ILIM\})
R_O x 0 \{RO\}
C_O x 0 \{CI\}
E_BUF OUT 0 x 0 1
.ends
* behavioral DFF: master/slave sample-and-hold of D at rising CLK edge
.subckt dff_beh D CLK Q QB
V_L vddl 0 3.3
S_M D m vddl CLK SW
C_M m 0 100f
S_S m qraw CLK 0 SW
C_Q qraw 0 100f
E_Q Q 0 VOL='1.65+1.65*tanh(20*(v(qraw)-1.65))'
E_QB QB 0 VOL='3.3-v(Q)'
.ends
.ic v(int)=\{VCM\}
.tran \{TSTEP\} \{TSTOP\} uic
.control
run
write tier1_sdm.raw
wrdata tier1_out.csv v(q) v(clk) v(vin) v(int)
.endc
"}
B 2 -1780 260 -380 660 {flags=graph
y1=0.8
y2=2.6
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=2e-6
divx=5
subdivx=1
node="vin
int"
color="4 7"
dataset=-1
unitx=1
logx=0
logy=0
}
B 2 -1780 700 -380 1100 {flags=graph
y1=-0.2
y2=3.5
ypos1=0
ypos2=2
divy=5
subdivy=1
unity=1
x1=0
x2=2e-6
divx=5
subdivx=1
node="clk
q
dac"
color="4 15 7"
dataset=-1
unitx=1
logx=0
logy=0
}
T {waveforms: click Netlist, then Simulate (silent, ~10 s), then Ctrl-click LOAD WAVES below.} -1780 200 0 0 0.3 0.3 {}
T {f = zoom full, right-drag = zoom box, a/b = measurement cursors} -1780 230 0 0 0.3 0.3 {}
C {devices/launcher.sym} -600 220 0 0 {name=h5
descr="LOAD WAVES (Ctrl-click)"
tclcommand="xschem raw_read $netlist_dir/[file tail [file rootname [xschem get current_name]]].raw tran"
}
T {to add a trace: double-click a graph (dialog opens), then click a net in the schematic and press k - it drops into the node list} -1780 1120 0 0 0.3 0.3 {}

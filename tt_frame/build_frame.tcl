# Build the TinyTapeout 1x2 (3.3V) analog frame for tt_um_pthomas_sigma_delta
# Based on TinyTapeout's magic_init_project.tcl (Apache-2.0, (c) Tiny Tapeout LTD)
# Extended to place the sigma-delta blocks from the design repo
# (https://gitlab.com/pthomas1/sigma-delta) inside the frame.
#
# Run: PDK_ROOT=... magic -dnull -noconsole \
#        -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc \
#        build_frame.tcl        (from the tt_frame/ directory)

set TOP_LEVEL_CELL     tt_um_pthomas_sigma_delta
set TEMPLATE_FILE      tt_analog_1x2_3v3.def
set POWER_STRIPE_WIDTH 2um                 ;# minimum width is 1.2um
set DESIGN_MAG         $env(SIGMA_DELTA_MAG)   ;# path to design repo mag/

set POWER_STRIPES {
    VDPWR 1um
    VGND  4um
    VAPWR 7um
}

# Read in the pin positions
def read $TEMPLATE_FILE
cellname rename tt_um_template $TOP_LEVEL_CELL
load $TOP_LEVEL_CELL

# Draw the power stripes
proc draw_power_stripe {name x} {
    global POWER_STRIPE_WIDTH
    box $x 5um $x 220.76um
    box width $POWER_STRIPE_WIDTH
    paint met4
    label $name FreeSans 0.25u -met4
    port make
    port use [expr {$name eq "VGND" ? "ground" : "power"}]
    port class bidirectional
    port connections n s e w
}
foreach {name x} $POWER_STRIPES {
    puts "Drawing power stripe $name at $x"
    draw_power_stripe $name $x
}

# Place the OTA (119 x 73 um core + routing bus): clear of the power
# stripes (x < 10um) and the top/bottom 10um pad-ring keepouts
addpath $DESIGN_MAG
box 10um 120um 10um 120um
getcell ota_layout child 0um 0um

# --- v0 analog pin wiring: ua[0] -> OTA INP, ua[1] -> OTA OUT ----------
# Precheck requires declared analog pins to carry adjacent metal (and
# VAPWR requires >= 1 analog pin). Both pads route on met4 stubs at the
# bottom edge, rise on met3 at the right of the OTA footprint, run west
# in a corridor above all OTA metal (OTA m3 tops out at y=207.4), and
# drop onto the INP/OUT nets' own met3 riser tops (slot x from
# mag/ota_layout.mag labels: INP slot 0 -> x 9.8-10.2, riser top y
# 197.01; OUT slot 25 -> x 34.8-35.2, riser top y 199.41). Regenerate
# these coordinates if the OTA floorplan changes.
proc wire {x1 y1 x2 y2 layer} {
    box ${x1}um ${y1}um ${x2}um ${y2}um
    paint $layer
}
# The two paths interleave (INP at x10, OUT at x35, both pads at the
# bottom right): INP takes the OUTER right-edge vertical and the UPPER
# corridor, OUT the inner vertical and lower corridor, each corridor
# stopping short of the other's vertical -- no met3 crossings.
# ua[0] (pad met4 at x 136.17-137.07, y 0-1) -> INP
wire 136.17 0    143.5  1.4   met4   ;# jog east from pad
wire 142.6  0.3  143.4  1.1   via3   ;# up to met3
wire 142.5  0.2  143.5  212.3 met3   ;# outer rise to upper corridor
wire 9.7    211.7 143.5 212.3 met3   ;# upper corridor west
wire 9.8    196.5 10.2  212.3 met3   ;# drop onto INP riser top
# ua[1] (pad met4 at x 116.85-117.75, y 0-1) -> OUT
wire 116.85 0    117.75 3.6   met4   ;# stub north from pad
wire 116.85 2.2  141.3  3.6   met4   ;# jog east (above ua[0]'s jog)
wire 140.4  2.4  141.2  3.2   via3
wire 140.3  2.3  141.3  210.3 met3   ;# inner rise to lower corridor
wire 34.7   209.7 141.3 210.3 met3   ;# lower corridor west
wire 34.8   199.0 35.2  210.3 met3   ;# drop onto OUT riser top

# Save; the GDS/LEF export runs in a SECOND magic process (export.tcl):
# after getcell, magic's notion of the current cell is unreliable and
# lef write kept exporting the OTA instead of the frame
save ${TOP_LEVEL_CELL}.mag
puts "FRAME BUILD DONE"
quit -noprompt

# Build the TinyTapeout 2x2 (3.3V) analog frame for tt_um_pthomas_sigma_delta
# Based on TinyTapeout's magic_init_project.tcl (Apache-2.0, (c) Tiny Tapeout LTD)
# Extended to place the assembled sigma-delta modulator (sd_top) from the
# design repo (https://gitlab.com/pthomas1/sigma-delta) inside the frame.
#
# sd_top was assembled in FRAME coordinates: its die matches the 2x2
# template (319.24 x 225.76 um) and its signal pin labels sit at the
# def's exact pin positions (ua[0] 136.62/0.5, ua[1] 117.30/0.5,
# uo_out[0] 78.66/225.26, uo_out[1] 75.90/225.26, clk 128.34/225.26,
# all met4) -- `def read` places the template pin geometry, sd_top's
# label legs arrive vertically at the same coordinates, and the
# overlapping met4 connects them. Power comes from three full-height
# met4 stripes drawn in lanes verified met4-free against the assembled
# design (tools/asm_route.py lane scan, DESIGN.md 2026-07-20), each
# tied to its net by a short met3 spur + via3 onto an existing run.
#
# Run: PDK_ROOT=... SIGMA_DELTA_MAG=<repo>/mag magic -dnull -noconsole \
#        -rcfile $PDK_ROOT/sky130A/libs.tech/magic/sky130A.magicrc \
#        build_frame.tcl        (from the tt_frame/ directory)

set TOP_LEVEL_CELL     tt_um_pthomas_sigma_delta
set TEMPLATE_FILE      tt_analog_2x2_3v3.def
set DESIGN_MAG         $env(SIGMA_DELTA_MAG)   ;# path to design repo mag/

# Read in the pin positions
def read $TEMPLATE_FILE
cellname rename tt_um_template $TOP_LEVEL_CELL
load $TOP_LEVEL_CELL

# Place the assembled modulator at the origin (frame coordinates)
addpath $DESIGN_MAG
box 0um 0um 0um 0um
getcell sd_top child 0um 0um

# --- power stripes -----------------------------------------------------
# Full-height vertical met4, >= 1.2um wide, in met4-free lanes:
#   VDPWR x 221.0-223.0  (lane 219.7-229.7)
#   VGND  x 256.0-258.0  (lane 255.3-270.4)
#   VAPWR x 310.0-312.0  (lane 309.3-319.2)
proc draw_power_stripe {name x1 x2} {
    # the label must cover the FULL stripe: precheck requires each
    # power port's LEF geometry to reach within 10um of both the top
    # and bottom tile edges (a mid-stripe label patch fails with
    # "Port too far from bottom/top edge")
    box ${x1}um 5um ${x2}um 220.76um
    paint met4
    label $name FreeSans 0.25u -met4
    port make
    port use [expr {$name eq "VGND" ? "ground" : "power"}]
    port class bidirectional
    port connections n s e w
}
draw_power_stripe VDPWR 221.0 223.0
draw_power_stripe VGND  256.0 258.0
draw_power_stripe VAPWR 310.0 312.0

# --- stripe-to-design spurs -------------------------------------------
# Each stripe ties to its net through a met3 spur landing on an
# existing sd_top run of the same net, with a via3 under the stripe.
proc spur {x1 y1 x2 y2} {
    box ${x1}um ${y1}um ${x2}um ${y2}um
    paint met3
}
proc via3_at {x y} {
    set h 0.17
    box [expr {$x-$h}]um [expr {$y-$h}]um [expr {$x+$h}]um [expr {$y+$h}]um
    paint via3
    set p 0.25
    box [expr {$x-$p}]um [expr {$y-$p}]um [expr {$x+$p}]um [expr {$y+$p}]um
    paint met3
    paint met4
}
# VDPWR: extend the y=210 odrv supply run (ends x~219.4) under the stripe
spur 219.1 209.7 222.6 210.3
via3_at 222.0 210.0
# VGND: the bufn.VSS -> rlp.B run crosses the stripe lane at y=62
via3_at 257.0 62.0
# VAPWR: extend the y=9 bufn.VDD -> rlt.R1 run (x240-286.5) east
spur 286.0 8.7 311.6 9.3
via3_at 311.0 9.0

# Save; the GDS/LEF export runs in a SECOND magic process (export.tcl):
# after getcell, magic's notion of the current cell is unreliable and
# lef write kept exporting the wrong cell
save ${TOP_LEVEL_CELL}.mag
puts "FRAME BUILD DONE"
quit -noprompt

# Layout: mask geometry, generated and interrogated

The OTA layout is not drawn — it is **generated**. Two scripts drive magic
in batch mode:

- `tools/gen_ota_layout.py` instantiates the 13 devices as PDK gencells
  (fingered, guard-ringed), measures each bounding box, and places them in
  analog rows with the floorplan recorded as JSON;
- `tools/route_ota.py` reads that manifest, the extracted port coordinates
  of every device, and the **golden netlist** (the xschem schematic's
  SPICE output), then paints source/drain/gate straps on met2, riser
  columns on met3, and a horizontal met1 track bus — every wire derived
  from the netlist it must implement. The router self-audits: same-layer
  overlaps between boxes assigned to different nets are reported *before*
  anything is painted.

Verification is a chain with no human transcription in it: magic
re-extracts the painted layout and the result is structurally compared
against the golden netlist device by device, then netgen runs full LVS.

**Current verdicts (from this build's pipeline):**

{{layout_status}}

## Two war stories your DRC flow should inherit

**The false clean.** magic's batch DRC on a freshly loaded cell reports
0 errors even when violations exist, because subcell instances default to
unexpanded and hierarchy-crossing checks are silently skipped. Every DRC
number in this project therefore comes from a fresh magic process that
explicitly expands the hierarchy before checking — and the checker itself
was validated by deliberately injecting a violation and confirming it gets
caught.

**The false dirty.** After routing, a fresh reload showed 894 violations —
poly-contact spacing and sub-minimum-width slivers *inside the PDK's own
device generators*, which should be correct by construction. Two plausible
root-cause theories (routing strap heights, guard-ring corners) failed to
explain the coordinates. The actual culprit, proven by an isolated
load-then-save experiment: magic's `writeall force` rewrites **unmodified**
subcells lambda-normalized without their `magscale` header, halving every
coordinate — and the gencells' odd 0.005 µm coordinates (a 0.235 µm
spacing is 47 units of 5 nm) don't survive the round trip
(47 → 23 → 46 units = 0.230 µm < 0.235 µm). All 894 violations were
manufactured by the *file writer*, not the layout. The fix: the router
saves only the cell it painted, and the DRC verdict above is computed from
the saved files in a separate process — the only number that reflects
what's actually on disk.

## The geometry itself

What tapes out is **GDSII** — the stacked 2D polygons, layer by layer,
that become lithography masks. Below is this build's actual OTA geometry,
extruded through the sky130 process stack (diffusion and poly at the
bottom; local interconnect; then met1–met3 with their vias). Drag to
orbit, scroll to zoom, toggle layers; the z axis is exaggerated (the full
stack is ~3.6 µm tall on a ~200 µm die footprint).

{{viewer3d}}

{{gds_link}}

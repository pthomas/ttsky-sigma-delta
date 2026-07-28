![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg)

# Continuous-Time Sigma-Delta ADC (sky130, TinyTapeout)

**📖 Design document & results: <https://pthomas1.gitlab.io/sigma-delta/>**

A first-order continuous-time sigma-delta modulator analog-to-digital
converter, designed entirely as code: generated schematics, generated
layout, tiered verification, and a continuously rebuilt design document.

- **Living design document** (CI-generated, start here):
  <https://pthomas1.gitlab.io/sigma-delta/> — every number on it was
  produced by the pipeline that published it.
- **TinyTapeout submission**: this repo doubles as the TT project
  ([docs/info.md](docs/info.md), `info.yaml`, `gds/`, `lef/`); the frame
  is rebuilt from `mag/` with `make tt`. Shuttle entry:
  <https://app.tinytapeout.com/projects/5413> (TTSKY26c).
- **Decision log**: [DESIGN.md](DESIGN.md) (append-only, with reopen
  conditions). **Session state**: [STATUS.md](STATUS.md).

Primary home: https://gitlab.com/pthomas1/sigma-delta — mirrored to
GitHub for the TinyTapeout toolchain.

## Goals

One modulator, one 50 MHz bitstream; the companion FPGA (PolarFire SoC)
runs two concurrent decimation paths on it:

| Path | Bandwidth | Target resolution | Use |
|---|---|---|---|
| Fast | ~1 MHz | ≥ 6 ENOB | protection / trip |
| Precision | ~100 kHz | 10–12 ENOB | measurement |

Platform: TinyTapeout 2x2 analog tiles (TTSKY26c shuttle, sky130A),
3.3 V analog + 1.8 V digital supplies, clean external clock, 0–3.3 V
input range. Measured results live on the
[generated design document](https://pthomas1.gitlab.io/sigma-delta/) —
this README stays number-free so it can't go stale.

## Reproduce

Toolchain: ngspice, xschem, magic + netgen (source-built), sky130A PDK
via ciel. See STATUS.md ("How to drive everything") and
`ci/lxd/cloud-init.yml` (the executable form of the toolchain setup).

## License

Apache-2.0.

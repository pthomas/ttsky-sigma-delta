![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg)

# Continuous-Time Sigma-Delta ADC (sky130, TinyTapeout)

A first-order continuous-time sigma-delta modulator analog-to-digital
converter, designed entirely as code: generated schematics, generated
layout, tiered verification, and a continuously rebuilt design document.

- **Living design document** (CI-generated, start here): the GitLab Pages
  site of this repo — every number on it was produced by the pipeline
  that published it.
- **TinyTapeout submission**: this repo doubles as the TT project
  ([docs/info.md](docs/info.md), `info.yaml`, `gds/`, `lef/`); the frame
  is rebuilt from `mag/` with `make tt`.
- **Decision log**: [DESIGN.md](DESIGN.md) (append-only, with reopen
  conditions). **Session state**: [STATUS.md](STATUS.md).

Primary home: https://gitlab.com/pthomas1/sigma-delta — mirrored to
GitHub for the TinyTapeout toolchain.

## Reproduce

Toolchain: ngspice, xschem, magic + netgen (source-built), sky130A PDK
via ciel. See STATUS.md ("How to drive everything") and
`ci/lxd/cloud-init.yml` (the executable form of the toolchain setup).

## License

Apache-2.0.

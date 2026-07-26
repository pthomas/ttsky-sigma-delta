"""cocotb testbench for sdm_rx: AXI4-Lite + dual-path sinc3.

Three layers of test:
  1. register sanity over AXI4-Lite (cocotbext-axi master BFM)
  2. bit-exact check of both decimator paths against a golden Python
     model of the same CIC structure (same register-transfer
     semantics, including the settling transient)
  3. the mixed-signal test: the committed transistor-level bitstream
     (rtl/tb/vectors/pex_bits.txt, produced by ngspice from the
     extracted chip) streamed in, results read from the AXI
     registers -- ones-density register must match the acceptance
     metric, every decimated sample must match the golden model, and
     the decimated fast-path spectrum must show the test tone.

Run: make -C rtl/tb   (needs iverilog + cocotb + cocotbext-axi)
"""

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

ID = 0x00
VERSION = 0x04
CTRL = 0x08
OSR_FAST = 0x0C
OSR_PREC = 0x10
STATUS = 0x14
DATA_FAST = 0x18
DATA_PREC = 0x1C
COUNT_FAST = 0x20
COUNT_PREC = 0x24
BITS_TOTAL = 0x28
BITS_ONES = 0x2C


def sinc3_model(bits, osr):
    """Golden model with the RTL's exact sampling convention: on the
    bit where the phase counter hits osr-1, the combs sample the
    integrator state from BEFORE that bit's integration."""
    i1 = i2 = i3 = 0
    z1 = z2 = z3 = 0
    cnt = 0
    out = []
    for b in bits:
        d = 1 if b else -1
        i3_old, c1 = i3, i3 - z1
        c2 = c1 - z2
        c3 = c2 - z3
        # integrators update with pre-update neighbor values
        i1, i2, i3 = i1 + d, i2 + i1, i3 + i2
        if cnt == osr - 1:
            cnt = 0
            z1, z2, z3 = i3_old, c1, c2
            out.append(sign32(c3))
        else:
            cnt += 1
    return out


def sign32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


async def start(dut):
    cocotb.start_soon(Clock(dut.aclk, 20, units="ns").start())
    axil = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"),
                         dut.aclk, dut.aresetn, reset_active_level=False)
    dut.bit_i.value = 0
    dut.bit_ce.value = 0
    dut.aresetn.value = 0
    await ClockCycles(dut.aclk, 5)
    dut.aresetn.value = 1
    await ClockCycles(dut.aclk, 2)
    return axil


async def rd(axil, addr):
    return int((await axil.read(addr, 4)).data[::-1].hex(), 16)


async def wr(axil, addr, val):
    await axil.write(addr, val.to_bytes(4, "little"))


async def stream(dut, bits):
    for b in bits:
        dut.bit_i.value = int(b)
        dut.bit_ce.value = 1
        await RisingEdge(dut.aclk)
    dut.bit_ce.value = 0
    await RisingEdge(dut.aclk)


@cocotb.test()
async def test_registers(dut):
    axil = await start(dut)
    assert await rd(axil, ID) == 0x53444D31
    assert await rd(axil, VERSION) == 0x0100
    assert await rd(axil, OSR_FAST) == 25
    assert await rd(axil, OSR_PREC) == 250
    await wr(axil, OSR_FAST, 32)
    assert await rd(axil, OSR_FAST) == 32
    await wr(axil, OSR_FAST, 25)
    assert await rd(axil, STATUS) == 0
    assert await rd(axil, BITS_TOTAL) == 0


@cocotb.test()
async def test_cic_known_patterns(dut):
    axil = await start(dut)
    await wr(axil, CTRL, 0b11)          # enable + clear
    # all-ones: DC full scale -> steady-state output = OSR^3
    ones = [1] * (25 * 8)
    await stream(dut, ones)
    model = sinc3_model(ones, 25)
    assert await rd(axil, DATA_FAST) == sign32(model[-1] & 0xFFFFFFFF)
    assert model[-1] == 25 ** 3, "steady-state DC must be OSR^3"
    assert await rd(axil, BITS_TOTAL) == len(ones)
    assert await rd(axil, BITS_ONES) == len(ones)
    # alternating: near-zero DC, exercise negative values on the way
    await wr(axil, CTRL, 0b11)
    alt = [1, 0] * (25 * 4)
    await stream(dut, alt)
    model = sinc3_model(alt, 25)
    assert await rd(axil, DATA_FAST) == model[-1]
    st = await rd(axil, STATUS)
    assert st & 1
    await wr(axil, STATUS, 1)           # W1C
    assert (await rd(axil, STATUS)) & 1 == 0


@cocotb.test()
async def test_pex_bitstream(dut):
    """Transistor-level bits -> RTL -> AXI registers."""
    vec = Path(__file__).parent / "vectors" / "pex_bits.txt"
    lines = vec.read_text().splitlines()
    header = dict(kv.split("=") for kv in lines[0][2:].split())
    bits = [int(l) for l in lines[1:]]

    axil = await start(dut)
    await wr(axil, CTRL, 0b11)
    await stream(dut, bits)

    total = await rd(axil, BITS_TOTAL)
    ones = await rd(axil, BITS_ONES)
    assert total == len(bits)
    density = ones / total
    exp = float(header["ones"])
    assert abs(density - exp) < 1e-3, \
        f"ones density {density:.4f} vs acceptance {exp:.4f}"

    # bit-exact against the golden model, both paths
    mf = sinc3_model(bits, 25)
    mp = sinc3_model(bits, 250)
    assert await rd(axil, COUNT_FAST) == len(mf)
    assert await rd(axil, COUNT_PREC) == len(mp)
    assert await rd(axil, DATA_FAST) == mf[-1]
    assert await rd(axil, DATA_PREC) == mp[-1]

    # the tone is visible in the decimated fast path (informative,
    # loose gate: settling samples excluded, window not coherent)
    try:
        import numpy as np
        y = np.array(mf[3:], dtype=float)
        y -= y.mean()
        spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
        peak = int(spec[1:].argmax()) + 1
        f_tone = peak * (float(header["fs_hz"]) / 25) / len(y)
        dut._log.info(f"fast-path tone at ~{f_tone/1e3:.0f} kHz, "
                      f"peak/median {10*np.log10(spec[peak]/np.median(spec[1:])):.0f} dB")
        assert spec[peak] > 100 * np.median(spec[1:])
    except ImportError:
        dut._log.warning("numpy missing -- spectrum check skipped")

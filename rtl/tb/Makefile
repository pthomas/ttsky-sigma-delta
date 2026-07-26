# cocotb testbench for sdm_rx.
#   make            -> run all tests under Icarus Verilog
#   make SIM=verilator  (optional, needs verilator >= 5)
# Needs: iverilog, pip install cocotb cocotbext-axi

SIM ?= icarus
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(PWD)/../sdm_rx.v
TOPLEVEL = sdm_rx
MODULE = test_sdm_rx

include $(shell cocotb-config --makefiles)/Makefile.sim

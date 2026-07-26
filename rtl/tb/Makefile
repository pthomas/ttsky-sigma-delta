# cocotb testbench for sdm_rx.
#   make            -> run all tests under Icarus Verilog
#   make WAVES=1    -> also dump sim_build/sdm_rx.fst (view with gtkwave)
#   make SIM=verilator  (optional, needs verilator >= 5)
# Needs: iverilog, pip install cocotb cocotbext-axi

SIM ?= icarus
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(PWD)/../sdm_rx.v
COCOTB_TOPLEVEL = sdm_rx
COCOTB_TEST_MODULES = test_sdm_rx

include $(shell cocotb-config --makefiles)/Makefile.sim

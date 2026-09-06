# Arty S7-50 image - September 6, 2026

For **xc7s50csga324-1**, with the Arty 12 MHz oscillator. Do not program an S7-25 with this image.

Program `debug_lab.bit` in Vivado Hardware Manager and select `debug_lab.ltx` as its probes file. The debug hub runs at 50 MHz. Start with 3 MHz JTAG for troubleshooting; 15 MHz meets the hub clock-ratio requirement for this image. UART is 115200, 8-N-1.

Built with Vivado 2026.1 using `scripts/rebuild_arty_debug.tcl` and the repository VHDL sources. Routed setup/hold slack: +3.775 ns / +0.018 ns. `debug_clocks.rpt` records the actual routed clocks; `sha256.json` identifies this bit/LTX pair. The AMD IP/probe/timing/clock artifact audit passed. No physical FPGA was connected for capture verification.

Follow [the capture guide](../../docs/capture_troubleshooting.md) to run an immediate capture and display the waveform, then arm an injected fault. Rebuild using [the root instructions](../../README.md) after changing FPGA sources.

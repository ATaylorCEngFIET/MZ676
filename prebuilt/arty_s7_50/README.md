# Arty S7-50 bitstream

For **xc7s50csga324-1**, with the Arty 12 MHz oscillator. Do not program an S7-25 with this image.

Program `debug_lab.bit` in Vivado Hardware Manager and select `debug_lab.ltx` as its probes file. The debug hub runs at 50 MHz. Start with 3 MHz JTAG for troubleshooting; 15 MHz meets the hub clock-ratio requirement for this image. UART is 115200, 8-N-1.

Built with Vivado 2026.1. Rebuild from the repository sources using `scripts/build.tcl`. Routed setup/hold slack: +3.775 ns / +0.018 ns. `debug_clocks.rpt` records the actual routed clocks; `sha256.json` identifies this bit/LTX pair. Timing, probe mappings and debug-clock checks passed. On-board capture has not been verified.

Follow [the capture guide](../../docs/capture_troubleshooting.md) to run an immediate capture and display the waveform, then arm an injected fault. Rebuild using [the root instructions](../../README.md) after changing FPGA sources.

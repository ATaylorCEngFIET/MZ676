# Validation

Tool versions: Vivado/XSim **2026.1**, Python **3.12.10**, Tk **8.6** on Windows.

## Simulation and host tests

- The VHDL regression passes 13 cases covering healthy operation, all six faults,
  removal of fault stimuli and recovery. Expected error masks for modes 0-6 are
  `00, 05, 06, 08, 01, 10, 20`. The tests pass with both the VHDL reference queue
  and AMD AXI4-Stream Data FIFO simulation model.
- UART-service tests cover independently timed AXI write channels, delayed read
  responses, TX FIFO backpressure, received-byte ordering and error flushing.
- Serial integration through AMD UARTLite and FIFO models checks identity,
  register access, malformed commands, partial-frame timeout, framing recovery,
  starting a fault and clearing it. Simulated duration: **37.74583 ms**.
- Board startup simulation checks MMCM lock, reset release, stopped/error-free
  initial state and a UART identity response.
- Fourteen Python host tests cover the protocol and GUI command ordering,
  polling, disconnects and error handling. The GUI preview is illustrative data.
- Five Tcl recipe tests check event/sticky masks, CDC completion, System ILA
  recipes and invalid/missing probe handling against the supplied LTX. Both
  capture scripts load in Vivado 2026.1.

Run the simulation and host commands listed in the [README](../README.md). Run
recipe tests with `python -m unittest discover -s scripts -p test_ila_recipes.py`.

## Arty S7-50 implementation

Results for the supplied `prebuilt/arty_s7_50/debug_lab.bit`:

| Result | Value |
|---|---:|
| Input clock | 12 MHz |
| Debug hub / fast ILA clock | 50 MHz |
| Slow ILA clock | 12.5 MHz |
| Worst setup slack | +3.775 ns |
| Worst hold slack | +0.018 ns |
| Worst pulse-width slack | +8.750 ns |
| Unconstrained internal endpoints | 0 |
| Slice LUTs | 10,991 / 32,600 (33.71%) |
| Slice registers | 18,153 / 65,200 (27.84%) |
| Block RAM tiles | 14 / 75 |
| DRC errors | 0 |

The routed DRC report contains three LUT-equation warnings and one
no-routable-loads warning inside the AMD debug hub. Bus-skew checks pass. The
related CDC clocks remain constrained; the injected pulse-loss fault is functional
and is not detected by timing analysis.

The main build script checks timing and debug clocks before exporting the bitstream
and probes. The [prebuilt folder](../prebuilt/arty_s7_50) contains the matching LTX,
routed clock report and SHA-256 checksums. All three ILA probe maps were checked,
including the System ILA AXI return signals.

## Hardware test status

On-board operation, ILA triggering and waveform upload have not been verified with
a connected FPGA. The advanced trigger state machine also needs validation in
Hardware Manager. See [the capture guide](capture_troubleshooting.md).

SP701 is an optional build profile. Match its input-clock argument to the actual
Si570 setting; the default is 33.333333 MHz. The published timing table and
prebuilt image above apply to Arty S7-50 only.

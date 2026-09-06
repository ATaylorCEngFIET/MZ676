# Validation: IP Integrator revision

Validated with Vivado/XSim **2026.1**, Python **3.12.10**, and Tk **8.6** on Windows. This revision replaces the earlier handwritten UART, storage FIFO and board wrapper. Old build results do not describe the current design.

## Completed functional checks

- The quick VHDL regression passes 13 experiment cases: healthy mode, all six faults, negative controls with required stimuli removed, and recovery to healthy operation. It also checks pending settings, range rejection and snapshot consistency.
- The same 13 cases pass against AMD's generated AXI4-Stream Data FIFO simulation model. Expected preset masks are **00, 05, 06, 08, 01, 10, 20** for modes 0 through 6. Mode 6 now isolates an accounting defect in the VHDL wrapper; AMD FIFO data stays correct.
- A VHDL UART-service test passes with address-first and data-first AXI writes, delayed read responses, delayed TX FIFO space, ordered received bytes and UART error flushing.
- The VHDL serial integration test passes through the actual AMD AXI UARTLite and FIFO models. It checks identity, register writes/readback, checksum/opcode/address rejection, partial-frame timeout, framing-error recovery, starting the AXI fault and clearing it through UART. Simulated duration: **37.74583 ms**.
- Fourteen Python host tests pass: eight protocol tests and six GUI polling/command-order regressions. The GUI preview and smoke test pass; the refreshed screenshot uses illustrative data and is not a hardware capture.
- The maintained `rtl/` and `sim/` directories contain only `.vhd` files. The board-facing wrapper is generated in VHDL. AMD-generated IP models may contain vendor Verilog/SystemVerilog internally.

The simulation runner checks for explicit completion markers, assertion failures and unbound components, so a missing vendor model cannot produce a passing result.

## Full design checks

The actual VHDL Arty board wrapper passes startup simulation with the MMCM, Processor System Reset, UARTLite, FIFO and debug IP present. It verifies clock lock, stopped/error-free initial status and a valid UART device-identity response.

Both board implementations originally completed bitstream generation and passed the original timing/interface audit. The September 6 correction explicitly clocks the debug hub at 50 MHz and adds a routed debug-clock audit. The Arty S7-50 is rebuilt for this correction; the earlier SP701 results below are historical and its image must be rebuilt before using the new audit.

| Result | Arty S7-50 (September 6) | SP701 (previous build) |
|---|---:|---:|
| Input clock configuration | 12 MHz | 33.333333 MHz |
| Worst setup slack | +3.775 ns | +9.009 ns |
| Worst hold slack | +0.018 ns | +0.032 ns |
| Worst pulse-width slack | +8.750 ns | +8.870 ns |
| Unconstrained internal endpoints | 0 | 0 |
| Slice LUTs | 10,991 / 32,600 (33.71%) | 11,003 / 64,000 (17.19%) |
| Slice registers | 18,153 / 65,200 (27.84%) | 18,153 / 128,000 (14.18%) |
| Block RAM tiles | 14 / 75 | 14 / 120 |
| DRC errors | 0 | 0 |

Each routed DRC report retains three LUT-equation warnings and one no-routable-loads warning inside AMD's generated debug hub. They did not prevent bitstream generation. The CDC reports classify the related-clock crossings as safely timed; this does not prevent the deliberately injected functional pulse loss.

Current artifacts are `build/ipi_arty_s7_50/debug_lab.bit` + `.ltx` and `build/ipi_sp701/debug_lab.bit` + `.ltx`. Reports and the generated `.xpr` are beside them. The corrected Arty SHA-256 hashes are in `build/artifact_sha256_arty_s7_50.json`; the old two-board manifest describes the earlier builds.

The advanced trigger example uses probe names verified in **both** LTX files. Hardware Manager's trigger-state-machine compilation and real trigger execution still require a connected FPGA and have not been claimed as tested.

## Hardware limits

No physical FPGA UART is connected in this workspace. On-board operation, ILA trigger execution and real captures remain untested. The SP701 image uses a **33.333333 MHz** input-clock assumption; match the build argument to the actual Si570 setting before programming. Both experiment clocks come from the MMCM and remain related in timing analysis.

## GUI polling and ILA recovery (September 6)

Background reads no longer toggle button states and foreground clicks wait for the current read. Six GUI regression tests cover this behavior, including cancelling a queued restart when the read fails. `scripts/hardware_capture.tcl` loads in Vivado 2026.1 and its hardware commands resolve. Real capture, trigger comparison acceptance and waveform display still require on-board testing. See [capture troubleshooting](capture_troubleshooting.md).

The corrected Arty artifact audit passes, including routed clock periods of 20 ns for the hub and fast ILA and 80 ns for the slow ILA. The matching bit/LTX pair, clock report and hashes are published under `prebuilt/arty_s7_50/`.

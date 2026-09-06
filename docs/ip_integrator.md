# IP Integrator implementation notes

The top-level design is `debug_system.bd`. Build it with `scripts/build.tcl`, open the generated project, then open **IP INTEGRATOR → Open Block Design**. Vivado generates `debug_system_wrapper.vhd`; there is no handwritten board-level wrapper.

## Blocks to inspect

| Block name | Type | Purpose |
|---|---|---|
| `clocks` | AMD Clocking Wizard 6.0 | Board oscillator to nominal 50 MHz and 12.5 MHz |
| `reset_controller` | AMD Processor System Reset 5.0 | Keep the control plane reset until the MMCM locks |
| `uart` | AMD AXI UARTLite 2.0 | 115200 baud, eight data bits, no parity, hardware RX/TX FIFOs |
| `control` | VHDL module reference | Service UARTLite over AXI-Lite and decode the GUI frames |
| `experiment` | VHDL module reference | Registers, stimulus, selectable faults and application checkers |
| `stream_fifo` | AMD AXI4-Stream Data FIFO 2.0 | Depth 16, four data bytes, TLAST, normal synchronous mode |
| `system_ila` | AMD System ILA 1.1 | Three bus monitors with protocol checks, 1024 samples |
| `ila_fast` | AMD ILA 6.2 | Six 32-bit native probes, advanced triggering, 1024 samples |
| `ila_slow` | AMD ILA 6.2 | One 64-bit probe on the slower clock, 1024 samples |
| `axi_monitor` | VHDL wire adapter | Present the deliberately faulty target's internal AXI write channels to System ILA |
| `heartbeat`, `heartbeat_bit`, `leds` | AMD Binary Counter, Slice, Concat | Front-panel activity and status |

The generated AMD files may include Verilog or encrypted implementation models. All project-authored RTL, module-reference wrappers and testbenches are VHDL. No AXI VIP or SystemVerilog testbench is used.

## Data and control paths

`control/M_AXI` connects directly to `uart/S_AXI`, mapped at byte address zero. A single initiator and a single peripheral need no interconnect. The VHDL service independently completes AW and W handshakes, polls the UART status, respects TX FIFO full, and flushes receive bytes after UART errors. It requires no MicroBlaze or software image.

`experiment/M_AXIS` connects to `stream_fifo/S_AXIS`. The FIFO's `M_AXIS` returns to `experiment/S_AXIS`. System ILA slots 0 and 1 attach to these actual bus connections. The FIFO is reset on each experiment restart, then traffic waits another 16 clocks for recovery. The VHDL occupancy counter observes accepted transfers; it does not control the vendor FIFO.

The exercise's intentionally faulty AXI target is separate from the UART control bus. Its deadlock therefore leaves the GUI control path operational. System ILA slot 2 observes this exercise. Explicitly wired AXI return signals are included in the LTX by `scripts/export_probes.tcl`; `scripts/audit_artifacts.py` checks the resulting maps.

The two experiment clocks come from the same MMCM and remain related in timing analysis. The CDC exercise demonstrates pulse loss and a corrected VHDL request/acknowledge transfer. The custom CDC logic and AXI target are retained because their faulty and corrected implementations are the teaching material.

## Reset and clock details

Processor System Reset's external and auxiliary inputs default to **active low** in this configuration. They are tied high; the debug-reset input is tied low. The MMCM `locked` output drives `dcm_locked`. The build checks the external/auxiliary polarity before continuing.

SP701's fractional input frequency can produce nominal clock metadata such as 49,999,999 Hz. VHDL module references accept propagated clock metadata rather than fixing it to an incompatible integer value. This does not change the intended nominal 50 MHz / 12.5 MHz clock rates. The actual Si570 configuration must match the build argument.

## Useful article sequence

1. Start in the block diagram: distinguish the control path, experiment path and debug instrumentation.
2. Prove healthy operation with sequence, packet and CDC counts.
3. Select a source handshake fault and compare System ILA protocol evidence with application checks.
4. Select the AXI target fault and recover through the independent UART control bus.
5. Trigger on a rare packet and investigate the lost-pulse crossing with both native ILAs.
6. Select the occupancy fault: show clean vendor-FIFO transfers alongside incorrect VHDL accounting.

The detailed trigger recipes are in `lab_guide.md`. Use the matching bitstream and LTX from the same `build/ipi_<board>` directory for captures.

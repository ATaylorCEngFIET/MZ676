# Register protocol

The GUI uses UART independently of the JTAG debug connection. One outstanding request is permitted. All packets have ten bytes:

| Byte | Request | Reply |
|---|---|---|
| 0 | `A5` | `A5` |
| 1 | Sequence, modulo 256 | Echo sequence |
| 2 | `01` read, `02` write | `00` success; `01` checksum; `02` opcode; `03` address error |
| 3 | 8-bit word register index | Echo index |
| 4–7 | 32-bit little-endian data | Read value / write readback |
| 8 | XOR of bytes 1–7 | XOR of bytes 1–7 |
| 9 | `5A` | `5A` |

No escaping is needed: after recognising A5, the parser consumes a fixed frame. Inter-byte timeout is 10 ms. A bad trailer is discarded without reply. Invalid opcodes/addresses and checksum errors cannot write registers. The PC validates checksum, sequence, address and identity. Mutating requests are not automatically retried after timeout because START may already have executed.

## Registers

All addresses below are hexadecimal **word indices**, not AXI byte addresses.

| Index | Access | Meaning |
|---|---|---|
| 00 | R | ID `53443701` |
| 01 | R/W | Read live status. Write command bits: 0 START, 1 STOP, 2 CLEAR+STOP, 3 SNAPSHOT |
| 02 | R/W | Pending mode, 0–6 |
| 03 | R/W | Pending words per packet, 2–256 |
| 04 | R/W | Pending stall cycles, 0–255 |
| 05 | R/W | Pending stall period, 2–65535 |
| 06 | R/W | Pending rare packet number, 32-bit, zero-based |
| 07 | R/W | Pending AXI address/data skew, 0–255 |
| 10 | R | Captured status |
| 11 | R | Captured sticky error bitmap |
| 12 | R | Accepted sink words |
| 13 | R | Completed expected packets |
| 14 | R | Expected stream word at first diagnostic |
| 15 | R | Observed sink word at first diagnostic |
| 16 | R | Sink packet index at first diagnostic |
| 17 | R | Cycle of first diagnostic |
| 18 | R | Completed AXI writes |
| 19 | R | CDC events sent |
| 1A | R | CDC events received; valid when completion bit is set |
| 1B | R | Experiment cycle count |
| 1C | R | FIFO debug word |
| 1D | R | Source packet index |
| 1E | R | Active mode |
| 1F | R | Implementation version, `00020000` (IP Integrator / AMD infrastructure) |

Status: bit 0 running; bit 1 any sticky error; bit 2 experiment resetting; bit 3 CDC complete; bits 6:4 active mode.

Error bits: 0 data sequence; 1 TLAST; 2 source payload stability under stall; 3 AXI response timeout; 4 CDC count mismatch; 5 FIFO occupancy mismatch.

Write SNAPSHOT first, then read 10–1F for a coherent snapshot. The GUI does this automatically. START holds the experiment in reset for 31 source clocks and latches all pending settings; this also resets the protocol checkers. Traffic starts after a further 16-clock FIFO recovery interval. The serial frame/register layout is unchanged from version 1. Counters are unsigned 32-bit and wrap. At 50 MHz the cycle counter wraps in approximately 85.9 seconds. STOP is an abort, not a protocol-draining operation. Inspect a capture from before STOP, or restart to clear protocol-checker state.

Out-of-range field writes leave their register unchanged, so the host checks readback. The GUI also rejects stall_cycles >= stall_period and warns through validation when selected stimuli cannot demonstrate the intended fault. Raw register writes remain useful for the negative-control tests (e.g. zero AXI skew).

First diagnostic fields capture the earliest event of any type. Expected/observed stream words directly diagnose data/TLAST failures only when those checks fire first. A stability, FIFO, AXI or CDC check can fire earlier; in those cases the stream fields are context, not the failing subsystem's data.

Example (from the project root):

```python
import sys
sys.path.insert(0, 'host')
from protocol import Device, Settings

device = Device('COM7')
try:
    device.start(Settings(mode=3, axi_skew=16))
    print(device.snapshot())
    device.stop()
finally:
    device.close()
```

The physical UART is AMD AXI UARTLite. Its local AXI byte offsets (RX 0, TX 4, status 8, control 12) are private to the VHDL service sequencer; they are not the GUI register indices above. A UART receive error clears the parser and flushes suspect receive bytes.

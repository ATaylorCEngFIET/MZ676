# Tcl ILA recipes

Source this once in the **Vivado GUI Tcl console**, after programming the supplied
Arty S7-50 bitstream and associating its matching LTX:

```tcl
source C:/hdl_projects/debugging_advanced/scripts/ila_recipes.tcl
```

Change that path to your checkout. Sourcing defines commands only. Each arm command
replaces that core's previous trigger setup, uses 1024 samples and captures **every
clock**. The scripts do not set the Python fault mode or start UART traffic.

For each run: select the mode in Python, **Clear + stop**, issue the Tcl arm command,
then **Apply + restart**. Finally upload and open the waveform with `lab_show_capture`.
The GUI status line must show the intended active mode. Changing its dropdown alone
does not apply the mode. Start with `lab_capture_now` if capture transport is uncertain.

## Native fast ILA: all six faults

| Python mode | Arm command | Trigger and evidence |
|---|---|---|
| 1 - AXI-Stream backpressure | `lab_arm_fault 1` | Flags bit 14: payload changed while stalled. Inspect a System ILA stream capture for changing TDATA with VALID=1, READY=0. |
| 2 - Packet TLAST counter | `lab_arm_fault 2` | Flags bit 13: incorrect TLAST. Count accepted sink beats in System ILA. |
| 3 - AXI-Lite split write | `lab_arm_fault 3` | Flags bit 15: response timeout. Native probe 5 shows channel acceptance and missing BVALID. |
| 4 - Rare packet corruption | `lab_arm_fault 4` | Flags bit 12: data mismatch. Inspect packet index (probe 2), expected word (probe 3), and System ILA sink data in a separate capture. |
| 5 - CDC lost pulse | `lab_arm_fault 5` | Flags bit 16: completed sent/received comparison failed. |
| 6 - FIFO simultaneous operations | `lab_arm_fault 6` | Flags bit 17: occupancy mismatch. Native probe 4 shows push, pop and wrapper occupancy. |

These recipes use 768 pre-trigger samples (15.36 us) and match the actual mode bits
as well as the event. After starting the experiment:

```tcl
lab_show_capture
```

For a diagnostic that also fires on an error already recorded, use e.g.
`lab_arm_fault 5 sticky`. This uses the corresponding sticky flag, eight bits above
the event flag. It cannot recover pre-error history when armed late. Healthy mode
is expected not to fire these fault-specific recipes.

## CDC: capture both domains

In Python select mode 5 and click Clear + stop. Before restarting, run:

```tcl
lab_arm_fault 5
lab_arm_cdc_slow
```

Click Apply + restart, then:

```tcl
lab_show_capture
lab_show_capture ila_slow
```

The slow ILA triggers on bit 39 (destination done). Its 768 pre-trigger samples
cover 61.44 us, enough for the roughly 24 us burst. Decode its 64-bit probe:

- Bits 31:0: received event count.
- Bit 33: CDC fault selected; must be 1 for mode 5.
- Bits 34/35: acknowledgement and synchronised request.
- Bits 36/37: synchronised pulse and its delayed copy; a rising edge increments the faulty receiver.
- Bits 38/39: source done and destination done.

Compare against healthy mode using **only** `lab_arm_cdc_slow`: healthy mode should
finish at 32/32; faulty mode should lose events. The native fast error trigger will
not fire in healthy mode. The two records have different sample periods and are
not aligned by sample index. Raw source pulse is not included in the present native
probe map; inspect its generation in `rtl/cdc_lab.vhd` alongside the captured count.

## System ILA: observe the bus cause

| Command | What it captures |
|---|---|
| `lab_arm_system source_stall` | Source TVALID=1 and TREADY=0; 256 pre-trigger samples. Useful for faults 1, 2 and FIFO accounting. A stall itself is legal and also occurs in healthy mode. |
| `lab_arm_system source_violation` | Source protocol-checker assertion; 768 pre-trigger samples. Useful for changing payload/TLAST during stalls. |
| `lab_arm_system sink_last` | An accepted sink TLAST; 768 pre-trigger samples. Count VALID AND READY beats to check packet length. TLAST alone is not proof of an error. |
| `lab_arm_system axi_address` | AWVALID; 32 pre-trigger samples, retaining the following separated write-data transfer. |
| `lab_arm_system axi_data` | WVALID; 32 pre-trigger samples for a data-first view. |

Read the result with:

```tcl
lab_show_capture system_ila
```

Use separate restarted runs to compare the initial AXI handshakes and the native
1024-cycle response timeout. A 1024-sample buffer cannot contain the whole interval
plus both pre/post-trigger history. All three System ILA interfaces are captured
on every sample regardless of which interface supplied the trigger.

These cores have no cross-trigger wiring in this image. Arming two cores gives
independent trigger points, not a guaranteed common timestamp. The first accepted
TLAST or first stall may be healthy even during a rare-fault run; use the native
mode-4 event/advanced trigger to locate the rare error.

## Rare packet: advanced trigger example

For a state sequence of **packet 10000 -> earlier stall -> data error**, use
[`rare_packet_10000.tsm`](rare_packet_10000.tsm) in the fast ILA advanced-trigger
editor. It is trigger-state-machine source, not a Tcl script to `source`.
To generate a different target (also set that target in Python):

```powershell
python scripts/make_trigger.py --flags debug_system_i/experiment_native0 --packet debug_system_i/experiment_native2 --target 8 --output build/rare_packet_8.tsm
```

Select advanced trigger mode, load/validate that file in Hardware Manager, retain
all-cycle capture, arm, then restart. The simpler `lab_arm_fault 4` needs no TSM.

## Validation limits

Probe names and widths are checked against the shipped Arty LTX. Automated Tcl
control-flow tests check compare masks, active-mode matching, reset/capture setup,
core selection and arm operations. The scripts also load in Vivado 2026.1. Physical
trigger execution and waveform display remain untested without a connected FPGA.

See [capture troubleshooting](capture_troubleshooting.md) if immediate capture fails.

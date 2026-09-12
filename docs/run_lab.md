# Arty S7-50 debug lab: runs and ILA signatures

Use this guide with the supplied Arty S7-50 bitstream, Python GUI and Tcl recipes.
The waveforms described below are expected from the RTL; they are not recorded
board captures. Each exercise includes the trigger, the evidence to inspect and
a healthy comparison.

## 1. Connect and check the setup

1. Connect the Arty S7-50 USB programming/UART port and power the board.
2. In Vivado Hardware Manager, open the target and program the FPGA with
   `prebuilt/arty_s7_50/debug_lab.bit`. Select the matching `debug_lab.ltx` as
   the probes file. Check that LED 2, MMCM locked, is on.
3. Start the Python GUI from PowerShell:

   ```powershell
   cd C:\hdl_projects\debugging_advanced
   python host/gui.py
   ```

   Select the FPGA UART COM port and click **Connect**. Do not use `--demo` for
   hardware testing. The UART configuration is 115200 baud, 8-N-1.
4. In the **Vivado Tcl console**, load the recipes:

   ```tcl
   source C:/hdl_projects/debugging_advanced/scripts/ila_recipes.tcl
   lab_capture_now
   lab_capture_now ila_slow
   lab_capture_now system_ila
   ```

   Each immediate capture should open a waveform, even with the experiment stopped.
   If it fails, use [capture troubleshooting](capture_troubleshooting.md) first.
   Try 3 MHz JTAG when diagnosing connection problems.

Use these GUI settings for every exercise unless an instruction changes one:

| GUI field | Value |
|---|---:|
| Words per packet | 16 |
| Stall cycles | 48 |
| Stall period | 64 |
| Rare packet (zero-based) | 8 for the first run; 10000 for the advanced exercise |
| AXI skew (cycles) | 16 |

The mode selection enables one faulty path. Stream, AXI-write and CDC traffic run
together. Changing the dropdown does **not** apply the mode until you click
**Apply + restart**. Confirm the active mode in the status line below the buttons.

### Use this order for every capture

1. Select the mode and settings in Python.
2. Click **Clear + stop** to clear old errors and completion flags.
3. Run the exercise's **Arm** commands in Vivado.
4. Click **Apply + restart** in Python.
5. Run the exercise's **Display** commands in Vivado.
6. Inspect and save the capture before starting the next run.

Do not click Stop while waiting for the fault: Stop aborts traffic and can itself
produce protocol symptoms. The capture completes while the experiment keeps running.
There is no need to stop it before uploading the waveform.

The Tcl recipes capture every clock. Keep this setting: handshake-only capture
would hide the stalled cycles needed to diagnose several faults.

## 2. Reading the traces

| Core | Sampling | Signals to use |
|---|---|---|
| `ila_fast` | 50 MHz, 20 ns/sample | `experiment_native0` through `experiment_native5` |
| `ila_slow` | 12.5 MHz, 80 ns/sample | `experiment_slow_debug[63:0]` |
| `system_ila` | 50 MHz, 20 ns/sample | SLOT_0_AXIS = FIFO input/source; SLOT_1_AXIS = FIFO output/sink; SLOT_2_AXI = AXI write experiment |

Use hexadecimal for TDATA and flags, unsigned decimal for counts and ages, and
individual bits for handshake/control signals. The native probe numbers below
refer to the corresponding `experiment_nativeN` vectors. The [full probe map](lab_guide.md#probe-map)
lists every field. Do not confuse the native flags word with the UART status word;
they use different bit positions.

**A stream transfer occurs only on a sampled edge with TVALID=1 and TREADY=1.**
Count those edges when checking sequence and packet length. During a stall,
TVALID remains asserted and the pending TDATA/TLAST must be held until acceptance.

The fault recipes use 1024 samples with 768 before the trigger: 15.36 us of history
on the fast ILA. The slow recipe gives 61.44 us of pre-trigger history. Error
latches can change a sample after the condition that caused them; inspect the
cycles immediately before the trigger as well as the trigger sample.

The three ILAs trigger independently. Arming two cores does not align their sample
indices or create a common trigger. Compare signal events and data values rather
than assuming that sample 768 represents the same instant in both captures.

## 3. Healthy baseline

Select **0 - Healthy baseline**, then Clear + stop.

**Arm:**

```tcl
lab_arm_system source_stall
lab_arm_cdc_slow
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture system_ila
lab_show_capture ila_slow
```

Expect increasing accepted stream words and AXI completed writes, **32/32** CDC
events and **No errors recorded**. In SLOT_0_AXIS, find TVALID=1/TREADY=0 and verify
that TDATA and TLAST stay fixed across the wait and into the accepting edge.
In the slow trace, the destination count finishes at 32. A stall is normal; the
incorrect handling of a stall is the fault in the next exercise.

Do not use `lab_arm_fault` for the healthy baseline: those triggers require a
specific faulty mode and error condition.

## 4. Fault 1: AXI-Stream backpressure

**GUI:** select **1 - AXI-Stream backpressure**, with the settings above. Clear + stop.

**Arm:**

```tcl
lab_arm_fault 1
lab_arm_system source_stall
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture
lab_show_capture system_ila
```

**Signature to find:**

- In System ILA **SLOT_0_AXIS**, TVALID stays high and TREADY is low, but **TDATA
  changes on successive stalled clocks**. The source counter is advancing without
  a transfer. Inspect the stalled clocks at and after the trigger.
- Fast probe 0 **bit 14** asserts: source payload changed after a stalled cycle.
  **Bit 22** latches that error; bit 1 becomes the overall sticky-error flag.
- At the FIFO output, accepted data later skips values because words were advanced
  while the FIFO could not accept them.
- GUI messages: **Payload changed while stalled** and **Data sequence mismatch**.
  Expected preset error bitmap: **0x05**.

This direct handshake trigger works for the healthy comparison as well. It does
not depend on the protocol checker's `pc_asserted` output. The separate
`lab_arm_system source_violation` recipe can wait indefinitely if that output
never asserts; use it as an additional checker investigation, not the first capture.

If the System ILA still waits, confirm the GUI says Running in mode 1 with 48/64
stalls, then try `lab_capture_now system_ila` while the experiment runs. This
replaces the waiting trigger and opens an immediate waveform. If immediate capture
works, inspect SLOT_0_AXIS TVALID/TREADY and the active trigger settings. If it
fails, troubleshoot capture transport and clocks. Check whether the native ILA
triggers and the GUI reports the expected errors; these are independent evidence
of whether the fault actually ran.

**Healthy comparison:** select mode 0 with the same stalls. TDATA/TLAST remain
stable while waiting; the data counter advances only on an accepted input beat.

## 5. Fault 2: packet TLAST counter

**GUI:** select **2 - Packet TLAST counter**. Keep 16 words/packet and 48/64 stalls.
Clear + stop.

**Arm:**

```tcl
lab_arm_fault 2
lab_arm_system sink_last
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture
lab_show_capture system_ila
```

**Signature to find:**

- Fast probe 0 **bit 13** asserts: the packet checker received an incorrect TLAST.
  **Bit 21** records the sticky packet error.
- In **SLOT_1_AXIS**, count only accepted beats. TLAST must accompany the 16th
  accepted word of each expected packet. Look for **TLAST missing on word 16, or
  asserted on a different word**. The first packet may be correct; inspect the
  following packet as well.
- In this mode TDATA is still an incrementing sequence from zero. With 16-word
  packets, an accepted word ending in hexadecimal `F` should have TLAST=1; other
  accepted words should have TLAST=0. This checks the intended boundary even if
  an earlier, incorrect TLAST has confused the transaction display.
- On the source side, TLAST can also change while stalled. The fault counts clock
  cycles rather than accepted transfers, so the protocol checker may flag it too.
- GUI: **Incorrect TLAST**, with **Payload changed while stalled** also expected
  for the preset run. Preset bitmap: **0x06**; bit 1 (`0x02`) is the packet error.

`sink_last` triggers on an accepted TLAST, not on proof that it is incorrect. If
its window misses the mismatch, repeat with `lab_arm_system source_violation`
to inspect the unstable TLAST and use the native trace to establish the packet error.

**Healthy comparison:** mode 0 has exactly 16 accepted words per packet. Stalls
stretch the packet in time but do not change its accepted-word count.

## 6. Fault 3: AXI-Lite split write

**GUI:** select **3 - AXI-Lite split write**, AXI skew **16**. Clear + stop.

**Arm:**

```tcl
lab_arm_fault 3
lab_arm_system axi_address
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture
lab_show_capture system_ila
```

**Signature to find:**

- In **SLOT_2_AXI**, the first transaction accepts its address on AWVALID AND
  AWREADY. Its WVALID/WREADY data handshake occurs separately, about 16 clocks later.
- Both transfers complete, BREADY is high, but **BVALID never asserts**. The faulty
  target only responds when the address and data handshakes occur on the same edge.
- Fast probe 5 **bits 1 and 2** show address/data accepted at the master;
  **bits 3 and 4** show the target remembered both. **Bit 5**, BVALID, stays low.
- Probe 5 **bits 31:16**, transaction age, advance to the 1024-clock timeout.
  **Bit 7** asserts; fast probe 0 **bit 15** reports the response timeout and
  **bit 23** latches it.
- GUI: **AXI response timeout**, bitmap **0x08**. AXI completed writes remain zero
  for this first deadlocked transaction. UART controls still work.

The System ILA uses trigger position 32 to retain the initial handshakes. The
native timeout trace has 768 pre-trigger samples, so it will not reach back to
the transaction's beginning. These captures answer different questions.

**Healthy comparison:** mode 0 with skew 16 accepts the independent channels and
then asserts BVALID. Completed-write count increases. A subsequent healthy
transaction reverses the channel order. AXI does not require simultaneous AW/W
handshakes; the 1024-clock deadline is this lab's application check.

## 7. Fault 4: rare packet corruption

**GUI:** select **4 - Rare packet corruption**, rare packet **8**, words/packet **16**,
stalls **48/64**. Packet numbering starts at zero. Clear + stop.

**Arm the native checker:**

```tcl
lab_arm_fault 4
```

For a System ILA capture of the same injected word, run this **before restarting**:

```tcl
set rare_ila [lab_recipe_setup system_ila 768]
set_property TRIGGER_COMPARE_VALUE eq32'h0000008E [lab_probe $rare_ila net_slot_0_axis_tdata]
set_property TRIGGER_COMPARE_VALUE eq1'b1 [lab_probe $rare_ila net_slot_0_axis_tvalid]
set_property TRIGGER_COMPARE_VALUE eq1'b1 [lab_probe $rare_ila net_slot_0_axis_tready]
set_property TRIGGER_COMPARE_VALUE eq1'b1 [lab_probe $rare_ila net_slot_0_axis_tlast]
run_hw_ila $rare_ila
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture
lab_show_capture system_ila
```

**Signature to find:**

- Packet 8 should contain data `0x80` through `0x8F`. Its last word has bit 0 flipped,
  so the accepted sequence ends **`... 0x8D, 0x8E, 0x8E`**, with TLAST on the second
  `0x8E`. The next packet resumes at `0x90`.
- The custom System ILA trigger selects the corrupted word with TLAST=1, avoiding
  the legitimate preceding `0x8E` word. Look for the same corrupted value at
  **SLOT_1_AXIS** after the FIFO delay.
- Fast probe 0 **bit 12** asserts on the sink data mismatch; **bit 20** latches it.
  Probe 3 supplies the expected sink word at the mismatch, **`0x0000008F`**.
- GUI first-error fields should show expected **`0x0000008F`**, observed
  **`0x0000008E`**, packet **8**. Bitmap: **0x01**, Data sequence mismatch.
- Handshakes and packet length remain legal. A protocol checker need not flag
  a wrong payload value; the application checker detects it.

Fast probe 2 is the **source** packet index. It may have advanced beyond 8 by the
time the corrupted word reaches the sink, so do not require it to equal the GUI's
first-error sink packet at the trigger.

For the longer run set rare packet **10000**. The expected/corrupted final values
become **`0x0002710F` / `0x0002710E`**. Change the System ILA TDATA comparison to
`eq32'h0002710E`, or use the [advanced trigger example](ila_tcl_recipes.md#rare-packet-advanced-trigger-example).
The formula is `expected = (packet + 1) * words_per_packet - 1`, then
`corrupted = expected XOR 1`, before 32-bit counter wrap.

**Healthy comparison:** mode 0 delivers `0x8F` correctly at packet 8's end. The
corrupted-word trigger will therefore wait; use `lab_arm_system sink_last` for
an ordinary healthy packet view. Keep stalls enabled for the faulty run: the
injection requires an earlier stall within the selected source packet.

## 8. Fault 5: CDC lost pulse

**GUI:** select **5 - CDC lost pulse**. Clear + stop.

**Arm:**

```tcl
lab_arm_fault 5
lab_arm_cdc_slow
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture
lab_show_capture ila_slow
```

**Signature to find in the slow 64-bit probe:**

| Field | Expected observation |
|---|---|
| Bit 33, fault selected | 1 |
| Bits 31:0, destination count | Finishes below 32; nominally around 8 |
| Bit 36, synchronised pulse | Only the pulses actually sampled by the slow domain appear |
| Bit 37, delayed pulse | One slow-clock delayed copy of bit 36 |
| Bits 38 and 39, completion | Rise when the source burst and destination counting finish |

The receiver increments after a sample with **bit 36=1 and bit 37=0**. Fast probe 0
**bit 16** reports the completed count mismatch; **bit 24** latches it. GUI:
**CDC event count mismatch**, bitmap **0x10**, with **32 sent and fewer received**.

The source sends one 20 ns pulse every 33 fast clocks. The destination samples
every 80 ns, so short pulses can occur entirely between its edges. The raw source
pulse is not in the current ILA probe map: use the GUI sent count and the received
pulse/count trace as the observable evidence. The related clocks make this an
event-loss example, not a measurement of analogue metastability.

The batch finishes in roughly 24 us and then stays at its final count. The GUI's
slower polling will normally show the completed result immediately. It does not
send another batch until the experiment restarts.

**Healthy comparison:** select mode 0, Clear + stop, run only `lab_arm_cdc_slow`,
then Apply + restart and `lab_show_capture ila_slow`. Expect fault bit 33=0,
request/acknowledgement bits 35/34 following one another and a final count of 32.
The GUI should read **32/32**. If mode 5 also gives 32/32, check the active GUI mode
and slow bit 33; that is not the expected faulty result.

## 9. Fault 6: FIFO simultaneous operations

**GUI:** select **6 - FIFO simultaneous operations**, retaining 48/64 stalls.
Clear + stop.

**Arm:**

```tcl
lab_arm_fault 6
lab_arm_system source_stall
```

Click Apply + restart.

**Display:**

```tcl
lab_show_capture
lab_show_capture system_ila
```

**Signature to find in fast probe 4:**

| Field | Meaning |
|---|---|
| Bits 12:8 | VHDL wrapper occupancy count |
| Bit 18 | Occupancy mismatch |
| Bit 19 | Push: an accepted FIFO input word |
| Bit 20 | Pop: an accepted FIFO output word |
| Bits 7:4 / 3:0 | Modulo-16 push/pop counters |

Near full, with at least 15 outstanding words, locate a sample with **push=1 and
pop=1**. These simultaneous operations should leave occupancy unchanged. Instead,
the faulty count **decrements by one** in the following sample; bit 18 then asserts.
Both modulo counters increment, consistent with one push and one pop. Fast probe 0
**bit 17** reports the error and **bit 25** latches it.

The injection occurs once per restart. The incorrect count remains offset from
the reference and can wrap when the FIFO drains. Inspect the first divergence,
not only the later wrapped value. The internal reference count is not directly
probed; reconstruct the expected change from push and pop:

`next_occupancy = occupancy + push - pop`

System ILA shows the real FIFO input/output handshakes. A source-stall capture
shows filling and subsequent draining, but its trigger is independent of the
native mismatch trigger. Use the native trace to locate the exact divergence.

GUI: **FIFO occupancy mismatch**, bitmap **0x20**. TDATA sequence and TLAST remain
correct: the fault is in the VHDL accounting counter, not AMD FIFO storage. The
GUI first-error expected/observed stream words are not the occupancy evidence.

**Healthy comparison:** mode 0 with the same stalls. Simultaneous push/pop leaves
the wrapper count unchanged, and no occupancy mismatch is recorded. Use
`lab_capture_now` while it is running for a native healthy trace; the mode-6
error trigger is not expected to fire in healthy mode.

## 10. Quick reference and evidence to keep

| Mode | Primary fast flags bit | Preset bitmap | Defining signature |
|---|---:|---|---|
| 1 | 14 | `0x05` | TDATA changes while a pending word is stalled |
| 2 | 13 | `0x06` | TLAST disagrees with the accepted 16-word boundary |
| 3 | 15 | `0x08` | Separate AW/W handshakes complete, but BVALID never arrives |
| 4 | 12 | `0x01` | One selected packet ends with a duplicate/wrong last value |
| 5 | 16 | `0x10` | Completed destination count is below 32 sent events |
| 6 | 17 | `0x20` | Simultaneous push/pop incorrectly decrements occupancy |

For each exercise save the waveform, the GUI **Export snapshot** JSON and a short
note identifying the decisive signals and sample interval. The JSON records the
applied settings and first-error fields. Error bitmaps are available in its
`errors` field; the GUI presents their decoded names.

If a capture keeps waiting, first verify **Running**, the active mode and required
stimulus. Clear, rearm and restart rather than rearming after a finite event has
passed. For a quick diagnostic, `lab_arm_fault 5 sticky` (substitute another mode)
can trigger on a recorded error, but it cannot recover the history before a late arm.

If Vivado reports a read-only `CONTROL.CAPTURE_MODE`, reload the current recipe
script; it includes the fixed-control handling. Keep the matching bit/LTX pair.
See [the Tcl recipe guide](ila_tcl_recipes.md) for other trigger choices and
[capture troubleshooting](capture_troubleshooting.md) for connection checks.

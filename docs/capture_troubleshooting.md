# Getting a first ILA waveform

The Python application controls fault selection and reads UART status. ILA arming,
JTAG transfers and waveform windows are handled by **Vivado Hardware Manager**.
Clicking **Apply + restart** alone does not open a waveform.

## Correct the two reported problems

Automatic status reads previously disabled/re-enabled the GUI buttons every 700 ms.
They now run in the background, leave controls enabled, and preserve a command
clicked during a read. **Auto-read status** can also be switched off. A failed read
cancels a waiting command and disconnects rather than starting an experiment after
communication has failed.

The original routed Arty image had its debug hub on **12.5 MHz**, although the fast
ILA sampled at 50 MHz. AMD requires a non-Versal debug hub clock at least 2.5 times
JTAG TCK. Thus that image needs TCK at most 5 MHz; **3 MHz** is a useful diagnostic
setting. This is a confirmed build defect that can explain capture trouble at a
15 MHz TCK; the actual board failure has not yet been reproduced here.

The updated build explicitly connects the hub to the free-running **50 MHz** clock,
checks the routed clock, and supports a 15 MHz TCK within that clock-ratio requirement.
Other cable/signal issues can still require a lower TCK. The slow ILA continues to
sample at 12.5 MHz; it does not supply the hub clock.

Use the [prebuilt Arty S7-50 bit/LTX pair](../prebuilt/arty_s7_50) to program the correction directly. To update an existing, successfully synthesized Arty S7-50 project:

```powershell
vivado -mode batch -source scripts/rebuild_arty_debug.tcl
python scripts/audit_artifacts.py --board arty_s7_50
```

This resets and reruns implementation in `build/ipi_arty_s7_50`. For a clean build,
use `scripts/build.tcl` as described in the README. Program the newly generated
`build/ipi_arty_s7_50/debug_lab.bit` and associate the matching `debug_lab.ltx`.
Changing Python or the Tcl source does not update an already programmed FPGA.

## Immediate capture: separate transport from trigger conditions

1. In Hardware Manager select the **xc7s50**, program the matching bit/LTX pair and
   refresh the device. Confirm the clock-lock LED (`led[2]`) is on.
2. For an older bitstream or a failing connection, close/reopen the selected target
   with **3 MHz JTAG frequency** in Open New Target. Do not confuse this with UART
   baud rate, which remains 115200.
3. In the Vivado **GUI Tcl console**, source the helper using your checkout path:

   ```tcl
   source C:/hdl_projects/debugging_advanced/scripts/hardware_capture.tcl
   lab_capture_now
   ```

The command selects `ila_fast`, restores default trigger settings, captures every
clock without qualification, forces a trigger, waits up to 15 seconds, uploads the
data and opens its waveform window. It replaces that core's previous capture and
trigger setup. It should work with the experiment stopped because the clock is
free-running. Source loading alone does not program, arm or connect to a target.

Check the other cores independently:

```tcl
lab_capture_now ila_slow
lab_capture_now system_ila
```

If an immediate capture fails, inspect the Tcl error and run `lab_ila_status`.
Check clock lock, target frequency and the matching LTX before investigating a
particular fault trigger. A missing core points to programming, LTX or debug-hub
communication. A static waveform can be valid when the experiment is stopped.

## Capture an injected error

1. In Python connect to the FPGA UART, select **1 - AXI-Stream backpressure**
   (the mode 1 entry) with default stall settings, and click **Clear + stop**.
2. In Vivado run `lab_arm_error`.
3. In Python click **Apply + restart**.
4. In Vivado run `lab_show_capture` to upload and display the result.

The helper triggers on `experiment_native0[1]`, the sticky error flag, with 256
pre-trigger samples. It therefore still detects an error if its one-cycle event
has passed. Use the event-bit and advanced recipes in the laboratory guide after
this basic check succeeds. Healthy mode is expected to wait indefinitely for an
error; faults with their necessary stimulus removed may also never fire.

The GUI's experiment cycles and accepted stream words should increase while the
stream is running. If they do not, check the running status and whether you used
Apply + restart. An AXI fault can deadlock its test bus while UART control remains
available. Clear + stop before rearming avoids an old sticky error firing a new
capture immediately. For System ILA, start with unqualified immediate capture;
then apply the protocol-specific trigger from the guide.

## Verification scope

Host regression tests exercise steady controls during polling, command ordering,
read failure cancellation, disconnects, duplicate reads and pausing auto-read.
The helper loads in Vivado 2026.1 and uses its documented hardware commands. A
connected FPGA is still required to validate real arming, upload and display.

References: [AMD debug-core clocking guidelines](https://docs.amd.com/r/2023.1-English/ug908-vivado-programming-debugging/Debug-Cores-Clocking-Guidelines),
[run_hw_ila](https://docs.amd.com/r/2024.1-English/ug835-vivado-tcl-commands/run_hw_ila),
[wait_on_hw_ila](https://docs.amd.com/r/2023.1-English/ug835-vivado-tcl-commands/wait_on_hw_ila).

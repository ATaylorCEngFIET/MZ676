# MicroZed Chronicles laboratory guide

Runnable setup commands are in [the Tcl recipe guide](ila_tcl_recipes.md) and `scripts/ila_recipes.tcl`.

For complete GUI settings, arm/display commands and expected waveforms, see [the run guide](run_lab.md).

## Common procedure

1. Program the board's matching bitstream and load its LTX.
2. Connect the Python GUI to the FPGA UART. Start with healthy mode and the default settings.
3. Verify increasing packet and AXI counts, 32/32 CDC events, and no error flags.
4. Select the fault, use Clear + stop to remove old sticky/CDC-completion flags, configure and arm the ILA, then Apply + restart.
5. Use 1024 samples with trigger position around 768 to retain the preceding cause. All-cycle capture is the starting point.
6. Save the ILA waveform/CSV and the GUI's JSON snapshot. Switch to healthy mode with the same stimuli and repeat.

The register-controlled fault mux makes experiments repeatable without rebuilding. For an article, show the faulty VHDL branch and the healthy branch beside the waveform. Hardware debugging finds the cause; the supplied simulation tests provide a repeatable regression for the corrected behavior.

## Probe map

Native fast ILA has six 32-bit probes (port numbers are stable even if Vivado displays hierarchical net names):

| Probe | Content |
|---|---|
| 0 | Flags: bit 0 run, 1 sticky error, 2 experiment reset, 3 earlier stall in source packet; bits 11:8 mode; bits 17:12 current diagnostic events; bits 25:20 sticky errors |
| 1 | Source-clock experiment cycle |
| 2 | Source packet index |
| 3 | Expected sink word |
| 4 | FIFO: bits 3:0 modulo-16 pop counter, 7:4 modulo-16 push counter, 12:8 wrapper occupancy; bit 16 input ready, 17 output valid, 18 occupancy error, 19 push, 20 pop |
| 5 | AXI: bit 0 fault enable, 1 address accepted at master, 2 data accepted at master, 3 address seen at target, 4 data seen at target, 5 BVALID, 6 active, 7 timeout; bits 31:16 transaction age |

System ILA slots: 0 source AXI-Stream, 1 sink AXI-Stream, 2 AXI4-Lite. The two stream interfaces carry 32-bit TDATA, TVALID, TREADY and TLAST. Protocol checkers and transaction tracking are enabled. The AXI read channels are tied inactive; this lab exercises writes.

Native slow ILA has one 64-bit probe: bits 31:0 destination event count, 32 local reset, 33 fault mode, 34 acknowledgement, 35 synchronised request, 36 synchronised pulse, 37 delayed pulse, 38 source done synchronised, 39 destination done.

## 1. It works until backpressure arrives

Keep 16 words/packet and 48 stalled cycles per 64 clocks. Trigger fast probe 0 bit 14 (stability event), or the source interface's protocol-checker violation. In the preceding cycles TVALID stays high and TREADY is low, but TDATA changes. The source counter's faulty enable is TVALID alone; the healthy enable includes TREADY. Sequence mismatches appear at the sink later.

Article lesson: trigger close to the causal violation. A downstream data-error trigger may be many transfers later. Capture stalled cycles; transaction-only storage qualification would discard the critical evidence.

## 2. The missing last word

Trigger fast probe 0 bit 13 (TLAST check). Count transfers at the sink using TVALID AND TREADY. TLAST must correspond to the configured packet length, not a count of elapsed clocks. In this implementation faulty TLAST also changes during some stalls, so the protocol checker may flag stability as well.

Article lesson: protocol checking does not know the application's intended packet length. A stable but wrongly placed TLAST could pass protocol checking and still fail this packet-length checker.

## 3. The register write that never completes

Use AXI skew 16. Trigger fast probe 0 bit 15 or probe 5 bit 7. Probe 5 shows both channels were accepted, yet BVALID never arrived. The source alternates address-first and data-first on successive healthy transactions; each VALID persists until its own READY handshake. The faulty target waits for both handshakes on the same cycle.

To see the initial address/data handshakes, take a separate System ILA capture triggered on AWVALID with trigger position 32. The timeout is 1024 clocks after transaction start, so a native capture with 768 pre-trigger samples shows the waiting state but does not reach the initial handshakes. These two captures illustrate why trigger placement matters.

The 1024-cycle timeout is an application diagnostic. AXI permits independently timed channels and does not impose this completion deadline. A protocol checker need not report this liveness failure with default timeout options. Show the separately remembered address/data acceptance in the corrected logic.

## 4. Catching the rare packet

Select rare packet 10000 (or 8 for a quick test), retaining default packet/stall settings. The last word is corrupted only if an earlier word in that selected source packet stalled. Trigger on fast probe 0 bit 12 (data error). Source packet numbers are zero-based; source and sink packet counters can differ because the FIFO introduces latency.

For the advanced trigger exercise, create three states in the native fast ILA's trigger-state-machine editor:

- Wait for probe 2 to equal the selected packet.
- Wait for probe 0 bit 3 to indicate an earlier stall.
- Wait for probe 0 bit 12, then trigger.

The supplied `docs/rare_packet_10000.tsm` uses the probe names verified in the generated LTX and targets packet 10000. Use `scripts/make_trigger.py` for another target or different probe names. It uses two match conditions on the flags word and one on the packet word; the generated fast ILA has two match units per probe. Validate the script in Hardware Manager before arming. The parser validation and hardware execution require a connected device and have not been claimed as tested here.

This is a data-integrity fault with a legal handshake; the packet checker supplies the trigger. The standard depth at 50 MHz records 20.48 microseconds, so advanced triggering focuses that buffer on the selected event rather than requiring memory for 10,000 packets.

## 5. Where did the event disappear?

Trigger the slow ILA on bit 39 (destination done), with most of the buffer before the trigger. Compare the final destination count with 32 source events in the GUI. Trigger the fast ILA on bit 16 to capture the comparison failure. Captures from the two ILAs are separate clock-domain records; sample numbers are not a shared timestamp.

The source generates a one-cycle pulse every 33 source clocks. The destination runs four times slower. The faulty two-flop pulse synchroniser misses pulses between sampling edges. The healthy request/acknowledge handshake holds each event until acknowledged. Demonstrate event loss, not analogue metastability: RTL simulation and ILA cannot show the analogue resolution of a metastable flip-flop.

The clocks are related intentionally, making the sampling-window failure deterministic. An extension can introduce unrelated clocks, but would also require reviewed CDC timing constraints and a new hardware validation pass.

## 6. Is the FIFO broken, or is the wrapper wrong?

Trigger fast probe 0 bit 17 (occupancy mismatch). The AMD AXI4-Stream Data FIFO owns storage and flow control. A separate VHDL counter accounts for accepted transfers. Near full, with at least 15 outstanding words, simultaneous push and pop should leave occupancy unchanged; the selected fault decrements it once. The reference counter remains correct.

The preset error bitmap is `0x20`. Sequence and TLAST checks remain healthy: the faulty accounting does not control the AMD FIFO. Probe 4's pointer fields are modulo-16 transfer counters maintained by the instrumentation, not the IP's internal pointers. Its occupancy is a five-bit unsigned value, so the deliberate offset can wrap when the queue drains.

Capture both stream interfaces and reconstruct occupancy from accepted input/output operations. The article can show why blaming a vendor FIFO based on one incorrect wrapper counter is misleading, and how independent checks isolate the actual RTL defect.

## Further advanced exercises with this same design

- Move the trigger between protocol violation and downstream checker failure; measure the causal latency.
- Use capture qualification for accepted transfers only, then demonstrate why it is unsuitable when investigating stalls. Include a cycle counter to identify gaps in qualified native-ILA captures.
- Compare debug-core utilization and timing reports with alternative capture depths. Instrumentation is part of the implemented design and can change routing/timing.
- Capture both healthy and faulty runs with identical settings, then attach the JSON settings and a simulation regression to each article.

The GUI controls the experiment; Vivado owns ILA arming, trigger editing and waveform capture. This release does not automate Hardware Manager through Python.

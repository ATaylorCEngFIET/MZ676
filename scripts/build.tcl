# The complete FPGA design is an IP Integrator block design; its wrapper is VHDL.
# vivado -mode batch -source scripts/build.tcl -tclargs arty_s7_50 [project|synth|bitstream]
set root [file normalize [file join [file dirname [info script]] ..]]
set board [lindex $argv 0]
if {$board eq ""} {set board arty_s7_50}
set stage [lindex $argv 1]
if {$stage eq ""} {set stage project}
if {$stage ni {project synth bitstream}} {error "Stage must be project, synth or bitstream"}
if {$board eq "arty_s7_50"} {
  set part xc7s50csga324-1; set input_mhz 12.0; set clock_type Single_ended_clock_capable_pin
} elseif {$board eq "sp701"} {
  set part xc7s100fgga676-2; set input_mhz 33.333333
  if {[llength $argv] >= 3} {set input_mhz [lindex $argv 2]}
  if {![string is double -strict $input_mhz] || $input_mhz < 10 || $input_mhz > 450} {error "Invalid Si570 input frequency"}
  set clock_type Differential_clock_capable_pin
} else {error "Board must be arty_s7_50 or sp701"}
# New directory prevents an old top-level architecture from being mistaken for this build.
set out [file join $root build ipi_$board]
file mkdir $out
create_project debug_lab $out -part $part -force
set_property target_language VHDL [current_project]
# AMD IP can supply encrypted Verilog internally; all project-authored HDL is VHDL.
set_property simulator_language Mixed [current_project]
foreach name {lab_pkg occupancy_checker cdc_lab axi_lab debug_lab command_parser uartlite_service control_bd experiment_bd axi_tap} {
  add_files [file join $root rtl ${name}.vhd]
}
set_property file_type {VHDL 2008} [get_files *.vhd]
set_property file_type VHDL [get_files {*control_bd.vhd *experiment_bd.vhd *axi_tap.vhd}]
update_compile_order -fileset sources_1
create_bd_design debug_system
proc net {a b} {connect_bd_net [get_bd_pins $a] [get_bd_pins $b]}
proc constant {name width value} {
  set c [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 $name]
  set_property -dict [list CONFIG.CONST_WIDTH $width CONFIG.CONST_VAL $value] $c
  return [get_bd_pins $c/dout]
}
set zero [constant zero 1 0]
set one [constant one 1 1]
set z32 [constant zero32 32 0]
set z3 [constant zero3 3 0]
set z2 [constant zero2 2 0]
set ones4 [constant ones4 4 15]
set clock [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clocks]
set_property -dict [list CONFIG.PRIM_IN_FREQ $input_mhz CONFIG.PRIM_SOURCE $clock_type CONFIG.CLKOUT1_REQUESTED_OUT_FREQ 50.0 CONFIG.CLKOUT2_USED true CONFIG.CLKOUT2_REQUESTED_OUT_FREQ 12.5 CONFIG.USE_RESET false CONFIG.USE_LOCKED true] $clock
if {$board eq "arty_s7_50"} {
  connect_bd_net [create_bd_port -dir I -type clk -freq_hz [expr {int($input_mhz*1e6)}] clk_in] [get_bd_pins clocks/clk_in1]
} else {
  foreach suffix {p n} {connect_bd_net [create_bd_port -dir I -type clk -freq_hz [expr {int($input_mhz*1e6)}] clk_in_$suffix] [get_bd_pins clocks/clk_in1_$suffix]}
}
set fast [get_bd_pins clocks/clk_out1]
set slow [get_bd_pins clocks/clk_out2]
set reset [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 reset_controller]

connect_bd_net $fast [get_bd_pins $reset/slowest_sync_clk]
net clocks/locked reset_controller/dcm_locked
# Processor System Reset defaults to active-low external/auxiliary inputs.
foreach p {ext_reset_in aux_reset_in} {connect_bd_net $one [get_bd_pins $reset/$p]}
connect_bd_net $zero [get_bd_pins $reset/mb_debug_sys_rst]
set lab [create_bd_cell -type module -reference experiment_bd experiment]
set control [create_bd_cell -type module -reference control_bd control]
foreach c {experiment control} {
  connect_bd_net $fast [get_bd_pins $c/clk]
  net reset_controller/peripheral_reset $c/rst
}
connect_bd_net $slow [get_bd_pins experiment/slow_clk]
foreach p {reg_write reg_addr reg_wdata reg_rdata} {net control/$p experiment/$p}
set uart [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_uartlite:2.0 uart]
set_property -dict [list CONFIG.C_BAUDRATE 115200 CONFIG.C_DATA_BITS 8 CONFIG.C_USE_PARITY 0] $uart
connect_bd_net $fast [get_bd_pins uart/s_axi_aclk]
net reset_controller/peripheral_aresetn uart/s_axi_aresetn
connect_bd_intf_net [get_bd_intf_pins control/M_AXI] [get_bd_intf_pins uart/S_AXI]
connect_bd_net [create_bd_port -dir I uart_rx] [get_bd_pins uart/rx]
connect_bd_net [create_bd_port -dir O uart_tx] [get_bd_pins uart/tx]
assign_bd_address -offset 0x00000000 -range 0x00010000 [get_bd_addr_segs uart/S_AXI/Reg]
set fifo [create_bd_cell -type ip -vlnv xilinx.com:ip:axis_data_fifo:2.0 stream_fifo]
set_property -dict [list CONFIG.TDATA_NUM_BYTES 4 CONFIG.HAS_TLAST 1 CONFIG.FIFO_DEPTH 16 CONFIG.FIFO_MODE 1 CONFIG.IS_ACLK_ASYNC 0] $fifo
connect_bd_net $fast [get_bd_pins stream_fifo/s_axis_aclk]
net experiment/fifo_resetn stream_fifo/s_axis_aresetn
connect_bd_intf_net [get_bd_intf_pins experiment/M_AXIS] [get_bd_intf_pins stream_fifo/S_AXIS]
connect_bd_intf_net [get_bd_intf_pins stream_fifo/M_AXIS] [get_bd_intf_pins experiment/S_AXIS]
set sys [create_bd_cell -type ip -vlnv xilinx.com:ip:system_ila:1.1 system_ila]
set_property -dict [list CONFIG.C_NUM_MONITOR_SLOTS 3 CONFIG.C_SLOT_0_INTF_TYPE xilinx.com:interface:axis_rtl:1.0 CONFIG.C_SLOT_1_INTF_TYPE xilinx.com:interface:axis_rtl:1.0 CONFIG.C_SLOT_2_INTF_TYPE xilinx.com:interface:aximm_rtl:1.0 CONFIG.C_SLOT_0_APC_EN 1 CONFIG.C_SLOT_1_APC_EN 1 CONFIG.C_SLOT_2_APC_EN 1 CONFIG.C_SLOT_0_AXIS_TDATA_WIDTH 32 CONFIG.C_SLOT_1_AXIS_TDATA_WIDTH 32 CONFIG.C_SLOT_2_AXI_PROTOCOL AXI4LITE CONFIG.C_SLOT_2_AXI_DATA_WIDTH 32 CONFIG.C_SLOT_2_AXI_ADDR_WIDTH 32 CONFIG.C_DATA_DEPTH 1024 CONFIG.C_EN_STRG_QUAL 1 CONFIG.C_ADV_TRIGGER 1] $sys
connect_bd_net $fast [get_bd_pins $sys/clk]
net experiment/fifo_resetn system_ila/resetn
connect_bd_intf_net [get_bd_intf_pins experiment/M_AXIS] [get_bd_intf_pins $sys/SLOT_0_AXIS]
connect_bd_intf_net [get_bd_intf_pins stream_fifo/M_AXIS] [get_bd_intf_pins $sys/SLOT_1_AXIS]
# The deliberately faulty AXI target lives inside the VHDL experiment. Wire-only
# adapter exposes its independent write channels as one monitorable AXI bus.
set tap [create_bd_cell -type module -reference axi_tap axi_monitor]
connect_bd_net $fast [get_bd_pins $tap/clk]
foreach {signal pin} {axi_awvalid raw2 axi_wdata raw3 axi_wvalid raw5 axi_bready raw6 axi_awready m_awready axi_wready m_wready axi_bvalid m_bvalid} {net experiment/$signal axi_monitor/$pin}
foreach pin {raw0 raw7 m_rdata} {connect_bd_net $z32 [get_bd_pins $tap/$pin]}
foreach pin {raw1 raw8} {connect_bd_net $z3 [get_bd_pins $tap/$pin]}
foreach pin {m_bresp m_rresp} {connect_bd_net $z2 [get_bd_pins $tap/$pin]}
connect_bd_net $ones4 [get_bd_pins $tap/raw4]
foreach pin {raw9 m_rvalid} {connect_bd_net $zero [get_bd_pins $tap/$pin]}
foreach pin {raw10 m_arready} {connect_bd_net $one [get_bd_pins $tap/$pin]}
connect_bd_intf_net [get_bd_intf_pins $tap/MON] [get_bd_intf_pins $sys/SLOT_2_AXI]
foreach signal {awready wready bvalid} {net experiment/axi_$signal system_ila/SLOT_2_AXI_$signal}
foreach signal {bresp rresp} {connect_bd_net $z2 [get_bd_pins $sys/SLOT_2_AXI_$signal]}
connect_bd_net $z32 [get_bd_pins $sys/SLOT_2_AXI_rdata]
connect_bd_net $zero [get_bd_pins $sys/SLOT_2_AXI_rvalid]
connect_bd_net $one [get_bd_pins $sys/SLOT_2_AXI_arready]
set native [create_bd_cell -type ip -vlnv xilinx.com:ip:ila:6.2 ila_fast]
set_property -dict [list CONFIG.C_MONITOR_TYPE Native CONFIG.C_NUM_OF_PROBES 6 CONFIG.C_DATA_DEPTH 1024 CONFIG.C_ADV_TRIGGER true CONFIG.C_EN_STRG_QUAL 1] $native
connect_bd_net $fast [get_bd_pins $native/clk]
for {set i 0} {$i < 6} {incr i} {
  set_property CONFIG.C_PROBE${i}_WIDTH 32 $native
  net experiment/native$i ila_fast/probe$i
}
set slow_ila [create_bd_cell -type ip -vlnv xilinx.com:ip:ila:6.2 ila_slow]
set_property -dict [list CONFIG.C_MONITOR_TYPE Native CONFIG.C_NUM_OF_PROBES 1 CONFIG.C_PROBE0_WIDTH 64 CONFIG.C_DATA_DEPTH 1024] $slow_ila
connect_bd_net $slow [get_bd_pins $slow_ila/clk]
net experiment/slow_debug ila_slow/probe0
# AMD counter, slice and concatenate IP drive the four front-panel LEDs.
set heartbeat [create_bd_cell -type ip -vlnv xilinx.com:ip:c_counter_binary:12.0 heartbeat]
set_property CONFIG.Output_Width 26 $heartbeat
connect_bd_net $fast [get_bd_pins $heartbeat/CLK]
set slice [create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice:1.0 heartbeat_bit]
set_property -dict [list CONFIG.DIN_WIDTH 26 CONFIG.DIN_FROM 25 CONFIG.DIN_TO 25 CONFIG.DOUT_WIDTH 1] $slice
net heartbeat/Q heartbeat_bit/Din
set concat [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconcat:2.1 leds]
set_property CONFIG.NUM_PORTS 4 $concat
foreach {source pin} {experiment/running In0 experiment/error_led In1 clocks/locked In2 heartbeat_bit/Dout In3} {net $source leds/$pin}
connect_bd_net [get_bd_pins leds/dout] [create_bd_port -dir O -from 3 -to 0 led]
validate_bd_design
foreach parameter {C_EXT_RESET_HIGH C_AUX_RESET_HIGH} {
  if {[get_property CONFIG.$parameter $reset] != 0} {error "Reset input polarity changed: $parameter; review inactive tie-offs"}
}
foreach {pin expected} {system_ila/SLOT_0_AXIS_tdata 32 system_ila/SLOT_1_AXIS_tdata 32 ila_fast/probe0 32 ila_fast/probe1 32 ila_fast/probe2 32 ila_fast/probe3 32 ila_fast/probe4 32 ila_fast/probe5 32 ila_slow/probe0 64} {
  set p [get_bd_pins $pin]
  set width [expr {abs([get_property LEFT $p] - [get_property RIGHT $p]) + 1}]
  if {$width != $expected} {error "Unexpected probe width: $pin has $width, expected $expected"}
}
save_bd_design
set bd [get_files debug_system.bd]
generate_target all $bd
add_files [make_wrapper -files $bd -top]
add_files -fileset constrs_1 [file join $root constraints ${board}.xdc]
add_files -fileset constrs_1 [file join $root constraints timing.xdc]
set_property top debug_system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "PROJECT READY: $out/debug_lab.xpr; input clock $input_mhz MHz"
if {$stage ne "project"} {
  launch_runs synth_1 -jobs 4
  wait_on_run synth_1
  if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis failed"}
  open_run synth_1
  report_utilization -file [file join $out utilization_synth.rpt]
  report_cdc -file [file join $out cdc.rpt]
  if {$stage eq "bitstream"} {
    launch_runs impl_1 -to_step write_bitstream -jobs 4
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
    open_run impl_1
    report_timing_summary -file [file join $out timing_summary.rpt]
    report_utilization -file [file join $out utilization_impl.rpt]
    report_bus_skew -file [file join $out bus_skew.rpt]
    report_drc -file [file join $out drc.rpt]
    foreach delay_type {max min} {
      set worst [get_timing_paths -delay_type $delay_type -max_paths 1]
      if {[llength $worst] && [get_property SLACK $worst] < 0} {error "Implementation has failing $delay_type timing"}
    }
    source [file join $root scripts export_probes.tcl]
    lab_export_probes [file join $out debug_lab.ltx]
    file copy -force [file join $out debug_lab.runs impl_1 debug_system_wrapper.bit] [file join $out debug_lab.bit]
    puts "BITSTREAM READY: $out/debug_lab.bit"
  }
}
exit


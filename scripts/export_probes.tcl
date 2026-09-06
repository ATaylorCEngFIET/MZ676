# Complete interface metadata for the three explicitly wired return signals
# of the intentionally faulty VHDL AXI target. Real AXIS connections are inferred.
proc lab_export_probes {path} {
  foreach {signal logical} {axi_awready AWREADY axi_wready WREADY axi_bvalid BVALID} {
    set wire [get_nets -hier -filter "NAME =~ *debug_system_i/experiment_$signal"]
    if {[llength $wire] != 1} {error "Cannot identify AXI monitor return net $signal"}
    set_property CONN_BUS_INFO "axi_monitor_MON xilinx.com:interface:aximm:1.0 AXI4LITE $logical" $wire
  }
  write_debug_probes -force $path
}

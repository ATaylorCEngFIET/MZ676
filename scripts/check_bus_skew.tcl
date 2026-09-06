set root [file normalize [file join [file dirname [info script]] ..]]
foreach board {arty_s7_50 sp701} {
  set out [file join $root build ipi_$board]
  open_checkpoint [file join $out debug_lab.runs impl_1 debug_system_wrapper_routed.dcp]
  report_bus_skew -file [file join $out bus_skew.rpt]
  close_design
}
exit

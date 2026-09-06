# Reuse existing synthesis when installing the debug-hub clock correction.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build ipi_arty_s7_50]
open_project [file join $out debug_lab.xpr]
if {[get_property PART [current_project]] ne "xc7s50csga324-1"} {error "Expected Arty S7-50 project"}
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Run scripts/build.tcl first; synthesis is not complete"}
reset_run impl_1
if {![llength [get_files -quiet debug_hub_clock.tcl]]} {
  add_files -fileset utils_1 [file join $root scripts debug_hub_clock.tcl]
}
set_property STEPS.OPT_DESIGN.TCL.PRE [file join $root scripts debug_hub_clock.tcl] [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation failed"}
open_run impl_1
foreach report {report_timing_summary report_utilization report_bus_skew report_drc} name {timing_summary utilization_impl bus_skew drc} {
  $report -file [file join $out ${name}.rpt]
}
foreach type {max min} {
  set worst [get_timing_paths -delay_type $type -max_paths 1]
  if {![llength $worst] || [get_property SLACK $worst] < 0} {error "Timing check failed: $type"}
}
source [file join $root scripts check_debug_clocks.tcl]
lab_check_debug_clocks [file join $out debug_clocks.rpt]
source [file join $root scripts export_probes.tcl]
lab_export_probes [file join $out debug_lab.ltx]
file copy -force [file join $out debug_lab.runs impl_1 debug_system_wrapper.bit] [file join $out debug_lab.bit]
puts "BITSTREAM READY: $out/debug_lab.bit"
exit

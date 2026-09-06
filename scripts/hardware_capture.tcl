# Source in the Vivado GUI Tcl console after programming the matching .bit/.ltx.
# Sourcing this file only defines commands; it does not change hardware state.
proc lab_ila {name} {
  set device [current_hw_device -quiet]
  if {[llength $device] != 1} {error "Select the programmed FPGA in Hardware Manager first"}
  set found {}
  foreach ila [get_hw_ilas -quiet -of_objects $device] {
    set cell [get_property CELL_NAME $ila]
    if {[string match "*/$name" $cell] || ($name eq "system_ila" && [string match "*/system_ila/*" $cell])} {
      lappend found $ila
    }
  }
  if {[llength $found] != 1} {error "Expected one $name core; refresh the device and associate the matching debug_lab.ltx"}
  return [lindex $found 0]
}
proc lab_capture_setup {ila} {
  reset_hw_ila $ila
  set_property CONTROL.CAPTURE_MODE ALWAYS $ila
  set_property CONTROL.TRIGGER_POSITION 0 $ila
  set_property CONTROL.WINDOW_COUNT 1 $ila
  set_property CONTROL.DATA_DEPTH 1024 $ila
}
proc lab_show_capture {{name ila_fast}} {
  set ila [lab_ila $name]
  # Vivado specifies timeout in MINUTES; 0.25 is 15 seconds.
  if {[catch {wait_on_hw_ila -timeout 0.25 $ila} reason]} {
    error "Capture did not complete: $reason. Check MMCM lock LED, matching bit/LTX and JTAG speed (try 3 MHz)."
  }
  set data [upload_hw_ila_data $ila]
  display_hw_ila_data $data
  return $data
}
proc lab_capture_now {{name ila_fast}} {
  set ila [lab_ila $name]
  lab_capture_setup $ila
  run_hw_ila -trigger_now $ila
  return [lab_show_capture $name]
}
proc lab_arm_error {} {
  set ila [lab_ila ila_fast]
  lab_capture_setup $ila
  set_property CONTROL.TRIGGER_POSITION 256 $ila
  set_property CONTROL.TRIGGER_CONDITION AND $ila
  set probes [get_hw_probes -of_objects $ila]
  set flags {}
  foreach probe $probes {
    set_property TRIGGER_COMPARE_VALUE "eq32'b[string repeat X 32]" $probe
    if {[string match "*/experiment_native0" [get_property NAME $probe]]} {lappend flags $probe}
  }
  if {[llength $flags] != 1} {error "Missing experiment_native0 flags; load this build's LTX file"}
  # Sticky error is bit 1. Other flags and probes are don't-care.
  set_property TRIGGER_COMPARE_VALUE "eq32'b[string repeat X 30]1X" $flags
  run_hw_ila $ila
  puts "Armed on sticky error. Click Apply + restart in Python, then run lab_show_capture."
}
proc lab_ila_status {} {
  foreach name {ila_fast ila_slow system_ila} {report_property [lab_ila $name]}
}
puts "Lab helpers loaded: lab_capture_now ?ila_fast|ila_slow|system_ila?, lab_arm_error, lab_show_capture, lab_ila_status"

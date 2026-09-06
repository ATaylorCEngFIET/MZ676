# Per-fault recipes for the supplied Arty S7-50 bit/LTX pair.
# Source this in Vivado's GUI Tcl console. Nothing arms until a lab_arm_* call.
source [file join [file dirname [info script]] hardware_capture.tcl]

proc lab_probe {ila suffix} {
  set matches {}
  foreach probe [get_hw_probes -of_objects $ila] {
    if {[string match "*/$suffix" [get_property NAME $probe]]} {lappend matches $probe}
  }
  if {[llength $matches] != 1} {
    error "Expected one probe ending /$suffix. Load the supplied matching LTX; inspect get_hw_probes -of_objects $ila."
  }
  return [lindex $matches 0]
}
proc lab_compare_bits {width pairs} {
  set mask [string repeat X $width]
  foreach {bit value} $pairs {
    if {![string is integer -strict $bit] || $bit < 0 || $bit >= $width || $value ni {0 1}} {
      error "Invalid bit comparison: bit=$bit value=$value width=$width"
    }
    set index [expr {$width - 1 - $bit}]
    set mask [string replace $mask $index $index $value]
  }
  return "eq${width}'b$mask"
}
proc lab_recipe_setup {name position} {
  set ila [lab_ila $name]
  lab_capture_setup $ila
  set_property CONTROL.TRIGGER_POSITION $position $ila
  set_property CONTROL.TRIGGER_CONDITION AND $ila
  return $ila
}
proc lab_arm_fault {mode {kind event}} {
  # Probe 0 event/sticky bit mappings are specified by rtl/debug_lab.vhd.
  set event_bits [dict create 1 14 2 13 3 15 4 12 5 16 6 17]
  if {![dict exists $event_bits $mode] || $kind ni {event sticky}} {
    error "Usage: lab_arm_fault <1..6> ?event|sticky?"
  }
  set bit [dict get $event_bits $mode]
  if {$kind eq "sticky"} {incr bit 8}
  # Require the actual active mode as well as the selected error flag.
  set pairs [list $bit 1]
  for {set i 0} {$i < 4} {incr i} {lappend pairs [expr {8+$i}] [expr {($mode >> $i) & 1}]}
  set ila [lab_recipe_setup ila_fast 768]
  set_property TRIGGER_COMPARE_VALUE [lab_compare_bits 32 $pairs] [lab_probe $ila experiment_native0]
  run_hw_ila $ila
  puts "Fast ILA armed: mode $mode, $kind bit $bit. Apply + restart mode $mode in Python, then lab_show_capture."
}
proc lab_arm_cdc_slow {} {
  # The full 32-event burst is about 24 us. 768 pre-trigger slow samples cover
  # 61.44 us, including the burst and synchronizer pipeline history.
  set ila [lab_recipe_setup ila_slow 768]
  set_property TRIGGER_COMPARE_VALUE [lab_compare_bits 64 {39 1}] [lab_probe $ila experiment_slow_debug]
  run_hw_ila $ila
  puts "Slow ILA armed on destination done. Restart in Python, then lab_show_capture ila_slow."
}
proc lab_arm_system {recipe} {
  # Names and packed AXI control bits are checked against the shipped LTX.
  # Reset clears all previous compare values; AND combines only specified terms.
  switch -- $recipe {
    source_stall {
      set position 256
      set terms {net_slot_0_axis_tvalid 1 {0 1} net_slot_0_axis_tready 1 {0 0}}
    }
    source_violation {
      set position 768
      set terms {net_slot_0_apc_pc_asserted 1 {0 1}}
    }
    sink_last {
      set position 768
      set terms {net_slot_1_axis_tvalid 1 {0 1} net_slot_1_axis_tready 1 {0 1} net_slot_1_axis_tlast 1 {0 1}}
    }
    axi_address {
      set position 32
      set terms {net_slot_2_axi_aw_ctrl 2 {0 1}}
    }
    axi_data {
      set position 32
      set terms {net_slot_2_axi_w_ctrl 2 {0 1}}
    }
    default {error "Use source_stall, source_violation, sink_last, axi_address or axi_data"}
  }
  set ila [lab_recipe_setup system_ila $position]
  foreach {suffix width pairs} $terms {
    set_property TRIGGER_COMPARE_VALUE [lab_compare_bits $width $pairs] [lab_probe $ila $suffix]
  }
  run_hw_ila $ila
  puts "System ILA armed: $recipe. Restart in Python, then lab_show_capture system_ila."
}
puts "Recipes loaded: lab_arm_fault <1..6> ?event|sticky?, lab_arm_cdc_slow, lab_arm_system <recipe>"

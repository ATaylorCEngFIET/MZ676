# Source in an open implemented design. Fail before publishing a bitstream if
# the debug transport or native ILA clocks differ from the intended clocks.
proc lab_check_debug_clocks {output} {
  set rows {}
  foreach {pin expected} {dbg_hub/clk 20.0 debug_system_i/ila_fast/clk 20.0 debug_system_i/ila_slow/clk 80.0} {
    set p [get_pins -quiet $pin]
    set clocks [get_clocks -quiet -of_objects $p]
    if {[llength $p] != 1 || [llength $clocks] != 1} {error "Missing or ambiguous clock on $pin"}
    set period [get_property PERIOD $clocks]
    if {abs($period - $expected) > 0.01} {error "Wrong clock on $pin: $period ns; expected $expected ns"}
    lappend rows "$pin period_ns=$period clock=$clocks"
  }
  set f [open $output w]
  puts $f [join $rows \n]
  close $f
  puts "PASS: debug hub 50 MHz, fast ILA 50 MHz, slow ILA 12.5 MHz"
}

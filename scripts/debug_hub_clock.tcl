# Implementation pre-opt hook: keep JTAG transport on the free-running 50 MHz
# clock. Vivado's automatic selection can choose the 12.5 MHz experiment clock.
set hub [get_debug_cores -quiet dbg_hub]
set fast_clock [get_nets -quiet -hier -filter {NAME == debug_system_i/clocks_clk_out1}]
if {[llength $hub] != 1 || [llength $fast_clock] != 1} {
  error "Expected one debug hub and the laboratory 50 MHz clock"
}
disconnect_debug_port dbg_hub/clk
connect_debug_port dbg_hub/clk $fast_clock
set_property C_CLK_INPUT_FREQ_HZ 50000000 $hub
set_property C_ENABLE_CLK_DIVIDER false $hub
puts "LAB_DEBUG_HUB: connected to $fast_clock at 50 MHz"

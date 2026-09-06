# Run VHDL testbenches against the generated AMD IP.
# vivado -mode batch -source scripts/simulate_ip.tcl -tclargs [tb_debug_lab|tb_uart_control]
set root [file normalize [file join [file dirname [info script]] ..]]
set top [lindex $argv 0]
if {$top eq ""} {set top tb_debug_lab}
if {$top ni {tb_debug_lab tb_uart_control tb_board_boot}} {error "Unknown testbench"}
set project [file join $root build ipi_arty_s7_50 debug_lab.xpr]
if {![file exists $project]} {error "Generate the Arty IP Integrator project first"}
open_project $project
# Give each testbench its own simulation fileset.
set simset ip_$top
if {[llength [get_filesets -quiet $simset]] == 0} {create_fileset -simset $simset}
foreach name {stream_fifo_model simulation_fifo} {add_files -fileset $simset [file join $root sim $name.vhd]}
add_files -fileset $simset [file join $root sim $top.vhd]
set_property file_type {VHDL 2008} [get_files -of_objects [get_filesets $simset] *.vhd]
# These testbenches instantiate leaf IP components rather than the whole BD.
# Add the generated simulation wrappers explicitly so compile-order pruning
# cannot silently replace them with unbound VHDL component black boxes.
set ipdir [file join $root build ipi_arty_s7_50 debug_lab.gen sources_1 bd debug_system ip]
add_files -fileset $simset [file join $ipdir debug_system_stream_fifo_0 sim debug_system_stream_fifo_0.v]
add_files -fileset $simset [file join $ipdir debug_system_uart_0 sim debug_system_uart_0.vhd]
# Use the installed AMD library revisions rather than hard-coding patch versions.
set f [open [file join $env(XILINX_VIVADO) data xsim xsim.ini] r]
set library_map [read $f]; close $f
set libraries {}
foreach line [split $library_map "\n"] {
  if {[regexp {^((axis_data_fifo|axis_infrastructure|fifo_generator|axi_uartlite)_v[0-9_]+)=} $line -> lib]} {lappend libraries -L $lib}
}
if {[llength $libraries] == 0} {error "AMD precompiled XSim IP libraries are required"}
set_property -dict [list xsim.elaborate.xelab.more_options $libraries] [get_filesets $simset]
set_property top $top [get_filesets $simset]
set_property top_lib xil_defaultlib [get_filesets $simset]
if {$top eq "tb_debug_lab"} {set_property generic {USE_AMD=true} [get_filesets $simset]}
set_property xsim.simulate.runtime all [get_filesets $simset]
set_property xsim.simulate.log_all_signals false [get_filesets $simset]
set_property xsim.elaborate.debug_level off [get_filesets $simset]
current_fileset -simset [get_filesets $simset]
update_compile_order -fileset $simset
launch_simulation -simset $simset
close_sim
set elaboration [file join $root build ipi_arty_s7_50 debug_lab.sim $simset behav xsim elaborate.log]
set f [open $elaboration r]; set elaborated [read $f]; close $f
if {[regexp {remains a black box|no binding entity} $elaborated]} {error "Unbound component in AMD IP simulation"}
set log [file join $root build ipi_arty_s7_50 debug_lab.sim $simset behav xsim simulate.log]
set f [open $log r]; set result [read $f]; close $f
if {![regexp {ALL .* TESTS PASSED} $result] || [regexp {Failure:|Fatal:|Error:} $result]} {error "IP integration simulation did not pass; inspect $log"}
puts "PASS AMD IP integration: $top"
close_project
exit


# SP701 board-store pin mappings, confirmed against UG1319.
# https://github.com/Xilinx/XilinxBoardStore/blob/2025.2/boards/Xilinx/sp701/1.0/part0_pins.xml
set_property -dict {PACKAGE_PIN AE8 IOSTANDARD LVDS_25} [get_ports clk_in_p]
set_property -dict {PACKAGE_PIN AE7 IOSTANDARD LVDS_25} [get_ports clk_in_n]
set_property -dict {PACKAGE_PIN Y22 IOSTANDARD LVCMOS33} [get_ports uart_rx]
set_property -dict {PACKAGE_PIN Y21 IOSTANDARD LVCMOS33} [get_ports uart_tx]
set_property -dict {PACKAGE_PIN J25 IOSTANDARD LVCMOS33} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN M24 IOSTANDARD LVCMOS33} [get_ports {led[1]}]
set_property -dict {PACKAGE_PIN L24 IOSTANDARD LVCMOS33} [get_ports {led[2]}]
set_property -dict {PACKAGE_PIN K25 IOSTANDARD LVCMOS33} [get_ports {led[3]}]
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

# UARTLite constrains its internal receiver synchronizer. Its external RX pin is
# asynchronous; no relationship to a board clock is assumed for the serial input.
set_false_path -from [get_ports uart_rx]
set_false_path -to [get_ports uart_tx]
set_false_path -to [get_ports {led[*]}]
# The 50 MHz and 12.5 MHz MMCM outputs remain related and timed, including CDC lab.

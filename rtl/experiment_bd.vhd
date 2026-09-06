library ieee;
use ieee.std_logic_1164.all;
entity experiment_bd is
  port (clk, slow_clk, rst : in std_logic;
    reg_write : in std_logic; reg_addr : in std_logic_vector(7 downto 0);
    reg_wdata : in std_logic_vector(31 downto 0); reg_rdata : out std_logic_vector(31 downto 0);
    source_data, axi_wdata : out std_logic_vector(31 downto 0); sink_data : in std_logic_vector(31 downto 0);
    source_valid, source_last, sink_ready : out std_logic;
    source_ready, sink_valid, sink_last : in std_logic;
    axi_awvalid, axi_awready, axi_wvalid, axi_wready, axi_bvalid, axi_bready : out std_logic;
    native0, native1, native2, native3, native4, native5 : out std_logic_vector(31 downto 0); slow_debug : out std_logic_vector(63 downto 0);
    running, error_led, fifo_resetn : out std_logic);
end entity;
architecture rtl of experiment_bd is
  signal fast_debug : std_logic_vector(191 downto 0);
  attribute X_INTERFACE_INFO : string;
  attribute X_INTERFACE_PARAMETER : string;
  attribute X_INTERFACE_INFO of source_data : signal is "xilinx.com:interface:axis:1.0 M_AXIS TDATA";
  attribute X_INTERFACE_INFO of source_valid : signal is "xilinx.com:interface:axis:1.0 M_AXIS TVALID";
  attribute X_INTERFACE_INFO of source_ready : signal is "xilinx.com:interface:axis:1.0 M_AXIS TREADY";
  attribute X_INTERFACE_INFO of source_last : signal is "xilinx.com:interface:axis:1.0 M_AXIS TLAST";
  attribute X_INTERFACE_PARAMETER of source_data : signal is "TDATA_NUM_BYTES 4, HAS_TLAST 1, HAS_TREADY 1, HAS_TKEEP 0, HAS_TSTRB 0, TID_WIDTH 0, TDEST_WIDTH 0, TUSER_WIDTH 0";
  attribute X_INTERFACE_INFO of sink_data : signal is "xilinx.com:interface:axis:1.0 S_AXIS TDATA";
  attribute X_INTERFACE_INFO of sink_valid : signal is "xilinx.com:interface:axis:1.0 S_AXIS TVALID";
  attribute X_INTERFACE_INFO of sink_ready : signal is "xilinx.com:interface:axis:1.0 S_AXIS TREADY";
  attribute X_INTERFACE_INFO of sink_last : signal is "xilinx.com:interface:axis:1.0 S_AXIS TLAST";
  attribute X_INTERFACE_PARAMETER of sink_data : signal is "TDATA_NUM_BYTES 4, HAS_TLAST 1, HAS_TREADY 1, HAS_TKEEP 0, HAS_TSTRB 0, TID_WIDTH 0, TDEST_WIDTH 0, TUSER_WIDTH 0";
  attribute X_INTERFACE_INFO of clk : signal is "xilinx.com:signal:clock:1.0 clk CLK";
  attribute X_INTERFACE_PARAMETER of clk : signal is "ASSOCIATED_BUSIF M_AXIS:S_AXIS, ASSOCIATED_RESET rst:fifo_resetn";
  attribute X_INTERFACE_INFO of slow_clk : signal is "xilinx.com:signal:clock:1.0 slow_clk CLK";
  attribute X_INTERFACE_INFO of rst : signal is "xilinx.com:signal:reset:1.0 rst RST";
  attribute X_INTERFACE_PARAMETER of rst : signal is "POLARITY ACTIVE_HIGH";
  attribute X_INTERFACE_INFO of fifo_resetn : signal is "xilinx.com:signal:reset:1.0 fifo_resetn RST";
  attribute X_INTERFACE_PARAMETER of fifo_resetn : signal is "POLARITY ACTIVE_LOW";
begin
  native0 <= fast_debug(31 downto 0);
  native1 <= fast_debug(63 downto 32);
  native2 <= fast_debug(95 downto 64);
  native3 <= fast_debug(127 downto 96);
  native4 <= fast_debug(159 downto 128);
  native5 <= fast_debug(191 downto 160);
  lab: entity work.debug_lab port map(
    clk => clk,
    slow_clk => slow_clk,
    rst => rst,
    reg_write => reg_write,
    reg_addr => reg_addr,
    reg_wdata => reg_wdata,
    reg_rdata => reg_rdata,
    source_data => source_data,
    sink_data => sink_data,
    axi_wdata => axi_wdata,
    source_valid => source_valid,
    source_ready => source_ready,
    source_last => source_last,
    sink_valid => sink_valid,
    sink_ready => sink_ready,
    sink_last => sink_last,
    axi_awvalid => axi_awvalid,
    axi_awready => axi_awready,
    axi_wvalid => axi_wvalid,
    axi_wready => axi_wready,
    axi_bvalid => axi_bvalid,
    axi_bready => axi_bready,
    fast_debug => fast_debug,
    slow_debug => slow_debug,
    running => running,
    error_led => error_led,
    fifo_resetn => fifo_resetn);
end architecture;

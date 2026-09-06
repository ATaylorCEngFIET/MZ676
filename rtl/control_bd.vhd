library ieee;
use ieee.std_logic_1164.all;
entity control_bd is
  port (clk, rst : in std_logic;
    reg_write : out std_logic; reg_addr : out std_logic_vector(7 downto 0);
    reg_wdata : out std_logic_vector(31 downto 0); reg_rdata : in std_logic_vector(31 downto 0);
    awaddr : out std_logic_vector(31 downto 0); awprot : out std_logic_vector(2 downto 0);
    awvalid : out std_logic; awready : in std_logic;
    wdata : out std_logic_vector(31 downto 0); wstrb : out std_logic_vector(3 downto 0);
    wvalid : out std_logic; wready : in std_logic;
    bresp : in std_logic_vector(1 downto 0); bvalid : in std_logic; bready : out std_logic;
    araddr : out std_logic_vector(31 downto 0); arprot : out std_logic_vector(2 downto 0);
    arvalid : out std_logic; arready : in std_logic;
    rdata : in std_logic_vector(31 downto 0); rresp : in std_logic_vector(1 downto 0);
    rvalid : in std_logic; rready : out std_logic);
end entity;
architecture rtl of control_bd is
  attribute X_INTERFACE_INFO : string;
  attribute X_INTERFACE_PARAMETER : string;
  attribute X_INTERFACE_INFO of awaddr : signal is "xilinx.com:interface:aximm:1.0 M_AXI AWADDR";
  attribute X_INTERFACE_INFO of awprot : signal is "xilinx.com:interface:aximm:1.0 M_AXI AWPROT";
  attribute X_INTERFACE_INFO of awvalid : signal is "xilinx.com:interface:aximm:1.0 M_AXI AWVALID";
  attribute X_INTERFACE_INFO of awready : signal is "xilinx.com:interface:aximm:1.0 M_AXI AWREADY";
  attribute X_INTERFACE_INFO of wdata : signal is "xilinx.com:interface:aximm:1.0 M_AXI WDATA";
  attribute X_INTERFACE_INFO of wstrb : signal is "xilinx.com:interface:aximm:1.0 M_AXI WSTRB";
  attribute X_INTERFACE_INFO of wvalid : signal is "xilinx.com:interface:aximm:1.0 M_AXI WVALID";
  attribute X_INTERFACE_INFO of wready : signal is "xilinx.com:interface:aximm:1.0 M_AXI WREADY";
  attribute X_INTERFACE_INFO of bresp : signal is "xilinx.com:interface:aximm:1.0 M_AXI BRESP";
  attribute X_INTERFACE_INFO of bvalid : signal is "xilinx.com:interface:aximm:1.0 M_AXI BVALID";
  attribute X_INTERFACE_INFO of bready : signal is "xilinx.com:interface:aximm:1.0 M_AXI BREADY";
  attribute X_INTERFACE_INFO of araddr : signal is "xilinx.com:interface:aximm:1.0 M_AXI ARADDR";
  attribute X_INTERFACE_INFO of arprot : signal is "xilinx.com:interface:aximm:1.0 M_AXI ARPROT";
  attribute X_INTERFACE_INFO of arvalid : signal is "xilinx.com:interface:aximm:1.0 M_AXI ARVALID";
  attribute X_INTERFACE_INFO of arready : signal is "xilinx.com:interface:aximm:1.0 M_AXI ARREADY";
  attribute X_INTERFACE_INFO of rdata : signal is "xilinx.com:interface:aximm:1.0 M_AXI RDATA";
  attribute X_INTERFACE_INFO of rresp : signal is "xilinx.com:interface:aximm:1.0 M_AXI RRESP";
  attribute X_INTERFACE_INFO of rvalid : signal is "xilinx.com:interface:aximm:1.0 M_AXI RVALID";
  attribute X_INTERFACE_INFO of rready : signal is "xilinx.com:interface:aximm:1.0 M_AXI RREADY";
  attribute X_INTERFACE_PARAMETER of awaddr : signal is "PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 32, READ_WRITE_MODE READ_WRITE, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1";
  attribute X_INTERFACE_INFO of clk : signal is "xilinx.com:signal:clock:1.0 clk CLK";
  attribute X_INTERFACE_PARAMETER of clk : signal is "ASSOCIATED_BUSIF M_AXI, ASSOCIATED_RESET rst";
  attribute X_INTERFACE_INFO of rst : signal is "xilinx.com:signal:reset:1.0 rst RST";
  attribute X_INTERFACE_PARAMETER of rst : signal is "POLARITY ACTIVE_HIGH";
  signal rd, td : std_logic_vector(7 downto 0);
  signal rv, re, ts, tb : std_logic;
begin
  parser: entity work.command_parser port map(clk, rst, rd, rv, re, td, ts, tb, reg_write, reg_addr, reg_wdata, reg_rdata);
  uart_service: entity work.uartlite_service port map(clk, rst, rd, rv, re, td, ts, tb,
awaddr, awprot, awvalid, awready, wdata, wstrb, wvalid, wready, bresp, bvalid, bready, araddr, arprot, arvalid, arready, rdata, rresp, rvalid, rready);
end architecture;


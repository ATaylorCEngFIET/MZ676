library ieee;
use ieee.std_logic_1164.all;
entity simulation_fifo is
  generic (USE_AMD : boolean := true);
  port (clk, resetn : in std_logic;
    sd : in std_logic_vector(31 downto 0); sv, sl : in std_logic; sr : out std_logic;
    md : out std_logic_vector(31 downto 0); mv, ml : out std_logic; mr : in std_logic);
end entity;
architecture test of simulation_fifo is
  component debug_system_stream_fifo_0 is
    port (s_axis_aresetn, s_axis_aclk, s_axis_tvalid : in std_logic; s_axis_tready : out std_logic;
      s_axis_tdata : in std_logic_vector(31 downto 0); s_axis_tlast : in std_logic;
      m_axis_tvalid : out std_logic; m_axis_tready : in std_logic;
      m_axis_tdata : out std_logic_vector(31 downto 0); m_axis_tlast : out std_logic);
  end component;
begin
  model: if not USE_AMD generate
    fifo: entity work.stream_fifo_model port map(clk,resetn,sd,sv,sl,sr,md,mv,ml,mr);
  end generate;
  vendor: if USE_AMD generate
    fifo: debug_system_stream_fifo_0 port map(resetn,clk,sv,sr,sd,sl,mv,mr,md,ml);
  end generate;
end architecture;

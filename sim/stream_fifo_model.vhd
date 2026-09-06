library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Simulation-only VHDL reference queue. Vendor integration tests select the
-- generated AMD AXI4-Stream Data FIFO instead of this functional model.
entity stream_fifo_model is
  port (clk, resetn : in std_logic;
    sd : in std_logic_vector(31 downto 0); sv, sl : in std_logic; sr : out std_logic;
    md : out std_logic_vector(31 downto 0); mv, ml : out std_logic; mr : in std_logic);
end entity;
architecture model of stream_fifo_model is
  type memory_t is array(0 to 15) of std_logic_vector(32 downto 0);
  signal memory : memory_t := (others => (others => '0'));
  signal rp, wp : natural range 0 to 15 := 0;
  signal count : natural range 0 to 16 := 0;
begin
  sr <= '1' when resetn = '1' and count < 16 else '0';
  mv <= '1' when resetn = '1' and count > 0 else '0';
  md <= memory(rp)(31 downto 0); ml <= memory(rp)(32);
  process(clk)
    variable push, pop : boolean;
  begin
    if rising_edge(clk) then
      if resetn = '0' then count <= 0; rp <= 0; wp <= 0;
      else
        push := sv = '1' and count < 16; pop := mr = '1' and count > 0;
        if push then memory(wp) <= sl & sd; wp <= (wp+1) mod 16; end if;
        if pop then rp <= (rp+1) mod 16; end if;
        if push and not pop then count <= count+1;
        elsif pop and not push then count <= count-1; end if;
      end if;
    end if;
  end process;
end architecture;

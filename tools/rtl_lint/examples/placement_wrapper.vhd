library ieee;
use ieee.std_logic_1164.all;
entity demo_core is
  port (d : in std_logic_vector(7 downto 0); q : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of demo_core is
begin
  q <= not d;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
entity placement_wrapper is
  port (clk : in std_logic;
        din : in std_logic_vector(7 downto 0);
        dout : out std_logic_vector(7 downto 0));
end entity;
architecture rtl of placement_wrapper is
  signal in_1, in_2, core_q, out_1, out_2 : std_logic_vector(7 downto 0);
  attribute shreg_extract : string;
  attribute shreg_extract of in_1, in_2, out_1, out_2 : signal is "no";
begin
  process(clk) begin
    if rising_edge(clk) then
      in_1 <= din;
      in_2 <= in_1;
      out_1 <= core_q;
      out_2 <= out_1;
    end if;
  end process;
  core_i : entity work.demo_core port map (d => in_2, q => core_q);
  dout <= out_2;
end architecture;

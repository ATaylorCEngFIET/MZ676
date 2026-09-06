library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Accounting logic around an AMD AXI4-Stream Data FIFO. The vendor FIFO owns
-- storage and flow control. This intentionally buggy counter never modifies it.
entity occupancy_checker is
  port (clk, rst, fault_enable : in std_logic;
    s_valid, s_ready, m_valid, m_ready : in std_logic;
    occupancy_error : out std_logic; debug : out std_logic_vector(31 downto 0));
end entity;
architecture rtl of occupancy_checker is
  signal wp, rp : unsigned(3 downto 0) := (others => '0');
  signal count, shadow_count : unsigned(4 downto 0) := (others => '0');
  signal push, pop, err, injected : std_logic := '0';
begin
  push <= s_valid and s_ready; pop <= m_valid and m_ready;
  err <= '1' when rst = '0' and count /= shadow_count else '0';
  occupancy_error <= err;
  debug <= x"00" & "000" & pop & push & err & m_valid & s_ready & "000" & std_logic_vector(count) & std_logic_vector(wp) & std_logic_vector(rp);
  process(clk) begin
    if rising_edge(clk) then
      if rst = '1' then
        wp <= (others => '0'); rp <= (others => '0'); count <= (others => '0'); shadow_count <= (others => '0'); injected <= '0';
      else
        if push = '1' then wp <= wp + 1; end if;
        if pop = '1' then rp <= rp + 1; end if;
        if push = '1' and pop = '0' then count <= count + 1; shadow_count <= shadow_count + 1;
        elsif pop = '1' and push = '0' then count <= count - 1; shadow_count <= shadow_count - 1; end if;
        -- FAULT 6: last assignment wins; simultaneous push/pop must leave count unchanged.
        -- Inject once, then preserve the offset for a clear trace against the reference.
        if fault_enable = '1' and push = '1' and pop = '1' and shadow_count >= 15 and injected = '0' then
          count <= count - 1; injected <= '1';
        end if;
      end if;
    end if;
  end process;
end architecture;

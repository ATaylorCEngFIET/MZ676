library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity axi_lab is
  port (clk, rst, run, fault_enable : in std_logic; skew : in unsigned(7 downto 0);
    awvalid, awready, wvalid, wready, bvalid, bready : out std_logic;
    wdata : out std_logic_vector(31 downto 0);
    timeout_error : out std_logic; completed : out std_logic_vector(31 downto 0);
    debug : out std_logic_vector(31 downto 0));
end entity;
architecture rtl of axi_lab is
  signal active, aw_done, w_done, aw_seen, w_seen, bv, timed_out : std_logic := '0';
  signal age : natural range 0 to 2047 := 0;
  signal transactions : unsigned(31 downto 0) := (others => '0');
  signal aw_fire, w_fire : std_logic;
begin
  -- Alternate address-first and data-first transactions. Once asserted, VALID persists.
  awvalid <= '1' when active = '1' and aw_done = '0' and (transactions(0) = '0' or age >= to_integer(skew)) else '0';
  wvalid <= '1' when active = '1' and w_done = '0' and (transactions(0) = '1' or age >= to_integer(skew)) else '0';
  awready <= not (rst or aw_seen or bv); wready <= not (rst or w_seen or bv);
  bvalid <= bv; bready <= '1'; wdata <= std_logic_vector(transactions);
  aw_fire <= awvalid and awready; w_fire <= wvalid and wready;
  completed <= std_logic_vector(transactions); timeout_error <= timed_out;
  debug <= std_logic_vector(to_unsigned(age,16)) & x"00" & timed_out & active & bv & w_seen & aw_seen & w_done & aw_done & fault_enable;
  process(clk) begin
    if rising_edge(clk) then
      if rst = '1' then
        active <= '0'; aw_done <= '0'; w_done <= '0'; aw_seen <= '0'; w_seen <= '0'; bv <= '0';
        timed_out <= '0'; age <= 0; transactions <= (others => '0');
      else
        if active = '0' and run = '1' then active <= '1'; age <= 0; aw_done <= '0'; w_done <= '0'; end if;
        if active = '1' then
          if age < 2047 then age <= age + 1; end if;
          if age = 1024 then timed_out <= '1'; end if;
          if aw_fire = '1' then aw_done <= '1'; aw_seen <= '1'; end if;
          if w_fire = '1' then w_done <= '1'; w_seen <= '1'; end if;
          if bv = '0' then
            if fault_enable = '1' then
              -- FAULT 3: legal, separately accepted channels never produce a response.
              if aw_fire = '1' and w_fire = '1' then bv <= '1'; end if;
            elsif (aw_seen = '1' or aw_fire = '1') and (w_seen = '1' or w_fire = '1') then bv <= '1'; end if;
          end if;
          if bv = '1' then
            bv <= '0'; aw_seen <= '0'; w_seen <= '0'; active <= '0'; transactions <= transactions + 1;
          end if;
        end if;
      end if;
    end if;
  end process;
end architecture;

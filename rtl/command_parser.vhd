library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.lab_pkg.all;
entity command_parser is
  generic (CLOCK_HZ : positive := 50000000);
  port (clk, rst : in std_logic;
    rx_data : in std_logic_vector(7 downto 0); rx_valid, rx_error : in std_logic;
    tx_data : out std_logic_vector(7 downto 0); tx_start : out std_logic; tx_busy : in std_logic;
    reg_write : out std_logic; reg_addr : out std_logic_vector(7 downto 0);
    reg_wdata : out word_t; reg_rdata : in word_t);
end entity;
architecture rtl of command_parser is
  type bytes_t is array (0 to 9) of std_logic_vector(7 downto 0);
  signal request, reply : bytes_t := (others => (others => '0'));
  signal index : natural range 0 to 9 := 0;
  signal timeout_count : natural range 0 to CLOCK_HZ/100 := 0;
  signal state : natural range 0 to 6 := 0;
  signal status : std_logic_vector(7 downto 0) := (others => '0');
begin
  process(clk)
    variable checksum : std_logic_vector(7 downto 0);
    variable a : natural;
  begin
    if rising_edge(clk) then
      reg_write <= '0'; tx_start <= '0';
      if rst = '1' then
        index <= 0; state <= 0; timeout_count <= 0; reg_addr <= (others => '0'); reg_wdata <= (others => '0');
      else
        case state is
          when 0 =>
            if index /= 0 then
              if timeout_count = CLOCK_HZ/100 then index <= 0; timeout_count <= 0;
              else timeout_count <= timeout_count + 1; end if;
            end if;
            if rx_error = '1' then index <= 0;
            elsif rx_valid = '1' then
              timeout_count <= 0;
              if index = 0 then
                if rx_data = x"A5" then request(0) <= rx_data; index <= 1; end if;
              else
                request(index) <= rx_data;
                if index = 9 then index <= 0; state <= 1; else index <= index+1; end if;
              end if;
            end if;
          when 1 =>
            checksum := x"00";
            for i in 1 to 7 loop checksum := checksum xor request(i); end loop;
            status <= x"00"; a := to_integer(unsigned(request(3)));
            reg_addr <= request(3); reg_wdata <= request(7) & request(6) & request(5) & request(4);
            if request(9) /= x"5A" then state <= 0;
            elsif checksum /= request(8) then status <= x"01"; state <= 2;
            elsif request(2) /= x"01" and request(2) /= x"02" then status <= x"02"; state <= 2;
            elsif (request(2) = x"01" and not (a <= 7 or (a >= 16 and a <= 31))) or
                  (request(2) = x"02" and not (a >= 1 and a <= 7)) then status <= x"03"; state <= 2;
            else
              if request(2) = x"02" then reg_write <= '1'; end if;
              state <= 2;
            end if;
          when 2 => state <= 3; -- let register writes commit before returning readback
          when 3 =>
            reply(0) <= x"A5"; reply(1) <= request(1); reply(2) <= status; reply(3) <= request(3);
            for i in 0 to 3 loop reply(4+i) <= reg_rdata(i*8+7 downto i*8); end loop;
            reply(8) <= request(1) xor status xor request(3) xor reg_rdata(7 downto 0) xor reg_rdata(15 downto 8) xor reg_rdata(23 downto 16) xor reg_rdata(31 downto 24);
            reply(9) <= x"5A"; index <= 0; state <= 4;
          when 4 => tx_data <= reply(index); tx_start <= '1'; state <= 5;
          when 5 => if tx_busy = '1' then state <= 6; end if;
          when others =>
            if tx_busy = '0' then
              if index = 9 then index <= 0; state <= 0; else index <= index+1; state <= 4; end if;
            end if;
        end case;
      end if;
    end if;
  end process;
end architecture;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.lab_pkg.all;
entity tb_board_boot is end;
architecture test of tb_board_boot is
  constant BIT_TIME : time := 8680 ns;
  signal clk : std_logic := '0';
  signal board_clk : std_logic := '0';
  signal leds : std_logic_vector(3 downto 0);
  signal rx : std_logic := '1'; signal tx : std_logic;
  type bytes_t is array (natural range <>) of std_logic_vector(7 downto 0);
  signal captured : bytes_t(0 to 999);
  signal captured_count : natural := 0;
begin
  clk <= not clk after 10 ns; -- testbench polling only
  board_clk <= not board_clk after 41.666667 ns; -- Arty 12 MHz oscillator
  board: entity work.debug_system_wrapper port map(clk_in => board_clk, uart_rx => rx, uart_tx => tx, led => leds);
  process
    variable value : std_logic_vector(7 downto 0);
  begin
    wait until tx = '0'; wait for BIT_TIME + BIT_TIME/2;
    for b in 0 to 7 loop value(b) := tx; wait for BIT_TIME; end loop;
    assert tx = '1' report "Bad TX stop bit" severity failure;
    captured(captured_count) <= value; captured_count <= captured_count + 1;
  end process;
  process
    variable seq_id : natural := 0;
    procedure send_byte(value : std_logic_vector(7 downto 0)) is begin
      rx <= '0'; wait for BIT_TIME;
      for b in 0 to 7 loop rx <= value(b); wait for BIT_TIME; end loop;
      rx <= '1'; wait for BIT_TIME;
    end;
    procedure request(op, a, data, expected_status : natural; variable result : out word_t; corrupt : boolean := false) is
      variable packet : bytes_t(0 to 9);
      variable checksum : std_logic_vector(7 downto 0);
      variable start_count : natural;
      variable dw : word_t;
    begin
      start_count := captured_count; seq_id := seq_id + 1; dw := std_logic_vector(to_unsigned(data,32));
      packet(0) := x"A5"; packet(1) := std_logic_vector(to_unsigned(seq_id,8));
      packet(2) := std_logic_vector(to_unsigned(op,8)); packet(3) := std_logic_vector(to_unsigned(a,8));
      for i in 0 to 3 loop packet(4+i) := dw(i*8+7 downto i*8); end loop;
      checksum := x"00"; for i in 1 to 7 loop checksum := checksum xor packet(i); end loop;
      if corrupt then checksum := checksum xor x"80"; end if;
      packet(8) := checksum; packet(9) := x"5A";
      for i in 0 to 9 loop send_byte(packet(i)); end loop;
      for i in 0 to 100000 loop
        exit when captured_count = start_count+10;
        wait until rising_edge(clk);
      end loop;
      assert captured_count = start_count+10 report "UART response timeout" severity failure;
      assert captured(start_count) = x"A5" and captured(start_count+9) = x"5A" report "Reply framing" severity failure;
      assert captured(start_count+1) = packet(1) and captured(start_count+3) = packet(3) report "Reply identity" severity failure;
      assert unsigned(captured(start_count+2)) = expected_status report "Reply status" severity failure;
      checksum := x"00"; for i in 1 to 7 loop checksum := checksum xor captured(start_count+i); end loop;
      assert checksum = captured(start_count+8) report "Reply checksum" severity failure;
      result := captured(start_count+7) & captured(start_count+6) & captured(start_count+5) & captured(start_count+4);
      wait for BIT_TIME;
    end;
    variable result : word_t;
  begin
    wait for 200 us;
    assert leds(2) = '1' and leds(1 downto 0) = "00" report "Board did not start locked and stopped" severity failure;
    request(1,0,0,0,result); assert result = DEVICE_ID report "Device ID" severity failure;
    report "ALL BOARD BOOT AND UART TESTS PASSED"; finish;
  end process;
  process begin wait for 10 ms; assert false report "UART test watchdog" severity failure; end process;
end architecture;


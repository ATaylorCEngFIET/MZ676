library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.lab_pkg.all;
entity tb_uart_control is end;
architecture test of tb_uart_control is
  constant BIT_TIME : time := 8680 ns; -- 115200 baud, 50 MHz UARTLite clock
  signal clk : std_logic := '0'; signal slow_clk : std_logic := '0'; signal rst : std_logic := '1';
  signal rx : std_logic := '1'; signal tx, wr : std_logic;
  signal addr : std_logic_vector(7 downto 0); signal wd, rd : word_t;
  type bytes_t is array (natural range <>) of std_logic_vector(7 downto 0);
  signal captured : bytes_t(0 to 999);
  signal captured_count : natural := 0;
  signal resetn, fifo_resetn, sv, sr, sl, mv, mr, ml : std_logic;
  signal sd, md : word_t;
  signal awaddr, araddr, wdata, rdata : word_t;
  signal awprot, arprot : std_logic_vector(2 downto 0);
  signal wstrb : std_logic_vector(3 downto 0);
  signal bresp, rresp : std_logic_vector(1 downto 0);
  signal av, ar, wv, ww, bv, br, rav, rar, rv, rr : std_logic;
  component debug_system_uart_0 is
    port (s_axi_aclk, s_axi_aresetn : in std_logic;
      s_axi_awaddr : in std_logic_vector(3 downto 0); s_axi_awvalid : in std_logic; s_axi_awready : out std_logic;
      s_axi_wdata : in word_t; s_axi_wstrb : in std_logic_vector(3 downto 0); s_axi_wvalid : in std_logic; s_axi_wready : out std_logic;
      s_axi_bresp : out std_logic_vector(1 downto 0); s_axi_bvalid : out std_logic; s_axi_bready : in std_logic;
      s_axi_araddr : in std_logic_vector(3 downto 0); s_axi_arvalid : in std_logic; s_axi_arready : out std_logic;
      s_axi_rdata : out word_t; s_axi_rresp : out std_logic_vector(1 downto 0); s_axi_rvalid : out std_logic; s_axi_rready : in std_logic;
      rx : in std_logic; tx, interrupt : out std_logic);
  end component;
begin
  clk <= not clk after 10 ns; slow_clk <= not slow_clk after 40 ns;
  resetn <= not rst;
  control: entity work.control_bd port map(clk, rst, wr, addr, wd, rd,
    awaddr, awprot, av, ar, wdata, wstrb, wv, ww, bresp, bv, br,
    araddr, arprot, rav, rar, rdata, rresp, rv, rr);
  uart: debug_system_uart_0 port map(clk, resetn,
    awaddr(3 downto 0), av, ar, wdata, wstrb, wv, ww, bresp, bv, br,
    araddr(3 downto 0), rav, rar, rdata, rresp, rv, rr, rx, tx, open);
  fifo: entity work.simulation_fifo generic map(true) port map(clk,fifo_resetn,sd,sv,sl,sr,md,mv,ml,mr);
  lab: entity work.debug_lab port map(clk => clk, slow_clk => slow_clk, rst => rst,
    reg_write => wr, reg_addr => addr, reg_wdata => wd, reg_rdata => rd,
    source_data => sd, sink_data => md, axi_wdata => open,
    source_valid => sv, source_ready => sr, source_last => sl, sink_valid => mv, sink_ready => mr, sink_last => ml,
    axi_awvalid => open, axi_awready => open, axi_wvalid => open, axi_wready => open, axi_bvalid => open, axi_bready => open,
    fast_debug => open, slow_debug => open, running => open, error_led => open, fifo_resetn => fifo_resetn);
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
    wait for 2 us; wait until falling_edge(clk); rst <= '0'; wait for 20 us;
    request(1,0,0,0,result); assert result = DEVICE_ID report "Device ID" severity failure;
    request(2,2,3,0,result); assert unsigned(result) = 3 report "Mode write" severity failure;
    request(2,2,6,1,result,true);
    request(1,2,0,0,result); assert unsigned(result) = 3 report "Bad checksum changed register" severity failure;
    request(9,2,0,2,result);
    request(2,0,0,3,result);
    request(1,8,0,3,result);
    -- Truncated frames time out; arbitrary noise before the next sync byte is ignored.
    send_byte(x"A5"); send_byte(x"22"); send_byte(x"01"); wait for 11 ms;
    send_byte(x"33"); send_byte(x"44");
    request(1,0,0,0,result); assert result = DEVICE_ID report "Parser did not recover" severity failure;
    -- A framing error resets the parser, then a fresh valid frame succeeds.
    rx <= '0'; wait for BIT_TIME*12; rx <= '1'; wait for BIT_TIME*12;
    request(1,0,0,0,result); assert result = DEVICE_ID report "Framing recovery" severity failure;
    request(2,1,1,0,result);
    wait for 30 us;
    request(2,1,8,0,result);
    request(1,17,0,0,result); assert result(3) = '1' report "UART-configured AXI fault was not recorded" severity failure;
    request(2,1,4,0,result);
    request(2,1,8,0,result);
    request(1,17,0,0,result); assert unsigned(result) = 0 report "Clear did not reset errors" severity failure;
    report "ALL UART INTEGRATION TESTS PASSED"; finish;
  end process;
  process begin wait for 100 ms; assert false report "UART test watchdog" severity failure; end process;
end architecture;


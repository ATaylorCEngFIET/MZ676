library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
entity tb_uartlite_service is end;
architecture test of tb_uartlite_service is
  signal clk : std_logic := '0'; signal rst : std_logic := '1';
  signal rd, td : std_logic_vector(7 downto 0) := (others => '0');
  signal rxv, rxe, start, busy : std_logic := '0';
  signal awaddr, wdata, araddr, rdata : std_logic_vector(31 downto 0) := (others => '0');
  signal awprot, arprot : std_logic_vector(2 downto 0); signal wstrb : std_logic_vector(3 downto 0);
  signal av, ar, wv, wr, bv, br, arv, arr, rv, rr : std_logic := '0';
  signal got_aw, got_w : std_logic := '0';
  signal saved_a, saved_d : std_logic_vector(31 downto 0) := (others => '0');
  signal writes, transmitted, received, rx_index, errors, cycles : natural := 0;
  signal error_request, error_reported : std_logic := '0';
  signal read_wait : natural range 0 to 4 := 0;
begin
  clk <= not clk after 10 ns;
  dut: entity work.uartlite_service port map(clk,rst,rd,rxv,rxe,td,start,busy,
    awaddr,awprot,av,ar,wdata,wstrb,wv,wr,"00",bv,br,araddr,arprot,arv,arr,rdata,"00",rv,rr);
  -- Alternate address-first and data-first target acceptance. Neither requires
  -- coincident VALID. Read responses and FIFO space are independently delayed.
  ar <= '1' when rst = '0' and got_aw = '0' and (writes mod 2 = 0 or got_w = '1') else '0';
  wr <= '1' when rst = '0' and got_w = '0' and (writes mod 2 = 1 or got_aw = '1') else '0';
  arr <= '1' when rst = '0' and read_wait = 0 and rv = '0' and cycles mod 5 = 0 else '0';
  bv <= got_aw and got_w;
  process(clk)
    variable data_v : std_logic_vector(31 downto 0);
  begin
    if rising_edge(clk) then
      if rst = '0' then
        cycles <= cycles + 1;
        if av = '1' and ar = '1' then saved_a <= awaddr; got_aw <= '1'; end if;
        if wv = '1' and wr = '1' then saved_d <= wdata; got_w <= '1'; end if;
        if bv = '1' and br = '1' then
          got_aw <= '0'; got_w <= '0'; writes <= writes + 1;
          if saved_a = x"0000000C" then
            if writes = 0 then assert saved_d = x"00000003" report "Missing UART init" severity failure;
            else assert saved_d = x"00000002" report "Wrong RX flush" severity failure; end if;
          else
            assert saved_a = x"00000004" and cycles >= 100 report "Bad or premature TX write" severity failure;
            if transmitted = 0 then assert saved_d = x"00000042" severity failure;
            else assert saved_d = x"00000099" severity failure; end if;
            transmitted <= transmitted + 1;
          end if;
        end if;
        if arv = '1' and arr = '1' then
          data_v := (others => '0');
          if araddr = x"00000008" then
            if cycles < 100 then data_v(3) := '1'; end if;
            if rx_index < 2 then data_v(0) := '1'; end if;
            if error_request = '1' and error_reported = '0' then data_v(5) := '1'; error_reported <= '1'; end if;
          else
            assert araddr = x"00000000" and rx_index < 2 report "Invalid RX read" severity failure;
            data_v(7 downto 0) := std_logic_vector(to_unsigned(16#B0#+rx_index,8)); rx_index <= rx_index+1;
          end if;
          rdata <= data_v; read_wait <= 4;
        elsif read_wait > 1 then read_wait <= read_wait-1;
        elsif read_wait = 1 then rv <= '1'; read_wait <= 0;
        elsif rv = '1' and rr = '1' then rv <= '0'; end if;
        if rxv = '1' then
          assert rd = std_logic_vector(to_unsigned(16#B0#+received,8)) report "RX byte ordering" severity failure;
          received <= received + 1;
        end if;
        if rxe = '1' then errors <= errors + 1; end if;
      end if;
    end if;
  end process;
  process
    procedure send(d : std_logic_vector(7 downto 0)) is begin
      wait until falling_edge(clk); td <= d; start <= '1';
      wait until falling_edge(clk); start <= '0';
      assert busy = '1' report "TX request not held" severity failure;
      wait until busy = '0';
    end;
  begin
    wait for 200 ns; wait until falling_edge(clk); rst <= '0';
    send(x"42"); send(x"99");
    wait until falling_edge(clk); error_request <= '1';
    wait until writes = 4; wait for 100 ns;
    assert transmitted = 2 and received = 2 and errors = 1 report "UART service accounting" severity failure;
    report "ALL UARTLITE SERVICE TESTS PASSED"; finish;
  end process;
  process begin wait for 100 us; assert false report "Service test watchdog" severity failure; end process;
end architecture;

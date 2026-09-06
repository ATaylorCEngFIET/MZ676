library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.env.all;
use work.lab_pkg.all;
entity tb_debug_lab is generic (USE_AMD : boolean := false); end;
architecture test of tb_debug_lab is
  signal clk : std_logic := '0'; signal slow_clk : std_logic := '0'; signal rst : std_logic := '1';
  signal wr : std_logic := '0'; signal addr : std_logic_vector(7 downto 0) := (others => '0');
  signal wd, rd, sd, md, ad : word_t := (others => '0');
  signal sv,sr,sl,mv,mr,ml,av,ar,wv,ww,bv,br,running,err : std_logic;
  signal fifo_resetn : std_logic;
  signal fd : std_logic_vector(191 downto 0); signal cd : std_logic_vector(63 downto 0);
begin
  clk <= not clk after 10 ns; slow_clk <= not slow_clk after 40 ns;
  dut: entity work.debug_lab port map(clk => clk, slow_clk => slow_clk, rst => rst,
    reg_write => wr, reg_addr => addr, reg_wdata => wd, reg_rdata => rd,
    source_data => sd, sink_data => md, axi_wdata => ad,
    source_valid => sv, source_ready => sr, source_last => sl, sink_valid => mv, sink_ready => mr, sink_last => ml,
    axi_awvalid => av, axi_awready => ar, axi_wvalid => wv, axi_wready => ww, axi_bvalid => bv, axi_bready => br,
    fast_debug => fd, slow_debug => cd, running => running, error_led => err, fifo_resetn => fifo_resetn);
  fifo: entity work.simulation_fifo generic map(USE_AMD) port map(clk,fifo_resetn,sd,sv,sl,sr,md,mv,ml,mr);
  process
    procedure write_reg(a : natural; d : natural) is begin
      wait until falling_edge(clk); addr <= std_logic_vector(to_unsigned(a,8)); wd <= std_logic_vector(to_unsigned(d,32)); wr <= '1';
      wait until falling_edge(clk); wr <= '0';
    end;
    procedure read_reg(a : natural; variable d : out word_t) is begin
      addr <= std_logic_vector(to_unsigned(a,8)); wait for 1 ns; d := rd;
    end;
    procedure run_case(m, stall, skew, target, required, forbidden : natural) is
      variable value : word_t; variable bits : unsigned(31 downto 0);
    begin
      write_reg(2,m); write_reg(3,16); write_reg(4,stall); write_reg(5,64); write_reg(6,target); write_reg(7,skew); write_reg(1,1);
      for i in 0 to 11999 loop wait until rising_edge(clk); end loop;
      write_reg(1,8); read_reg(17,value); bits := unsigned(value);
      assert (bits and to_unsigned(required,32)) = to_unsigned(required,32)
        report "Missing fault for mode " & integer'image(m) & " got " & to_hstring(value) severity failure;
      assert (bits and to_unsigned(forbidden,32)) = 0
        report "Unexpected fault for mode " & integer'image(m) & " got " & to_hstring(value) severity failure;
      if m = 0 then
        read_reg(18,value); assert unsigned(value) > 100 report "No stream traffic" severity failure;
        read_reg(24,value); assert unsigned(value) > 10 report "No AXI completions" severity failure;
        read_reg(26,value); assert unsigned(value) = 32 report "Healthy CDC did not deliver 32 events" severity failure;
      end if;
      report "PASS mode=" & integer'image(m) & " stall=" & integer'image(stall) & " skew=" & integer'image(skew) & " errors=" & to_hstring(std_logic_vector(bits));
      write_reg(1,2);
    end;
    variable v : word_t;
  begin
    wait for 200 ns; wait until falling_edge(clk); rst <= '0';
    read_reg(0,v); assert v = DEVICE_ID severity failure;
    run_case(0,48,16,8,0,63);
    run_case(1,48,16,8,5,56);
    run_case(2,48,16,8,2,57);
    run_case(3,48,16,8,8,55);
    run_case(4,48,16,8,1,62);
    run_case(5,48,16,8,16,47);
    run_case(6,48,16,8,32,28);
    run_case(1,0,16,8,0,63);
    run_case(2,0,16,8,0,63);
    run_case(3,48,0,8,0,63);
    run_case(4,0,16,8,0,63);
    run_case(6,0,16,8,0,63);
    run_case(0,48,16,8,0,63);
    -- Pending writes must not alter the active mode without START.
    write_reg(2,3); read_reg(1,v);
    assert v(6 downto 4) = "000" report "Pending mode changed active experiment" severity failure;
    write_reg(2,7); read_reg(2,v);
    assert unsigned(v) = 3 report "Out-of-range mode accepted" severity failure;
    write_reg(3,1); read_reg(3,v);
    assert unsigned(v) = 16 report "Out-of-range packet length accepted" severity failure;
    -- Once captured, snapshot registers remain unchanged while the live design runs.
    write_reg(2,0); write_reg(1,1);
    for i in 0 to 1000 loop wait until rising_edge(clk); end loop;
    write_reg(1,8); read_reg(27,v);
    for i in 0 to 1000 loop wait until rising_edge(clk); end loop;
    assert rd = v report "Snapshot changed without another snapshot command" severity failure;
    report "ALL RTL EXPERIMENT TESTS PASSED";
    finish;
  end process;
  process begin wait for 10 ms; assert false report "Test watchdog" severity failure; end process;
end architecture;

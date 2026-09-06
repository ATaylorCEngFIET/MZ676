library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.lab_pkg.all;

entity debug_lab is
  port (clk, slow_clk, rst : in std_logic;
    reg_write : in std_logic; reg_addr : in std_logic_vector(7 downto 0);
    reg_wdata : in word_t; reg_rdata : out word_t;
    source_data, axi_wdata : out word_t; sink_data : in word_t;
    source_valid, source_last, sink_ready : out std_logic;
    source_ready, sink_valid, sink_last : in std_logic;
    axi_awvalid, axi_awready, axi_wvalid, axi_wready, axi_bvalid, axi_bready : out std_logic;
    fast_debug : out std_logic_vector(191 downto 0); slow_debug : out std_logic_vector(63 downto 0);
    running, error_led, fifo_resetn : out std_logic);
end entity;
architecture rtl of debug_lab is
  signal cfg_mode, mode : natural range 0 to 6 := 0;
  signal cfg_words, packet_words : natural range 2 to 256 := 16;
  signal cfg_stall, stall_cycles : natural range 0 to 255 := 48;
  signal cfg_period, stall_period : natural range 2 to 65535 := 64;
  signal cfg_rare, rare_packet : unsigned(31 downto 0) := to_unsigned(10000,32);
  signal cfg_skew, axi_skew : unsigned(7 downto 0) := to_unsigned(16,8);
  signal run_i : std_logic := '0';
  signal reset_count : natural range 0 to 31 := 31;
  signal exp_rst, flow_run : std_logic;
  signal warmup : natural range 0 to 16 := 0;
  signal seq, packet_id, expected, words_seen, packets_seen, cycles : unsigned(31 downto 0) := (others => '0');
  signal beat, bad_beat, check_beat : natural range 0 to 255 := 0;
  signal phase : natural range 0 to 65534 := 0;
  signal saw_stall, prior_stall : std_logic := '0';
  signal held_payload : std_logic_vector(32 downto 0) := (others => '0');
  signal fifo_fault, axi_fault, cdc_fault, fifo_error, axi_error, cdc_complete : std_logic;
  signal fifo_debug, axi_debug, axi_completed, cdc_sent, cdc_received : word_t;
  signal errors, events : std_logic_vector(5 downto 0) := (others => '0');
  signal first_expected, first_actual, first_packet, first_cycle : word_t := (others => '0');
  signal snapshot : words_t(0 to 15) := (others => (others => '0'));
  signal status_word : word_t;
begin
  exp_rst <= '1' when rst = '1' or reset_count /= 0 else '0';
  fifo_resetn <= not exp_rst;
  flow_run <= run_i when warmup = 16 else '0';
  process(clk) begin
    if rising_edge(clk) then
      if exp_rst = '1' then warmup <= 0;
      elsif warmup < 16 then warmup <= warmup + 1; end if;
    end if;
  end process;
  running <= run_i; error_led <= '1' when errors /= "000000" else '0';
  fifo_fault <= '1' when mode = F_FIFO else '0'; axi_fault <= '1' when mode = F_AXI else '0'; cdc_fault <= '1' when mode = F_CDC else '0';
  source_valid <= flow_run and not exp_rst;
  -- Fault 4 is armed by an earlier stall in this packet; it corrupts only its last word.
  source_data <= std_logic_vector(seq xor x"00000001") when mode = F_RARE and packet_id = rare_packet and beat = packet_words-1 and saw_stall = '1' else std_logic_vector(seq);
  source_last <= '1' when (mode = F_TLAST and bad_beat = packet_words-1) or (mode /= F_TLAST and beat = packet_words-1) else '0';
  sink_ready <= '1' when flow_run = '1' and exp_rst = '0' and phase >= stall_cycles else '0';
  accounting: entity work.occupancy_checker port map(clk, exp_rst, fifo_fault,
    source_valid, source_ready, sink_valid, sink_ready, fifo_error, fifo_debug);
  axi: entity work.axi_lab port map(clk, exp_rst, flow_run, axi_fault, axi_skew,
    axi_awvalid, axi_awready, axi_wvalid, axi_wready, axi_bvalid, axi_bready, axi_wdata, axi_error, axi_completed, axi_debug);
  cdc: entity work.cdc_lab port map(clk, slow_clk, exp_rst, flow_run, cdc_fault, cdc_sent, cdc_received, cdc_complete, slow_debug);

  process(all)
    variable e : std_logic_vector(5 downto 0);
  begin
    e := (others => '0');
    if exp_rst = '0' and flow_run = '1' then
      if sink_valid = '1' and sink_ready = '1' then
        if sink_data /= std_logic_vector(expected) then e(0) := '1'; end if;
        if (sink_last = '1' and check_beat /= packet_words-1) or (sink_last = '0' and check_beat = packet_words-1) then e(1) := '1'; end if;
      end if;
      if prior_stall = '1' and (source_valid = '0' or (source_last & source_data) /= held_payload) then e(2) := '1'; end if;
      e(3) := axi_error;
      if cdc_complete = '1' and cdc_sent /= cdc_received then e(4) := '1'; end if;
      e(5) := fifo_error;
    end if;
    events <= e;
  end process;

  process(clk) begin
    if rising_edge(clk) then
      if exp_rst = '1' then
        seq <= (others => '0'); packet_id <= (others => '0'); expected <= (others => '0');
        words_seen <= (others => '0'); packets_seen <= (others => '0'); cycles <= (others => '0');
        beat <= 0; bad_beat <= 0; check_beat <= 0; phase <= 0; saw_stall <= '0'; prior_stall <= '0';
        held_payload <= (others => '0'); errors <= (others => '0');
        first_expected <= (others => '0'); first_actual <= (others => '0'); first_packet <= (others => '0'); first_cycle <= (others => '0');
      else
        if flow_run = '1' then
          cycles <= cycles + 1;
          if phase = stall_period-1 then phase <= 0; else phase <= phase + 1; end if;
          if bad_beat = packet_words-1 then bad_beat <= 0; else bad_beat <= bad_beat + 1; end if;
        end if;
        if source_valid = '1' then
          -- FAULT 1: the data counter ignores backpressure.
          if source_ready = '1' or mode = F_BACKPRESSURE then seq <= seq + 1; end if;
          if source_ready = '0' and beat /= packet_words-1 then saw_stall <= '1'; end if;
          if source_ready = '1' then
            if beat = packet_words-1 then beat <= 0; packet_id <= packet_id + 1; saw_stall <= '0'; else beat <= beat + 1; end if;
          end if;
        end if;
        prior_stall <= source_valid and not source_ready;
        held_payload <= source_last & source_data;
        if sink_valid = '1' and sink_ready = '1' then
          expected <= expected + 1; words_seen <= words_seen + 1;
          if check_beat = packet_words-1 then check_beat <= 0; packets_seen <= packets_seen + 1; else check_beat <= check_beat + 1; end if;
        end if;
        errors <= errors or events;
        if errors = "000000" and events /= "000000" then
          first_expected <= std_logic_vector(expected); first_actual <= sink_data;
          first_packet <= std_logic_vector(packets_seen); first_cycle <= std_logic_vector(cycles);
        end if;
      end if;
    end if;
  end process;

  status_word <= x"000000" & '0' & std_logic_vector(to_unsigned(mode,3)) & cdc_complete & exp_rst & error_led & run_i;
  -- Six native probe words, low word first: flags/events, cycle, packet, expected, FIFO, AXI.
  fast_debug <= axi_debug & fifo_debug & std_logic_vector(expected) & std_logic_vector(packet_id) & std_logic_vector(cycles) &
                "000000" & errors & "00" & events & std_logic_vector(to_unsigned(mode,4)) & "0000" & saw_stall & exp_rst & error_led & run_i;
  process(all)
    variable a : natural;
  begin
    a := to_integer(unsigned(reg_addr)); reg_rdata <= (others => '0');
    case a is
      when 0 => reg_rdata <= DEVICE_ID;
      when 1 => reg_rdata <= status_word;
      when 2 => reg_rdata <= std_logic_vector(to_unsigned(cfg_mode,32));
      when 3 => reg_rdata <= std_logic_vector(to_unsigned(cfg_words,32));
      when 4 => reg_rdata <= std_logic_vector(to_unsigned(cfg_stall,32));
      when 5 => reg_rdata <= std_logic_vector(to_unsigned(cfg_period,32));
      when 6 => reg_rdata <= std_logic_vector(cfg_rare);
      when 7 => reg_rdata <= std_logic_vector(resize(cfg_skew,32));
      when 16 to 31 => reg_rdata <= snapshot(a-16);
      when others => null;
    end case;
  end process;
  process(clk)
    variable a : natural;
  begin
    if rising_edge(clk) then
      if rst = '1' then
        cfg_mode <= 0; mode <= 0; cfg_words <= 16; packet_words <= 16; cfg_stall <= 48; stall_cycles <= 48;
        cfg_period <= 64; stall_period <= 64; cfg_rare <= to_unsigned(10000,32); rare_packet <= to_unsigned(10000,32);
        cfg_skew <= to_unsigned(16,8); axi_skew <= to_unsigned(16,8); run_i <= '0'; reset_count <= 31;
        snapshot <= (others => (others => '0'));
      else
        if reset_count /= 0 then reset_count <= reset_count - 1; end if;
        if reg_write = '1' then
          a := to_integer(unsigned(reg_addr));
          case a is
            when 1 =>
              if reg_wdata(0) = '1' then
                mode <= cfg_mode; packet_words <= cfg_words; stall_cycles <= cfg_stall; stall_period <= cfg_period;
                rare_packet <= cfg_rare; axi_skew <= cfg_skew; reset_count <= 31; run_i <= '1';
              elsif reg_wdata(1) = '1' then run_i <= '0';
              elsif reg_wdata(2) = '1' then run_i <= '0'; reset_count <= 31; end if;
              if reg_wdata(3) = '1' then
                snapshot(0) <= status_word; snapshot(1) <= (31 downto 6 => '0') & errors;
                snapshot(2) <= std_logic_vector(words_seen); snapshot(3) <= std_logic_vector(packets_seen);
                snapshot(4) <= first_expected; snapshot(5) <= first_actual; snapshot(6) <= first_packet; snapshot(7) <= first_cycle;
                snapshot(8) <= axi_completed; snapshot(9) <= cdc_sent; snapshot(10) <= cdc_received;
                snapshot(11) <= std_logic_vector(cycles); snapshot(12) <= fifo_debug;
                snapshot(13) <= std_logic_vector(packet_id); snapshot(14) <= std_logic_vector(to_unsigned(mode,32)); snapshot(15) <= x"00020000";
              end if;
            when 2 => if unsigned(reg_wdata) <= 6 then cfg_mode <= to_integer(unsigned(reg_wdata(2 downto 0))); end if;
            when 3 => if unsigned(reg_wdata) >= 2 and unsigned(reg_wdata) <= 256 then cfg_words <= to_integer(unsigned(reg_wdata(8 downto 0))); end if;
            when 4 => if unsigned(reg_wdata) <= 255 then cfg_stall <= to_integer(unsigned(reg_wdata(7 downto 0))); end if;
            when 5 => if unsigned(reg_wdata) >= 2 and unsigned(reg_wdata) <= 65535 then cfg_period <= to_integer(unsigned(reg_wdata(15 downto 0))); end if;
            when 6 => cfg_rare <= unsigned(reg_wdata);
            when 7 => if unsigned(reg_wdata) <= 255 then cfg_skew <= unsigned(reg_wdata(7 downto 0)); end if;
            when others => null;
          end case;
        end if;
      end if;
    end if;
  end process;
end architecture;

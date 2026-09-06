library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity cdc_lab is
  port (clk, slow_clk, rst, run, fault_enable : in std_logic;
    sent, received : out std_logic_vector(31 downto 0);
    complete : out std_logic; slow_debug : out std_logic_vector(63 downto 0));
end entity;
architecture rtl of cdc_lab is
  signal slow_reset : std_logic_vector(1 downto 0) := "11";
  signal req, pulse, source_done, ack, pulse_d, slow_done : std_logic := '0';
  signal pacing, settle : natural range 0 to 255 := 0;
  signal ack_sync, done_sync, req_sync, pulse_sync, source_done_sync : std_logic_vector(1 downto 0) := "00";
  signal sent_i, received_i, slow_received : unsigned(31 downto 0) := (others => '0');
  signal complete_i : std_logic := '0';
  attribute ASYNC_REG : string;
  attribute ASYNC_REG of ack_sync, done_sync, req_sync, pulse_sync, source_done_sync, slow_reset : signal is "TRUE";
begin
  sent <= std_logic_vector(sent_i); received <= std_logic_vector(received_i); complete <= complete_i;
  process(slow_clk, rst) begin
    if rst = '1' then slow_reset <= "11";
    elsif rising_edge(slow_clk) then slow_reset <= slow_reset(0) & '0'; end if;
  end process;
  process(clk) begin
    if rising_edge(clk) then
      if rst = '1' then
        sent_i <= (others => '0'); received_i <= (others => '0'); complete_i <= '0'; req <= '0'; pulse <= '0';
        pacing <= 0; settle <= 0; source_done <= '0'; ack_sync <= "00"; done_sync <= "00";
      else
        ack_sync <= ack_sync(0) & ack; done_sync <= done_sync(0) & slow_done; pulse <= '0';
        if run = '1' and sent_i < 32 then
          -- 33 source clocks walks the short pulse through the /4 clock phases.
          if pacing = 32 and (fault_enable = '1' or req = ack_sync(1)) then
            req <= not req; pulse <= '1'; sent_i <= sent_i + 1; pacing <= 0;
          elsif pacing < 32 then pacing <= pacing + 1; end if;
        end if;
        if sent_i = 32 and source_done = '0' then
          if settle = 128 then source_done <= '1'; else settle <= settle + 1; end if;
        end if;
        -- slow_received is held stable before slow_done crosses: bundled-data handshake.
        if done_sync(1) = '1' and complete_i = '0' then received_i <= slow_received; complete_i <= '1'; end if;
      end if;
    end if;
  end process;
  process(slow_clk) begin
    if rising_edge(slow_clk) then
      if slow_reset(1) = '1' then
        req_sync <= "00"; pulse_sync <= "00"; source_done_sync <= "00";
        ack <= '0'; pulse_d <= '0'; slow_done <= '0'; slow_received <= (others => '0');
      else
        req_sync <= req_sync(0) & req; pulse_sync <= pulse_sync(0) & pulse;
        source_done_sync <= source_done_sync(0) & source_done; pulse_d <= pulse_sync(1);
        if source_done_sync(1) = '0' then
          if fault_enable = '1' then
            -- FAULT 5: a two-flop synchroniser does not guarantee capture of a short pulse.
            if pulse_sync(1) = '1' and pulse_d = '0' then slow_received <= slow_received + 1; end if;
          elsif req_sync(1) /= ack then slow_received <= slow_received + 1; ack <= req_sync(1); end if;
        else slow_done <= '1'; end if;
      end if;
    end if;
  end process;
  slow_debug <= x"000000" & slow_done & source_done_sync(1) & pulse_d & pulse_sync(1) & req_sync(1) & ack & fault_enable & slow_reset(1) & std_logic_vector(slow_received);
end architecture;

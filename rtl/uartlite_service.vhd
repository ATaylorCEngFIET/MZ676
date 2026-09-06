library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

-- Small VHDL bus sequencer services AMD AXI UARTLite. No processor/firmware.
-- AXI UARTLite offsets: RX=0, TX=4, status=8, control=12 (PG142).
entity uartlite_service is
  port (clk, rst : in std_logic;
    rx_data : out std_logic_vector(7 downto 0); rx_valid, rx_error : out std_logic;
    tx_data : in std_logic_vector(7 downto 0); tx_start : in std_logic; tx_busy : out std_logic;
    awaddr : out std_logic_vector(31 downto 0); awprot : out std_logic_vector(2 downto 0);
    awvalid : out std_logic; awready : in std_logic;
    wdata : out std_logic_vector(31 downto 0); wstrb : out std_logic_vector(3 downto 0);
    wvalid : out std_logic; wready : in std_logic;
    bresp : in std_logic_vector(1 downto 0); bvalid : in std_logic; bready : out std_logic;
    araddr : out std_logic_vector(31 downto 0); arprot : out std_logic_vector(2 downto 0);
    arvalid : out std_logic; arready : in std_logic;
    rdata : in std_logic_vector(31 downto 0); rresp : in std_logic_vector(1 downto 0);
    rvalid : in std_logic; rready : out std_logic);
end entity;
architecture rtl of uartlite_service is
  type state_t is (initialize, write_send, write_reply, status_addr, status_reply, rx_addr, rx_reply);
  signal state : state_t := initialize;
  signal pending, aw_done, w_done, writing_tx : std_logic := '0';
  signal tx_byte : std_logic_vector(7 downto 0) := (others => '0');
  signal write_address, write_data : std_logic_vector(31 downto 0) := (others => '0');
begin
  tx_busy <= pending;
  awaddr <= write_address; wdata <= write_data; awprot <= "000"; wstrb <= "1111";
  awvalid <= not aw_done when state = write_send else '0';
  wvalid <= not w_done when state = write_send else '0';
  bready <= '1' when state = write_reply else '0';
  araddr <= x"00000000" when state = rx_addr else x"00000008";
  arprot <= "000";
  arvalid <= '1' when state = status_addr or state = rx_addr else '0';
  rready <= '1' when state = status_reply or state = rx_reply else '0';
  process(clk) begin
    if rising_edge(clk) then
      rx_valid <= '0'; rx_error <= '0';
      if rst = '1' then
        state <= initialize; pending <= '0'; aw_done <= '0'; w_done <= '0'; writing_tx <= '0';
        rx_data <= (others => '0'); tx_byte <= (others => '0');
        write_address <= (others => '0'); write_data <= (others => '0');
      else
        if tx_start = '1' and pending = '0' then tx_byte <= tx_data; pending <= '1'; end if;
        case state is
          when initialize =>
            write_address <= x"0000000C"; write_data <= x"00000003"; -- reset both FIFOs; interrupts disabled
            aw_done <= '0'; w_done <= '0'; writing_tx <= '0'; state <= write_send;
          when write_send =>
            if awready = '1' then aw_done <= '1'; end if;
            if wready = '1' then w_done <= '1'; end if;
            if (aw_done = '1' or awready = '1') and (w_done = '1' or wready = '1') then state <= write_reply; end if;
          when write_reply =>
            if bvalid = '1' then
              if bresp /= "00" then rx_error <= '1'; end if;
              if writing_tx = '1' then pending <= '0'; end if;
              state <= status_addr;
            end if;
          when status_addr => if arready = '1' then state <= status_reply; end if;
          when status_reply =>
            if rvalid = '1' then
              if rresp /= "00" then rx_error <= '1'; state <= status_addr;
              elsif rdata(7 downto 5) /= "000" then
                -- Flush suspect receive bytes and reset the packet parser on UART errors.
                rx_error <= '1'; write_address <= x"0000000C"; write_data <= x"00000002";
                aw_done <= '0'; w_done <= '0'; writing_tx <= '0'; state <= write_send;
              elsif pending = '1' and rdata(3) = '0' then
                write_address <= x"00000004"; write_data <= x"000000" & tx_byte;
                aw_done <= '0'; w_done <= '0'; writing_tx <= '1'; state <= write_send;
              elsif rdata(0) = '1' then state <= rx_addr;
              else state <= status_addr; end if;
            end if;
          when rx_addr => if arready = '1' then state <= rx_reply; end if;
          when rx_reply =>
            if rvalid = '1' then
              if rresp = "00" then rx_data <= rdata(7 downto 0); rx_valid <= '1';
              else rx_error <= '1'; end if;
              state <= status_addr;
            end if;
        end case;
      end if;
    end if;
  end process;
end architecture;

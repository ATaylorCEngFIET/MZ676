library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package lab_pkg is
  subtype word_t is std_logic_vector(31 downto 0);
  type words_t is array (natural range <>) of word_t;
  constant DEVICE_ID : word_t := x"53443701";
  constant F_HEALTHY : natural := 0;
  constant F_BACKPRESSURE : natural := 1;
  constant F_TLAST : natural := 2;
  constant F_AXI : natural := 3;
  constant F_RARE : natural := 4;
  constant F_CDC : natural := 5;
  constant F_FIFO : natural := 6;
end package;

"""Generate a rare-fault ILA trigger after obtaining probe names from Hardware Manager."""
import argparse
from pathlib import Path


def mask(bit):
    bits = ['x'] * 32
    bits[31-bit] = '1'
    return "32'b" + ''.join(bits)


def generate(flags, packet, target):
    if not 0 <= target <= 0xFFFFFFFF:
        raise ValueError('Target must fit in 32 bits')
    if any(c in flags + packet for c in '\n\r;'):
        raise ValueError('Use a single hardware probe name for each argument')
    return f'''# Rare packet -> earlier stall -> downstream data error.
# Arm BEFORE restarting the experiment. Use all-cycle capture.
state wait_packet:
  if ({packet} == 32'h{target:08x}) then
    goto wait_stall;
  else
    goto wait_packet;
  endif
state wait_stall:
  if ({flags} == {mask(3)}) then
    goto wait_error;
  else
    goto wait_stall;
  endif
state wait_error:
  if ({flags} == {mask(12)}) then
    trigger;
  else
    goto wait_error;
  endif
'''

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flags', required=True, help='Full name of native fast ILA probe 0')
    parser.add_argument('--packet', required=True, help='Full name of native fast ILA probe 2')
    parser.add_argument('--target', type=int, default=10000)
    parser.add_argument('--output', type=Path, default=Path('rare_packet.tsm'))
    args = parser.parse_args()
    args.output.write_text(generate(args.flags, args.packet, args.target), encoding='utf-8')
    print(args.output)

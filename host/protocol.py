"""Binary UART control protocol shared by the GUI and command-line users."""
from __future__ import annotations
from dataclasses import dataclass
from functools import reduce
from operator import xor
import struct
import time

DEVICE_ID = 0x53443701
MODES = (
    '0 — Healthy baseline', '1 — AXI-Stream backpressure', '2 — Packet TLAST counter',
    '3 — AXI-Lite split write', '4 — Rare packet corruption', '5 — CDC lost pulse',
    '6 — FIFO simultaneous operations',
)
ERRORS = ('Data sequence mismatch', 'Incorrect TLAST', 'Payload changed while stalled',
          'AXI response timeout', 'CDC event count mismatch', 'FIFO occupancy mismatch')
NOTES = (
    'All three laboratories run with their healthy logic. Expect no error flags.',
    'The source advances its data counter while TREADY is low. Trigger on flags bit 14, then inspect source TDATA.',
    'The packet counter advances on clock cycles. Trigger on flags bit 13 and count accepted transfers.',
    'The target assumes AW and W are accepted together. Use a nonzero AXI skew; trigger on flags bit 15.',
    'One last word is corrupted at the selected zero-based source packet after an earlier stall. Trigger on flags bit 12.',
    '32 one-cycle events cross to a /4 clock. The faulty synchroniser loses events. Compare both ILAs and the final counts.',
    'VHDL occupancy accounting decrements during simultaneous push/pop near full; AMD FIFO data stays intact. Trigger on flags bit 17 and inspect FIFO probe 4.',
)

@dataclass(frozen=True)
class Settings:
    mode: int = 0
    packet_words: int = 16
    stall_cycles: int = 48
    stall_period: int = 64
    rare_packet: int = 10000
    axi_skew: int = 16

    def validate(self):
        limits = {'mode': (0, 6), 'packet_words': (2, 256), 'stall_cycles': (0, 255),
                  'stall_period': (2, 65535), 'rare_packet': (0, 0xFFFFFFFF), 'axi_skew': (0, 255)}
        for name, (lo, hi) in limits.items():
            value = getattr(self, name)
            if not isinstance(value, int) or not lo <= value <= hi:
                raise ValueError(f'{name} must be between {lo} and {hi}.')
        if self.stall_cycles >= self.stall_period:
            raise ValueError('Stall cycles must be smaller than the period so traffic can progress.')
        if self.mode == 3 and self.axi_skew == 0:
            raise ValueError('Use a nonzero AXI skew to demonstrate the split-write fault.')
        if self.mode in (1, 2, 4, 6) and self.stall_cycles == 0:
            raise ValueError('This demonstration needs backpressure. Use the preset or enable stalls.')
        if self.mode == 4 and self.stall_cycles < 17:
            raise ValueError('Rare corruption needs a stall that fills the 16-word FIFO; use at least 17 cycles.')
        return self


def frame(sequence: int, operation: int, address: int, data: int = 0) -> bytes:
    payload = struct.pack('<BBBI', sequence, operation, address, data)
    return b'\xa5' + payload + bytes([reduce(xor, payload, 0), 0x5A])


def decode(packet: bytes):
    if len(packet) != 10 or packet[0] != 0xA5 or packet[9] != 0x5A:
        raise ValueError('Invalid UART frame boundary.')
    if reduce(xor, packet[1:8], 0) != packet[8]:
        raise ValueError('UART checksum mismatch.')
    return struct.unpack('<BBBI', packet[1:8])


class Device:
    def __init__(self, port: str, timeout: float = 1.0, serial_factory=None):
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        self.timeout = timeout
        self.serial = serial_factory(port, 115200, timeout=0.05, write_timeout=1,
                                     rtscts=False, dsrdtr=False)
        self.sequence = 0
        try:
            self.serial.reset_input_buffer()
            if self.read(0) != DEVICE_ID:
                raise RuntimeError('The selected port is not running the Spartan-7 debug laboratory design.')
        except Exception:
            self.close()
            raise

    def close(self):
        self.serial.close()

    def transact(self, operation, address, data=0):
        self.sequence = (self.sequence + 1) & 255
        packet = frame(self.sequence, operation, address, data)
        if self.serial.write(packet) != len(packet):
            raise IOError('Incomplete UART write; reconnect before restarting the experiment.')
        deadline = time.monotonic() + self.timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            buffer.extend(self.serial.read(max(1, 10 - len(buffer))))
            while buffer:
                if buffer[0] != 0xA5:
                    del buffer[0]
                    continue
                if len(buffer) < 10:
                    break
                try:
                    seq, status, addr, result = decode(bytes(buffer[:10]))
                except ValueError:
                    del buffer[0]
                    continue
                del buffer[:10]
                if seq != self.sequence or addr != address:
                    continue
                if status:
                    reason = {1: 'bad checksum', 2: 'unknown command', 3: 'invalid register'}.get(status, str(status))
                    raise RuntimeError(f'FPGA rejected the command: {reason}.')
                return result
        # Do not replay START automatically after an uncertain response.
        raise TimeoutError('No valid FPGA reply. Check the COM port, bitstream and clock; reconnect before retrying.')

    def read(self, address):
        return self.transact(1, address)

    def write(self, address, data):
        return self.transact(2, address, data)

    def start(self, settings: Settings):
        settings.validate()
        self.write(1, 2)
        for address, value in enumerate((settings.mode, settings.packet_words, settings.stall_cycles,
                                         settings.stall_period, settings.rare_packet, settings.axi_skew), 2):
            if self.write(address, value) != value:
                raise RuntimeError(f'Register {address} did not accept {value}; experiment was not started.')
        self.write(1, 1)
        return self.snapshot()

    def stop(self):
        self.write(1, 2)
        return self.snapshot()

    def clear(self):
        self.write(1, 4)
        return self.snapshot()

    def snapshot(self):
        self.write(1, 8)
        return dict(zip(SNAPSHOT_KEYS, (self.read(a) for a in range(16, 32))))


SNAPSHOT_KEYS = ('status', 'errors', 'words', 'packets', 'first_expected', 'first_actual',
                 'first_packet', 'first_cycle', 'axi_completed', 'cdc_sent', 'cdc_received',
                 'cycles', 'fifo_debug', 'source_packet', 'active_mode', 'version')


class PreviewDevice:
    """Illustrative GUI preview only; deliberately not an RTL simulator."""
    def __init__(self):
        self.settings = Settings()
        self.is_running = False
        self.started = time.monotonic()
        self.state = dict.fromkeys(SNAPSHOT_KEYS, 0)

    def close(self):
        pass

    def start(self, settings):
        self.settings = settings.validate()
        self.clear()
        self.is_running = True
        self.started = time.monotonic()
        return self.snapshot()

    def stop(self):
        self.snapshot()
        self.is_running = False
        return self.snapshot()

    def clear(self):
        self.is_running = False
        self.state = dict.fromkeys(SNAPSHOT_KEYS, 0)
        return self.snapshot()

    def snapshot(self):
        s = self.state
        m = self.settings.mode
        if self.is_running:
            elapsed = time.monotonic() - self.started
            s['cycles'] = int(elapsed * 50000000) & 0xFFFFFFFF
            s['words'] = int(elapsed * 1000000) & 0xFFFFFFFF
            s['packets'] = s['words'] // self.settings.packet_words
            s['source_packet'] = s['packets']
            s['axi_completed'] = 0 if m == 3 else int(elapsed * 10000)
            s['cdc_sent'] = 32
            s['cdc_received'] = 8 if m == 5 else 32
            if elapsed > 0.4 and (m != 4 or s['packets'] > self.settings.rare_packet):
                s['errors'] = (0, 5, 6, 8, 1, 16, 32)[m]
        s['version'] = 0x00020000
        s['active_mode'] = m
        s['status'] = int(self.is_running) | (2 if s['errors'] else 0) | (8 if s['cdc_sent'] else 0) | (m << 4)
        return s.copy()


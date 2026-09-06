import unittest
from unittest.mock import patch
from protocol import Device, Settings, frame, decode, DEVICE_ID

class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.buffer = bytearray()
        self.regs = {0: DEVICE_ID, 2: 0, 3: 16, 4: 48, 5: 64, 6: 10000, 7: 16}
        self.closed = False
        self.bad_status = 0
        self.no_response = False
        self.writes = []
    def reset_input_buffer(self): self.buffer.clear()
    def close(self): self.closed = True
    def write(self, packet):
        self.writes.append(packet)
        sequence, operation, address, value = decode(packet)
        if operation == 2: self.regs[address] = value
        if not self.no_response:
            # Noise and a malformed frame must not hide a subsequent valid reply.
            self.buffer.extend(b'noise\xa5' + b'\x00'*9)
            self.buffer.extend(frame(sequence, self.bad_status, address, self.regs.get(address, 0)))
        return len(packet)
    def read(self, size):
        data = bytes(self.buffer[:min(size,3)])
        del self.buffer[:len(data)]
        return data

class ProtocolTests(unittest.TestCase):
    def test_golden_packet(self):
        self.assertEqual(frame(1,2,2,6), bytes.fromhex('a5 01 02 02 06 00 00 00 07 5a'))
        self.assertEqual(decode(frame(255,1,0,DEVICE_ID)), (255,1,0,DEVICE_ID))
    def test_corruption_rejected(self):
        damaged = bytearray(frame(1,1,0)); damaged[4] ^= 1
        with self.assertRaises(ValueError): decode(bytes(damaged))
    def test_partial_reads_noise_and_readback(self):
        device = Device('fake', serial_factory=FakeSerial)
        self.assertEqual(device.write(2,6), 6)
        self.assertEqual(device.read(2), 6)
        device.close(); self.assertTrue(device.serial.closed)
    def test_identity_failure_closes_port(self):
        serial = FakeSerial(); serial.regs[0] = 0
        with self.assertRaises(RuntimeError): Device('fake', serial_factory=lambda *a,**k: serial)
        self.assertTrue(serial.closed)
    def test_fpga_error_and_no_automatic_retry(self):
        device = Device('fake', timeout=0.01, serial_factory=FakeSerial)
        device.serial.bad_status = 3
        with self.assertRaises(RuntimeError): device.read(8)
        device.serial.no_response = True
        count = len(device.serial.writes)
        with self.assertRaises(TimeoutError): device.write(1,1)
        self.assertEqual(len(device.serial.writes), count+1)
    def test_configuration_validation(self):
        for settings in (Settings(mode=7), Settings(packet_words=1), Settings(stall_cycles=64),
                         Settings(mode=3,axi_skew=0), Settings(mode=4,stall_cycles=2)):
            with self.assertRaises(ValueError): settings.validate()
        for mode in range(7): Settings(mode=mode).validate()
    def test_start_writes_all_settings_before_start(self):
        device = Device('fake', serial_factory=FakeSerial)
        device.start(Settings(mode=5))
        operations = [decode(p)[:3] + (decode(p)[3],) for p in device.serial.writes]
        writes = [(a,d) for _,op,a,d in operations if op == 2]
        self.assertEqual(writes[:8], [(1,2),(2,5),(3,16),(4,48),(5,64),(6,10000),(7,16),(1,1)])
    def test_sequence_wrap(self):
        device = Device('fake', serial_factory=FakeSerial)
        device.sequence = 255
        self.assertEqual(device.read(0), DEVICE_ID)
        self.assertEqual(device.sequence, 0)

if __name__ == '__main__': unittest.main()

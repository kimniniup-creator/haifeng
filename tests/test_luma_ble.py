import unittest

from bridge.luma_ble import FileReassembler, _decode_control, _file_frame, checksum, choose_device, command_frame


class Device:
    def __init__(self, name, address):
        self.name = name
        self.address = address


class LumaProtocolTests(unittest.TestCase):
    def test_command_frame_matches_upstream_photo_capture(self):
        self.assertEqual(command_frame(0x22, b"1").hex(), "ab550003223153")
        self.assertEqual(command_frame(0x64).hex(), "ab550003640064")

    def test_control_deframer_handles_fragmentation_and_corruption(self):
        frame = bytes.fromhex("ac5500051734390185")
        buffer = bytearray(frame[:5])
        self.assertEqual(_decode_control(buffer), [])
        buffer.extend(frame[5:])
        self.assertEqual(_decode_control(buffer), [(0x17, b"49\x01")])
        corrupt = bytearray(frame)
        corrupt[-1] ^= 1
        buffer.extend(corrupt + frame)
        self.assertEqual(_decode_control(buffer), [(0x17, b"49\x01")])

    def test_reassembler_completes_reordered_and_duplicate_chunks(self):
        data = b"\xff\xd8reordered-jpeg\xff\xd9"
        info = _file_frame(0x97, len(data).to_bytes(4, "big") + b"\x02")
        first = _file_frame(0x98, (0).to_bytes(4, "big") + data[:5])
        second = _file_frame(0x98, (5).to_bytes(4, "big") + data[5:])
        end = _file_frame(0x99, b"\x00")
        parser = FileReassembler()
        for frame in (info, second, first, first, end):
            parser.push(frame)
        self.assertEqual(parser.completed, data)
        self.assertIsNone(parser.error)

    def test_reassembler_drops_corrupt_and_rejects_holey_file(self):
        data = b"0123456789"
        info = _file_frame(0x97, len(data).to_bytes(4, "big") + b"\x02")
        corrupt = bytearray(_file_frame(0x98, (0).to_bytes(4, "big") + data[:5]))
        corrupt[-3] ^= 1
        tail = _file_frame(0x98, (5).to_bytes(4, "big") + data[5:])
        parser = FileReassembler()
        for frame in (info, corrupt, tail, _file_frame(0x99, b"\x00")):
            parser.push(frame)
        self.assertIsNone(parser.completed)
        self.assertEqual(parser.error, "incomplete file transfer")

    def test_reassembler_rejects_out_of_range_data(self):
        parser = FileReassembler()
        parser.push(_file_frame(0x97, (2).to_bytes(4, "big") + b"\x02"))
        parser.push(_file_frame(0x98, (1).to_bytes(4, "big") + b"xx"))
        self.assertEqual(parser.error, "file chunk outside declared range")

    def test_auto_selection_refuses_ambiguous_devices(self):
        with self.assertRaisesRegex(Exception, "ambiguous"):
            choose_device([Device("E06-1", "A"), Device("E09-2", "B")], None)
        self.assertEqual(choose_device([Device("E06-1", "A")], None).address, "A")


if __name__ == "__main__":
    unittest.main()

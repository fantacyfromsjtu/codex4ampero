import unittest

from ampero_control.protocol import (
    decode_model,
    decode_parameter,
    encode_set_model,
    encode_set_parameter,
    pack_float,
    pack_int,
)


class ProtocolTests(unittest.TestCase):
    def test_integer_and_float_encoding_are_little_endian(self):
        self.assertEqual(pack_int(0x1234, 2), b"\x34\x12")
        self.assertEqual(pack_float(35.0), b"\x00\x00\x0c\x42")

    def test_parameter_round_trip(self):
        payload = encode_set_parameter(3, 1, 35.0)
        self.assertEqual(payload, b"\x03\x00\x01\x00\x00\x00\x0c\x42")
        slot, parameter, value = decode_parameter(payload)
        self.assertEqual((slot, parameter), (3, 1))
        self.assertAlmostEqual(value, 35.0)

    def test_model_round_trip(self):
        payload = encode_set_model(3, 4, 117440513, True)
        self.assertEqual(payload, b"\x03\x04\x01\x00\x00\x07\x01")
        self.assertEqual(decode_model(payload), (3, 4, 117440513, True))


if __name__ == "__main__":
    unittest.main()

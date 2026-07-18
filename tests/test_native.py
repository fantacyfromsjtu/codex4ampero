import unittest

from ampero_control.errors import NativeLibraryError
from ampero_control.native import NativeTransport


class NativeTransportTests(unittest.TestCase):
    def test_connected_operations_require_dart_bridge(self):
        transport = NativeTransport.__new__(NativeTransport)

        with self.assertRaises(NativeLibraryError):
            transport.connect()
        with self.assertRaises(NativeLibraryError):
            transport.request(0x01040002)


if __name__ == "__main__":
    unittest.main()

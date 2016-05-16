import unittest

import emolog


class TestEmolog(unittest.TestCase):

    def test_decode_sane(self):
        parser = emolog.ClientParser()
        encoded = emolog.encode_version()
        msg = parser.incoming(encoded)
        self.assertIsInstance(msg, emolog.Version)

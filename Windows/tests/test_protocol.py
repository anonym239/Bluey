import unittest

from bluey.protocol import Decoder, encode


class ProtocolTest(unittest.TestCase):
    def test_round_trip_and_partial_lines(self):
        d = Decoder()
        data = encode({"hello": "PC"}) + encode({"face": {"gazeX": 0.5, "mood": "happy"}})
        self.assertEqual(d.feed(data[:7]), [])
        packets = d.feed(data[7:])
        self.assertEqual(packets, [{"hello": "PC"}, {"face": {"gazeX": 0.5, "mood": "happy"}}])

    def test_umlauts_split_across_reads(self):
        d = Decoder()
        data = encode({"text": "Grüße 🫐"})
        out = []
        for i in range(len(data)):
            out += d.feed(data[i:i + 1])
        self.assertEqual(out, [{"text": "Grüße 🫐"}])

    def test_garbage_is_skipped(self):
        self.assertEqual(Decoder().feed(b"nope\n[1,2]\n{\"a\":1}\n"), [{"a": 1}])

    def test_too_large(self):
        with self.assertRaises(ValueError):
            Decoder(maximum=10).feed(b"x" * 50)

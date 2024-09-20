import unittest
from pieces.bencoding import Decoder, Encoder
from collections import OrderedDict

class TestBencoding(unittest.TestCase):

    def test_integer(self):
        self.assertEqual(Decoder(b'i123e').decode(), 123)

    def test_string(self):
        self.assertEqual(Decoder(b'12:Middle Earth').decode(), b'Middle Earth')

    def test_list(self):
        self.assertEqual(Decoder(b'l4:spam4:eggsi123ee').decode(), [b'spam', b'eggs', 123])

    def test_dict(self):
        self.assertEqual(
            Decoder(b'd3:cow3:moo4:spam4:eggse').decode(),
            OrderedDict([(b'cow', b'moo'), (b'spam', b'eggs')])
        )

    def test_encoder(self):
        self.assertEqual(Encoder(123).encode(), b'i123e')
        self.assertEqual(Encoder('Middle Earth').encode(), b'12:Middle Earth')
        self.assertEqual(Encoder(['spam', 'eggs', 123]).encode(), bytearray(b'l4:spam4:eggsi123ee'))
        d = OrderedDict()
        d['cow'] = 'moo'
        d['spam'] = 'eggs'
        self.assertEqual(Encoder(d).encode(), bytearray(b'd3:cow3:moo4:spam4:eggse'))

if __name__ == '__main__':
    unittest.main()

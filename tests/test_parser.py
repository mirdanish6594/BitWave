import unittest
from pieces.bencoding import Decoder

class TestParser(unittest.TestCase):

    def test_torrent_parsing(self):
        with open('tests/data/sample.torrent', 'rb') as f:
            meta_info = f.read()
            torrent = Decoder(meta_info).decode()
            self.assertIn(b'announce', torrent)

if __name__ == '__main__':
    unittest.main()

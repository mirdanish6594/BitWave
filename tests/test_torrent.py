import unittest
from pieces.torrent import Torrent

class TestTorrent(unittest.TestCase):

    def test_torrent_properties(self):
        with open('docs/test.torrent', 'rb') as f:
            meta_info = f.read()
            torrent = Torrent(meta_info)
            self.assertEqual(torrent.name, b'example.torrent')
            self.assertEqual(torrent.length, 123456)
            self.assertEqual(torrent.piece_length, 16384)

if __name__ == '__main__':
    unittest.main()

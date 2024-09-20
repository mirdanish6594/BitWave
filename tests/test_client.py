import unittest
from pieces.client import Client

class TestClient(unittest.TestCase):

    def test_client_initialization(self):
        client = Client('docs/test.torrent')
        self.assertIsNotNone(client.torrent)
        self.assertTrue(client.is_initialized())

if __name__ == '__main__':
    unittest.main()

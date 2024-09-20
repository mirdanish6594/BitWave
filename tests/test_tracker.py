import unittest
from pieces.tracker import Tracker

class TestTracker(unittest.TestCase):

    def test_tracker_connection(self):
        tracker = Tracker('http://example.com/announce')
        self.assertTrue(tracker.connect())

if __name__ == '__main__':
    unittest.main()

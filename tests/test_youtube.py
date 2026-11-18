import unittest
from clipdistrict.youtube import video_id_from_url


class TestYouTubeURL(unittest.TestCase):
    def test_watch(self):
        self.assertEqual(video_id_from_url("https://www.youtube.com/watch?v=ABCDEFGHI01&t=42"), "ABCDEFGHI01")

    def test_short(self):
        self.assertEqual(video_id_from_url("https://youtube.com/shorts/ABCDEFGHI01"), "ABCDEFGHI01")

    def test_youtu_be(self):
        self.assertEqual(video_id_from_url("https://youtu.be/ABCDEFGHI01"), "ABCDEFGHI01")

    def test_reject_host_spoof(self):
        for url in [
            "https://youtube.com.evil.test/watch?v=ABCDEFGHI01",
            "http://youtube.com/watch?v=ABCDEFGHI01",
            "https://evil.test/?v=ABCDEFGHI01",
            "https://youtube.com/watch?v=ABCDEFGHI01JUNK",
            "https://youtube.com@evil.test/watch?v=ABCDEFGHI01",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                video_id_from_url(url)

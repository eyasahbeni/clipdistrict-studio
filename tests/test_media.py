import unittest
from clipdistrict.media import MediaError, parse_time, export_short


class TestMedia(unittest.TestCase):
    def test_parse_time(self):
        self.assertEqual(parse_time("01:02:03.5"), 3723.5)
        self.assertEqual(parse_time("00:45"), 45)
        self.assertEqual(parse_time("30"), 30)

    def test_invalid_time(self):
        for value in ["", "bad", "01:70", "-1", "nan", "inf", "01:01:80"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_time(value)

    def test_refuse_bad_output_name_before_reading_source(self):
        with self.assertRaises(MediaError):
            export_short("nonexistent.mp4", 0, 20, "../../escape.mp4")

    def test_refuse_too_long_duration(self):
        with self.assertRaises(MediaError):
            export_short("nonexistent.mp4", 0, 181, "ok.mp4")

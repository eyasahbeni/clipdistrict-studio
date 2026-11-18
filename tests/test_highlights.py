import tempfile
import unittest
from pathlib import Path
from clipdistrict.highlights import parse_srt, suggest


class TestHighlights(unittest.TestCase):
    def test_parser_and_suggestions(self):
        text = (
            "1\n00:00:10,000 --> 00:00:12,500\nNo way GTA 6!\n\n"
            "2\n00:01:01,000 --> 00:01:04,000\nVice City is insane!"
        )
        self.assertEqual(len(parse_srt(text)), 2)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "approved.srt"
            path.write_text(text, encoding="utf-8")
            results = suggest(path, length=30, limit=3)
            self.assertGreater(len(results), 0)
            self.assertTrue(all(r["duration"] == 30 for r in results))

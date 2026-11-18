import unittest
from clipdistrict.captions import THEMES, ass_color, build_ass


WORDS = [{"start": 10 + i * 0.4, "end": 10.35 + i * 0.4, "word": w}
         for i, w in enumerate("no way this GTA 6 chase is insane".split())]


class TestCaptions(unittest.TestCase):
    def test_color(self):
        self.assertEqual(ass_color("#FF2E88"), "&H00882EFF")

    def test_every_theme_builds(self):
        for theme in THEMES:
            with self.subTest(theme=theme):
                ass = build_ass(WORDS, 10, 14, {"theme": theme, "hook": "NO WAY", "watermark": "@ClipDistrict"})
                self.assertIn("[Events]", ass)
                self.assertIn("Hook", ass)
                self.assertIn("@ClipDistrict", ass)

    def test_word_highlight_and_offset(self):
        ass = build_ass(WORDS, 10, 14, {"theme": "hype-yellow", "show_hook": False})
        lines = [l for l in ass.splitlines() if l.startswith("Dialogue: 1")]
        self.assertEqual(len(lines), len(WORDS))
        self.assertTrue(lines[0].split(",")[1].startswith("0:00:00.00"))
        self.assertIn("NO", lines[0])

    def test_escapes_braces(self):
        ass = build_ass([{"start": 0, "end": 1, "word": "{\\pos(0,0)}hi"}], 0, 2, {"show_hook": False})
        self.assertNotIn("{\\pos(0,0)}hi", ass)

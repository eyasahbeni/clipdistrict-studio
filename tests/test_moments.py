import unittest
import numpy as np
from clipdistrict.moments import find_moments, hook_line, title_ideas


def transcript():
    text = ("this is just normal talking about the weather today " * 6
            + "NO WAY bro GTA 6 police chase oh my god let's go this is insane hahaha ")
    words, t = [], 0.0
    for w in text.split():
        words.append({"start": t, "end": t + 0.3, "word": w})
        t += 0.45
    return {"segments": [{"start": 0, "end": t, "text": text, "words": words}]}, t


class TestMoments(unittest.TestCase):
    def test_hype_wins(self):
        tr, dur = transcript()
        loud = np.full(int(dur / 0.5) + 1, -30.0, dtype=np.float32)
        loud[int(28 / 0.5):int(34 / 0.5)] = -8
        found = find_moments(tr, loud, dur, length=12, count=2)
        self.assertTrue(found)
        best = max(found, key=lambda m: m["score"])
        self.assertGreater(best["end"], 27)
        self.assertTrue(best["hook"])
        self.assertTrue(best["titles"])

    def test_no_overlap(self):
        tr, dur = transcript()
        found = find_moments(tr, None, dur, length=10, count=4)
        for a, b in zip(found, found[1:]):
            self.assertLessEqual(a["end"], b["start"] + 0.6)

    def test_audio_only(self):
        loud = np.random.default_rng(1).normal(-30, 3, 400).astype(np.float32)
        found = find_moments({"segments": []}, loud, 200, length=20, count=3)
        self.assertEqual(len(found), 3)

    def test_hook_and_titles(self):
        self.assertEqual(hook_line("bro. no way this is the GTA"), "NO WAY")
        self.assertLessEqual(len(title_ideas("police chase in vice city")), 4)


class TestKeywords(unittest.TestCase):
    def test_parse(self):
        from clipdistrict.moments import parse_keywords
        self.assertEqual(parse_keywords("Police Chase:6, speed, bad:abc"),
                         {"police chase": 6.0, "speed": 4.0, "bad": 4.0})

    def test_custom_keyword_wins(self):
        from clipdistrict.moments import find_moments
        words, t = [], 0.0
        for w in ("filler words here " * 20 + "the banana phone rings " + "filler words here " * 20).split():
            words.append({"start": t, "end": t + 0.3, "word": w}); t += 0.45
        tr = {"segments": [{"start": 0, "end": t, "text": "", "words": words}]}
        best = find_moments(tr, None, t, length=10, count=1, keywords={"banana phone": 10})[0]
        self.assertLessEqual(best["start"], 27.5)
        self.assertGreaterEqual(best["end"], 27.5)
        self.assertTrue(any("your keywords" in r for r in best["reasons"]))

    def test_search(self):
        from clipdistrict.moments import search_transcript
        words = [{"start": i, "end": i + .5, "word": x} for i, x in enumerate("Yo, POLICE chase! then crash".split())]
        hits = search_transcript({"segments": [{"words": words}]}, "police chase, crash", 60)
        self.assertEqual([h["term"] for h in hits], ["police chase", "crash"])

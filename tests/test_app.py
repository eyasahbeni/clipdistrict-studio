import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="cd-test-")
os.environ["CLIPDISTRICT_HOME"] = TMP

from clipdistrict import render  # noqa: E402
from clipdistrict.config import ffmpeg_bin  # noqa: E402
from clipdistrict.server import app  # noqa: E402


def have_ffmpeg():
    try:
        ffmpeg_bin()
        return True
    except RuntimeError:
        return False


class TestServer(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.c = app.test_client()

    def test_pages(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/assets/app.js").status_code, 200)
        themes = self.c.get("/api/themes").get_json()
        self.assertIn("vice-city", [t["id"] for t in themes["themes"]])

    def test_import_rejects_non_links(self):
        r = self.c.post("/api/projects", json={"url": "not a link"})
        self.assertEqual(r.status_code, 400)

    def test_rejects_local_urls(self):
        r = self.c.post("/api/projects", json={"url": "http://127.0.0.1/x", "permission": True})
        self.assertEqual(r.status_code, 400)

    def test_bad_project_id(self):
        self.assertEqual(self.c.get("/api/projects/../../etc").status_code, 404)


@unittest.skipUnless(have_ffmpeg(), "ffmpeg not available")
class TestRender(unittest.TestCase):
    def test_all_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.mp4"
            subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=4",
                            "-f", "lavfi", "-i", "sine=d=4", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", str(src)], check=True)
            words = [{"start": 0.2, "end": 0.6, "word": "GTA"}, {"start": 0.7, "end": 1.2, "word": "six"}]
            for layout in render.LAYOUTS:
                with self.subTest(layout=layout):
                    out = render.render(src, Path(tmp) / f"{layout}.mp4", 0.5, 3.0, words,
                                        {"layout": layout, "hook": "test", "watermark": "@x", "preset": "ultrafast"})
                    self.assertGreater(out.stat().st_size, 1000)


class TestWorkflow(unittest.TestCase):
    def test_cleanup_and_storage(self):
        from clipdistrict import projects, workflow
        meta = projects.create("x")
        src = projects.source_path(meta["id"])
        src.write_bytes(b"0" * 1000)
        (projects.project_dir(meta["id"]) / "source.mp4.part").write_bytes(b"1")
        workflow.sweep_temp()
        self.assertFalse((projects.project_dir(meta["id"]) / "source.mp4.part").exists())
        self.assertGreaterEqual(workflow.storage()["sources"], 1000)
        self.assertEqual(workflow.free_source(meta["id"]), 1000)
        self.assertTrue(projects.load(meta["id"])["source_removed"])

    def test_automation_endpoints(self):
        c = app.test_client()
        self.assertEqual(c.get("/api/automation").status_code, 200)
        self.assertEqual(c.post("/api/watch/channels", json={"channel": "@x"}).status_code, 400)  # no API key
        r = c.post("/api/settings", json={"auto_clips": 2, "keywords": "banana:9"}).get_json()
        self.assertEqual(r["auto_clips"], 2)


class TestCancel(unittest.TestCase):
    def test_cancel_queued_and_running(self):
        import threading
        import time
        from clipdistrict import jobs
        gate = threading.Event()
        seen = []

        def slow(progress):
            gate.wait(5)
            progress(0.5, "half")        # raises once cancelled
            seen.append("finished")

        first = jobs.submit("t", "slow", slow, project_id="p1")
        second = jobs.submit("t", "waiting", lambda p: seen.append("second ran"), project_id="p1")
        time.sleep(0.2)
        self.assertEqual(jobs.cancel_project("p1"), 2)
        gate.set()
        time.sleep(0.5)
        self.assertEqual(seen, [])
        self.assertEqual(jobs.get(first)["state"], "cancelled")
        self.assertEqual(jobs.get(second)["state"], "cancelled")


@unittest.skipUnless(have_ffmpeg(), "ffmpeg not available")
class TestInbox(unittest.TestCase):
    def test_inbox_import_with_section(self):
        import time
        from clipdistrict import projects
        from clipdistrict.config import INBOX_DIR
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        src = INBOX_DIR / "stream part.mkv"
        subprocess.run([ffmpeg_bin(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=6",
                        "-f", "lavfi", "-i", "sine=d=6", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", str(src)], check=True)
        c = app.test_client()
        self.assertEqual([f["name"] for f in c.get("/api/inbox").get_json()["files"]], ["stream part.mkv"])
        self.assertEqual(c.post("/api/inbox/import", json={"name": "../x.mp4"}).status_code, 400)
        meta = c.post("/api/inbox/import", json={"name": "stream part.mkv", "start": "1", "end": "4"}).get_json()
        for _ in range(60):
            status = projects.load(meta["id"])["status"]
            if status in ("ready", "error"):
                break
            time.sleep(0.5)
        p = projects.load(meta["id"])
        self.assertEqual(p["status"], "ready", p["error"])
        self.assertAlmostEqual(p["duration"], 3, delta=0.5)
        self.assertTrue(src.exists())  # original stays in the inbox


class TestPlanAndAI(unittest.TestCase):
    def test_plan_gives_several_clips(self):
        from clipdistrict.workflow import plan
        self.assertEqual(plan(33)["count"], 2)
        self.assertLess(plan(33)["target"], 20)
        self.assertGreaterEqual(plan(1200)["count"], 5)
        self.assertEqual(plan(600, clip_length=30, clips=4)["count"], 4)

    def test_ai_pick_parses_and_removes_overlaps(self):
        from unittest import mock
        from clipdistrict import ai
        fake = ('```json\n[{"start": 10, "end": 30, "score": 90, "title": "No way 😳", "hook": "NO WAY", "reason": "big"},'
                '{"start": 20, "end": 40, "score": 50, "title": "x", "hook": "y", "reason": "overlap"},'
                '{"start": 60, "end": 80, "score": 70, "title": "Chase", "hook": "RUN", "reason": "chase"}]\n```')
        tr = {"segments": [{"start": 0, "end": 100, "text": "hello", "words": []}]}
        with mock.patch.object(ai, "api_key", return_value="k"), mock.patch.object(ai, "_ask", return_value=fake):
            got = ai.pick_moments(tr, 100, count=3, min_len=10, max_len=30)
        self.assertEqual([(m["start"], m["end"]) for m in got], [(10, 30), (60, 80)])
        self.assertEqual(got[0]["hook"], "NO WAY")


class TestChunkedUpload(unittest.TestCase):
    def test_chunks_resume_and_finish(self):
        c = app.test_client()
        uid = c.post("/api/uploads").get_json()["id"]
        self.assertEqual(c.put(f"/api/uploads/{uid}?offset=0", data=b"a" * 10).get_json()["offset"], 10)
        # wrong offset -> server tells the real one, nothing appended
        r = c.put(f"/api/uploads/{uid}?offset=4", data=b"b" * 5).get_json()
        self.assertEqual(r, {"offset": 10, "resync": True})
        self.assertEqual(c.put(f"/api/uploads/{uid}?offset=10", data=b"c" * 5).get_json()["offset"], 15)
        self.assertEqual(c.post(f"/api/uploads/{uid}/finish", json={"name": "x.exe"}).status_code, 400)
        self.assertEqual(c.put("/api/uploads/../../etc?offset=0", data=b"x").status_code, 404)


class TestFacecam(unittest.TestCase):
    def test_crop_box_shape_and_bounds(self):
        from clipdistrict.facecam import crop_box
        b = crop_box(0.95, 0.05, 0.1, 1920, 1080)
        self.assertGreaterEqual(b["x"], 0); self.assertLessEqual(b["x"] + b["w"], 1.0001)
        self.assertGreaterEqual(b["y"], 0); self.assertLessEqual(b["y"] + b["h"], 1.0001)
        self.assertAlmostEqual((b["w"] * 1920) / (b["h"] * 1080), 1080 / 960, places=1)

    def test_split_filter_uses_box_and_position(self):
        from clipdistrict.render import video_filter
        f = video_filter({"layout": "split", "cam_box": {"x": 0.7, "y": 0.1, "w": 0.17, "h": 0.2},
                          "cam_position": "bottom"})
        self.assertIn("crop=iw*0.1700:ih*0.2000:iw*0.7000:ih*0.1000", f)
        self.assertIn("[game][cam]vstack", f)

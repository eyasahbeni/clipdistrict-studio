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

    def test_import_needs_permission(self):
        r = self.c.post("/api/projects", json={"url": "https://youtube.com/watch?v=ABCDEFGHI01"})
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

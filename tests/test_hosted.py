import os
import subprocess
import sys
import tempfile
import unittest

CODE = r"""
import os
from clipdistrict.server import app
c = app.test_client()
assert c.get("/").status_code == 302
assert c.get("/api/status").status_code == 401
assert c.get("/assets/app.css").status_code == 200
assert c.post("/login", data={"password": "nope"}).status_code == 200
r = c.post("/login", data={"password": "pw"})
assert r.status_code == 302, r.status_code
"""


class TestHostedLogin(unittest.TestCase):
    def test_password_gate(self):
        env = dict(os.environ, APP_PASSWORD="pw", PUBLIC_URL="http://localhost:7860",
                   CLIPDISTRICT_HOME=tempfile.mkdtemp())
        result = subprocess.run([sys.executable, "-c", CODE], env=env, capture_output=True, text=True,
                                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(result.returncode, 0, result.stderr[-800:])

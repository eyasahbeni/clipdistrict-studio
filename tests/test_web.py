import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from clipdistrict.web import StudioState, create_server, cut_subtitle, _format_ts

class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = StudioState(Path(cls.tmp.name))
        cls.srv = create_server(0, cls.state)
        cls.port = cls.srv.server_port
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def request(self, path, method='GET', data=None, token=True, mime=None, headers=None):
        headers = dict(headers or {})
        if method == 'POST' and token:
            headers['X-ClipDistrict-Token'] = self.state.token
        if mime:
            headers['Content-Type'] = mime
        req = Request(f'http://127.0.0.1:{self.port}{path}', data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as r:
                return r.status, r.read(), dict(r.headers)
        except HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_status_and_csrf(self):
        status, data, _ = self.request('/api/status')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)['token'])
        bad, _, _ = self.request('/api/settings', method='POST', data=b'{}', token=False, mime='application/json')
        self.assertEqual(bad, 403)
        bad, _, _ = self.request('/api/settings', method='POST', data=b'{}', mime='application/json', headers={'Origin':'https://malicious.example'})
        self.assertEqual(bad, 403)

    def test_assets_and_input_validation(self):
        status, html, h = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn(b'ClipDistrict', html)
        self.assertIn(b"default-src 'self'", h['Content-Security-Policy'].encode())
        status, _, _ = self.request('/style.css')
        self.assertEqual(status, 200)
        status, _, _ = self.request('/api/inspect?url=https://evil.example/')
        self.assertNotEqual(status, 200)
        status, _, _ = self.request('/media/../../.ssh/id_rsa')
        self.assertNotEqual(status, 200)

    def test_upload_subtitles_suggestions_and_render_validation(self):
        # Arbitrary fixture bytes may be stored but only FFmpeg can decode them.
        raw = b'not a real video'
        status, data, _ = self.request('/api/import', method='POST', data=raw, mime='application/octet-stream',
                                       headers={'X-Filename': 'my-test.mp4'})
        self.assertEqual(status, 200)
        vid = json.loads(data)['video_id']
        self.assertRegex(vid, r'^[0-9a-f]{32}$')
        status, _, _ = self.request(f'/media/{vid}',headers={'Range':'bytes=0-3'})
        self.assertEqual(status, 206)
        content = b'1\n00:00:00,500 --> 00:00:01,300\nGTA 6 no way!\n'
        status, data, _ = self.request('/api/subtitles/'+vid, method='POST', data=content,
                                       mime='application/octet-stream', headers={'X-Filename':'video.srt'})
        self.assertEqual(status, 200)
        status, data, _ = self.request('/api/suggest', method='POST', data=json.dumps({'video_id':vid,'length':30}).encode(), mime='application/json')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)['items'])
        status, _, _ = self.request('/api/render',method='POST',data=json.dumps({'video_id':vid,'duration':400}).encode(),mime='application/json')
        self.assertEqual(status, 400)
        status, _, _ = self.request('/api/upload',method='POST',data=json.dumps({'output_id':'a'*32}).encode(),mime='application/json')
        self.assertEqual(status, 400)

    def test_subtitle_cut(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            source = folder/'sub.srt'; out = folder/'clip.srt'
            source.write_text('1\n00:00:10,000 --> 00:00:13,000\nHello GTA 6\n',encoding='utf-8')
            self.assertTrue(cut_subtitle(source,11,2,out))
            self.assertIn('00:00:00,000 --> 00:00:02,000',out.read_text())

if __name__ == '__main__':
    unittest.main()

"""Loopback-only local studio: no cloud media uploads or arbitrary filesystem browser.

Start with `python -m clipdistrict.web`. All state lives in process or a dedicated
ClipDistrictStudioData directory. API writes require a per-process CSRF header.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .highlights import suggest, parse_srt
from .media import export_short, probe_duration, MediaError
from .youtube import inspect as inspect_youtube, search as search_youtube
from .uploader import upload_private_video

MAX_VIDEO = 2 * 1024**3
MAX_SRT = 8 * 1024**2
MAX_OAUTH = 32 * 1024
MAX_JSON = 128 * 1024
VIDEO_TYPES = {".mp4", ".mov", ".mkv", ".webm"}
ALLOWED_MODELS = {"tiny", "base", "small"}


def workspace() -> Path:
    base = os.environ.get("CLIPDISTRICT_HOME")
    root = Path(base).expanduser() if base else Path.home() / "ClipDistrictStudioData"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


class StudioState:
    def __init__(self, home: Path | None = None):
        self.home = (home or workspace()).resolve()
        self.inputs = self.home / "inputs"
        self.outputs = self.home / "exports"
        self.subtitles = self.home / "subtitles"
        self.secrets = self.home / "secrets"
        self.cache = self.home / "models"
        for p in [self.inputs, self.outputs, self.subtitles, self.secrets, self.cache]:
            p.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(36)
        self.jobs = {}
        self.lock = threading.RLock()
        self.api_key = os.environ.get("YOUTUBE_API_KEY", "")
        self.oauth_file = self.secrets / "youtube_desktop_client.json"

    def videos(self):
        files = []
        for path in self.inputs.iterdir():
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in VIDEO_TYPES:
                continue
            video_id = path.stem
            if not re.fullmatch(r"[0-9a-f]{32}", video_id):
                continue
            files.append({"id": video_id, "file_name": path.name, "size": path.stat().st_size,
                          "subtitle": (self.subtitles / f"{video_id}.srt").is_file()})
        return sorted(files, key=lambda x: x["id"], reverse=True)

    def video_path(self, video_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", video_id):
            raise ValueError("Invalid video ID")
        for ext in VIDEO_TYPES:
            path = self.inputs / f"{video_id}{ext}"
            if path.is_file() and not path.is_symlink():
                return path
        raise FileNotFoundError("Imported video not found")

    def output_path(self, output_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", output_id):
            raise ValueError("Invalid output ID")
        path = self.outputs / f"{output_id}.mp4"
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("Output not found")
        return path

    def outputs_list(self):
        results = []
        for path in self.outputs.glob("*.mp4"):
            if path.is_file() and not path.is_symlink() and re.fullmatch(r"[0-9a-f]{32}\.mp4", path.name):
                results.append({"id": path.stem, "size": path.stat().st_size,
                                "created": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
        return sorted(results, key=lambda x: x["created"], reverse=True)

    def launch_job(self, kind, function):
        job_id = uuid.uuid4().hex
        with self.lock:
            self.jobs[job_id] = {"id": job_id, "kind": kind, "state": "queued", "message": "Queued"}

        def run():
            with self.lock:
                self.jobs[job_id].update(state="running", message="Processing")
            try:
                result = function()
                with self.lock:
                    self.jobs[job_id].update(state="done", message="Completed", result=result)
            except Exception as exc:
                with self.lock:
                    self.jobs[job_id].update(state="error", message=str(exc)[:400])

        threading.Thread(target=run, daemon=True, name=f"clipdistrict-{kind}").start()
        return job_id


def _format_ts(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    h, rem = divmod(milliseconds, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def cut_subtitle(srt_path: Path, start: float, duration: float, dest: Path):
    cues = parse_srt(srt_path.read_text(encoding="utf-8-sig"))
    out = []
    for at, end, text in cues:
        if end <= start or at >= start + duration:
            continue
        b = max(0, at - start)
        e = min(duration, end - start)
        if e - b >= 0.1:
            out.append(f"{len(out)+1}\n{_format_ts(b)} --> {_format_ts(e)}\n{text}\n")
    if not out:
        return False
    dest.write_text("\n".join(out), encoding="utf-8")
    return True


def _escape_ffmpeg_filter_path(path: Path) -> str:
    """Escape separators/quotes for FFmpeg's filter option parser (including Windows drive colon)."""
    s = path.resolve().as_posix()
    # First escape filter option-level specials, then escape the backslashes for graph-level parsing.
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\\\\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def render_with_subtitles(state: StudioState, input_path: Path, output_id: str, start: float,
                          duration: float, style: str, position: str):
    """Render in landscape-to-portrait; optional clip-relative SRT captions.

    Subtitles are converted to ASS by libass's subtitle filter. Paths are under the fixed
    workspace, not provided by the browser. Subtitle contents are plain text, never commands.
    """
    srt_path = state.subtitles / f"{input_path.stem}.srt"
    output = state.outputs / f"{output_id}.mp4"
    if not srt_path.is_file():
        return export_short(input_path, start, duration, f"{output_id}.mp4", state.outputs)
    temp_sub = state.subtitles / f"clip-{output_id}.srt"
    try:
        if not cut_subtitle(srt_path, start, duration, temp_sub):
            return export_short(input_path, start, duration, f"{output_id}.mp4", state.outputs)
        if not shutil.which("ffmpeg"):
            raise MediaError("FFmpeg not found on PATH")
        if start + duration > probe_duration(input_path) + 0.1:
            raise ValueError("Clip goes beyond video length")
        # Typography is intentionally fixed to a small allowlist; no user-supplied filters.
        style_setting = {
            "classic": "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Bold=1,Alignment=2,MarginV=70",
            "neon": "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H006F2BC8,BorderStyle=1,Outline=3,Shadow=1,Bold=1,Alignment=2,MarginV=70",
        }.get(style, "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Bold=1,Alignment=2,MarginV=70")
        # Source is cropped before the subtitle render, so font size fits 1080-wide output.
        filter_str = (
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,"
            f"subtitles=filename='{_escape_ffmpeg_filter_path(temp_sub)}':force_style='{style_setting}'"
        )
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-n",
               "-ss", str(start), "-t", str(duration), "-protocol_whitelist", "file", "-i", str(input_path),
               "-vf", filter_str, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        if proc.returncode != 0:
            output.unlink(missing_ok=True)
            raise MediaError("FFmpeg subtitle rendering failed: " + proc.stderr[-450:])
        return output
    finally:
        temp_sub.unlink(missing_ok=True)


def transcribe_with_whisper(state: StudioState, video_id: str, model_name: str, allow_download: bool):
    """Transcribe local video with faster-whisper; external model retrieval is opt-in only."""
    if model_name not in ALLOWED_MODELS:
        raise ValueError("Unknown speech model")
    video = state.video_path(video_id)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("Install faster-whisper: python -m pip install faster-whisper") from None
    model = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=str(state.cache),
                         local_files_only=not allow_download)
    segments, _ = model.transcribe(str(video), beam_size=3, vad_filter=True)
    lines = []
    for i, segment in enumerate(segments, start=1):
        if i > 100000:
            raise ValueError("Transcript too long")
        lines.extend([str(i), f"{_format_ts(segment.start)} --> {_format_ts(segment.end)}", segment.text.strip(), ""])
    subtitles = state.subtitles / f"{video_id}.srt"
    subtitles.write_text("\n".join(lines), encoding="utf-8")
    return {"video_id": video_id, "segments": len(lines)//4, "subtitle": True}


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "ClipDistrictStudio/1.0"
    state: StudioState

    def log_message(self, fmt, *args):
        # Do not log URL queries or user-provided filenames containing sensitive data.
        print("[ClipDistrict]", self.command, self.path.split("?")[0], self.address_string(), flush=True)

    def _headers(self, status, content_type, length=None, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' https://i.ytimg.com data:; media-src 'self'; frame-src https://www.youtube.com https://www.youtube-nocookie.com; style-src 'self'; script-src 'self'; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; object-src 'none'")
        if length is not None:
            self.send_header("Content-Length", str(length))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()

    def respond(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def error(self, message, status=400):
        self.respond({"error": str(message)[:500]}, status)

    def _json(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise ValueError("Expected application/json")
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_JSON:
            raise ValueError("Invalid JSON length")
        return json.loads(self.rfile.read(length))

    def _stream_upload(self, folder: Path, allowed: set, max_bytes: int):
        name = self.headers.get("X-Filename", "").strip()
        ext = Path(name).suffix.lower()
        if len(name) > 180 or ext not in allowed:
            raise ValueError("Unsupported file format")
        size = int(self.headers.get("Content-Length", "0"))
        if not 1 <= size <= max_bytes:
            raise ValueError("Invalid or oversized file")
        output = folder / (uuid.uuid4().hex + ext)
        remain = size
        try:
            with output.open("xb") as f:
                while remain:
                    chunk = self.rfile.read(min(remain, 1024 * 1024))
                    if not chunk:
                        raise ValueError("Upload interrupted")
                    f.write(chunk)
                    remain -= len(chunk)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return output

    def _stream_video(self, path: Path, download=False):
        size = path.stat().st_size
        request = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if request:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", request.strip())
            if not match:
                self._headers(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            start = int(match.group(1))
            end = min(int(match.group(2)) if match.group(2) else size - 1, size - 1)
            if start >= size or end < start:
                self._headers(416, "text/plain", 0, {"Content-Range": f"bytes */{size}"})
                return
            status = 206
        extra = {"Accept-Ranges": "bytes", "Content-Disposition": "attachment; filename=clipdistrict-short.mp4" if download else "inline"}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(status, mimetypes.guess_type(path.name)[0] or "application/octet-stream", end-start+1, extra)
        with path.open("rb") as f:
            f.seek(start)
            remain = end-start+1
            while remain:
                data = f.read(min(256*1024, remain))
                if not data:
                    break
                self.wfile.write(data)
                remain -= len(data)

    def do_GET(self):
        try:
            parsed = urlsplit(self.path)
            route = parsed.path
            q = parse_qs(parsed.query)
            if route == "/":
                html = (Path(__file__).parent / "static" / "index.html").read_bytes()
                self._headers(200, "text/html; charset=utf-8", len(html))
                self.wfile.write(html)
            elif route in {"/app.js", "/style.css"}:
                file = Path(__file__).parent / "static" / route.lstrip("/")
                blob = file.read_bytes()
                self._headers(200, "application/javascript" if route.endswith("js") else "text/css", len(blob))
                self.wfile.write(blob)
            elif route == "/api/status":
                self.respond({"ok": True, "token": self.state.token,
                              "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
                              "api_key": bool(self.state.api_key),
                              "oauth_ready": self.state.oauth_file.is_file(),
                              "workspace": str(self.state.home),
                              "whisper_installed": self._whisper_ready()})
            elif route == "/api/videos":
                self.respond({"items": self.state.videos()})
            elif route == "/api/exports":
                self.respond({"items": self.state.outputs_list()})
            elif route == "/api/jobs":
                with self.state.lock:
                    self.respond({"items": list(self.state.jobs.values())[-30:]})
            elif route == "/api/search":
                import os as local_os
                key = self.state.api_key
                if not key:
                    raise ValueError("Set a YouTube Data API key in Settings")
                # Search client expects environment key; keep mutation serialized.
                with self.state.lock:
                    previous = local_os.environ.get("YOUTUBE_API_KEY")
                    local_os.environ["YOUTUBE_API_KEY"] = key
                    try:
                        results = search_youtube(q.get("q", ["GTA 6"])[0],
                                                 live=q.get("live", ["false"])[0] == "true", limit=10)
                    finally:
                        if previous is None:
                            local_os.environ.pop("YOUTUBE_API_KEY", None)
                        else:
                            local_os.environ["YOUTUBE_API_KEY"] = previous
                self.respond({"items": results})
            elif route == "/api/inspect":
                with self.state.lock:
                    previous = os.environ.get("YOUTUBE_API_KEY")
                    os.environ["YOUTUBE_API_KEY"] = self.state.api_key
                    try:
                        result = inspect_youtube(q.get("url", [""])[0])
                    finally:
                        if previous is None:
                            os.environ.pop("YOUTUBE_API_KEY", None)
                        else:
                            os.environ["YOUTUBE_API_KEY"] = previous
                self.respond(result)
            elif route.startswith("/media/"):
                video_id = route.split("/")[2]
                self._stream_video(self.state.video_path(video_id))
            elif route.startswith("/output/"):
                output_id = route.split("/")[2]
                self._stream_video(self.state.output_path(output_id), download=q.get("download", ["0"])[0] == "1")
            else:
                self.error("Not found", 404)
        except (ValueError, FileNotFoundError) as exc:
            self.error(exc, 404 if isinstance(exc, FileNotFoundError) else 400)
        except Exception as exc:
            self.error("Request failed: " + str(exc), 500)

    @staticmethod
    def _whisper_ready():
        try:
            import faster_whisper  # noqa F401
            return True
        except ImportError:
            return False

    def do_POST(self):
        try:
            # Unsafe methods require same-origin random header; blocks cross-site form CSRF.
            if self.headers.get("X-ClipDistrict-Token") != self.state.token:
                self.error("CSRF token missing", 403)
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
                self.error("Cross-origin request rejected", 403)
                return
            path = urlsplit(self.path).path
            if path == "/api/import":
                source = self._stream_upload(self.state.inputs, VIDEO_TYPES, MAX_VIDEO)
                self.respond({"ok": True, "video_id": source.stem, "size": source.stat().st_size})
            elif path.startswith("/api/subtitles/"):
                video_id = path.split("/")[3]
                self.state.video_path(video_id)
                tmp = self._stream_upload(self.state.subtitles, {".srt"}, MAX_SRT)
                try:
                    txt = tmp.read_text(encoding="utf-8-sig")
                    cues = parse_srt(txt)
                    if not cues:
                        raise ValueError("No valid SRT subtitles found")
                    (self.state.subtitles / f"{video_id}.srt").write_text(txt, encoding="utf-8")
                finally:
                    tmp.unlink(missing_ok=True)
                self.respond({"ok": True, "cue_count": len(cues)})
            elif path == "/api/settings":
                body = self._json()
                key = str(body.get("api_key", "")).strip()
                if len(key) > 256:
                    raise ValueError("Invalid API key length")
                self.state.api_key = key
                self.respond({"ok": True, "api_key": bool(key)})
            elif path == "/api/oauth-client":
                tmp = self._stream_upload(self.state.secrets, {".json"}, MAX_OAUTH)
                try:
                    payload = json.loads(tmp.read_text(encoding="utf-8"))
                    if "installed" not in payload or "client_id" not in payload["installed"]:
                        raise ValueError("Provide Google OAuth Desktop client JSON")
                    self.state.oauth_file.write_text(json.dumps(payload), encoding="utf-8")
                    try:
                        self.state.oauth_file.chmod(0o600)
                    except OSError:
                        pass
                finally:
                    tmp.unlink(missing_ok=True)
                self.respond({"ok": True})
            elif path == "/api/suggest":
                data = self._json()
                video_id = str(data.get("video_id", ""))
                self.state.video_path(video_id)
                srt = self.state.subtitles / f"{video_id}.srt"
                if not srt.is_file():
                    raise ValueError("Upload SRT or transcribe this video first")
                items = suggest(srt, length=int(data.get("length", 30)), limit=int(data.get("limit", 5)))
                self.respond({"items": items})
            elif path == "/api/transcribe":
                data = self._json()
                video_id = str(data.get("video_id", ""))
                self.state.video_path(video_id)
                model = str(data.get("model", "tiny"))
                if model not in ALLOWED_MODELS:
                    raise ValueError("Unsupported model")
                if not isinstance(data.get("download_model", False), bool):
                    raise ValueError("Invalid download flag")
                allow_download = data.get("download_model", False)
                job_id = self.state.launch_job("transcribe", lambda: transcribe_with_whisper(self.state, video_id, model, allow_download))
                self.respond({"job_id": job_id}, 202)
            elif path == "/api/render":
                data = self._json()
                video_id = str(data.get("video_id", ""))
                source = self.state.video_path(video_id)
                start = float(data.get("start", 0))
                duration = float(data.get("duration", 30))
                if not 1 <= duration <= 180 or not 0 <= start <= 86400:
                    raise ValueError("Start must be 0–86400s; duration 1–180s")
                style = str(data.get("style", "classic"))
                captions = data.get("captions", False) is True
                if style not in {"classic", "neon"}:
                    raise ValueError("Unknown style")
                output_id = uuid.uuid4().hex

                def do_render():
                    if captions:
                        path = render_with_subtitles(self.state, source, output_id, start, duration, style, "bottom")
                    else:
                        path = export_short(source, start, duration, output_id + ".mp4", self.state.outputs)
                    return {"output_id": output_id, "size": path.stat().st_size}

                self.respond({"job_id": self.state.launch_job("render", do_render)}, 202)
            elif path == "/api/upload":
                data = self._json()
                out_id = str(data.get("output_id", ""))
                output = self.state.output_path(out_id)
                if data.get("rights_confirmed") is not True:
                    raise ValueError("Confirm that you have the required rights to publish")
                if not self.state.oauth_file.is_file():
                    raise ValueError("Import Google OAuth Desktop credentials in Settings first")
                title = str(data.get("title", ""))
                desc = str(data.get("description", ""))
                audience = str(data.get("audience", "not-made-for-kids"))
                if audience not in {"made-for-kids", "not-made-for-kids"}:
                    raise ValueError("Select the audience accurately")
                if not 1 <= len(title) <= 100 or len(desc) > 4900:
                    raise ValueError("Invalid video title or description")
                if data.get("confirm") != "UPLOAD PRIVATE":
                    raise ValueError("Type UPLOAD PRIVATE to confirm")
                job_id = self.state.launch_job("upload", lambda: {
                    "studio_url": upload_private_video(output, self.state.oauth_file, title, desc,
                                                       made_for_kids=audience == "made-for-kids")})
                self.respond({"job_id": job_id}, 202)
            else:
                self.error("Not found", 404)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
            self.error(exc)
        except Exception as exc:
            self.error("Request failed: " + str(exc), 500)


def create_server(port: int = 8765, state: StudioState | None = None):
    state = state or StudioState()
    handler = type("ClipDistrictHandler", (StudioHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    return server


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Local ClipDistrict Studio browser application")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_server(args.port)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"ClipDistrict Studio on {url} — data in {server.RequestHandlerClass.state.home}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ClipDistrict Studio")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

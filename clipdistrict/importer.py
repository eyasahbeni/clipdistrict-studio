"""Get a source video into a project: from a link (yt-dlp) or an uploaded file.

Only import streams you have the creator's permission to clip.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from . import projects
from .config import ffmpeg_bin
from .media import probe

MAX_HEIGHT = 1080


def check_url(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Paste a full video link that starts with https://")
    if parsed.hostname in ("localhost",) or parsed.hostname.startswith(("127.", "10.", "192.168.")):
        raise ValueError("Local network links are not allowed")
    return url


def _base_opts() -> dict:
    """Shared yt-dlp options. YouTube needs a JavaScript runtime; we ship deno via pip."""
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    try:
        import deno
        opts["js_runtimes"] = {"deno": {"path": deno.find_deno_bin()}}
    except Exception:
        pass
    return opts


def fetch_info(url: str) -> dict:
    """Title / creator / duration without downloading."""
    import yt_dlp
    opts = {**_base_opts(), "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(check_url(url), download=False)
    return {
        "title": info.get("title") or "Untitled",
        "creator": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration") or 0,
        "thumbnail": info.get("thumbnail") or "",
        "is_live": bool(info.get("is_live")),
    }


def download(project_id: str, url: str, start: float | None = None, end: float | None = None,
             on_progress=None) -> Path:
    """Download (optionally only a section of) a video as MP4 up to 1080p."""
    import yt_dlp
    folder = projects.project_dir(project_id)
    target = folder / "source.%(ext)s"

    def hook(d):
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                on_progress(min(0.99, done / total), f"Downloading {done / 1e6:.0f} / {total / 1e6:.0f} MB")
            else:
                on_progress(None, f"Downloading {done / 1e6:.0f} MB")

    opts = {
        **_base_opts(),
        "outtmpl": str(target),
        "format": (f"bv*[height<={MAX_HEIGHT}][ext=mp4]+ba[ext=m4a]/"
                   f"b[height<={MAX_HEIGHT}][ext=mp4]/bv*[height<={MAX_HEIGHT}]+ba/b"),
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_bin(),
        "progress_hooks": [hook],
        "retries": 5,
        "concurrent_fragment_downloads": 4,
    }
    if start is not None or end is not None:
        from yt_dlp.utils import download_range_func
        opts["download_ranges"] = download_range_func(None, [(start or 0, end or float("inf"))])
        opts["force_keyframes_at_cuts"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([check_url(url)])

    produced = sorted(folder.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    produced = [p for p in produced if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
    if not produced:
        raise RuntimeError("Download finished but no video file was found")
    return normalize(produced[0], projects.source_path(project_id))


def normalize(src: Path, dest: Path) -> Path:
    """Make sure the source is a seekable H.264/AAC MP4 the browser can preview."""
    if src.suffix.lower() == ".mp4":
        if src != dest:
            shutil.move(str(src), dest)
        return dest
    tmp = dest.with_name("source.converting.mp4")
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=6 * 3600)
    tmp.replace(dest)
    src.unlink(missing_ok=True)
    return dest


def finish_import(project_id: str) -> dict:
    info = probe(projects.source_path(project_id))
    return projects.update(project_id, duration=info["duration"], width=info["width"],
                           height=info["height"], has_audio=info["has_audio"])

"""Restricted local file clipping with FFmpeg (no shell, network off)."""
from __future__ import annotations
import math
import re
import subprocess
from pathlib import Path

from .config import ffmpeg_bin

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,75}\.mp4$")


class MediaError(RuntimeError):
    pass


def parse_time(text: str) -> float:
    parts = text.strip().split(":")
    if len(parts) > 3 or not parts or any(not p for p in parts):
        raise ValueError("Time must be seconds, MM:SS, or HH:MM:SS")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        raise ValueError("Invalid time") from None
    if not all(math.isfinite(x) and x >= 0 for x in values):
        raise ValueError("Invalid time")
    if len(values) > 1 and any(x >= 60 for x in values[1:]):
        raise ValueError("Minutes/seconds must be less than 60")
    seconds = 0.0
    for value in values:
        seconds = seconds * 60 + value
    if seconds > 86400:
        raise ValueError("Time exceeds one day")
    return seconds


def check_local_video(src: str | Path) -> Path:
    source = Path(src).expanduser()
    if source.is_symlink():
        raise MediaError("Symlink inputs are disabled")
    source = source.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXT:
        raise MediaError("Input must be a local MP4/MOV/MKV/WEBM file")
    return source


DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
SIZE_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")


def probe(src: Path) -> dict:
    """Return duration/width/height. Uses only ffmpeg (ffprobe is optional)."""
    try:
        ffmpeg = ffmpeg_bin()
    except RuntimeError as err:
        raise MediaError(str(err)) from None
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-i", str(src)]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=35,
                                encoding="utf-8", errors="replace")
    except subprocess.SubprocessError as err:
        raise MediaError(f"Could not inspect video: {type(err).__name__}") from None
    match = DURATION_RE.search(result.stderr)
    if not match:
        raise MediaError("Could not read video duration")
    h, m, s = match.groups()
    duration = int(h) * 3600 + int(m) * 60 + float(s)
    size = SIZE_RE.search(result.stderr)
    width, height = (int(size.group(1)), int(size.group(2))) if size else (1920, 1080)
    if not math.isfinite(duration) or duration <= 0:
        raise MediaError("Video duration invalid")
    return {"duration": duration, "width": width, "height": height,
            "has_audio": "Audio:" in result.stderr}


def probe_duration(src: Path) -> float:
    return probe(src)["duration"]


def export_short(src: str | Path, start: float, duration: float, name: str,
                 export_dir: str | Path = "exports") -> Path:
    if not math.isfinite(start) or start < 0 or not math.isfinite(duration) or not 1 <= duration <= 180:
        raise MediaError("Clip must be 1–180 seconds, with a non-negative start")
    if not NAME_RE.fullmatch(name):
        raise MediaError("Output name must use letters, numbers, - or _, ending in .mp4")
    try:
        ffmpeg = ffmpeg_bin()
    except RuntimeError as err:
        raise MediaError(str(err)) from None
    source = check_local_video(src)
    available = probe_duration(source)
    if start + duration > available + 0.1:
        raise MediaError(f"Time range exceeds source duration ({available:.1f}s)")
    folder = Path(export_dir).expanduser()
    if folder.is_symlink():
        raise MediaError("Symlink export directories are disabled")
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / name
    if output.exists():
        raise MediaError("Refusing to overwrite an existing file")
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    cmd = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-n",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-protocol_whitelist", "file", "-i", str(source),
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-max_muxing_queue_size", "1024", str(output),
    ]
    try:
        subprocess.run(cmd, check=True, text=True, capture_output=True, timeout=1200)
    except subprocess.TimeoutExpired:
        output.unlink(missing_ok=True)
        raise MediaError("Rendering timed out") from None
    except subprocess.CalledProcessError as err:
        output.unlink(missing_ok=True)
        raise MediaError(f"FFmpeg failed: {err.stderr[-500:] if err.stderr else 'unknown error'}") from None
    return output

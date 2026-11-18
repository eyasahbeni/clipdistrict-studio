"""Paths, settings and tool discovery shared by the whole app."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
FONTS_DIR = PACKAGE_DIR / "fonts"
WEB_DIR = PACKAGE_DIR / "web"


def _load_dotenv() -> None:
    """Read KEY=value lines from a .env file next to the project (no extra dependency)."""
    for candidate in (Path.cwd() / ".env", PACKAGE_DIR.parent / ".env"):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            break


_load_dotenv()

WORKSPACE = Path(os.environ.get("CLIPDISTRICT_HOME", PACKAGE_DIR.parent / "workspace")).expanduser().resolve()
PROJECTS_DIR = WORKSPACE / "projects"
SECRETS_DIR = WORKSPACE / "secrets"
SETTINGS_FILE = WORKSPACE / "settings.json"

DEFAULT_SETTINGS = {
    "whisper_model": os.environ.get("WHISPER_MODEL", "small"),
    "language": "",            # empty = auto-detect
    "default_theme": "vice-city",
    "default_layout": "blur",
    "clip_length": 35,
    "clips_per_video": 6,
    "channel_tag": "@ClipDistrict",
    "default_hashtags": "#GTA6 #GTAVI #ViceCity #Shorts",
    # your own keywords: "phrase:weight" (weight 1-10, default 4)
    "keywords": "police chase:5, wanted level:4, five star:4, heist:4, crash:3, lucia:3, jason:3, "
                "leonida:3, vice city:4, rockstar:2, no way:4, let's go:4",
    # autopilot: what happens after a video is imported
    "autopilot": False,
    "auto_clips": 3,
    "auto_min_score": 40,
    "auto_max_seconds": 59,
    "auto_upload": "off",          # off | private | unlisted | public
    "auto_channel": "",
    "auto_theme": "vice-city",
    "auto_layout": "blur",
    # cleanup
    "delete_source_after_auto": True,
    "delete_clip_after_upload": False,
    "keep_days": 7,                # delete source videos older than this (0 = never)
    # watchlist: check creators' channels for new GTA 6 videos
    "watch_enabled": False,
    "watch_channels": [],          # [{"input": "@IShowSpeed", "id": "UC...", "title": "..."}]
    "watch_keywords": "GTA 6, GTA VI, GTA6, Vice City",
    "watch_interval": 30,          # minutes
    "watch_max_minutes": 240,
}


def ensure_dirs() -> None:
    for folder in (WORKSPACE, PROJECTS_DIR, SECRETS_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    data = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.is_file():
        try:
            stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            data.update({k: v for k, v in stored.items() if k in DEFAULT_SETTINGS})
        except (OSError, ValueError):
            pass
    return data


def save_settings(values: dict) -> dict:
    data = load_settings()
    for key, value in values.items():
        if key in DEFAULT_SETTINGS:
            data[key] = value
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def ffmpeg_bin() -> str:
    """System FFmpeg first, otherwise the copy bundled by the imageio-ffmpeg package."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    if os.name == "nt" and winget.is_file():
        return str(winget)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as err:  # pragma: no cover - depends on machine
        raise RuntimeError("FFmpeg not found. Run start.bat again or install FFmpeg.") from err


def oauth_client_file() -> Path | None:
    configured = os.environ.get("YOUTUBE_OAUTH_CLIENT", "").strip()
    if configured and Path(configured).expanduser().is_file():
        return Path(configured).expanduser()
    default = SECRETS_DIR / "client_secret.json"
    return default if default.is_file() else None


_caption_support: bool | None = None


def ffmpeg_has_captions() -> bool:
    """True if this FFmpeg can burn in styled captions (needs libass)."""
    global _caption_support
    if _caption_support is None:
        import subprocess
        try:
            out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-filters"], capture_output=True,
                                 text=True, timeout=20).stdout
            _caption_support = " ass " in out
        except Exception:
            _caption_support = False
    return _caption_support

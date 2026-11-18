"""YouTube upload via Google OAuth (official API). Never uses cookies or passwords.

You can connect several channels. Each sign-in is saved in workspace/secrets/tokens/<channel id>.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import SECRETS_DIR, ensure_dirs, oauth_client_file
from .media import check_local_video

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
TOKENS_DIR = SECRETS_DIR / "tokens"
CHANNELS_FILE = SECRETS_DIR / "channels.json"
LEGACY_TOKEN = SECRETS_DIR / "token.json"
PRIVACY = {"private", "unlisted", "public"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def _libs():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as err:
        raise RuntimeError("Google libraries missing. Run start.bat again to install them.") from err
    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload


def list_channels() -> list[dict]:
    if CHANNELS_FILE.is_file():
        try:
            data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
            return [c for c in data if (TOKENS_DIR / f"{c['id']}.json").is_file()]
        except (OSError, ValueError, KeyError):
            return []
    return []


def _save_channels(channels: list[dict]) -> None:
    ensure_dirs()
    CHANNELS_FILE.write_text(json.dumps(channels, indent=2), encoding="utf-8")


def _token_path(channel_id: str) -> Path:
    if not ID_RE.fullmatch(channel_id or ""):
        raise ValueError("Invalid channel id")
    return TOKENS_DIR / f"{channel_id}.json"


def _load(channel_id: str):
    Request, Credentials, *_ = _libs()
    path = _token_path(channel_id)
    if not path.is_file():
        raise RuntimeError("That channel isn't connected. Sign in again in Settings.")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError("Sign-in expired for this channel. Sign in again in Settings.")
    return creds


def sign_in() -> dict:
    """Open Google sign-in in the browser and add the chosen channel."""
    _, _, InstalledAppFlow, build, _ = _libs()
    client_file = oauth_client_file()
    if not client_file:
        raise RuntimeError("Add your Google OAuth client file in Settings first")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes=SCOPES)
    creds = flow.run_local_server(host="localhost", port=0, open_browser=True,
                                  access_type="offline", prompt="consent select_account")
    service = build("youtube", "v3", credentials=creds, cache_discovery=False)
    items = service.channels().list(part="snippet", mine=True).execute().get("items", [])
    if not items:
        raise RuntimeError("This Google account has no YouTube channel")
    channel = {"id": items[0]["id"], "title": items[0]["snippet"]["title"],
               "thumb": items[0]["snippet"].get("thumbnails", {}).get("default", {}).get("url", "")}
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    _token_path(channel["id"]).write_text(creds.to_json(), encoding="utf-8")
    channels = [c for c in list_channels() if c["id"] != channel["id"]] + [channel]
    _save_channels(channels)
    return channel


def remove_channel(channel_id: str) -> None:
    _token_path(channel_id).unlink(missing_ok=True)
    _save_channels([c for c in list_channels() if c["id"] != channel_id])


def upload(file: str | Path, title: str, description: str, *, tags: list[str] | None = None,
           privacy: str = "private", channel_id: str = "", made_for_kids: bool = False,
           on_progress=None) -> dict:
    source = check_local_video(file)
    title = title.strip()
    if not 1 <= len(title) <= 100 or len(description) > 4900:
        raise ValueError("Title must be 1–100 characters; description max 4900")
    if privacy not in PRIVACY:
        raise ValueError("Privacy must be private, unlisted or public")
    channels = list_channels()
    if not channels:
        raise RuntimeError("Connect a YouTube channel in Settings first")
    channel = next((c for c in channels if c["id"] == channel_id), channels[0])
    _, _, _, build, MediaFileUpload = _libs()
    service = build("youtube", "v3", credentials=_load(channel["id"]), cache_discovery=False)
    body = {
        "snippet": {"title": title, "description": description, "categoryId": "20",
                    "tags": [t.strip("# ")[:30] for t in (tags or []) if t.strip("# ")][:15]},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids},
    }
    request = service.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(source), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and on_progress:
            on_progress(status.progress(), f"Uploading {status.progress() * 100:.0f}%")
    vid = response["id"]
    return {"video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
            "studio_url": f"https://studio.youtube.com/video/{vid}/edit", "privacy": privacy,
            "channel": channel["title"]}


def upload_private_video(file: str | Path, oauth_client: str | Path, title: str,
                         description: str, made_for_kids: bool) -> str:
    """Kept for the command-line tool."""
    client = Path(oauth_client).expanduser().resolve(strict=True)
    if client.suffix.lower() != ".json":
        raise ValueError("OAuth desktop client JSON not found")
    save_client_file(client.read_bytes())
    if not list_channels():
        sign_in()
    return upload(file, title, description, made_for_kids=made_for_kids)["studio_url"]


def save_client_file(data: bytes) -> Path:
    payload = json.loads(data.decode("utf-8"))
    if "installed" not in payload and "web" not in payload:
        raise ValueError("This is not a Google OAuth client file (download it as 'Desktop app')")
    ensure_dirs()
    target = SECRETS_DIR / "client_secret.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target

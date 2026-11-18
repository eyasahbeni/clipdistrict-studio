"""Read-only metadata discovery via the official YouTube Data API v3.

This module does not download YouTube video/audio or import cookies.
"""
from __future__ import annotations
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
HOSTS = {"www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
API_ROOT = "https://www.googleapis.com/youtube/v3"


class YouTubeError(RuntimeError):
    pass


def video_id_from_url(text: str) -> str:
    parsed = urlparse(text.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Please provide an HTTPS youtube.com or youtu.be URL")
    if parsed.hostname == "youtu.be":
        value = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        value = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
        value = parsed.path.split("/")[2]
    else:
        raise ValueError("Unsupported YouTube URL format")
    if not VIDEO_ID_RE.fullmatch(value):
        raise ValueError("Invalid YouTube video ID")
    return value


def _get(endpoint: str, params: dict) -> dict:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise YouTubeError("Set YOUTUBE_API_KEY for read-only YouTube search/metadata")
    if endpoint not in {"search", "videos", "channels", "playlistItems"}:
        raise ValueError("Unsupported API endpoint")
    args = urlencode({**params, "key": key})
    request = Request(
        f"{API_ROOT}/{endpoint}?{args}",
        headers={"Accept": "application/json", "User-Agent": "ClipDistrictStudio/0.1"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as err:
        raise YouTubeError(f"YouTube API HTTP {err.code}; check API key, quotas and permissions") from None
    except (URLError, TimeoutError):
        raise YouTubeError("Network request failed") from None


def search(query: str = "GTA 6", *, live: bool = False, limit: int = 10) -> list[dict]:
    if not 1 <= limit <= 25:
        raise ValueError("limit must be between 1 and 25")
    query = query.strip()
    if not 1 <= len(query) <= 150:
        raise ValueError("query must be 1–150 characters")
    params = {"part": "snippet", "q": query, "type": "video", "maxResults": limit, "order": "date"}
    if live:
        params["eventType"] = "live"
    payload = _get("search", params)
    return [
        {
            "id": item.get("id", {}).get("videoId", ""),
            "title": item.get("snippet", {}).get("title", ""),
            "creator": item.get("snippet", {}).get("channelTitle", ""),
            "channel_id": item.get("snippet", {}).get("channelId", ""),
            "published_at": item.get("snippet", {}).get("publishedAt", ""),
            "url": "https://www.youtube.com/watch?v=" + item.get("id", {}).get("videoId", ""),
            "thumbnail": item.get("snippet", {}).get("thumbnails", {}).get("medium", {}).get("url", ""),
        }
        for item in payload.get("items", [])
        if VIDEO_ID_RE.fullmatch(item.get("id", {}).get("videoId", ""))
    ]


def inspect(url: str) -> dict:
    video_id = video_id_from_url(url)
    payload = _get("videos", {"part": "snippet,contentDetails,liveStreamingDetails", "id": video_id})
    if not payload.get("items"):
        raise YouTubeError("Video not found or is not public")
    item = payload["items"][0]
    snippet = item.get("snippet", {})
    return {
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "embed_url": f"https://www.youtube.com/embed/{video_id}",
        "title": snippet.get("title", ""),
        "creator": snippet.get("channelTitle", ""),
        "description": snippet.get("description", "")[:600],
        "published_at": snippet.get("publishedAt", ""),
        "duration": item.get("contentDetails", {}).get("duration", ""),
        "live_details": item.get("liveStreamingDetails", {}),
        "note": "Metadata and preview only. No video is downloaded.",
    }


CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def resolve_channel(text: str) -> dict:
    """Accept @handle, a channel URL or a UC... id. Returns id, title, uploads playlist."""
    value = text.strip()
    if value.startswith("http"):
        path = urlparse(value).path.strip("/")
        if path.startswith("channel/"):
            value = path.split("/")[1]
        elif path.startswith("@"):
            value = path.split("/")[0]
        else:
            raise ValueError("Use a channel link like youtube.com/@name")
    params = {"part": "snippet,contentDetails"}
    if CHANNEL_ID_RE.fullmatch(value):
        params["id"] = value
    else:
        handle = value if value.startswith("@") else "@" + value
        if not re.fullmatch(r"@[A-Za-z0-9._-]{2,100}", handle):
            raise ValueError("Invalid channel handle")
        params["forHandle"] = handle
    items = _get("channels", params).get("items", [])
    if not items:
        raise YouTubeError(f"Channel not found: {text}")
    item = items[0]
    return {"id": item["id"], "title": item["snippet"]["title"],
            "uploads": item["contentDetails"]["relatedPlaylists"]["uploads"],
            "thumb": item["snippet"].get("thumbnails", {}).get("default", {}).get("url", "")}


def recent_uploads(uploads_playlist: str, limit: int = 10) -> list[dict]:
    """Newest videos of a channel (1 quota unit, much cheaper than search)."""
    payload = _get("playlistItems", {"part": "snippet,contentDetails", "playlistId": uploads_playlist,
                                     "maxResults": max(1, min(50, limit))})
    out = []
    for item in payload.get("items", []):
        vid = item.get("contentDetails", {}).get("videoId", "")
        if VIDEO_ID_RE.fullmatch(vid):
            out.append({"id": vid, "title": item["snippet"].get("title", ""),
                        "published_at": item["contentDetails"].get("videoPublishedAt", ""),
                        "url": f"https://www.youtube.com/watch?v={vid}"})
    return out


def durations(video_ids: list[str]) -> dict[str, float]:
    """Seconds per video id; live/upcoming streams come back as 0."""
    if not video_ids:
        return {}
    payload = _get("videos", {"part": "contentDetails,snippet", "id": ",".join(video_ids[:50])})
    result = {}
    for item in payload.get("items", []):
        live = item.get("snippet", {}).get("liveBroadcastContent", "none")
        iso = item.get("contentDetails", {}).get("duration", "")
        m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
        secs = 0.0
        if m and live == "none":
            d, h, mi, se = (int(x or 0) for x in m.groups())
            secs = d * 86400 + h * 3600 + mi * 60 + se
        result[item["id"]] = secs
    return result

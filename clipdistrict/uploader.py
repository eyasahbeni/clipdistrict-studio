"""Optional private YouTube upload via Google OAuth; never accepts cookies or passwords."""
from __future__ import annotations
from pathlib import Path
from .media import check_local_video

SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


def upload_private_video(file: str | Path, oauth_client: str | Path, title: str,
                         description: str, made_for_kids: bool) -> str:
    source = check_local_video(file)
    client_file = Path(oauth_client).expanduser().resolve(strict=True)
    if not client_file.is_file() or client_file.suffix.lower() != ".json":
        raise ValueError("OAuth desktop client JSON not found")
    if not 1 <= len(title.strip()) <= 100 or len(description) > 4900:
        raise ValueError("Title must be 1–100 characters; description max 4900")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as err:
        raise RuntimeError("Install optional Google SDK: pip install -e '.[youtube-upload]'") from err

    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), scopes=SCOPE)
    credentials = flow.run_local_server(host="localhost", port=0, open_browser=True, access_type="offline")
    service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    body = {
        "snippet": {"title": title.strip(), "description": description, "categoryId": "20"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": made_for_kids},
    }
    request = service.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(source), mimetype="video/mp4", resumable=True),
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return "https://studio.youtube.com/video/" + response["id"] + "/edit"

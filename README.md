# ClipDistrict Studio — GTA 6 Shorts Editor

**Local-first YouTube discovery, vertical Shorts editing, subtitle generation, and private uploads.** A free, open-source app designed to help create original GTA 6 video clips from footage you own or are permitted to edit.

[![Tests](https://github.com/eyasahbeni/clipdistrict-studio/actions/workflows/tests.yml/badge.svg)](https://github.com/eyasahbeni/clipdistrict-studio/actions/workflows/tests.yml)

## Start on Windows

1. Install **Python 3.11 or newer** from https://www.python.org/downloads/ (tick “Add Python to PATH”).
2. Install a **trusted FFmpeg and FFprobe build** from https://ffmpeg.org/download.html and add it to PATH. Run `ffmpeg -version` and `ffprobe -version` in PowerShell to check.
3. Download this project's source ZIP, extract it into a folder, and double-click **`START_WINDOWS.bat`**. The application opens locally at **http://127.0.0.1:8765**.
4. Go to **Clip Editor → Choose video file**, import your own video or a creator-provided authorized source recording, select start/duration, and click **Generate vertical Short**. MP4 exports are available in **My Exports**.

A small **sample video and SRT** are included in `examples/` so you can test the editor immediately. No `pip install` is needed for basic cutting, subtitles from SRT, or the browser interface. **Do not run as Windows Administrator.** No API account is required to edit a locally supplied file.

If you do not want to use a batch file:

```powershell
cd path\to\clipdistrict-studio
py -3 -m clipdistrict.web
```

Stop with Ctrl+C in the terminal. Source videos, temporary files, and exports are stored by default under `C:\Users\<your-user>\ClipDistrictStudioData`; nothing is uploaded by the application without your explicit action.

## The full workflow

### 1. Discover GTA 6 streamers

In **Discover**, paste a YouTube video or livestream URL to preview using YouTube's official embedded player (**no key required**). To also search public video metadata directly inside the app, create a **YouTube Data API v3 key** at https://console.cloud.google.com/apis/library/youtube.googleapis.com, enable the API, and enter the key in **Settings**. The app holds that key only in RAM for the session. Use queries such as “GTA 6 streamers”, “GTA VI trailer reactions”, or “Vice City gameplay”.

**The app deliberately does not download other creators' YouTube video streams.** YouTube's Data API does not provide general video download access and API policies restrict this use. Request original footage directly from participating creators or import your own recording. The YouTube preview and the editable video file are separate sources.

### 2. Import an MP4/WEBM/MOV/MKV

From **Clip Editor**, choose a video or drag-and-drop it. The browser sends it *to the local app on your own computer*, not to a remote server. Maximum file size: **2 GB**. Use the embedded local player to inspect your video.

### 3. Find highlights and create subtitles

- **Manual:** Pick start time and duration (up to 180 seconds).
- **Transcript-assisted:** Upload an `.srt` subtitle file and press **Suggest highlights**. The candidate scoring is rule-based, not advanced AI; inspect every suggestion.
- **Optional speech transcription:** Install `faster-whisper` if desired: `py -3 -m pip install faster-whisper`. Press **Auto-transcribe**. If the small speech model is not on your PC, explicitly check **Allow downloading the free Whisper model** and confirm. The model may require network access *only when you opt in*; after download, transcription happens locally. CPU transcription can take time.

You may switch between **Classic bold white** and **Vice City neon outline** caption treatments. Burned captions use the available SRT file. For clips with no subtitle data, the app renders clean video (without captions).

### 4. Generate and export Shorts

Click **Generate vertical Short**. The app uses FFmpeg to crop the middle of the image and output H.264/AAC **1080 × 1920 MP4** with the selected start and duration. You can track the render job at the bottom of the page. Downloads are under **My Exports**. Smart face tracking and custom zoom are not in this release.

### 5. Optionally upload privately to YouTube

To upload through the app, you must configure Google Cloud yourself:

1. Enable the YouTube Data API v3 in a Google Cloud project.
2. Configure the OAuth consent screen and create an **OAuth Desktop app** client ID.
3. Download the desktop OAuth JSON and import it under **Settings → YouTube Upload OAuth**. The file stays in your local application data directory and should **never** be committed to GitHub.
4. Install the optional libraries (requires an internet connection): `py -3 -m pip install "google-api-python-client>=2.140,<3" "google-auth-oauthlib>=1.2,<2"`.
5. In **My Exports**, select a Short, add an accurate title and description, verify your content rights, and authorize **Upload private**. The Google OAuth sign-in runs in your browser. The upload is always **PRIVATE**, so you can review it in YouTube Studio before changing its visibility yourself.

Google may require additional verification before an OAuth app can authorize other users; upload may be blocked until its setup requirements are fulfilled. **A phone number alone does not grant permission to publish to a YouTube channel.** We have not exercised a live Google upload from this development environment.

## Security properties

- Server binds only to `127.0.0.1`; all modifying requests require a per-session CSRF header.
- No cookies, no telemetry, no unrequested downloads, and no remote shell execution.
- The interface can access only imported source and exported video IDs (not arbitrary computer paths).
- Rendering uses FFmpeg via command arguments, with a file-only protocol whitelist and no overwriting existing exports.
- Source recordings and raw transcripts remain on your PC. Google OAuth client JSON is stored in your local data directory; Google access tokens are not intentionally persisted by the app.
- Third-party codecs and large untrusted media still pose risks; do not process suspicious files on your primary Windows installation. This is not security-certified software.

See [`SECURITY.md`](SECURITY.md) for known limitations.

## Tests

```sh
python -m unittest discover -s tests -v
node --check clipdistrict/static/app.js     # optional JavaScript syntax check
```

The suite includes URL validation, timing/safe filenames, HTTP server controls, upload restrictions, SRT processing, and CSRF validation. We also performed an end-to-end test with a generated MP4, imported captions, rendered a Short, and checked FFprobe output at 1080 × 1920. YouTube API search and OAuth upload are not tested live.

## Source & attribution

Conceptually inspired by [`op7418/Youtube-clipper-skill`](https://github.com/op7418/Youtube-clipper-skill) and [`jipraks/yt-short-clipper`](https://github.com/jipraks/yt-short-clipper); implemented independently for this starter. MIT licensed. All rights to third-party video material belong to their respective owners. No affiliation with Rockstar Games or YouTube.

References: [YouTube API Policies](https://developers.google.com/youtube/terms/developer-policies), [Google OAuth](https://developers.google.com/youtube/data/guides/authentication), [YouTube upload guide](https://developers.google.com/youtube/data/guides/uploading_a_video).

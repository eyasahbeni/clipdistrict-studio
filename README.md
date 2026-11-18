# ClipDistrict Studio

**Experimental, local-first GTA 6 Shorts workflow** — discover relevant YouTube streams through the official Data API, select authorized source recordings, suggest highlights from SRT transcripts, create 9:16 clips with FFmpeg, and optionally upload *privately* to your own YouTube channel.

**Status: v0.1 CLI starter.** This is not a complete desktop app, automatic YouTube downloader, or fully autonomous AI editor.

## Features
- YouTube GTA 6 video and livestream **search/metadata** via the official YouTube Data API (API key required).
- Secure YouTube URL parsing; no scraping or browser-cookie extraction.
- Explainable keyword-based highlight suggestions from local SRT subtitles (not trained AI).
- Local FFmpeg cropping to 1080×1920 MP4 for explicitly chosen time ranges.
- Optional **private-only** YouTube upload through Google's OAuth desktop flow. No automatic posting.
- No telemetry, hidden downloads, or embedded user credentials.

## Windows quick start
Requires Python 3.11+ and a separately installed, trusted FFmpeg/ffprobe available on PATH.

1. Create and activate a virtual environment: `py -3 -m venv .venv`; `.venv\Scripts\activate`
2. You can use the CLI directly without installing dependencies: `python -m clipdistrict --help`
3. Set your YouTube Data API key in PowerShell: `$env:YOUTUBE_API_KEY="YOUR_API_KEY"`
4. Discover: `python -m clipdistrict search --query "GTA 6 streamer reaction" --limit 10`
5. Find live content: `python -m clipdistrict search --query "GTA 6" --live`
6. Inspect metadata: `python -m clipdistrict inspect "https://www.youtube.com/watch?v=VIDEO_ID"`
7. Suggest local transcript highlights: `python -m clipdistrict suggest "C:\Videos\authorized.srt" --length 30 --limit 3`
8. Render a Short from an authorized local file: `python -m clipdistrict clip "C:\Videos\authorized.mp4" --start 00:10:15 --duration 30 --name clip-01.mp4`

## Optional private YouTube upload
Enable YouTube Data API v3 in Google Cloud, create an **OAuth Desktop app** client, and store the downloaded client JSON outside this repository. Install optional dependencies: `python -m pip install -e ".[youtube-upload]"`.

Example:
`python -m clipdistrict upload "exports\clip-01.mp4" --oauth-client "C:\Secrets\youtube-client.json" --title "GTA 6 reaction explained" --description "Original commentary using authorized footage." --audience not-made-for-kids --rights-confirmed`

The command asks for an explicit typed confirmation and the Google browser OAuth flow, then uploads as **PRIVATE**. A phone number alone cannot authorize a channel upload. OAuth tokens are not persisted by this prototype.

## Important limits
YouTube's Data API allows discovery, video details, and authorized uploading; it does **not** expose a general-purpose way to download other people's YouTube audiovisual streams. This project deliberately does not implement third-party YouTube media extraction. Obtain source recordings from your own content or creator-approved delivery channels, with any required permissions, and add meaningful original value before publishing.

No live Google API calls or uploads are performed by the included tests. Use `python -m unittest discover -s tests -v`.

Read [SECURITY.md](SECURITY.md), [Architecture](docs/ARCHITECTURE.md), and [Roadmap](docs/ROADMAP.md) before running or contributing.

Inspired by features of op7418/Youtube-clipper-skill and jipraks/yt-short-clipper, but independently implemented. MIT licensed.

Official references: [YouTube Search API](https://developers.google.com/youtube/data/reference/rest/v3/search/list), [Uploads](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert), [Developer policies](https://developers.google.com/youtube/terms/developer-policies/).

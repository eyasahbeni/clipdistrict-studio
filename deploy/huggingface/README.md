---
title: ClipDistrict Studio
emoji: 🎬
colorFrom: pink
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# ClipDistrict Studio

GTA 6 Shorts studio: import a stream → auto subtitles → best moments → styled captions → upload.
Source: https://github.com/eyasahbeni/clipdistrict-studio

Set these in **Settings → Variables and secrets**:

| Name | Type | What |
|---|---|---|
| `APP_PASSWORD` | Secret | Password to open the app (required) |
| `YOUTUBE_API_KEY` | Secret | For searching streams + watchlist |
| `GOOGLE_OAUTH_CLIENT_JSON` | Secret | Contents of the **Web application** OAuth client JSON (for uploading) |
| `SECRET_KEY` | Secret | Any long random text (keeps you logged in after restarts) |

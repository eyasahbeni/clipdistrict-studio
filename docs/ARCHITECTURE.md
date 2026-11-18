# Architecture

```text
Browser UI (web/)  ──HTTP, 127.0.0.1 only──►  Flask server (server.py)
                                                  │  background jobs (jobs.py, 1 heavy worker)
   link ──► importer.py (yt-dlp + deno) ─┐        │
   file ──► upload + optional .srt ──────┼──► workspace/projects/<id>/source.mp4
                                         │
                transcribe.py (faster-whisper, word timings) ─► transcript.json
                moments.py (hype words + loudness + talk speed) ─► project.json moments
                                         │
          editor settings ─► captions.py (ASS themes) + render.py (FFmpeg layouts)
                                         │
                               clips/<clip>.mp4 ─► uploader.py (Google OAuth) ─► YouTube
```

## Storage

`workspace/` (git-ignored) holds projects, settings and `secrets/` (API key, OAuth client, saved token).
Set `CLIPDISTRICT_HOME` to move it.

## Safety rules

- The server listens on `127.0.0.1` only.
- FFmpeg runs with argument arrays, no shell. Captions and fonts are written to a temporary folder.
- Project and clip ids are validated with strict patterns before touching the disk.
- Link import refuses local-network URLs and requires the "creator allows clipping" confirmation.
- Uploads require a permission checkbox and default to private; public needs an extra confirm.

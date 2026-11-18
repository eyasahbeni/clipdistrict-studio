# ClipDistrict Studio security policy

This is an experimental local-first video processing application, **not independently audited or guaranteed free of vulnerabilities**.

- Binds to loopback (`127.0.0.1`) only, not the public network.
- Browser POST requests must include an unpredictable per-process CSRF header.
- User files are imported into a dedicated local data directory and served only by opaque UUIDs; the UI does not expose arbitrary local file paths.
- Local file video processing calls FFmpeg with argument arrays, never shell-evaluated commands. FFmpeg/ffprobe are expected to be installed and verified separately.
- No Google session cookies, telemetry, browser scraping, or silent model downloads.
- YouTube public search uses the official YouTube Data API; third-party video download is not implemented.
- The optional transcription model only downloads when a user explicitly approves the operation.
- The optional Google OAuth Desktop client is stored under a dedicated local secrets directory; credentials must never be pushed to Git.
- OAuth upload scopes are limited to `youtube.upload`; all uploads are private and require explicit human approval.

## Remaining risks

- **Untrusted media:** FFmpeg and its codec parsers process complex inputs. Avoid untrusted videos and consider a separate Windows VM/sandbox for unknown footage. Windows OS-level process sandboxing is not provided in this release.
- **Security boundaries:** Folder/ID checks and loopback binding are helpful but not a guarantee against compromise of the user account or other local processes.
- **Dependencies:** External binaries, optional Google libraries, and Whisper model weights are not bundled or cryptographically pinned in this source archive. Verify their provenance before installing.
- **Large video files:** The server accepts imports up to 2 GB; consider system memory and free disk space. The local server should not run as Administrator.
- **OAuth UI:** Google sign-in and upload flow have not been live-tested here; cloud account and consent configurations are provided by the user.
- **Transcript safety:** Subtitle strings are untrusted data. They are not executed as code, but malformed subtitles can still expose codec/library bugs.
- **Local privacy:** OAuth client JSON is placed in the user's application data folder and may remain there until removed by the user. Access token persistence has intentionally not been implemented.

Report security issues using a private GitHub vulnerability report (when enabled) rather than posting live credentials or exploits in public issues.

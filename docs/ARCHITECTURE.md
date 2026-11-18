# Architecture and trust boundaries

```text
YouTube Data API (metadata only) ---> Discovery + URL preview ---> Creator review
                                                   |
Authorized local source footage -------------------+--> Local FFmpeg clip/render
Local SRT subtitles -------------------------------+--> Heuristic highlight suggestions
                                                            |
                                                  Human review and rights check
                                                            |
                                       Google OAuth youtube.upload ---> Private upload
```

## Trust boundaries

- Treat all YouTube metadata, titles, and subtitle content as untrusted text.
- The CLI accepts only official YouTube URL hostnames for metadata inspection.
- Never execute video titles, AI-supplied strings, or subtitles as shell commands.
- Never send arbitrary YouTube content to a media downloader. Obtain authorized source files separately.
- FFmpeg uses file-only protocols, command argument arrays, no shell, and no automatic overwrites.
- Upload requires explicit human confirmation and remains private.
- Credentials must be stored outside the repository; this prototype does not persist Google OAuth tokens.

## Production hardening roadmap

- Move media processing into a sandbox with CPU, memory, disk and time limits.
- Add locally installable transcription and caption overlays (not included yet).
- Add source-permission and original-commentary checklists.
- Build a UI with secure local file selection instead of free-text system paths.
- Add mock OAuth and YouTube API tests.
- Add dependency integrity files, SBOM and automated security CI.

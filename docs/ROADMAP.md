# ClipDistrict Studio roadmap

## v0.1 — published CLI baseline
- [x] Official YouTube Data API GTA 6 video and live-stream metadata search
- [x] Strict YouTube link parsing and metadata inspection
- [x] Highlight candidates from local SRT (keyword heuristics, **not** AI)
- [x] Local FFmpeg 1080x1920 cropping and MP4 export
- [x] Optional private-only upload using Google OAuth
- [x] Unit tests covering parsing and dangerous input
- [ ] Real-world YouTube API/OAuth integration verification

## v0.2 — next milestone
- [ ] React user interface for discovery and clip review
- [ ] Local video preview and approved source-file mapping
- [ ] Local Whisper speech transcription (user-managed model installation)
- [ ] Subtitle overlay and export job progress
- [ ] Source-rights and permissions registry

## v0.3 — later
- [ ] AI-assisted highlight evaluation
- [ ] Smart crop and face tracking
- [ ] Batch clip approval
- [ ] Signed Windows builds, pinned dependencies, CI security scanning

## Non-goals
- Google/YouTube session cookie harvesting
- Unauthorized download or reupload of streamer footage
- Automatic public publishing without deliberate user approval

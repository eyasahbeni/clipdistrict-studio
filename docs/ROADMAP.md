# Roadmap

## v1.0 — Local browser studio (implemented)
- YouTube official API public metadata search and official embedded video preview
- Local video import (up to 2 GB), range-enabled playback, internal file IDs
- SRT import, simple GTA-related highlight suggestions, optional local faster-whisper transcription
- 9:16 MP4 exports with FFmpeg; two subtitle styles
- Async background jobs and results/download view
- Optional OAuth private upload, manual confirmation
- Simple Windows batch starter, no UI dependencies, basic security and tests

## Pending before calling this a production application
- Live end-to-end Google OAuth search/upload verification with real credentials
- Strong OS-level process sandboxing for untrusted videos and model loaders
- Advanced tracking-based reframing and AI highlight ranking
- Editable caption timeline, trim handles, drag and drop multiple clips
- Signed Windows desktop installer and reproducible pinned dependency builds
- User review and accessibility testing on real Windows PCs

## Non-goals
- Harvesting Google session cookies
- Circumventing YouTube protections or downloading third-party streams without required permissions and approvals
- Blind automatic public publishing or mass reuploads of minimally altered third-party videos

# ClipDistrict Studio roadmap

## v1.0 — local studio (this release)
- [x] Web app (local, `start.bat`) with live 9:16 preview
- [x] Link import with yt-dlp (YouTube, Twitch, Kick…), optional section only
- [x] File import + optional SRT
- [x] Local Whisper transcription with word timings
- [x] Moment scoring: hype words, loud reactions, talking speed — each with reasons
- [x] 7 animated caption themes, 3 layouts, hook title, credit, progress bar, loudness boost
- [x] Batch render, title ideas, auto description with credit
- [x] YouTube upload (private / unlisted / public) with saved sign-in
- [x] CI installs FFmpeg and runs the full test suite

## v1.1
- [x] Your own keywords with points + search inside a stream
- [x] 16 caption themes (box, glow, karaoke, reveal, one-word, tilt)
- [x] Autopilot, watchlist of creators, several channels
- [x] Cleanup: delete sources after autopilot / after N days, temp files
- [x] Clips start on the first word (no dead air)

## Next
- [ ] Auto face tracking for the facecam layout
- [ ] Optional AI (Claude / OpenAI key) for better titles and moment picking
- [ ] Scheduled uploads
- [ ] Packaged Windows installer (.exe)

## Non-goals
- Google/YouTube session cookie harvesting
- Clipping creators who haven't allowed it

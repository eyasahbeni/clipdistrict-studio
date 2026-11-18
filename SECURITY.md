# Security policy

**Experimental prototype. Not certified safe for production use.**

Do not run as Administrator, disclose browser cookies, or process unknown video files outside a sandbox. Install a trusted, current FFmpeg build separately.

## Security properties intended in v0.1

- No browser cookie export, credential scraping, telemetry or silent auto-updates.
- Read-only discovery through the official YouTube Data API; no YouTube stream downloads.
- Local FFmpeg/ffprobe run through argument arrays, not shell injection-prone strings.
- FFmpeg uses a file-only protocol whitelist and refuses to overwrite existing exports.
- Explicit upload rights acknowledgement, typed confirmation, upload-only Google OAuth scope, private uploads only.
- OAuth tokens are not intentionally written to disk by the CLI.

## Remaining risks

- Untrusted media could exploit FFmpeg vulnerabilities. Isolate decoding for production.
- Current dependencies are version-bounded but not hash-pinned or independently audited.
- No signed Windows builds, sandboxed desktop GUI, SBOM or release provenance yet.
- Upload integration has not been tested with a real Google account.
- The prototype CLI does not enforce per-folder capability restrictions; local users control input/output paths.
- Secure disclosure: use GitHub private vulnerability reporting if configured by repository owner.

Do not put OAuth client JSON, credentials, cookies, videos, or transcripts into the repository.

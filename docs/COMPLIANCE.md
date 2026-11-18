# YouTube media sourcing and creator permissions

YouTube discovery and metadata inspection use the official YouTube Data API. That API does not offer a general-purpose download method for other creators' YouTube videos.

YouTube API Services Developer Policies restrict downloading, caching, or storing audiovisual content without authorization from YouTube. Link import uses yt-dlp, which is separate from the official API key and still goes against YouTube's Terms of Service even when the creator allows clipping. Only import streams whose creator allows clipping (public clip policy or a clipping program), keep proof, and prefer files the creator shares directly when available.

Before publishing:

1. Confirm rights to video and audio, including embedded third-party music.
2. Check platform-specific obligations and any creator agreement.
3. Add meaningful original value and truthful title/description.
4. Attribute the source appropriately.
5. Review the final video before uploading. Uploads default to private.

Even authorized footage can fail YouTube's reused-content monetization standards if insufficiently transformed.

Sources:
- https://developers.google.com/youtube/terms/developer-policies
- https://support.google.com/youtube/answer/1311392

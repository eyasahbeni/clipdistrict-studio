"""Command-line entry point; does not do anything on import."""
import argparse
import json
import sys
from . import __version__
from .youtube import YouTubeError, inspect, search
from .media import MediaError, export_short, parse_time
from .highlights import suggest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipdistrict", description="GTA 6 YouTube discovery + local Shorts editor + private upload"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    find = commands.add_parser("search", help="Discover GTA 6 YouTube videos using official API")
    find.add_argument("--query", default="GTA 6")
    find.add_argument("--live", action="store_true", help="Only current livestreams")
    find.add_argument("--limit", type=int, default=10)

    info = commands.add_parser("inspect", help="Preview YouTube URL metadata (no download)")
    info.add_argument("url")

    high = commands.add_parser("suggest", help="Find promising ranges in local SRT subtitles")
    high.add_argument("srt")
    high.add_argument("--length", type=int, default=30)
    high.add_argument("--limit", type=int, default=3)

    clip = commands.add_parser("clip", help="Convert authorized LOCAL video into a 9:16 MP4")
    clip.add_argument("video")
    clip.add_argument("--start", required=True)
    clip.add_argument("--duration", type=float, default=30)
    clip.add_argument("--name", default="short-01.mp4")
    clip.add_argument("--output-dir", default="exports")

    publish = commands.add_parser("upload", help="Upload approved local MP4 to YouTube PRIVATE")
    publish.add_argument("video")
    publish.add_argument("--oauth-client", required=True)
    publish.add_argument("--title", required=True)
    publish.add_argument("--description", default="")
    publish.add_argument("--audience", choices=["not-made-for-kids", "made-for-kids"], required=True)
    publish.add_argument("--rights-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "search":
            result = search(args.query, live=args.live, limit=args.limit)
        elif args.command == "inspect":
            result = inspect(args.url)
        elif args.command == "suggest":
            result = suggest(args.srt, length=args.length, limit=args.limit)
        elif args.command == "clip":
            output = export_short(args.video, parse_time(args.start), args.duration,
                                  args.name, args.output_dir)
            result = {"output": str(output), "status": "rendered", "upload_status": "not uploaded"}
        elif args.command == "upload":
            if not args.rights_confirmed:
                raise ValueError("Add --rights-confirmed after verifying rights and permission to publish")
            print(f"Upload PRIVATE to the channel selected in Google sign-in?\nFile: {args.video}\nTitle: {args.title}")
            if input("Type UPLOAD to proceed: ").strip() != "UPLOAD":
                print("Cancelled; no upload performed")
                return 0
            from .uploader import upload_private_video
            result = {
                "studio_edit_url": upload_private_video(
                    args.video, args.oauth_client,
                    args.title, args.description, args.audience == "made-for-kids"
                )
            }
        else:
            raise ValueError("Unknown command")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, FileNotFoundError, MediaError, YouTubeError, RuntimeError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Turn a moment of the source video into a finished 1080x1920 Short."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .captions import THEMES, W, H, build_ass
from .config import FONTS_DIR, ffmpeg_bin, ffmpeg_has_captions, gpu_encoder

LAYOUTS = {
    "auto": "Auto (facecam if found)",
    "blur": "Full frame + blurred background",
    "crop": "Fill screen (crop)",
    "split": "Facecam top + gameplay bottom",
}
CAM_CORNERS = {"top-left", "top-right", "bottom-left", "bottom-right"}


def _f(value, low, high, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def video_filter(style: dict) -> str:
    layout = style.get("layout", "blur")
    focus = _f(style.get("focus_x"), 0, 1, 0.5)
    zoom = _f(style.get("zoom"), 1, 2, 1.0)

    if layout == "crop":
        return (f"[0:v]scale=-2:{H},crop={W}:{H}:(iw-{W})*{focus:.3f}:0,setsar=1[base]")

    if layout == "split":
        top_h, bottom_h = 720, H - 720
        box = style.get("cam_box")
        if isinstance(box, dict) and all(k in box for k in "xywh"):
            bx, by = _f(box["x"], 0, 0.99, 0), _f(box["y"], 0, 0.99, 0)
            bw, bh = _f(box["w"], 0.01, 1 - bx, 0.3), _f(box["h"], 0.01, 1 - by, 0.3)
            cam = (f"[c]crop=iw*{bw:.4f}:ih*{bh:.4f}:iw*{bx:.4f}:ih*{by:.4f},"
                   f"scale={W}:{top_h}:force_original_aspect_ratio=increase,crop={W}:{top_h},setsar=1[cam]")
        else:  # manual corner fallback
            corner = style.get("cam_corner", "top-right")
            corner = corner if corner in CAM_CORNERS else "top-right"
            size = _f(style.get("cam_size"), 0.15, 0.6, 0.3)
            cam_x = "0" if "left" in corner else f"iw-iw*{size:.3f}"
            cam_y = "0" if "top" in corner else f"ih-iw*{size:.3f}*{top_h / W:.4f}"
            cam = (f"[c]crop=iw*{size:.3f}:iw*{size:.3f}*{top_h / W:.4f}:{cam_x}:{cam_y},"
                   f"scale={W}:{top_h},setsar=1[cam]")
        game = (f"[g]scale=-2:{bottom_h},crop={W}:{bottom_h}:(iw-{W})*{focus:.3f}:0,setsar=1[game]")
        order = "[game][cam]" if style.get("cam_position") == "bottom" else "[cam][game]"
        line_y = bottom_h - 3 if style.get("cam_position") == "bottom" else top_h - 3
        return (f"[0:v]split=2[c][g];{cam};{game};"
                f"{order}vstack=inputs=2,drawbox=x=0:y={line_y}:w={W}:h=6:color=black@0.9:t=fill[base]")

    # blur (default): whole frame in the middle, blurred copy behind it
    fg_w = int(W * zoom) // 2 * 2
    return (f"[0:v]split=2[bgsrc][fgsrc];"
            f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma=28,eq=brightness=-0.08:saturation=1.25[bg];"
            f"[fgsrc]scale={fg_w}:-2,crop=min(iw\\,{W}):ih:(iw-min(iw\\,{W}))*{focus:.3f}:0,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2-60[base]")


def video_codec(style: dict) -> list[str]:
    if gpu_encoder() and not style.get("preset"):
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", style.get("preset", "veryfast"), "-crf", "20"]


def render(source: Path, output: Path, start: float, end: float, words: list[dict],
           style: dict, *, on_progress=None) -> Path:
    source, output = Path(source).resolve(), Path(output).resolve()
    duration = end - start
    if not 1 <= duration <= 180:
        raise ValueError("Clip must be between 1 and 180 seconds")
    theme = THEMES.get(style.get("theme", ""), THEMES["vice-city"])

    with tempfile.TemporaryDirectory(prefix="clipdistrict-") as tmp:
        work = Path(tmp)
        (work / "captions.ass").write_text(build_ass(words, start, end, style), encoding="utf-8")
        shutil.copytree(FONTS_DIR, work / "fonts")

        graph = video_filter(style)
        if not ffmpeg_has_captions():
            raise RuntimeError("Your FFmpeg can't draw captions. Run start.bat again so it installs the full FFmpeg.")
        graph += ";[base]ass=captions.ass:fontsdir=fonts[capped]"
        inputs = ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source)]
        if style.get("show_progress", True):
            bar = theme["accent"].lstrip("#")
            inputs += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", f"color=c=0x{bar}:s={W}x12:r=30"]
            graph += f";[capped][1:v]overlay=x='-w+w*t/{duration:.3f}':y={H - 12}:eval=frame:shortest=1[out]"
        else:
            graph += ";[capped]null[out]"

        audio = ["-map", "0:a?", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
        if style.get("normalize_audio", True):
            audio = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] + audio

        tmp_out = work / "out.mp4"
        cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
               "-progress", "pipe:1", *inputs,
               "-filter_complex", graph, "-map", "[out]", *audio,
               *video_codec(style),
               "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p", "-r", "30",
               "-movflags", "+faststart", "-t", f"{duration:.3f}", str(tmp_out)]
        proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            if on_progress and line.startswith("out_time_us="):
                try:
                    done = int(line.split("=")[1]) / 1e6
                    on_progress(min(0.99, done / duration), f"Rendering {done:.0f}/{duration:.0f}s")
                except ValueError:
                    pass
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RuntimeError("FFmpeg failed: " + err[-600:])
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), output)
    return output


def thumbnail(source: Path, at: float, output: Path) -> Path:
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{at:.2f}",
           "-i", str(source), "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(output)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return output

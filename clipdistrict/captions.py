"""Animated word-by-word caption themes, written as ASS subtitles and burned in by FFmpeg."""
from __future__ import annotations

import re

W, H = 1080, 1920

# Colors are normal web hex (#RRGGBB). "shadow" is the glow/drop colour behind the text.
THEMES: dict[str, dict] = {
    "vice-city": {
        "label": "Vice City", "font": "Anton", "size": 104, "text": "#FFFFFF", "active": "#FF2E88",
        "outline": "#2B0A3D", "outline_w": 7, "shadow": "#00E5FF", "shadow_d": 6,
        "upper": True, "words": 3, "pop": 112, "accent": "#FF2E88", "accent_text": "#FFFFFF",
    },
    "hype-yellow": {
        "label": "Hype Yellow", "font": "Anton", "size": 108, "text": "#FFFFFF", "active": "#FFE600",
        "outline": "#000000", "outline_w": 8, "shadow": "#000000", "shadow_d": 4,
        "upper": True, "words": 3, "pop": 115, "accent": "#FFE600", "accent_text": "#000000",
    },
    "wanted": {
        "label": "Wanted Level", "font": "Anton", "size": 104, "text": "#FFFFFF", "active": "#FF2A2A",
        "outline": "#000000", "outline_w": 8, "shadow": "#5A0000", "shadow_d": 5,
        "upper": True, "words": 2, "pop": 118, "accent": "#FF2A2A", "accent_text": "#FFFFFF",
    },
    "neon-green": {
        "label": "Neon Money", "font": "Archivo Black", "size": 84, "text": "#FFFFFF", "active": "#39FF14",
        "outline": "#000000", "outline_w": 7, "shadow": "#0B3D00", "shadow_d": 5,
        "upper": True, "words": 3, "pop": 112, "accent": "#39FF14", "accent_text": "#000000",
    },
    "sunset": {
        "label": "Leonida Sunset", "font": "Archivo Black", "size": 84, "text": "#FFF4E0", "active": "#FF8A00",
        "outline": "#3A0D2E", "outline_w": 7, "shadow": "#FF2E88", "shadow_d": 5,
        "upper": True, "words": 3, "pop": 110, "accent": "#FF8A00", "accent_text": "#1A0B00",
    },
    "ice": {
        "label": "Ice Cold", "font": "Anton", "size": 104, "text": "#FFFFFF", "active": "#7DF9FF",
        "outline": "#00151F", "outline_w": 7, "shadow": "#0077FF", "shadow_d": 5,
        "upper": True, "words": 3, "pop": 112, "accent": "#7DF9FF", "accent_text": "#00151F",
    },
    "clean": {
        "label": "Clean White", "font": "Archivo Black", "size": 76, "text": "#FFFFFF", "active": "#FFFFFF",
        "outline": "#000000", "outline_w": 5, "shadow": "#000000", "shadow_d": 3,
        "upper": False, "words": 4, "pop": 108, "accent": "#FFFFFF", "accent_text": "#000000",
    },
    # ---- styles inspired by popular Shorts editors ------------------------
    "box-pop": {
        "label": "Box Pop", "font": "Anton", "size": 100, "text": "#FFFFFF", "active": "#FFE600",
        "outline": "#000000", "outline_w": 7, "shadow": "#000000", "shadow_d": 4,
        "upper": True, "words": 3, "pop": 108, "accent": "#FFE600", "accent_text": "#000000",
        "mode": "box", "box_text": "#000000",
    },
    "breaking": {
        "label": "Breaking News", "font": "Anton", "size": 98, "text": "#FFFFFF", "active": "#E1121B",
        "outline": "#000000", "outline_w": 6, "shadow": "#000000", "shadow_d": 3,
        "upper": True, "words": 3, "pop": 106, "accent": "#E1121B", "accent_text": "#FFFFFF",
        "mode": "box", "box_text": "#FFFFFF",
    },
    "neon-glow": {
        "label": "Neon Glow", "font": "Archivo Black", "size": 82, "text": "#FFFFFF", "active": "#FFFFFF",
        "outline": "#FF2E88", "outline_w": 5, "shadow": "#FF2E88", "shadow_d": 0,
        "upper": True, "words": 3, "pop": 115, "accent": "#FF2E88", "accent_text": "#FFFFFF",
        "blur": 6, "mode": "highlight",
    },
    "cyber-glow": {
        "label": "Cyber Glow", "font": "Anton", "size": 104, "text": "#E8FFFF", "active": "#00F0FF",
        "outline": "#00A6FF", "outline_w": 5, "shadow": "#00A6FF", "shadow_d": 0,
        "upper": True, "words": 2, "pop": 116, "accent": "#00F0FF", "accent_text": "#001018",
        "blur": 5, "mode": "highlight",
    },
    "karaoke": {
        "label": "Karaoke Fill", "font": "Archivo Black", "size": 80, "text": "#FFFFFF", "active": "#FF8A00",
        "outline": "#000000", "outline_w": 6, "shadow": "#000000", "shadow_d": 3,
        "upper": True, "words": 4, "pop": 104, "accent": "#FF8A00", "accent_text": "#000000",
        "mode": "karaoke",
    },
    "type-reveal": {
        "label": "Type Reveal", "font": "Anton", "size": 104, "text": "#FFFFFF", "active": "#39FF14",
        "outline": "#000000", "outline_w": 8, "shadow": "#000000", "shadow_d": 4,
        "upper": True, "words": 4, "pop": 110, "accent": "#39FF14", "accent_text": "#000000",
        "mode": "reveal",
    },
    "one-word": {
        "label": "One Word Punch", "font": "Anton", "size": 150, "text": "#FFFFFF", "active": "#FFE600",
        "outline": "#000000", "outline_w": 10, "shadow": "#000000", "shadow_d": 6,
        "upper": True, "words": 1, "pop": 108, "accent": "#FFE600", "accent_text": "#000000",
    },
    "hype-tilt": {
        "label": "Hype Tilt", "font": "Anton", "size": 106, "text": "#FFFFFF", "active": "#FF2E88",
        "outline": "#000000", "outline_w": 8, "shadow": "#7A00FF", "shadow_d": 6,
        "upper": True, "words": 3, "pop": 120, "accent": "#7A00FF", "accent_text": "#FFFFFF",
        "tilt": -6,
    },
    "minimal": {
        "label": "Minimal", "font": "Archivo Black", "size": 66, "text": "#FFFFFF", "active": "#FFFFFF",
        "outline": "#000000", "outline_w": 3, "shadow": "#000000", "shadow_d": 2,
        "upper": False, "words": 5, "pop": 100, "accent": "#FFFFFF", "accent_text": "#000000",
        "mode": "reveal",
    },
}

THEME_DEFAULTS = {"mode": "highlight", "blur": 0, "box_text": "#000000", "tilt": 0}
for _t in THEMES.values():
    for _k, _v in THEME_DEFAULTS.items():
        _t.setdefault(_k, _v)

POSITIONS = {"upper": 560, "middle": 1180, "lower": 1430}


def ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR"""
    value = hex_color.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "FFFFFF"
    r, g, b = value[0:2], value[2:4], value[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def theme_list() -> list[dict]:
    return [{"id": key, **value} for key, value in THEMES.items()]


def build_ass(words: list[dict], clip_start: float, clip_end: float, style: dict) -> str:
    theme = THEMES.get(style.get("theme", ""), THEMES["vice-city"])
    upper = style.get("uppercase", theme["upper"])
    per_line = int(style.get("words_per_line") or theme["words"])
    y = POSITIONS.get(style.get("caption_position", "middle"), POSITIONS["middle"])
    size = int(theme["size"] * float(style.get("caption_scale", 1.0)))
    length = clip_end - clip_start

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{theme['font']},{size},{ass_color(theme['text'])},{ass_color(theme['active'])},{ass_color(theme['outline'])},{ass_color(theme['shadow'], 0x20)},0,0,0,0,100,100,1,0,1,{theme['outline_w']},{theme['shadow_d']},5,60,60,0,1
Style: Hook,{theme['font']},{int(size * 0.72)},{ass_color(theme['accent_text'])},{ass_color(theme['accent_text'])},{ass_color(theme['accent'])},{ass_color('#000000', 0x60)},0,0,0,0,100,100,1,0,3,18,0,8,70,70,190,1
Style: Tag,Archivo Black,40,{ass_color('#FFFFFF', 0x30)},{ass_color('#FFFFFF')},{ass_color('#000000', 0x40)},{ass_color('#000000', 0x80)},0,0,0,0,100,100,1,0,1,3,1,2,40,40,70,1
Style: Credit,Archivo Black,30,{ass_color('#FFFFFF', 0x40)},{ass_color('#FFFFFF')},{ass_color('#000000', 0x40)},{ass_color('#000000', 0x80)},0,0,0,0,100,100,0,0,1,2,1,8,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []

    # --- word-by-word captions -------------------------------------------------
    if style.get("captions", True) and words:
        local = []
        for w in words:
            a, b = w["start"] - clip_start, w["end"] - clip_start
            if b <= 0 or a >= length:
                continue
            text = _clean(w["word"]).strip()
            if not text:
                continue
            local.append({"start": max(0.0, a), "end": min(length, b), "word": text.upper() if upper else text})

        chunks: list[list[dict]] = []
        for w in local:
            gap = chunks and w["start"] - chunks[-1][-1]["end"] > 0.6
            ends_sentence = chunks and re.search(r"[.!?]$", chunks[-1][-1]["word"])
            if not chunks or len(chunks[-1]) >= per_line or gap or ends_sentence:
                chunks.append([])
            chunks[-1].append(w)

        pop = int(theme["pop"])
        mode = theme["mode"]
        active = ass_color(theme["active"])
        blur = r"\blur" + str(theme["blur"]) if theme["blur"] else ""
        tilt = r"\frz" + str(theme["tilt"]) if theme["tilt"] else ""
        hidden = r"{\alpha&HFF&}"
        for c_i, chunk in enumerate(chunks):
            chunk_end = chunk[-1]["end"] + 0.25
            if c_i + 1 < len(chunks):
                chunk_end = min(chunk_end, chunks[c_i + 1][0]["start"])
            for i, w in enumerate(chunk):
                a = w["start"] if i else chunk[0]["start"]
                b = chunk[i + 1]["start"] if i + 1 < len(chunk) else chunk_end
                if b - a < 0.04:
                    continue
                parts = []
                for j, other in enumerate(chunk):
                    word = other["word"]
                    if j == i:
                        if mode == "box":
                            tag = (r"\c" + ass_color(theme["box_text"]) + r"\3c" + active
                                   + r"\bord" + str(max(10, theme["outline_w"] * 2)) + r"\shad0")
                        else:
                            tag = r"\c" + active
                        parts.append("{" + tag + r"\fscx" + str(pop) + r"\fscy" + str(pop) + tilt + "}"
                                     + word + r"{\r}" + ("{" + blur + "}" if blur else ""))
                    elif j > i and mode == "reveal":
                        parts.append(hidden + word + r"{\r}" + ("{" + blur + "}" if blur else ""))
                    elif j < i and mode == "karaoke":
                        parts.append(r"{\c" + active + "}" + word + r"{\r}" + ("{" + blur + "}" if blur else ""))
                    else:
                        parts.append(word)
                intro = r"{\fad(60,0)\t(0,90,\fscx106\fscy106)\t(90,160,\fscx100\fscy100)}" if i == 0 else ""
                lines.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Cap,,0,0,0,,"
                             + r"{\an5\pos(540," + str(y) + ")" + blur + "}" + intro + " ".join(parts))

    # --- hook title on top --------------------------------------------------
    hook = _clean(style.get("hook", "")).strip()
    if style.get("show_hook", True) and hook:
        hook_len = float(style.get("hook_seconds", 3.5))
        end = length if hook_len <= 0 else min(length, hook_len)
        hook_text = hook.upper() if upper else hook
        seam = r"\an5\pos(540,960)" if style.get("layout") == "split" else ""   # between face and gameplay
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(end)},Hook,,0,0,0,,"
                     + r"{" + seam + r"\fad(120,200)\t(0,140,\fscx104\fscy104)\t(140,240,\fscx100\fscy100)}" + hook_text)

    # --- channel tag + credit -----------------------------------------------
    tag = _clean(style.get("watermark", "")).strip()
    if tag:
        lines.append(f"Dialogue: 0,{_ts(0)},{_ts(length)},Tag,,0,0,0,,{tag}")
    credit = _clean(style.get("credit", "")).strip()
    if credit:
        lines.append(f"Dialogue: 0,{_ts(0)},{_ts(length)},Credit,,0,0,0,,{credit}")

    return head + "\n".join(lines) + "\n"

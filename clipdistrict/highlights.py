"""Explainable transcript keyword scoring baseline, not artificial intelligence."""
from __future__ import annotations
import re
from pathlib import Path

CUE_RE = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d{3})\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d{3})")
SIGNALS = {
    "gta 6": 5, "gta vi": 5, "vice city": 4, "leonida": 4,
    "no way": 3, "oh my god": 3, "what just happened": 4,
    "insane": 2, "crazy": 2, "clutch": 3, "police": 2,
    "chase": 2, "first time": 2, "unbelievable": 3,
}


def _stamp(groups: tuple[str, str, str, str]) -> float:
    h, m, s, ms = (int(x) for x in groups)
    if m >= 60 or s >= 60:
        raise ValueError("Invalid SRT timestamp")
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    entries = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        match = CUE_RE.search(block)
        if not match:
            continue
        start = _stamp(match.groups()[:4])
        end = _stamp(match.groups()[4:])
        if end <= start:
            continue
        phrase = block[match.end():].replace("\n", " ").strip()[:1200]
        entries.append((start, end, phrase))
    return sorted(entries, key=lambda x: x[0])


def suggest(srt: str | Path, *, length: int = 30, limit: int = 3) -> list[dict]:
    if not 10 <= length <= 120 or not 1 <= limit <= 20:
        raise ValueError("length must be 10–120s and limit 1–20")
    path = Path(srt).expanduser()
    if path.is_symlink() or path.suffix.lower() != ".srt" or not path.is_file() or path.stat().st_size > 4_000_000:
        raise ValueError("Provide a local SRT subtitle file under 4 MB (no symlinks)")
    cues = parse_srt(path.read_text(encoding="utf-8-sig"))
    ranked = []
    for start, end, line in cues:
        if not line:
            continue
        window_start = max(0.0, start - 4)
        window_end = window_start + length
        matched = [(a, b, msg) for a, b, msg in cues if a < window_end and b > window_start]
        words = " ".join(m.lower() for _, _, m in matched)
        score = sum(weight for keyword, weight in SIGNALS.items() if keyword in words)
        score += min(words.count("!"), 4)
        if score:
            ranked.append({
                "start": round(window_start, 2), "duration": length,
                "score": score, "preview": line[:140],
                "why": "Keyword and emphasis heuristic; human review required",
            })
    picked = []
    for item in sorted(ranked, key=lambda x: (-x["score"], x["start"])):
        if all(abs(item["start"] - prev["start"]) >= length for prev in picked):
            picked.append(item)
        if len(picked) == limit:
            break
    return sorted(picked, key=lambda x: x["start"])

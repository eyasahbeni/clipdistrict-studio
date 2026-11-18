"""Find the best moments in a stream: hype words + loud reactions + fast talking.

Free and fully local. Every suggestion says *why* it was picked so you can judge it.
"""
from __future__ import annotations

import bisect
import re
import subprocess
import uuid
from pathlib import Path

import numpy as np

from .config import ffmpeg_bin

HYPE = {
    # GTA 6 topic words
    "gta 6": 4, "gta six": 4, "gta vi": 4, "vice city": 4, "leonida": 3, "lucia": 3, "jason": 2,
    "rockstar": 2, "trailer": 2, "map": 1, "heist": 3, "wanted": 2, "five star": 3, "5 star": 3,
    # reactions
    "no way": 4, "oh my god": 4, "omg": 3, "what the": 3, "what just happened": 5, "let's go": 4,
    "lets go": 4, "bro": 1, "yo": 1, "insane": 3, "crazy": 3, "clutch": 3, "unbelievable": 4,
    "i can't believe": 4, "are you serious": 4, "look at this": 2, "watch this": 3, "run": 2,
    "chase": 3, "cops": 2, "police": 2, "crash": 3, "dead": 2, "killed": 2, "help": 2,
    "funny": 2, "hilarious": 3, "wait": 1, "stop": 1, "speed": 1, "screaming": 3, "why": 1,
}
LAUGH_RE = re.compile(r"\b(ha){2,}|\blol\b|\blmao\b", re.I)


def loudness_curve(video: Path, step: float = 0.5, rate: int = 8000) -> np.ndarray:
    """Loudness (dB) for every `step` seconds of audio."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(video),
           "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]
    hop = int(rate * step)
    values: list[float] = []
    leftover = np.zeros(0, dtype=np.float32)
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        while True:
            chunk = proc.stdout.read(hop * 2 * 240)
            if not chunk:
                break
            data = np.concatenate([leftover, np.frombuffer(chunk, dtype=np.int16).astype(np.float32)])
            usable = len(data) // hop * hop
            if usable:
                blocks = data[:usable].reshape(-1, hop) / 32768.0
                rms = np.sqrt(np.mean(blocks ** 2, axis=1)) + 1e-6
                values.extend((20 * np.log10(rms)).tolist())
            leftover = data[usable:]
    return np.array(values, dtype=np.float32)


def parse_keywords(text: str) -> dict[str, float]:
    """'police chase:5, speed, lucia:3' -> {'police chase': 5, 'speed': 4, 'lucia': 3}"""
    result: dict[str, float] = {}
    for part in re.split(r"[,\n]+", text or ""):
        part = part.strip().lower()
        if not part:
            continue
        word, _, weight = part.partition(":")
        word = re.sub(r"[^\w\s']", " ", word).strip()
        word = re.sub(r"\s+", " ", word)
        try:
            value = float(weight) if weight.strip() else 4.0
        except ValueError:
            value = 4.0
        if word:
            result[word] = max(0.5, min(10.0, value))
    return result


def _norm(text: str) -> str:
    return " " + re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", text.lower())) + " "


def _text_score(text: str, extra: dict[str, float] | None = None) -> tuple[float, list[str]]:
    low = _norm(text)
    score, hits = 0.0, []
    table = {**HYPE, **(extra or {})}
    for phrase, weight in table.items():
        count = low.count(" " + phrase + " ")
        if count:
            score += weight * min(count, 3)
            hits.append(phrase)
    laughs = len(LAUGH_RE.findall(text))
    score += min(laughs, 3) * 2
    score += min(text.count("!"), 4)
    return score, hits


def find_moments(transcript: dict, loudness: np.ndarray | None, duration: float, *,
                 length: float = 35, count: int = 6, step: float = 0.5,
                 keywords: dict[str, float] | None = None) -> list[dict]:
    length = float(max(10, min(90, length)))
    segments = transcript.get("segments", [])
    words = sorted((w for s in segments for w in s.get("words", [])), key=lambda w: w["start"])
    starts = [w["start"] for w in words]

    def text_between(a: float, b: float) -> str:
        return " ".join(w["word"] for w in words[bisect.bisect_left(starts, a):bisect.bisect_left(starts, b)])

    # loudness z-score so it works for quiet and loud streamers alike
    if loudness is not None and len(loudness) > 10:
        voiced = loudness[loudness > -60]
        base = float(np.median(voiced)) if len(voiced) else -30.0
        spread = float(np.std(voiced)) + 1e-3 if len(voiced) else 6.0
        z = (loudness - base) / spread
    else:
        z = None

    stride = 2.0
    candidates = []
    t = 0.0
    while t + min(length, duration) <= duration + 0.01:
        end = min(duration, t + length)
        text = text_between(t, end)
        text_score, hits = _text_score(text, keywords)
        reasons = []
        if hits:
            mine = [h for h in hits if keywords and h in keywords]
            if mine:
                reasons.append("your keywords: " + ", ".join(f'"{h}"' for h in mine[:4]))
            other = [h for h in hits if h not in mine]
            if other:
                reasons.append("says: " + ", ".join(f'"{h}"' for h in other[:4]))
        density = len(text.split()) / max(1.0, end - t)          # words per second
        score = text_score + min(density, 4) * 1.5
        if density > 2.6:
            reasons.append("fast, excited talking")
        if z is not None:
            a, b = int(t / step), int(end / step)
            window = z[a:b]
            if len(window):
                peak = float(np.percentile(window, 95))
                loud_share = float(np.mean(window > 1.5))
                score += max(0.0, peak) * 3 + loud_share * 12
                if peak > 2.0:
                    reasons.append("loud reaction / screaming")
                if float(np.mean(window < -1.8)) > 0.5:
                    score -= 6  # mostly silence
        if not words:
            reasons.append("audio-only pick (no transcript)")
        candidates.append({"start": t, "end": end, "score": score, "reasons": reasons, "text": text})
        t += stride

    candidates.sort(key=lambda c: -c["score"])
    picked: list[dict] = []
    for c in candidates:
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= count:
            break

    top = max((c["score"] for c in picked), default=1) or 1
    result = []
    for c in sorted(picked, key=lambda c: c["start"]):
        start, end = _snap(c["start"], c["end"], segments, duration)
        start, end = _trim_silence(start, end, words, starts, duration)
        text = text_between(start, end)
        result.append({
            "id": uuid.uuid4().hex[:8],
            "start": round(start, 2), "end": round(end, 2),
            "score": round(100 * c["score"] / top),
            "reasons": c["reasons"] or ["steady talking segment"],
            "hook": hook_line(text),
            "titles": title_ideas(text),
            "transcript": text[:600],
        })
    return result


def _trim_silence(start: float, end: float, words: list[dict], starts: list[float],
                  duration: float) -> tuple[float, float]:
    """Start right before the first word so the Short doesn't open on dead air (keeps the length)."""
    i = bisect.bisect_left(starts, start)
    if i < len(words) and words[i]["start"] < end and words[i]["start"] - start > 1.2:
        shift = words[i]["start"] - 0.3 - start
        start += shift
        end = min(duration, end + shift)
    return start, end


def _snap(start: float, end: float, segments: list[dict], duration: float) -> tuple[float, float]:
    """Start on a sentence start and end on a sentence end so clips don't cut mid-word."""
    starts = [s["start"] for s in segments if start - 4 <= s["start"] <= start + 2]
    ends = [s["end"] for s in segments if end - 3 <= s["end"] <= end + 4]
    new_start = min(starts, key=lambda x: abs(x - start)) if starts else start
    new_end = min(ends, key=lambda x: abs(x - end)) if ends else end
    new_start = max(0.0, new_start - 0.15)
    new_end = min(duration, new_end + 0.35)
    if new_end - new_start < 8:
        new_end = min(duration, new_start + 8)
    return new_start, new_end


def hook_line(text: str) -> str:
    """Short top-of-video hook taken from the most hyped sentence."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip().split()) >= 2]
    if not sentences:
        return "GTA 6 IS INSANE"
    best = max(sentences, key=lambda s: _text_score(s)[0] + min(len(s.split()), 8) * 0.1)
    words = best.split()[:7]
    while len(words) > 2 and words[-1].lower() in {"gta", "the", "a", "and", "to", "of", "in", "this", "is"}:
        words.pop()
    return re.sub(r"[.,;:]+$", "", " ".join(words)).upper()


def title_ideas(text: str) -> list[str]:
    _, hits = _text_score(text)
    hook = hook_line(text).title()
    ideas = []
    if hook:
        ideas.append(f"{hook} 😳 #GTA6")
    if any(h in hits for h in ("chase", "cops", "police", "wanted", "five star", "5 star")):
        ideas.append("This GTA 6 police chase got out of hand 🚔")
    if any(h in hits for h in ("vice city", "leonida", "map")):
        ideas.append("Vice City in GTA 6 looks unreal 🌴")
    if any(h in hits for h in ("funny", "hilarious")) or LAUGH_RE.search(text):
        ideas.append("I can't stop laughing at this GTA 6 moment 😂")
    ideas.append("Streamer's craziest GTA 6 reaction 🔥")
    ideas.append("Wait for it… GTA 6 moment 👀")
    seen, unique = set(), []
    for idea in ideas:
        if idea not in seen:
            seen.add(idea)
            unique.append(idea[:100])
    return unique[:4]


def search_transcript(transcript: dict, query: str, duration: float, *, before: float = 8,
                      after: float = 22, limit: int = 40) -> list[dict]:
    """Find every time a phrase is said. Several phrases: separate with commas."""
    terms = [t for t in (_norm(q).strip() for q in query.split(",")) if t]
    if not terms:
        return []
    words = sorted((w for s in transcript.get("segments", []) for w in s.get("words", [])),
                   key=lambda w: w["start"])
    tokens = [_norm(w["word"]).strip() for w in words]
    hits = []
    for term in terms:
        parts = term.split()
        for i in range(len(tokens) - len(parts) + 1):
            if all(tokens[i + k] == parts[k] or (k == len(parts) - 1 and tokens[i + k].startswith(parts[k]))
                   for k in range(len(parts))):
                t = words[i]["start"]
                if hits and abs(hits[-1]["at"] - t) < 4 and hits[-1]["term"] == term:
                    continue
                a, b = max(0.0, t - before), min(duration, t + after)
                context = " ".join(w["word"] for w in words if a + 4 <= w["start"] <= t + 8)
                hits.append({"term": term, "at": round(t, 2), "start": round(a, 2), "end": round(b, 2),
                             "context": context[:220]})
    hits.sort(key=lambda h: h["at"])
    return hits[:limit]

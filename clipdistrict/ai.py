"""Optional AI moment picking with Google Gemini (free tier via Google AI Studio).

Set GEMINI_API_KEY (or GOOGLE_API_KEY, which Colab's "Gemini API keys" creates), or save it in Settings.
Without a key the app uses its free rule-based picker instead.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from .config import SECRETS_DIR

API = "https://generativelanguage.googleapis.com/v1beta"
KEY_FILE = SECRETS_DIR / "gemini_api_key.txt"
DEFAULT_MODEL = "gemini-flash-latest"
_model_cache: dict[str, str] = {}


def api_key() -> str:
    if KEY_FILE.is_file():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def save_key(key: str) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key.strip(), encoding="utf-8")


def _post(model: str, body: dict, key: str) -> dict:
    req = urllib.request.Request(f"{API}/models/{model}:generateContent", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def _pick_model(key: str) -> str:
    """Use the 'latest Flash' alias; if Google renamed things, take any available Flash model."""
    if key in _model_cache:
        return _model_cache[key]
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    try:
        req = urllib.request.Request(f"{API}/models?pageSize=200", headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=30) as resp:
            names = [m["name"].split("/", 1)[1] for m in json.loads(resp.read().decode()).get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
        if model not in names:
            flash = [n for n in names if "flash" in n and "lite" not in n and "tts" not in n
                     and "image" not in n and "live" not in n and "audio" not in n]
            if flash:
                model = sorted(flash)[-1]
    except Exception:
        pass
    _model_cache[key] = model
    return model


def _ask(prompt: str, key: str) -> str:
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}}
    model = _pick_model(key)
    try:
        data = _post(model, body, key)
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        if err.code == 400 and "responseMimeType" in detail:
            body.pop("generationConfig")
            data = _post(model, body, key)
        else:
            raise RuntimeError(f"Gemini error {err.code}: {detail}") from None
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def pick_moments(transcript: dict, duration: float, *, count: int, min_len: float, max_len: float,
                 request: str = "", topic: str = "GTA 6") -> list[dict]:
    """Ask Gemini for the most viral, self-contained moments. Returns [] if not possible."""
    key = api_key()
    segments = transcript.get("segments", [])
    if not key or not segments:
        return []
    lines, total = [], 0
    for s in segments:
        line = f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}"
        total += len(line)
        if total > 400_000:          # keep very long streams inside the model's limits
            break
        lines.append(line)
    prompt = f"""You are a viral YouTube Shorts editor for a {topic} clipping channel.
Below is a timestamped transcript (seconds) of a {duration / 60:.1f}-minute video.

Pick the {count} BEST moments to turn into separate Shorts.
Rules:
- Each moment is {min_len:.0f} to {max_len:.0f} seconds long and makes sense on its own.
- It must start right on the hook (a strong line, reaction or question) — no slow intro.
- It ends right after the payoff (punchline, reaction, result) — not mid-sentence.
- Moments must NOT overlap. Prefer big reactions, funny lines, surprises, hype, drama, insane gameplay.
{f'- The creator asked specifically for: "{request}". Prioritise moments that match this.' if request else ''}
Return ONLY JSON: a list of objects with keys
"start" (number, seconds), "end" (number, seconds), "score" (1-100 viral potential),
"title" (catchy YouTube Shorts title, max 70 chars, 1 emoji ok),
"hook" (on-screen hook text, max 6 words, punchy),
"reason" (why it will perform, max 12 words).

Transcript:
""" + "\n".join(lines)
    raw = _ask(prompt, key)
    match = re.search(r"\[.*\]", raw, re.S)
    items = json.loads(match.group(0) if match else raw)
    result = []
    for it in items if isinstance(items, list) else []:
        try:
            start, end = float(it["start"]), float(it["end"])
        except (KeyError, TypeError, ValueError):
            continue
        start, end = max(0.0, start), min(duration, end)
        if end - start < 5:
            continue
        if end - start > max_len + 5:
            end = start + max_len
        result.append({"start": start, "end": end,
                       "score": int(max(1, min(100, float(it.get("score", 70))))),
                       "title": str(it.get("title", ""))[:100], "hook": str(it.get("hook", ""))[:60],
                       "reason": str(it.get("reason", ""))[:120]})
    result.sort(key=lambda m: -m["score"])
    picked = []
    for m in result:
        if all(m["end"] <= p["start"] or m["start"] >= p["end"] for p in picked):
            picked.append(m)
    return sorted(picked[:count], key=lambda m: m["start"])

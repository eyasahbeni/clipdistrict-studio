"""Speech-to-text with word timings, running locally with faster-whisper (free, no API)."""
from __future__ import annotations

import json
from pathlib import Path

from .highlights import parse_srt

_models: dict = {}


def _model(name: str):
    if name not in _models:
        from faster_whisper import WhisperModel
        _models[name] = WhisperModel(name, device="auto", compute_type="int8")
    return _models[name]


def transcribe(video: Path, out: Path, *, model: str = "small", language: str = "",
               duration: float = 0, on_progress=None) -> dict:
    whisper = _model(model)
    segments, info = whisper.transcribe(
        str(video), language=language or None, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
        condition_on_previous_text=False,
    )
    result = {"language": info.language, "segments": []}
    for seg in segments:
        words = [{"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word.strip()}
                 for w in (seg.words or []) if w.word.strip()]
        result["segments"].append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                                   "text": seg.text.strip(), "words": words})
        if on_progress and duration:
            on_progress(min(0.99, seg.end / duration), f"Transcribing {seg.end / 60:.1f} / {duration / 60:.1f} min")
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def from_srt(text: str, out: Path) -> dict:
    """Use an existing subtitle file; word timings are spread evenly inside each line."""
    result = {"language": "", "segments": []}
    for start, end, line in parse_srt(text):
        tokens = line.split()
        step = (end - start) / max(1, len(tokens))
        words = [{"start": round(start + i * step, 2), "end": round(start + (i + 1) * step, 2), "word": t}
                 for i, t in enumerate(tokens)]
        result["segments"].append({"start": start, "end": end, "text": line, "words": words})
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def load(path: Path) -> dict:
    if not path.is_file():
        return {"language": "", "segments": []}
    return json.loads(path.read_text(encoding="utf-8"))


def words_between(transcript: dict, start: float, end: float) -> list[dict]:
    return [w for seg in transcript.get("segments", []) for w in seg.get("words", [])
            if w["end"] > start and w["start"] < end]

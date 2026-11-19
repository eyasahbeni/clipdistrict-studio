"""The whole clipping flow in one place: import → subtitles → moments → render → upload → cleanup.

Used by the web app (manual mode), autopilot and the channel watchlist.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

from . import ai, facecam, importer, jobs, moments, projects, render, transcribe, uploader
from .config import PROJECTS_DIR, WORKSPACE, ensure_dirs, load_settings, save_settings

ACTIVITY_FILE = WORKSPACE / "activity.json"
WATCH_STATE = WORKSPACE / "watch_state.json"
_activity_lock = threading.Lock()


# ------------------------------------------------------------------ activity log
def log(message: str, level: str = "info", project_id: str = "") -> None:
    ensure_dirs()
    with _activity_lock:
        items = activity()
        items.insert(0, {"t": time.time(), "msg": message[:300], "level": level, "project_id": project_id})
        ACTIVITY_FILE.write_text(json.dumps(items[:200], ensure_ascii=False), encoding="utf-8")


def activity() -> list[dict]:
    if ACTIVITY_FILE.is_file():
        try:
            return json.loads(ACTIVITY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    return []


# ------------------------------------------------------------------ analysis
def plan(duration: float, clip_length: float = 0, clips: int = 0) -> dict:
    """How long and how many clips, so short videos still give several different moments."""
    if clip_length and clip_length > 0:
        target = float(clip_length)
    else:
        target = 20.0 if duration < 180 else 30.0 if duration < 900 else 40.0
    target = max(8.0, min(target, duration * 0.5)) if duration >= 16 else max(3.0, duration)
    if clips and clips > 0:
        count = int(clips)
    else:
        count = 2 if duration < 60 else 3 if duration < 300 else 5 if duration < 900 else 8 if duration < 1800 else 10
    count = max(1, min(count, int(duration // max(target, 1)) or 1))
    return {"target": target, "count": count,
            "min": max(5.0, round(target * 0.6)), "max": min(90.0, round(target * 1.6))}


def analyze(pid: str, progress) -> dict:
    meta = projects.load(pid)
    settings = load_settings()
    src = projects.source_path(pid)
    tpath = projects.transcript_path(pid)
    warning = ""
    if not tpath.is_file() and meta.get("has_audio", True):
        projects.update(pid, status="transcribing")
        progress(None, f"Loading subtitle model '{settings['whisper_model']}' "
                       "(first time it downloads: base ≈150 MB, small ≈480 MB)…")
        try:
            transcribe.transcribe(src, tpath, model=settings["whisper_model"], language=settings["language"],
                                  duration=meta["duration"], on_progress=progress)
        except jobs.JobCancelled:
            raise
        except Exception as err:
            print(f"[subtitles] failed: {err!r}", flush=True)
            warning = (f"SUBTITLES_FAILED: Auto-subtitles failed ({str(err)[:200]}). "
                       "No captions, and moments were picked from loudness only.")
    projects.update(pid, status="analyzing")
    sizes = plan(meta["duration"], float(settings["clip_length"] or 0), int(settings["clips_per_video"] or 0))
    transcript = transcribe.load(tpath)
    request = meta.get("request", "")
    found = []
    if ai.api_key() and transcript.get("segments"):
        progress(None, f"AI is picking the {sizes['count']} best moments…")
        try:
            picks = ai.pick_moments(transcript, meta["duration"], count=sizes["count"], min_len=sizes["min"],
                                    max_len=sizes["max"], request=request)
            for m in picks:
                text = " ".join(w["word"] for w in transcribe.words_between(transcript, m["start"], m["end"]))
                found.append({"id": uuid.uuid4().hex[:8], "start": round(m["start"], 2), "end": round(m["end"], 2),
                              "score": m["score"], "reasons": ["AI: " + m["reason"]] if m["reason"] else ["AI pick"],
                              "hook": m["hook"].upper() or moments.hook_line(text),
                              "titles": [t for t in [m["title"]] + moments.title_ideas(text) if t][:4],
                              "transcript": text[:600], "ai": True})
        except Exception as err:
            warning = (warning + " " if warning else "") + f"AI picking failed ({str(err)[:120]}), used the free picker."
    if not found:
        progress(None, "Finding the best moments…")
        loud = moments.loudness_curve(src) if meta.get("has_audio", True) else None
        keywords = moments.parse_keywords(settings["keywords"])
        if request:  # "moments to include" without AI: treat the words as strong keywords
            keywords.update({k: 7.0 for k in moments.parse_keywords(request)})
        found = moments.find_moments(transcript, loud, meta["duration"], length=sizes["target"],
                                     count=sizes["count"], keywords=keywords)
    return projects.update(pid, status="ready", moments=found, error=warning)


def import_job(pid: str, *, url: str = "", start=None, end=None, raw_file: Path | None = None,
               copy_from: Path | None = None, autopilot: bool = False):
    def run(progress):
        try:
            if url:
                projects.update(pid, status="downloading")
                importer.download(pid, url, start, end, on_progress=progress)
            elif copy_from:
                projects.update(pid, status="downloading")
                progress(None, f"Copying {copy_from.name} from your inbox…")
                importer.import_file(copy_from, projects.source_path(pid), start, end)
            elif raw_file:
                progress(None, "Preparing video…")
                importer.normalize(raw_file, projects.source_path(pid))
            meta = importer.finish_import(pid)
            try:
                render.thumbnail(projects.source_path(pid), min(5, meta["duration"] / 2),
                                 projects.project_dir(pid) / "poster.jpg")
            except Exception:
                pass
            meta = analyze(pid, progress)
            log(f"Found {len(meta['moments'])} moments in “{meta['title'][:60]}”", project_id=pid)
        except jobs.JobCancelled:
            raise
        except Exception as err:
            if not projects.project_dir(pid).is_dir():
                raise jobs.JobCancelled() from None   # project was deleted
            msg = str(err)
            if "not a bot" in msg or "Sign in to confirm" in msg:
                msg = ("YouTube blocked this download (bot check on server IPs). Put the video in your "
                       "inbox folder instead, or run the app on your own PC.")
            projects.update(pid, status="error", error=msg[:500])
            log(f"Import failed: {msg[:200]}", "error", pid)
            raise
        if autopilot:
            start_autopilot(pid)
        return {"project": pid}
    return run


def start_import(*, url: str = "", title: str = "", creator: str = "", start=None, end=None,
                 raw_file: Path | None = None, copy_from: Path | None = None, pid: str = "",
                 autopilot: bool = False, permission_note: str = "", request: str = "") -> dict:
    meta = projects.load(pid) if pid else projects.create(title or url, url, creator)
    meta = projects.update(meta["id"], permission_note=permission_note[:300], autopilot=autopilot,
                           request=request.strip()[:300])
    jobs.submit("import", f"Import: {meta['title'][:50]}",
                import_job(meta["id"], url=url, start=start, end=end, raw_file=raw_file, copy_from=copy_from,
                           autopilot=autopilot),
                project_id=meta["id"])
    return meta


# ------------------------------------------------------------------ render + upload
def _set_clip(pid: str, clip_id: str, **changes) -> None:
    with projects._lock:
        meta = projects.load(pid)
        for c in meta["clips"]:
            if c["id"] == clip_id:
                c.update(changes)
        projects.save(meta)


def queue_render(pid: str, start: float, end: float, style: dict, *, moment_id: str = "",
                 title: str = "", titles: list | None = None, then=None) -> dict:
    clip_id = uuid.uuid4().hex[:8]
    clip = {"id": clip_id, "moment_id": moment_id, "start": start, "end": end, "style": style,
            "status": "rendering", "created_at": time.time(), "title": title[:100],
            "titles": titles or [], "upload": None, "error": ""}
    with projects._lock:
        meta = projects.load(pid)
        meta["clips"].append(clip)
        projects.save(meta)

    def run(progress):
        if not projects.source_path(pid).is_file():
            _set_clip(pid, clip_id, status="error", error="Source video was cleaned up")
            raise RuntimeError("Source video was cleaned up")
        words = transcribe.words_between(transcribe.load(projects.transcript_path(pid)), start, end)
        if style.get("layout") in ("auto", "split") and not style.get("cam_box"):
            progress(None, "Finding the facecam…")
            meta = projects.load(pid)
            box = facecam.detect(projects.source_path(pid), start, end, meta.get("width") or 1920,
                                 meta.get("height") or 1080)
            if box:
                style.update(layout="split", cam_box=box)
            elif style.get("layout") == "auto":
                style["layout"] = "blur"
            _set_clip(pid, clip_id, style=style)
        elif style.get("layout") == "auto":
            style["layout"] = "split" if style.get("cam_box") else "blur"
        try:
            render.render(projects.source_path(pid), projects.clip_path(pid, clip_id), start, end, words,
                          style, on_progress=progress)
        except Exception as err:
            _set_clip(pid, clip_id, status="error", error=str(err)[:500])
            raise
        _set_clip(pid, clip_id, status="ready")
        if then:
            then(clip_id)
        return {"clip": clip_id}

    jobs.submit("render", f"Render Short ({end - start:.0f}s)", run, project_id=pid, clip_id=clip_id)
    return clip


def describe(meta: dict, title: str) -> str:
    settings = load_settings()
    credit = ""
    if meta.get("creator"):
        credit = f"🎥 Credit: {meta['creator']}" + (f" — {meta['source_url']}" if meta.get("source_url") else "") + "\n"
    elif meta.get("source_url"):
        credit = f"Source: {meta['source_url']}\n"
    return f"{title}\n\n{credit}Clipped with permission.\n\n{settings['default_hashtags']}"


def queue_upload(pid: str, clip_id: str, *, title: str, description: str, tags: list[str],
                 privacy: str, channel_id: str = "") -> None:
    path = projects.clip_path(pid, clip_id)

    def run(progress):
        _set_clip(pid, clip_id, upload={"state": "uploading"})
        try:
            result = uploader.upload(path, title, description, tags=tags, privacy=privacy,
                                     channel_id=channel_id, on_progress=progress)
        except Exception as err:
            _set_clip(pid, clip_id, upload={"state": "error", "error": str(err)[:400]})
            log(f"Upload failed: {str(err)[:200]}", "error", pid)
            raise
        _set_clip(pid, clip_id, upload={"state": "done", **result})
        log(f"Uploaded “{title[:60]}” to {result['channel']} ({privacy})", "ok", pid)
        if load_settings()["delete_clip_after_upload"]:
            path.unlink(missing_ok=True)
            _set_clip(pid, clip_id, status="uploaded-removed")
        return result

    jobs.submit("upload", f"Upload: {title[:40]}", run, project_id=pid, clip_id=clip_id, heavy=False)


# ------------------------------------------------------------------ autopilot
def start_autopilot(pid: str) -> int:
    """Render the best moments with the default look and (optionally) upload them."""
    settings = load_settings()
    meta = projects.load(pid)
    max_len = float(settings["auto_max_seconds"])
    picks = sorted((m for m in meta["moments"] if m["score"] >= int(settings["auto_min_score"])),
                   key=lambda m: -m["score"])[: int(settings["auto_clips"])]
    if not picks:
        log("Autopilot: no moment scored high enough, nothing rendered", "warn", pid)
        return 0
    style = {"theme": settings["auto_theme"], "layout": settings["auto_layout"],
             "watermark": settings["channel_tag"],
             "credit": f"Clip: {meta['creator']}" if meta.get("creator") else ""}
    remaining = {"n": len(picks)}
    lock = threading.Lock()

    def after_render(clip_id: str, moment: dict):
        title = (moment.get("titles") or ["GTA 6 moment 🔥"])[0]
        if settings["auto_upload"] in ("private", "unlisted", "public"):
            queue_upload(pid, clip_id, title=title, description=describe(meta, title),
                         tags=["GTA6", "GTAVI", "ViceCity", "Shorts", "gaming"],
                         privacy=settings["auto_upload"], channel_id=settings["auto_channel"])
        with lock:
            remaining["n"] -= 1
            done = remaining["n"] == 0
        if done and settings["delete_source_after_auto"]:
            free_source(pid)
            log("Autopilot finished, source video deleted to save space", "ok", pid)

    for m in picks:
        end = min(m["end"], m["start"] + max_len)
        queue_render(pid, m["start"], end, {**style, "hook": m.get("hook", "")}, moment_id=m["id"],
                     title=(m.get("titles") or [""])[0], titles=m.get("titles", []),
                     then=lambda cid, mm=m: after_render(cid, mm))
    log(f"Autopilot: rendering {len(picks)} Shorts" +
        (f", then uploading as {settings['auto_upload']}" if settings["auto_upload"] != "off" else ""), "info", pid)
    return len(picks)


# ------------------------------------------------------------------ cleanup
def free_source(pid: str) -> int:
    """Delete the big source video but keep subtitles, moments and finished Shorts."""
    folder = projects.project_dir(pid)
    freed = 0
    for name in ("source.mp4", "source.converting.mp4"):
        path = folder / name
        if path.is_file():
            freed += path.stat().st_size
            path.unlink()
    for path in folder.glob("upload.*"):
        freed += path.stat().st_size
        path.unlink()
    projects.update(pid, source_removed=True)
    return freed


def sweep_temp() -> None:
    """Remove half-finished downloads and uploads left by a crash or a closed window."""
    uploads = WORKSPACE / "uploads"
    if uploads.is_dir():
        for path in uploads.glob("*.part"):
            if time.time() - path.stat().st_mtime > 86400:
                path.unlink(missing_ok=True)
    if not PROJECTS_DIR.is_dir():
        return
    for path in PROJECTS_DIR.glob("*/*"):
        if path.is_file() and (path.suffix in (".part", ".ytdl", ".tmp") or ".part-Frag" in path.name
                               or path.name == "source.converting.mp4"):
            path.unlink(missing_ok=True)


def sweep_old(keep_days: float) -> int:
    if keep_days <= 0:
        return 0
    cutoff = time.time() - keep_days * 86400
    freed = 0
    for meta in projects.list_all():
        if meta.get("created_at", 0) < cutoff and projects.source_path(meta["id"]).is_file():
            freed += free_source(meta["id"])
    if freed:
        log(f"Cleanup: deleted old source videos ({freed / 1e9:.1f} GB freed)", "ok")
    return freed


def storage() -> dict:
    total = sources = clips = 0
    if PROJECTS_DIR.is_dir():
        for path in PROJECTS_DIR.rglob("*"):
            if path.is_file():
                size = path.stat().st_size
                total += size
                if path.name == "source.mp4":
                    sources += size
                elif path.parent.name == "clips":
                    clips += size
    return {"total": total, "sources": sources, "clips": clips}


# ------------------------------------------------------------------ watchlist
def _watch_state() -> dict:
    if WATCH_STATE.is_file():
        try:
            return json.loads(WATCH_STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"seen": [], "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "last_check": 0}


def _save_watch_state(state: dict) -> None:
    state["seen"] = state["seen"][-2000:]
    WATCH_STATE.write_text(json.dumps(state), encoding="utf-8")


def check_watchlist() -> int:
    """Look for new GTA 6 videos on watched channels and send them through autopilot."""
    from .youtube import durations, recent_uploads
    settings = load_settings()
    state = _watch_state()
    terms = [t.strip().lower() for t in settings["watch_keywords"].split(",") if t.strip()]
    max_secs = float(settings["watch_max_minutes"]) * 60
    added = 0
    for ch in settings["watch_channels"]:
        if not ch.get("uploads"):
            continue
        try:
            videos = recent_uploads(ch["uploads"], 8)
        except Exception as err:
            log(f"Watchlist: couldn't check {ch.get('title', ch.get('input'))}: {str(err)[:120]}", "error")
            continue
        fresh = [v for v in videos if v["id"] not in state["seen"] and v["published_at"] >= state["started"]]
        lengths = durations([v["id"] for v in fresh]) if fresh else {}
        for v in fresh:
            title = v["title"].lower()
            if terms and not any(t in title for t in terms):
                state["seen"].append(v["id"])
                continue
            secs = lengths.get(v["id"], 0)
            if secs <= 0:
                continue  # still live or upcoming: check again next time
            state["seen"].append(v["id"])
            section_end = min(secs, max_secs) if secs > max_secs else None
            start_import(url=v["url"], title=v["title"], creator=ch.get("title", ""), end=section_end,
                         autopilot=True, permission_note=f"Watchlist: {ch.get('title', '')}")
            log(f"Watchlist: new video from {ch.get('title')}: “{v['title'][:60]}”"
                + (f" (first {max_secs / 60:.0f} min)" if section_end else ""), "info")
            added += 1
    state["last_check"] = time.time()
    _save_watch_state(state)
    return added


def reset_watch_start() -> None:
    state = _watch_state()
    state["started"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _save_watch_state(state)


def _loop() -> None:
    last_sweep = 0.0
    while True:
        try:
            settings = load_settings()
            now = time.time()
            if now - last_sweep > 3600:
                sweep_old(float(settings["keep_days"]))
                last_sweep = now
            if settings["watch_enabled"] and settings["watch_channels"]:
                state = _watch_state()
                if now - state.get("last_check", 0) >= max(10, int(settings["watch_interval"])) * 60:
                    check_watchlist()
        except Exception as err:  # never let the background loop die
            log(f"Background check error: {str(err)[:200]}", "error")
        time.sleep(30)


def start_background() -> None:
    sweep_temp()
    threading.Thread(target=_loop, name="watchlist", daemon=True).start()


def add_watch_channel(text: str) -> dict:
    from .youtube import resolve_channel
    info = resolve_channel(text)
    settings = load_settings()
    channels = [c for c in settings["watch_channels"] if c.get("id") != info["id"]]
    channels.append({"input": text.strip(), **info})
    save_settings({"watch_channels": channels})
    return info


def remove_watch_channel(channel_id: str) -> None:
    settings = load_settings()
    save_settings({"watch_channels": [c for c in settings["watch_channels"] if c.get("id") != channel_id]})


def clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:100]

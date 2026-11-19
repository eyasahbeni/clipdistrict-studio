"""Local web app: http://127.0.0.1:8765 (only reachable from your own computer)."""
from __future__ import annotations

import os
import threading
import time
import uuid
import webbrowser
from pathlib import Path

import hmac
import secrets

from flask import Flask, abort, jsonify, redirect, request, send_file, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

from . import __version__, ai, captions, importer, jobs, moments, projects, render, transcribe, uploader, workflow
from .config import (INBOX_DIR, APP_PASSWORD, HOSTED, PUBLIC_URL, WORKSPACE, FONTS_DIR, SECRETS_DIR, WEB_DIR, ensure_dirs, ffmpeg_bin, ffmpeg_has_captions, load_settings,
                     oauth_client_file, save_settings)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 ** 3  # 8 GB uploads
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def _secret_key() -> bytes:
    env = os.environ.get("SECRET_KEY", "")
    if env:
        return env.encode()
    ensure_dirs()
    path = WORKSPACE / ".secret_key"
    if not path.is_file():
        path.write_bytes(secrets.token_bytes(32))
    return path.read_bytes()


app.secret_key = _secret_key()
if HOSTED:
    # Hugging Face shows the app inside an iframe on huggingface.co, so the cookie must allow that.
    app.config.update(SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_SECURE=True,
                      PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)

LOGIN_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ClipDistrict Studio · Sign in</title>
<link rel="stylesheet" href="/assets/app.css"></head><body><div class="bg-glow"></div>
<main class="login"><form method="post" class="card login-card">
<div class="brand"><span class="brand-mark">CD</span><span class="brand-name">CLIPDISTRICT<em>STUDIO</em></span></div>
<label>Password<input type="password" name="password" autofocus required></label>
{error}<button class="btn primary" type="submit">Enter</button></form></main></body></html>"""

OPEN_PATHS = ("/login", "/assets/", "/fonts/", "/oauth/callback")


@app.before_request
def require_login():
    if not APP_PASSWORD or request.path.startswith(OPEN_PATHS) or session.get("ok"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "Please sign in again"}), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect("/")
    error = ""
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", "").encode(), APP_PASSWORD.encode()):
            session.permanent = True
            session["ok"] = True
            return redirect("/")
        time.sleep(1.5)  # slow down guessing
        error = '<p class="hint bad">Wrong password</p>'
    return LOGIN_PAGE.replace("{error}", error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


def _redirect_uri() -> str:
    return (PUBLIC_URL or request.host_url.rstrip("/")) + "/oauth/callback"


@app.get("/oauth/start")
def oauth_start():
    try:
        url, state, verifier = uploader.web_sign_in_url(_redirect_uri())
    except Exception as err:
        return f"<p>Couldn't start Google sign-in: {err}</p><p><a href='/'>Back</a></p>", 400
    session["oauth_state"], session["oauth_verifier"] = state, verifier
    return redirect(url)


@app.get("/oauth/callback")
def oauth_callback():
    if APP_PASSWORD and not session.get("ok"):
        return redirect("/login")
    if request.args.get("error"):
        return redirect("/#/?google=" + request.args["error"])
    if request.args.get("state") != session.get("oauth_state"):
        return "<p>Sign-in expired, please try again.</p><p><a href='/'>Back</a></p>", 400
    try:
        uploader.web_sign_in_finish(_redirect_uri(), session.pop("oauth_state"),
                                    session.pop("oauth_verifier", ""), request.args.get("code", ""))
    except Exception as err:
        return f"<p>Google sign-in failed: {err}</p><p><a href='/'>Back</a></p>", 400
    return redirect("/#/auto")
API_KEY_FILE = SECRETS_DIR / "youtube_api_key.txt"


def _api_key() -> str:
    if API_KEY_FILE.is_file():
        key = API_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            os.environ["YOUTUBE_API_KEY"] = key
    return os.environ.get("YOUTUBE_API_KEY", "").strip()


def _err(message: str, code: int = 400):
    return jsonify({"error": message}), code


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------- pages ----
@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/assets/<path:name>")
def assets(name):
    return send_from_directory(WEB_DIR, name)


@app.get("/fonts/<path:name>")
def fonts(name):
    return send_from_directory(FONTS_DIR, name)


# --------------------------------------------------------------- status ----
@app.get("/api/status")
def status():
    try:
        ffmpeg_ok = bool(ffmpeg_bin()) and ffmpeg_has_captions()
    except RuntimeError:
        ffmpeg_ok = False
    try:
        import faster_whisper  # noqa: F401
        whisper_ok = True
    except ImportError:
        whisper_ok = False
    channels = uploader.list_channels()
    return jsonify({
        "version": __version__, "ffmpeg": ffmpeg_ok, "whisper": whisper_ok,
        "api_key": bool(_api_key()), "oauth_client": bool(oauth_client_file()), "ai": bool(ai.api_key()),
        "channel": channels[0] if channels else None, "channels": channels,
        "settings": load_settings(), "storage": workflow.storage(),
        "hosted": HOSTED, "public_url": PUBLIC_URL, "redirect_uri": _redirect_uri() if HOSTED else "",
        "login": bool(APP_PASSWORD),
    })


@app.get("/api/themes")
def themes():
    return jsonify({"themes": captions.theme_list(), "layouts": render.LAYOUTS,
                    "positions": captions.POSITIONS})


@app.post("/api/settings")
def settings():
    data = _body()
    if "gemini_api_key" in data:
        ai.save_key(str(data.pop("gemini_api_key")))
    if "youtube_api_key" in data:
        ensure_dirs()
        API_KEY_FILE.write_text(str(data.pop("youtube_api_key")).strip(), encoding="utf-8")
        os.environ.pop("YOUTUBE_API_KEY", None)
        _api_key()
    return jsonify(save_settings(data))


@app.post("/api/settings/oauth-client")
def oauth_client():
    file = request.files.get("file")
    if not file:
        return _err("Choose the client_secret JSON file")
    try:
        uploader.save_client_file(file.read())
    except (ValueError, UnicodeDecodeError) as err:
        return _err(str(err) or "Invalid file")
    return jsonify({"ok": True})


@app.post("/api/youtube/signin")
def signin():
    try:
        return jsonify({"channel": uploader.sign_in()})
    except Exception as err:
        return _err(str(err))


@app.post("/api/youtube/remove")
def remove_channel():
    try:
        uploader.remove_channel(_body().get("id", ""))
    except ValueError as err:
        return _err(str(err))
    return jsonify({"ok": True})


# ------------------------------------------------------------ automation ----
@app.get("/api/automation")
def automation():
    state = workflow._watch_state()
    return jsonify({"activity": workflow.activity()[:60], "last_check": state.get("last_check", 0),
                    "watch_started": state.get("started"), "storage": workflow.storage()})


@app.post("/api/watch/channels")
def watch_add():
    if not _api_key():
        return _err("Add your YouTube API key in Settings first")
    try:
        return jsonify(workflow.add_watch_channel(_body().get("channel", "")))
    except Exception as err:
        return _err(str(err))


@app.delete("/api/watch/channels/<cid>")
def watch_remove(cid):
    workflow.remove_watch_channel(cid)
    return jsonify({"ok": True})


@app.post("/api/watch/check")
def watch_check():
    if not _api_key():
        return _err("Add your YouTube API key in Settings first")
    try:
        return jsonify({"added": workflow.check_watchlist()})
    except Exception as err:
        return _err(str(err))


@app.post("/api/watch/reset")
def watch_reset():
    workflow.reset_watch_start()
    return jsonify({"ok": True})


@app.post("/api/cleanup")
def cleanup():
    data = _body()
    freed = 0
    if data.get("all_sources"):
        for meta in projects.list_all():
            freed += workflow.free_source(meta["id"])
    else:
        freed = workflow.sweep_old(float(data.get("older_than_days", load_settings()["keep_days"]) or 0.01))
    workflow.sweep_temp()
    return jsonify({"freed": freed, "storage": workflow.storage()})


@app.get("/api/search")
def search():
    if not _api_key():
        return _err("Add your YouTube API key in Settings to search")
    from .youtube import YouTubeError, search as yt_search
    try:
        results = yt_search(request.args.get("q", "GTA 6"), live=request.args.get("live") == "1",
                            limit=int(request.args.get("limit", 12)))
    except (ValueError, YouTubeError) as err:
        return _err(str(err))
    return jsonify({"results": results})


@app.post("/api/info")
def info():
    try:
        return jsonify(importer.fetch_info(_body().get("url", "")))
    except Exception as err:
        msg = str(err)
        if "not a bot" in msg or "Sign in to confirm" in msg:
            return _err("YouTube is blocking this server (bot check). Put the video in your inbox folder "
                        "instead, or run the app on your own PC where links work.")
        return _err(f"Couldn't read that link: {msg[:300]}")


@app.get("/api/jobs")
def list_jobs():
    return jsonify({"jobs": jobs.all_jobs()})


# ------------------------------------------------------------- projects ----
def _num(value):
    if value in (None, ""):
        return None
    from .media import parse_time
    return parse_time(str(value))


@app.get("/api/projects")
def list_projects():
    return jsonify({"projects": projects.list_all()})


@app.post("/api/projects")
def create_project():
    data = _body()
    try:
        url = importer.check_url(data.get("url", ""))
        start, end = _num(data.get("start")), _num(data.get("end"))
    except ValueError as err:
        return _err(str(err))
    if start is not None and end is not None and end <= start:
        return _err("'To' must be after 'From'")
    meta = workflow.start_import(url=url, title=data.get("title") or url, creator=data.get("creator", ""),
                                 start=start, end=end, autopilot=bool(data.get("autopilot")),
                                 request=str(data.get("request", "")))
    return jsonify(meta)


@app.post("/api/projects/upload")
def upload_project():
    file = request.files.get("file")
    if not file or not file.filename:
        return _err("Choose a video file")
    if Path(file.filename).suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        return _err("Video must be MP4, MOV, MKV or WEBM")
    meta = projects.create(Path(file.filename).stem, "", request.form.get("creator", ""))
    pid = meta["id"]
    raw = projects.project_dir(pid) / ("upload" + Path(file.filename).suffix.lower())
    file.save(raw)
    srt = request.files.get("srt")
    if srt and srt.filename:
        transcribe.from_srt(srt.read().decode("utf-8-sig", errors="replace"), projects.transcript_path(pid))
    workflow.start_import(pid=pid, raw_file=raw, autopilot=request.form.get("autopilot") == "1")
    return jsonify(meta)


# ------------------------------------------------------- chunked uploads ----
UPLOADS_DIR = WORKSPACE / "uploads"
UPLOAD_ID_RE = __import__("re").compile(r"^[a-f0-9]{16}$")


def _upload_part(uid: str) -> Path:
    if not UPLOAD_ID_RE.fullmatch(uid or ""):
        abort(404)
    return UPLOADS_DIR / f"{uid}.part"


@app.post("/api/uploads")
def upload_start():
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    uid = uuid.uuid4().hex[:16]
    _upload_part(uid).write_bytes(b"")
    return jsonify({"id": uid, "offset": 0})


@app.put("/api/uploads/<uid>")
def upload_chunk(uid):
    part = _upload_part(uid)
    if not part.is_file():
        return _err("Upload expired, start again", 404)
    offset = int(request.args.get("offset", -1))
    size = part.stat().st_size
    if offset != size:                       # tell the browser where to resume
        return jsonify({"offset": size, "resync": True})
    with part.open("ab") as fh:
        fh.write(request.get_data(cache=False))
    return jsonify({"offset": part.stat().st_size})


@app.post("/api/uploads/<uid>/finish")
def upload_finish(uid):
    part = _upload_part(uid)
    data = _body()
    name = Path(str(data.get("name", "video.mp4"))).name
    suffix = Path(name).suffix.lower()
    if suffix not in importer.VIDEO_EXTS:
        part.unlink(missing_ok=True)
        return _err("Video must be MP4, MOV, MKV or WEBM")
    if not part.is_file() or part.stat().st_size == 0:
        return _err("Upload is empty, try again")
    try:
        start, end = _num(data.get("start")), _num(data.get("end"))
    except ValueError as err:
        return _err(str(err))
    meta = projects.create(Path(name).stem, "", data.get("creator", ""))
    raw = projects.project_dir(meta["id"]) / ("upload" + suffix)
    part.replace(raw)
    if start is None and end is None:
        meta = workflow.start_import(pid=meta["id"], raw_file=raw, autopilot=bool(data.get("autopilot")),
                                     request=str(data.get("request", "")))
    else:
        meta = workflow.start_import(pid=meta["id"], copy_from=raw, start=start, end=end,
                                     autopilot=bool(data.get("autopilot")), request=str(data.get("request", "")))
    return jsonify(meta)


@app.delete("/api/uploads/<uid>")
def upload_cancel(uid):
    _upload_part(uid).unlink(missing_ok=True)
    return jsonify({"ok": True})


@app.get("/api/inbox")
def inbox():
    ensure_dirs()
    items = []
    for path in sorted(INBOX_DIR.iterdir(), key=lambda p: -p.stat().st_mtime):
        if path.is_file() and path.suffix.lower() in importer.VIDEO_EXTS:
            items.append({"name": path.name, "size": path.stat().st_size, "mtime": path.stat().st_mtime})
    return jsonify({"folder": str(INBOX_DIR), "files": items})


@app.post("/api/inbox/import")
def inbox_import():
    data = _body()
    name = Path(str(data.get("name", ""))).name
    src = INBOX_DIR / name
    if not name or not src.is_file() or src.suffix.lower() not in importer.VIDEO_EXTS:
        return _err("That file isn't in the inbox anymore")
    try:
        start, end = _num(data.get("start")), _num(data.get("end"))
    except ValueError as err:
        return _err(str(err))
    if start is not None and end is not None and end <= start:
        return _err("'To' must be after 'From'")
    meta = workflow.start_import(copy_from=src, title=Path(name).stem, creator=data.get("creator", ""),
                                 start=start, end=end, autopilot=bool(data.get("autopilot")),
                                 request=str(data.get("request", "")))
    return jsonify(meta)


@app.get("/api/projects/<pid>")
def get_project(pid):
    try:
        return jsonify(projects.load(pid))
    except (ValueError, OSError):
        abort(404)


@app.delete("/api/projects/<pid>")
def delete_project(pid):
    jobs.cancel_project(pid)
    projects.delete(pid)
    return jsonify({"ok": True})


@app.get("/api/projects/<pid>/source")
def project_source(pid):
    path = projects.source_path(pid)
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="video/mp4", conditional=True)


@app.get("/api/projects/<pid>/poster.jpg")
def project_poster(pid):
    path = projects.project_dir(pid) / "poster.jpg"
    if not path.is_file():
        abort(404)
    return send_file(path, mimetype="image/jpeg")


@app.get("/api/projects/<pid>/words")
def project_words(pid):
    data = transcribe.load(projects.transcript_path(pid))
    a, b = float(request.args.get("start", 0)), float(request.args.get("end", 1e9))
    return jsonify({"words": transcribe.words_between(data, a, b)})


@app.post("/api/projects/<pid>/reanalyze")
def reanalyze(pid):
    data = _body()
    save_settings({k: data[k] for k in ("clip_length", "clips_per_video") if k in data})
    if not projects.source_path(pid).is_file():
        return _err("The source video was cleaned up, import it again to re-analyze")
    jobs.submit("analyze", "Finding moments again", lambda p: workflow.analyze(pid, p)["id"], project_id=pid)
    return jsonify({"ok": True})


@app.post("/api/projects/<pid>/retranscribe")
def retranscribe(pid):
    if not projects.source_path(pid).is_file():
        return _err("The source video was cleaned up, import it again")
    projects.transcript_path(pid).unlink(missing_ok=True)
    projects.update(pid, error="", status="transcribing")
    jobs.submit("analyze", "Subtitles + moments again", lambda p: workflow.analyze(pid, p)["id"], project_id=pid)
    return jsonify({"ok": True})


@app.get("/api/projects/<pid>/search")
def search_stream(pid):
    meta = projects.load(pid)
    hits = moments.search_transcript(transcribe.load(projects.transcript_path(pid)),
                                     request.args.get("q", ""), meta["duration"])
    return jsonify({"hits": hits})


@app.post("/api/projects/<pid>/free")
def free_project(pid):
    freed = workflow.free_source(pid)
    return jsonify({"freed": freed})


@app.post("/api/projects/<pid>/autopilot")
def project_autopilot(pid):
    if not projects.source_path(pid).is_file():
        return _err("The source video was cleaned up")
    return jsonify({"queued": workflow.start_autopilot(pid)})


@app.post("/api/projects/<pid>/moments")
def add_moment(pid):
    data = _body()
    meta = projects.load(pid)
    try:
        start, end = _num(data.get("start")), _num(data.get("end"))
    except ValueError as err:
        return _err(str(err))
    if start is None or end is None or not 3 <= end - start <= 180 or end > meta["duration"] + 0.5:
        return _err("Pick a range between 3 and 180 seconds inside the video")
    text = " ".join(w["word"] for w in transcribe.words_between(transcribe.load(projects.transcript_path(pid)), start, end))
    moment = {"id": uuid.uuid4().hex[:8], "start": start, "end": end, "score": 0,
              "reasons": ["added by you"], "hook": moments.hook_line(text) if text else "",
              "titles": moments.title_ideas(text), "transcript": text[:600], "manual": True}
    meta["moments"] = sorted(meta["moments"] + [moment], key=lambda m: m["start"])
    projects.save(meta)
    return jsonify(moment)


@app.delete("/api/projects/<pid>/moments/<mid>")
def delete_moment(pid, mid):
    meta = projects.load(pid)
    meta["moments"] = [m for m in meta["moments"] if m["id"] != mid]
    projects.save(meta)
    return jsonify({"ok": True})


# ---------------------------------------------------------------- clips ----
@app.post("/api/projects/<pid>/render")
def render_clip(pid):
    data = _body()
    meta = projects.load(pid)
    try:
        start, end = float(data["start"]), float(data["end"])
    except (KeyError, TypeError, ValueError):
        return _err("Missing start/end")
    if not 1 <= end - start <= 180 or start < 0 or end > meta["duration"] + 0.5:
        return _err("Clip must be 1–180 seconds inside the video")
    style = dict(data.get("style") or {})
    if not projects.source_path(pid).is_file():
        return _err("The source video was cleaned up, import it again to make more Shorts")
    clip = workflow.queue_render(pid, start, end, style, moment_id=data.get("moment_id", ""),
                                 title=str(data.get("title") or ""), titles=data.get("titles", []))
    return jsonify(clip)


@app.get("/api/projects/<pid>/clips/<cid>.mp4")
def clip_file(pid, cid):
    path = projects.clip_path(pid, cid)
    if not path.is_file():
        abort(404)
    download = request.args.get("download") == "1"
    return send_file(path, mimetype="video/mp4", conditional=True, as_attachment=download,
                     download_name=f"clipdistrict-{cid}.mp4")


@app.delete("/api/projects/<pid>/clips/<cid>")
def delete_clip(pid, cid):
    with projects._lock:
        meta = projects.load(pid)
        meta["clips"] = [c for c in meta["clips"] if c["id"] != cid]
        projects.save(meta)
    projects.clip_path(pid, cid).unlink(missing_ok=True)
    return jsonify({"ok": True})


@app.post("/api/projects/<pid>/clips/<cid>/upload")
def upload_clip(pid, cid):
    data = _body()
    path = projects.clip_path(pid, cid)
    if not path.is_file():
        return _err("Render the clip first")
    tags = [t for t in str(data.get("tags", "")).replace(",", " ").split() if t]
    workflow.queue_upload(pid, cid, title=str(data.get("title", "")), description=str(data.get("description", "")),
                          tags=tags, privacy=data.get("privacy", "private"), channel_id=data.get("channel_id", ""))
    return jsonify({"ok": True})


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    ensure_dirs()
    _api_key()
    if host not in ("127.0.0.1", "localhost") and not APP_PASSWORD:
        print("\n  WARNING: the app is reachable from the network but APP_PASSWORD is not set.\n")
    workflow.start_background()
    url = PUBLIC_URL or f"http://{host}:{port}"
    print(f"\n  ClipDistrict Studio is running → {url}\n  Keep this window open. Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, threaded=True, debug=False)

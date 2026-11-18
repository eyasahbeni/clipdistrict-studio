"""A project = one source video + its transcript, suggested moments and rendered Shorts."""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from .config import PROJECTS_DIR, ensure_dirs

ID_RE = re.compile(r"^[a-f0-9]{12}$")
_lock = threading.RLock()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def project_dir(project_id: str) -> Path:
    if not ID_RE.fullmatch(project_id or ""):
        raise ValueError("Invalid project id")
    return PROJECTS_DIR / project_id


def create(title: str, source_url: str = "", creator: str = "") -> dict:
    ensure_dirs()
    pid = new_id()
    folder = project_dir(pid)
    (folder / "clips").mkdir(parents=True)
    meta = {
        "id": pid, "title": title[:200] or "Untitled", "source_url": source_url,
        "creator": creator, "created_at": time.time(), "status": "importing",
        "duration": 0, "width": 0, "height": 0, "error": "",
        "moments": [], "clips": [], "permission_note": "",
    }
    save(meta)
    return meta


def load(project_id: str) -> dict:
    path = project_dir(project_id) / "project.json"
    with _lock:
        return json.loads(path.read_text(encoding="utf-8"))


def save(meta: dict) -> None:
    path = project_dir(meta["id"]) / "project.json"
    with _lock:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def update(project_id: str, **changes) -> dict:
    with _lock:
        meta = load(project_id)
        meta.update(changes)
        save(meta)
        return meta


def list_all() -> list[dict]:
    ensure_dirs()
    items = []
    for folder in PROJECTS_DIR.iterdir():
        if folder.is_dir() and ID_RE.fullmatch(folder.name) and (folder / "project.json").is_file():
            try:
                items.append(load(folder.name))
            except (OSError, ValueError):
                continue
    return sorted(items, key=lambda m: -m.get("created_at", 0))


def delete(project_id: str) -> None:
    folder = project_dir(project_id)
    if folder.is_dir():
        shutil.rmtree(folder)


def source_path(project_id: str) -> Path:
    return project_dir(project_id) / "source.mp4"


def transcript_path(project_id: str) -> Path:
    return project_dir(project_id) / "transcript.json"


def clip_path(project_id: str, clip_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{8}", clip_id or ""):
        raise ValueError("Invalid clip id")
    return project_dir(project_id) / "clips" / f"{clip_id}.mp4"

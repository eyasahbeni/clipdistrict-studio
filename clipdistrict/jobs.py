"""Background jobs with progress, so the app stays responsive while it works."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_heavy = ThreadPoolExecutor(max_workers=1, thread_name_prefix="heavy")   # download / transcribe / render
_light = ThreadPoolExecutor(max_workers=2, thread_name_prefix="light")   # uploads


def _set(job_id: str, **changes) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(changes, updated=time.time())


def submit(kind: str, label: str, fn, *, project_id: str = "", clip_id: str = "", heavy: bool = True) -> str:
    job_id = uuid.uuid4().hex[:10]
    with _lock:
        _jobs[job_id] = {"id": job_id, "kind": kind, "label": label, "project_id": project_id,
                         "clip_id": clip_id, "state": "queued", "progress": None, "message": "Waiting…",
                         "error": "", "result": None, "created": time.time(), "updated": time.time()}

    def progress(value, message=""):
        if is_cancelled(job_id):
            raise JobCancelled()
        _set(job_id, progress=None if value is None else round(float(value), 3), message=message)

    def run():
        with _lock:
            if _jobs.get(job_id, {}).get("state") == "cancelled":
                return
        _set(job_id, state="running", message="Starting…")
        try:
            result = fn(progress)
            if not is_cancelled(job_id):
                _set(job_id, state="done", progress=1.0, message="Done", result=result)
        except Exception as err:  # report every failure to the UI
            if is_cancelled(job_id):
                return
            traceback.print_exc()
            _set(job_id, state="error", message="Failed", error=str(err)[:800])

    (_heavy if heavy else _light).submit(run)
    return job_id


class JobCancelled(Exception):
    pass


def is_cancelled(job_id: str) -> bool:
    with _lock:
        return _jobs.get(job_id, {}).get("state") == "cancelled"


def cancel_project(project_id: str) -> int:
    """Stop waiting jobs of a project and tell running ones to stop at their next progress update."""
    count = 0
    with _lock:
        for job in _jobs.values():
            if job["project_id"] == project_id and job["state"] in ("queued", "running"):
                job.update(state="cancelled", message="Cancelled", updated=time.time())
                count += 1
    return count


def all_jobs() -> list[dict]:
    cutoff = time.time() - 3600
    with _lock:
        for key in [k for k, j in _jobs.items() if j["state"] in ("done", "error", "cancelled") and j["updated"] < cutoff]:
            _jobs.pop(key)
        return sorted((dict(j) for j in _jobs.values()), key=lambda j: -j["created"])


def get(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
